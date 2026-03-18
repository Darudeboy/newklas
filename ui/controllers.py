from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
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
        self._ui_set_connection = ui_set_connection

        self._init_master_analyzer()

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

