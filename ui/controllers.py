from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
import os
import re
import subprocess
import sys
from datetime import datetime
from typing import Any, Callable, Dict, Optional, Tuple

from config import (
    CONFLUENCE_PARENT_PAGE_TITLE,
    CONFLUENCE_SPACE_KEY,
    CONFLUENCE_TEMPLATE_PAGE_ID,
    CONFLUENCE_TOKEN,
    CONFLUENCE_URL,
    TEAM_NAME,
)
from core.jira_client import JiraService
from core.orchestrator import format_release_gate_report, run_release_check
from core.snapshot_builder import build_release_snapshot
from history import OperationHistory
from lt import run_lt_check_with_target
from master_analyzer import ConfluenceDeployPlanGenerator, MasterServicesAnalyzer
from release_pr_status import collect_release_tasks_pr_status, format_release_tasks_pr_report
from rqg import run_rqg_check

logger = logging.getLogger(__name__)


@dataclass
class AppState:
    last_snapshot: Optional[Dict[str, Any]] = None
    last_result: Optional[Dict[str, Any]] = None


class AppController:
    def __init__(
        self,
        *,
        jira_service: JiraService,
        history: OperationHistory,
        history_path: str,
        ui_set_status: Callable[[str, str], None],
        ui_set_result_text: Callable[[str], None],
        ui_show_error: Callable[[str, str], None],
        ui_show_info: Callable[[str, str], None],
        ui_ask_yes_no: Callable[[str, str], bool],
        ui_set_connection: Callable[[bool], None],
    ):
        self.jira_service = jira_service
        self.history = history
        self.history_path = history_path
        self.state = AppState()
        self.guided_cycle_context: dict[str, dict] = {}

        self._ui_set_status = ui_set_status
        self._ui_set_result_text = ui_set_result_text
        self._ui_show_error = ui_show_error
        self._ui_show_info = ui_show_info
        self._ui_ask_yes_no = ui_ask_yes_no
        self._ui_set_connection = ui_set_connection

        self._init_master_analyzer()
        self.current_analysis: Optional[Dict[str, Any]] = None
        self._output_lines: list[str] = []

    def _reset_output(self, header: str) -> None:
        self._output_lines = []
        self._append_output(header)

    def _append_output(self, line: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._output_lines.append(f"[{ts}] {line}")
        if len(self._output_lines) > 4000:
            self._output_lines = self._output_lines[-3500:]
        self._ui_set_result_text("\n".join(self._output_lines))

    def _init_master_analyzer(self) -> None:
        try:
            self.confluence_generator = ConfluenceDeployPlanGenerator(
                confluence_url=CONFLUENCE_URL,
                confluence_token=CONFLUENCE_TOKEN,
                template_page_id=CONFLUENCE_TEMPLATE_PAGE_ID,
            )
            self.master_analyzer = MasterServicesAnalyzer(
                jira_service=self.jira_service,
                confluence_generator=self.confluence_generator,
            )
        except Exception as e:
            logger.error("Ошибка инициализации Confluence/Master analyzer: %s", e)
            self.confluence_generator = None
            self.master_analyzer = None

    def get_context(self) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        return self.state.last_snapshot, self.state.last_result

    def execute_chat_command(self, text: str) -> str:
        """
        Deterministic command handler for chat panel (no LLM).

        Supported:
        - "собери бизнес-требования для HRPRELEASE-12345" (+ optional "проект HRM")
        """
        raw = (text or "").strip()
        lowered = raw.lower()
        m = re.search(r"\b(HRPRELEASE-\d+)\b", raw, re.IGNORECASE)
        release_key = m.group(1).upper() if m else ""
        project_match = re.search(r"\b(HRC|HRM|NEUROUI|SFILE|SEARCHCS|NEURO|HRPDEV)\b", raw, re.IGNORECASE)
        project_key = project_match.group(1).upper() if project_match else ""

        if ("бизнес" in lowered and "треб" in lowered) or "bt" in lowered or "бт" in lowered:
            if not release_key:
                return "Укажи релиз в формате HRPRELEASE-12345."
            self.run_business_requirements(release_key=release_key, project_key=project_key or None)
            return f"Запускаю сбор БТ/FR для {release_key}" + (f" (проект {project_key})" if project_key else "") + ". Результат появится во вкладке «Результаты»."

        return "Я понимаю только: summary/blockers/next actions и команды БТ/FR (например: «собери бизнес-требования для HRPRELEASE-12345, проект HRM»)."

    def check_connection_async(self) -> None:
        def worker():
            ok, _msg = self.jira_service.test_connection()
            self._ui_set_connection(ok)

        threading.Thread(target=worker, daemon=True).start()

    def run_release_check(
        self,
        *,
        release_key: str,
        profile: str = "auto",
        dry_run: bool = False,
        post_success_comment: bool = False,
    ) -> None:
        safe_release = (release_key or "").strip().upper()
        if not safe_release:
            self._ui_show_error("Ошибка", "Введите ключ релиза.")
            return

        self._ui_set_status("Проверка гейтов…", "#1565C0")
        self._ui_set_result_text(f"Запуск проверки гейтов для {safe_release}…")

        def worker():
            try:
                result = run_release_check(
                    jira_service=self.jira_service,
                    release_key=safe_release,
                    profile_name=profile,
                    manual_confirmations=(
                        self.guided_cycle_context.get(safe_release, {}) or {}
                    ).get("manual_confirmations"),
                    post_success_comment=post_success_comment,
                    dry_run=dry_run,
                )
                snapshot = build_release_snapshot(self.jira_service, safe_release)
                report = format_release_gate_report(result)
                self.state.last_result = result
                self.state.last_snapshot = snapshot
                self._ui_set_result_text(report)
                self._ui_set_status(
                    "Готово" if result.get("success") else "Ошибка",
                    "#2E7D32" if result.get("success") else "#C62828",
                )
                self.history.add(
                    "Проверка гейтов",
                    {"release": safe_release, "profile": profile, "dry_run": dry_run},
                )
                self.history.save_to_file(self.history_path)
            except Exception as e:
                self._ui_set_status("Ошибка", "#C62828")
                self._ui_set_result_text(f"Ошибка проверки: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def start_release_guided_cycle(
        self, *, release_key: str, profile: str = "auto", dry_run: bool = False
    ) -> None:
        safe_release = (release_key or "").strip().upper()
        if not safe_release:
            self._ui_show_error("Ошибка", "Введите ключ релиза.")
            return

        self._ui_set_status(f"Guided cycle: {safe_release}", "#1565C0")
        self._ui_set_result_text(f"Guided cycle для {safe_release}…")

        def worker():
            try:
                ctx = self.guided_cycle_context.get(safe_release, {}) or {}
                result = run_release_check(
                    jira_service=self.jira_service,
                    release_key=safe_release,
                    profile_name=profile,
                    manual_confirmations=ctx.get("manual_confirmations"),
                    dry_run=dry_run,
                )
                report = format_release_gate_report(result)
                snapshot = build_release_snapshot(self.jira_service, safe_release)

                self.state.last_result = result
                self.state.last_snapshot = snapshot
                self._ui_set_result_text(report)
                self._ui_set_status(
                    "Готово" if result.get("success") else "Ошибка",
                    "#2E7D32" if result.get("success") else "#C62828",
                )

                if result.get("success"):
                    self.guided_cycle_context[safe_release] = {
                        "profile": result.get("profile_name", profile),
                        "dry_run": dry_run,
                        "last_result": result,
                        "manual_confirmations": ctx.get("manual_confirmations", {}) or {},
                    }
                    self.history.add(
                        "Guided cycle",
                        {
                            "release": safe_release,
                            "profile": result.get("profile_name", profile),
                            "dry_run": dry_run,
                            "ready_for_transition": result.get("ready_for_transition", False),
                        },
                    )
                    self.history.save_to_file(self.history_path)
            except Exception as e:
                self._ui_set_status("Ошибка", "#C62828")
                self._ui_set_result_text(f"Ошибка guided cycle: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def run_next_release_step(self, *, release_key: str, dry_run: bool = False) -> None:
        safe_release = (release_key or "").strip().upper()
        if not safe_release:
            self._ui_show_error("Ошибка", "Введите ключ релиза.")
            return
        ctx = self.guided_cycle_context.get(safe_release, {}) or {}
        profile = ctx.get("profile", "auto")
        effective_dry = bool(ctx.get("dry_run", dry_run))
        self.start_release_guided_cycle(
            release_key=safe_release, profile=profile, dry_run=effective_dry
        )

    def move_release_if_ready(self, *, release_key: str, dry_run: bool = False) -> None:
        safe_release = (release_key or "").strip().upper()
        if not safe_release:
            self._ui_show_error("Ошибка", "Введите ключ релиза.")
            return

        def worker():
            try:
                ctx = self.guided_cycle_context.get(safe_release)
                if not ctx or not ctx.get("last_result"):
                    result = run_release_check(self.jira_service, safe_release, "auto")
                    ctx = {
                        "profile": result.get("profile_name", "auto"),
                        "dry_run": dry_run,
                        "last_result": result,
                        "manual_confirmations": {},
                    }
                    self.guided_cycle_context[safe_release] = ctx

                last = ctx.get("last_result") or {}
                if not last.get("ready_for_transition"):
                    report = format_release_gate_report(last)
                    self._ui_set_result_text(
                        "Переход заблокирован: не пройдены все гейты.\n\n" + report
                    )
                    return

                next_status = last.get("next_allowed_transition")
                next_id = last.get("next_allowed_transition_id")
                if not next_status:
                    self._ui_set_result_text(
                        "Следующий этап не определён (финальный статус или вне workflow)."
                    )
                    return

                effective_dry = bool(ctx.get("dry_run", dry_run))
                if effective_dry:
                    suffix = f" (transition id: {next_id})" if next_id else ""
                    self._ui_set_result_text(
                        f"[DRY-RUN] Релиз {safe_release} готов к переходу в '{next_status}'{suffix}. Фактический перевод не выполнен."
                    )
                    return

                if next_id:
                    ok, msg = self.jira_service.transition_issue_by_id(safe_release, next_id)
                else:
                    ok, msg = self.jira_service.transition_issue(safe_release, next_status)
                if not ok:
                    self._ui_set_result_text(f"Не удалось перевести релиз: {msg}")
                    return

                self.history.add(
                    "Guided transition", {"release": safe_release, "target_status": next_status}
                )
                self.history.save_to_file(self.history_path)
                self._ui_show_info("Готово", msg)
                self.start_release_guided_cycle(
                    release_key=safe_release,
                    profile=ctx.get("profile", "auto"),
                    dry_run=effective_dry,
                )
            except Exception as e:
                self._ui_set_result_text(f"Ошибка перехода: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def run_lt_check(self, *, release_key: str, target_lt: float) -> None:
        safe_release = (release_key or "").strip().upper()
        if not safe_release:
            self._ui_show_error("Ошибка", "Введите ключ релиза.")
            return
        self._ui_set_status("LT…", "#1565C0")
        self._ui_set_result_text(f"Запуск проверки LT для {safe_release}…")

        def worker():
            try:
                report = run_lt_check_with_target(safe_release, float(target_lt))
                self._ui_set_result_text(report)
                self._ui_set_status("Готово", "#2E7D32")
                self.history.add(
                    "Проверка LT", {"release": safe_release, "target_lt": target_lt}
                )
                self.history.save_to_file(self.history_path)
            except Exception as e:
                self._ui_set_status("Ошибка", "#C62828")
                self._ui_set_result_text(f"Ошибка LT: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def run_rqg_check(self, *, release_key: str) -> None:
        safe_release = (release_key or "").strip().upper()
        if not safe_release:
            self._ui_show_error("Ошибка", "Введите ключ релиза.")
            return
        self._ui_set_status("RQG…", "#1565C0")
        self._ui_set_result_text(f"Запуск RQG-проверки для {safe_release}…")

        def worker():
            try:
                report = run_rqg_check(
                    self.jira_service, safe_release, max_depth=2, trigger_button=True
                )
                self._ui_set_result_text(report)
                self._ui_set_status("Готово", "#2E7D32")
                self.history.add("RQG-проверка", {"release": safe_release})
                self.history.save_to_file(self.history_path)
            except Exception as e:
                self._ui_set_status("Ошибка", "#C62828")
                self._ui_set_result_text(f"Ошибка RQG: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def run_release_pr_status(self, *, release_key: str) -> None:
        safe_release = (release_key or "").strip().upper()
        if not safe_release:
            self._ui_show_error("Ошибка", "Введите ключ релиза.")
            return
        self._ui_set_status("Tasks+PR…", "#1565C0")
        self._ui_set_result_text(f"Проверка задач и PR для {safe_release}…")

        def worker():
            try:
                report_data = collect_release_tasks_pr_status(
                    self.jira_service, safe_release, progress_callback=None
                )
                text = format_release_tasks_pr_report(report_data)
                self._ui_set_result_text(text)
                self._ui_set_status("Готово", "#2E7D32")
                self.history.add("Проверка задач и PR", {"release": safe_release})
                self.history.save_to_file(self.history_path)
            except Exception as e:
                self._ui_set_status("Ошибка", "#C62828")
                self._ui_set_result_text(f"Ошибка Tasks+PR: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def run_business_requirements(self, *, release_key: str, project_key: str | None = None) -> None:
        safe_release = (release_key or "").strip().upper()
        if not safe_release:
            self._ui_show_error("Ошибка", "Введите ключ релиза.")
            return

        snapshot = self.state.last_snapshot or {}
        derived_project = (snapshot.get("project_key") or "").strip().upper()
        effective_project = (project_key or derived_project).strip().upper()
        if not effective_project:
            self._ui_show_error(
                "Нужен проект",
                "Не удалось определить project_key. Запусти сначала проверку гейтов (чтобы собрать snapshot) "
                "или укажи в чате: «проект HRM».",
            )
            return

        script_path = os.path.join(os.path.dirname(__file__), "..", "bt3.py")
        script_path = os.path.abspath(script_path)
        if not os.path.exists(script_path):
            self._ui_show_error("Нет bt3.py", f"Скрипт не найден: {script_path}")
            return

        self._ui_set_status("БТ/FR…", "#1565C0")
        self._ui_set_result_text(f"Запуск bt3.py для {safe_release} / {effective_project}…")

        def worker():
            try:
                proc = subprocess.run(
                    [sys.executable, script_path, safe_release, effective_project],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                stdout = (proc.stdout or "").strip()
                stderr = (proc.stderr or "").strip()

                ok = False
                url = ""
                msg = ""
                for line in stdout.splitlines():
                    if line.startswith("ok="):
                        ok = line.split("=", 1)[1].strip().lower() == "true"
                    elif line.startswith("url="):
                        url = line.split("=", 1)[1].strip()
                    elif line.startswith("msg="):
                        msg = line.split("=", 1)[1].strip()

                if proc.returncode != 0 and not msg:
                    msg = stderr[-1500:] if stderr else f"bt3.py exit_code={proc.returncode}"

                if ok and url:
                    text_out = f"✅ БТ/FR готово: {url}\n{msg}".strip()
                    self._ui_set_result_text(text_out)
                    self._ui_set_status("Готово", "#2E7D32")
                    self.history.add("BT/FR", {"release": safe_release, "project": effective_project, "url": url})
                    self.history.save_to_file(self.history_path)
                    return

                preview = stdout[-2000:] if stdout else ""
                err_preview = stderr[-2000:] if stderr else ""
                text_out = (
                    "❌ Не удалось собрать БТ/FR.\n"
                    + (f"{msg}\n" if msg else "")
                    + (f"\nSTDOUT:\n{preview}\n" if preview else "")
                    + (f"\nSTDERR:\n{err_preview}\n" if err_preview else "")
                ).strip()
                self._ui_set_result_text(text_out)
                self._ui_set_status("Ошибка", "#C62828")
            except Exception as e:
                self._ui_set_result_text(f"Ошибка BT/FR: {e}")
                self._ui_set_status("Ошибка", "#C62828")

        threading.Thread(target=worker, daemon=True).start()

    def analyze_master_services(self, *, release_key: str) -> None:
        safe_release = (release_key or "").strip().upper()
        if not safe_release:
            self._ui_show_error("Ошибка", "Введите ключ релиза.")
            return
        if not self.master_analyzer:
            self._ui_show_error("Ошибка", "Confluence/Master analyzer не настроен. Проверь .env.")
            return

        self._ui_set_status("Master analyze…", "#1565C0")
        self._ui_set_result_text(f"Анализ master-сервисов для {safe_release}…")

        def worker():
            try:
                analysis = self.master_analyzer.analyze_release(safe_release)
                self.current_analysis = analysis
                self.state.last_snapshot = self.state.last_snapshot or {}
                self.state.last_snapshot["master_analysis"] = analysis
                self._ui_set_result_text(
                    json.dumps(analysis, ensure_ascii=False, indent=2)[:20000]
                )
                self._ui_set_status("Готово", "#2E7D32")
                self.history.add(
                    "Master analyze",
                    {"release": safe_release, "services": len(analysis.get("services", []) or [])},
                )
                self.history.save_to_file(self.history_path)
            except Exception as e:
                self._ui_set_status("Ошибка", "#C62828")
                self._ui_set_result_text(f"Ошибка master analysis: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def create_deploy_plan(self) -> None:
        """
        Создать/обновить Deploy plan в Confluence по результату последнего master анализа.
        """
        analysis = self.current_analysis or (self.state.last_snapshot or {}).get("master_analysis")
        if not analysis or not isinstance(analysis, dict) or not analysis.get("success"):
            self._ui_show_error("Ошибка", "Сначала выполни Master analyze.")
            return
        services = analysis.get("services") or []
        if not services:
            self._ui_show_error("Нет сервисов", "Нет сервисов для Deploy plan.")
            return
        if not self.master_analyzer:
            self._ui_show_error("Ошибка", "Confluence не настроен. Проверь .env.")
            return

        preview = ", ".join(services[:5]) + (f"… (+{len(services)-5})" if len(services) > 5 else "")
        ok = self._ui_ask_yes_no(
            "Подтверждение",
            "Создать/обновить Deploy plan?\n\n"
            f"Релиз: {analysis.get('release_key')}\n"
            f"Сервисов: {len(services)}\n"
            f"Пример: {preview}\n\n"
            f"Confluence: {CONFLUENCE_SPACE_KEY}/{CONFLUENCE_PARENT_PAGE_TITLE}\n"
            f"Команда: {TEAM_NAME}",
        )
        if not ok:
            return

        self._ui_set_status("Deploy plan…", "#1565C0")
        self._reset_output("📝 Создание Deploy plan…")

        def worker():
            try:
                result = self.master_analyzer.generate_deploy_plan(
                    analysis_result=analysis,
                    space_key=CONFLUENCE_SPACE_KEY,
                    parent_page_title=CONFLUENCE_PARENT_PAGE_TITLE,
                    team_name=TEAM_NAME,
                )
                if result.get("success"):
                    page_url = result.get("page_url", "")
                    page_title = result.get("page_title", "")
                    self._append_output("✅ Deploy plan создан/обновлён")
                    self._append_output(f"📄 {page_title}")
                    self._append_output(f"🔗 {page_url}")
                    self._ui_set_status("Готово", "#2E7D32")
                    self.history.add(
                        "Deploy plan",
                        {"release": analysis.get("release_key"), "services_count": len(services), "page_url": page_url},
                    )
                    self.history.save_to_file(self.history_path)
                else:
                    msg = result.get("message") or "Не удалось создать Deploy plan"
                    details = result.get("details") or ""
                    self._append_output(f"❌ {msg}")
                    if details:
                        self._append_output(str(details)[:2000])
                    self._ui_set_status("Ошибка", "#C62828")
            except Exception as e:
                self._append_output(f"❌ Ошибка Deploy plan: {e}")
                self._ui_set_status("Ошибка", "#C62828")

        threading.Thread(target=worker, daemon=True).start()

    def link_issues(self, *, release_key: str, fix_version: str, dry_run: bool = False) -> None:
        safe_release = (release_key or "").strip().upper()
        fv = (fix_version or "").strip()
        if not safe_release or not fv:
            self._ui_show_error("Ошибка", "Нужны release_key и fixVersion.")
            return

        self._ui_set_status("Linking…", "#1565C0")
        self._reset_output(f"🔗 Привязка задач fixVersion='{fv}' -> {safe_release}")

        def worker():
            try:
                self._append_output("Поиск задач по fixVersion…")
                jql = (
                    'project IN (HRM, HRC, NEUROUI, SFILE, SEARCHCS) '
                    'AND issuetype IN (Bug, Story) '
                    f'AND fixVersion = \"{fv}\"'
                )
                issues = self.jira_service.search_issues(jql)
                if not issues:
                    self._append_output("ℹ️ Нет задач для привязки.")
                    self._ui_set_status("Готово", "#2E7D32")
                    return

                link_types = self.jira_service.get_link_types() or {}
                link_type_name = next((name for name in link_types if "part" in name.lower()), None)
                if not link_type_name:
                    self._append_output("❌ Не найден подходящий тип связи (PartOf).")
                    self._ui_set_status("Ошибка", "#C62828")
                    return

                self._append_output("Проверка существующих связей релиза…")
                already_linked = set(self.jira_service.get_linked_issues(safe_release))
                issues_to_link = [
                    issue for issue in issues
                    if issue.get("key") and issue["key"] not in already_linked and issue["key"] != safe_release
                ]
                if not issues_to_link:
                    self._append_output(f"ℹ️ Все задачи уже привязаны к {safe_release}.")
                    self._ui_set_status("Готово", "#2E7D32")
                    return

                total = len(issues_to_link)
                success_count = 0
                errors: list[str] = []
                for i, issue in enumerate(issues_to_link, 1):
                    key = issue["key"]
                    if dry_run:
                        self._append_output(f"🔍 {key} (dry-run)")
                        success_count += 1
                    else:
                        if self.jira_service.create_issue_link(key, safe_release, link_type_name):
                            success_count += 1
                            self._append_output(f"✅ {key}")
                        else:
                            errors.append(key)
                            self._append_output(f"❌ {key}")
                    if i % 25 == 0 or i == total:
                        self._ui_set_status(f"Linking… {i}/{total}", "#1565C0")

                self.history.add(
                    "Привязка задач",
                    {"release_key": safe_release, "fix_version": fv, "total": total, "success": success_count, "errors": len(errors)},
                )
                self.history.save_to_file(self.history_path)

                msg = f"Готово. Успешно: {success_count}/{total}" + (f", ошибок: {len(errors)}" if errors else "")
                self._append_output(msg)
                self._ui_set_status("Готово", "#2E7D32" if not errors else "#EF6C00")
            except Exception as e:
                self._append_output(f"❌ Ошибка линкинга: {e}")
                self._ui_set_status("Ошибка", "#C62828")

        threading.Thread(target=worker, daemon=True).start()

    def cleanup_issues(self, *, release_key: str, fix_version: str, dry_run: bool = False) -> None:
        safe_release = (release_key or "").strip().upper()
        fv = (fix_version or "").strip()
        if not safe_release or not fv:
            self._ui_show_error("Ошибка", "Нужны release_key и fixVersion.")
            return

        self._ui_set_status("Cleanup…", "#1565C0")
        self._reset_output(f"🧹 Очистка связей релиза {safe_release} (оставить только fixVersion='{fv}')")

        def worker():
            try:
                linked = self.jira_service.get_linked_issues(safe_release)
                if not linked:
                    self._append_output("ℹ️ Нет связанных задач.")
                    self._ui_set_status("Готово", "#2E7D32")
                    return

                total = len(linked)
                removed = 0
                for i, issue_key in enumerate(linked, 1):
                    issue_data = self.jira_service.get_issue_details(issue_key)
                    if not issue_data:
                        continue
                    fields = issue_data.get("fields", {}) or {}
                    version_names = [v.get("name") for v in (fields.get("fixVersions") or []) if isinstance(v, dict)]
                    if fv not in version_names:
                        for link in fields.get("issuelinks", []) or []:
                            outward = (link.get("outwardIssue") or {}).get("key")
                            inward = (link.get("inwardIssue") or {}).get("key")
                            if outward == safe_release or inward == safe_release:
                                link_id = link.get("id")
                                if not link_id:
                                    break
                                if dry_run:
                                    removed += 1
                                    self._append_output(f"🔍 {issue_key} (dry-run remove)")
                                else:
                                    if self.jira_service.delete_issue_link(str(link_id)):
                                        removed += 1
                                        self._append_output(f"✅ {issue_key} (removed)")
                                break
                    if i % 25 == 0 or i == total:
                        self._ui_set_status(f"Cleanup… {i}/{total}", "#1565C0")

                self.history.add("Очистка связей", {"release_key": safe_release, "fix_version": fv, "total": total, "removed": removed})
                self.history.save_to_file(self.history_path)
                self._append_output(f"Готово. Удалено: {removed}/{total}")
                self._ui_set_status("Готово", "#2E7D32")
            except Exception as e:
                self._append_output(f"❌ Ошибка cleanup: {e}")
                self._ui_set_status("Ошибка", "#C62828")

        threading.Thread(target=worker, daemon=True).start()

    def remove_all_issues(self, *, release_key: str, fix_version: str, dry_run: bool = False) -> None:
        safe_release = (release_key or "").strip().upper()
        fv = (fix_version or "").strip()
        if not safe_release or not fv:
            self._ui_show_error("Ошибка", "Нужны release_key и fixVersion.")
            return

        if not dry_run:
            ok = self._ui_ask_yes_no(
                "Подтверждение",
                f"Удалить ВСЕ связи для {safe_release} по fixVersion='{fv}'?\n\nЭто действие необратимо!",
            )
            if not ok:
                return

        self._ui_set_status("Remove all…", "#1565C0")
        self._reset_output(f"🗑 Удаление всех связей {safe_release} (fixVersion='{fv}')")

        def worker():
            try:
                linked = self.jira_service.get_linked_issues(safe_release)
                if not linked:
                    self._append_output("ℹ️ Нет связанных задач.")
                    self._ui_set_status("Готово", "#2E7D32")
                    return

                total = len(linked)
                removed = 0
                errors: list[str] = []
                for i, issue_key in enumerate(linked, 1):
                    issue_data = self.jira_service.get_issue_details(issue_key)
                    if not issue_data:
                        continue
                    fields = issue_data.get("fields", {}) or {}
                    version_names = [v.get("name") for v in (fields.get("fixVersions") or []) if isinstance(v, dict)]
                    if fv in version_names:
                        for link in fields.get("issuelinks", []) or []:
                            outward = (link.get("outwardIssue") or {}).get("key")
                            inward = (link.get("inwardIssue") or {}).get("key")
                            if outward == safe_release or inward == safe_release:
                                link_id = link.get("id")
                                if not link_id:
                                    break
                                if dry_run:
                                    removed += 1
                                    self._append_output(f"🔍 {issue_key} (dry-run remove)")
                                else:
                                    if self.jira_service.delete_issue_link(str(link_id)):
                                        removed += 1
                                        self._append_output(f"✅ {issue_key} removed")
                                    else:
                                        errors.append(issue_key)
                                        self._append_output(f"❌ {issue_key} failed")
                                break
                    if i % 25 == 0 or i == total:
                        self._ui_set_status(f"Remove all… {i}/{total}", "#1565C0")

                self.history.add("Удаление всех связей", {"release_key": safe_release, "fix_version": fv, "total": total, "removed": removed, "errors": len(errors)})
                self.history.save_to_file(self.history_path)
                msg = f"Готово. Удалено: {removed}/{total}" + (f", ошибок: {len(errors)}" if errors else "")
                self._append_output(msg)
                self._ui_set_status("Готово", "#2E7D32" if not errors else "#EF6C00")
            except Exception as e:
                self._append_output(f"❌ Ошибка remove-all: {e}")
                self._ui_set_status("Ошибка", "#C62828")

        threading.Thread(target=worker, daemon=True).start()

    def run_architecture_update(self, *, release_key: str, project_key: str, fix_version: str) -> None:
        safe_release = (release_key or "").strip().upper()
        pk = (project_key or "").strip().upper()
        fv = (fix_version or "").strip()
        if not pk or not fv:
            # try derive from snapshot
            snap = self.state.last_snapshot or {}
            pk = pk or (snap.get("project_key") or "").strip().upper()
            # fixVersion: from release_issue.fixVersions if present
            rel = (snap.get("release_issue") or {}).get("fields", {}) if isinstance(snap.get("release_issue"), dict) else {}
            if not fv and isinstance(rel, dict):
                for item in rel.get("fixVersions", []) or []:
                    if isinstance(item, dict) and item.get("name"):
                        fv = str(item["name"]).strip()
                        break
        if not pk or not fv:
            self._ui_show_error("Нужны параметры", "Укажи Project и fixVersion (или сначала запусти проверку для snapshot).")
            return

        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "arch.py"))
        if not os.path.exists(script_path):
            self._ui_show_error("Нет arch.py", f"Скрипт не найден: {script_path}")
            return

        self._ui_set_status("Architecture…", "#1565C0")
        self._reset_output(f"🏗 Проставление архитектуры: {pk} / {fv}")

        def worker():
            try:
                proc = subprocess.run(
                    [sys.executable, script_path, "--project-key", pk, "--fix-version", fv, "--yes"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                out = (proc.stdout or "").strip()
                err = (proc.stderr or "").strip()
                if proc.returncode == 0:
                    self._append_output("✅ Готово")
                    if out:
                        self._append_output(out[-2000:])
                    self._ui_set_status("Готово", "#2E7D32")
                    self.history.add("Architecture", {"project": pk, "fix_version": fv})
                    self.history.save_to_file(self.history_path)
                else:
                    self._append_output(f"❌ Ошибка arch.py (exit={proc.returncode})")
                    if out:
                        self._append_output("STDOUT:\n" + out[-2000:])
                    if err:
                        self._append_output("STDERR:\n" + err[-2000:])
                    self._ui_set_status("Ошибка", "#C62828")
            except Exception as e:
                self._append_output(f"❌ Ошибка Architecture: {e}")
                self._ui_set_status("Ошибка", "#C62828")

        threading.Thread(target=worker, daemon=True).start()
