"""
Единая точка входа: проверка гейтов релиза и выполнение перехода.
run_release_check: сбор snapshot → rules → учёт manual_confirmations → результат.
run_release_action: переход в целевой статус workflow (to.name) или по id/имени кнопки.
run_workflow_autopilot: цикл проверка → переход, пока гейты зелёные.
"""
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from core.confluence_client import ConfluenceClient
from core.snapshot_builder import build_release_snapshot
from core.rules import evaluate_gates
from core.release_flow_config import get_release_flow_profile

logger = logging.getLogger(__name__)

SUCCESS_COMMENT_MARKER = "Релиз проверен"
SUCCESS_COMMENT_TEXT = SUCCESS_COMMENT_MARKER
# Старые шаблоны — не дублировать комментарий после смены текста.
_LEGACY_COMMENT_MARKERS = (
    SUCCESS_COMMENT_MARKER,
    "[Release-Gates]",
    "Релиз готов к внедрению",
)


def _release_already_commented(jira_service: Any, release_key: str) -> bool:
    has_recent = getattr(jira_service, "has_recent_comment", None)
    if not callable(has_recent):
        return False
    for marker in _LEGACY_COMMENT_MARKERS:
        if has_recent(release_key, marker, lookback=50):
            return True
    return False


def maybe_post_success_comment(
    jira_service: Any,
    result: Dict[str, Any],
    *,
    dry_run: bool = False,
) -> Tuple[bool, str]:
    """
    Публикует один комментарий «Релиз проверен» в Jira (анти-спам по маркеру).
    Условия:
    - проверка успешна, auto_failed пуст
    - ready_for_transition
    - dry_run=False
    - комментария с маркером ещё не было
    """
    if dry_run:
        return False, "dry-run: comment skipped"
    if not result.get("success"):
        return False, "result not successful"
    if result.get("auto_failed"):
        return False, "auto_failed not empty"
    if not result.get("ready_for_transition"):
        return False, "not ready for transition"

    release_key = (result.get("release_key") or "").strip().upper()
    if not release_key:
        return False, "missing release_key"

    if _release_already_commented(jira_service, release_key):
        return False, "already posted"

    add_comment = getattr(jira_service, "add_issue_comment", None)
    if not callable(add_comment):
        return False, "jira_service does not support comments"
    return jira_service.add_issue_comment(release_key, SUCCESS_COMMENT_TEXT)


def run_release_check(
    jira_service: Any,
    release_key: str,
    profile_name: str = "auto",
    manual_confirmations: Optional[Dict[str, bool]] = None,
    *,
    post_success_comment: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Оценка гейтов релиза. Совместимый с прежним evaluate_release_gates результат.
    """
    safe_release = (release_key or "").strip().upper()
    if not safe_release:
        return {"success": False, "message": "Не указан release_key."}

    # Best-effort: enrich snapshot with Confluence checks similar to approve-job (if token configured).
    cf_token = (os.getenv("CONFLUENCE_TOKEN") or "").strip()
    cf_url = (os.getenv("CONFLUENCE_URL") or "").strip()
    confluence_client = (
        ConfluenceClient(url=cf_url, token=cf_token, verify_ssl=False)
        if cf_url and cf_token
        else None
    )

    snapshot = build_release_snapshot(
        jira_service, safe_release, confluence_client=confluence_client
    )
    if not snapshot:
        return {"success": False, "message": f"Релиз {safe_release} не найден."}

    project_key = snapshot.get("project_key", "")
    profile = get_release_flow_profile(
        project_key=project_key,
        requested_profile=profile_name,
    )

    result = evaluate_gates(snapshot, profile)
    confirmations = manual_confirmations or {}

    manual_pending = result["manual_pending"]
    manual_done: list = []
    still_pending: list = []
    for item in manual_pending:
        check_id = item.get("id")
        if confirmations.get(check_id) is True:
            manual_done.append(item)
        else:
            still_pending.append(item)

    result["manual_pending"] = still_pending
    result["manual_done"] = manual_done
    result["ready_for_transition"] = (
        len(result["auto_failed"]) == 0 and len(still_pending) == 0 and bool(result.get("next_allowed_transition"))
    )

    comment_posted = False
    comment_message = ""
    if post_success_comment:
        ok, msg = maybe_post_success_comment(
            jira_service,
            result,
            dry_run=dry_run,
        )
        comment_posted = bool(ok)
        comment_message = str(msg or "")
        if ok:
            logger.info("Posted success comment for %s", safe_release)
        else:
            logger.debug("Skip/failed posting success comment for %s: %s", safe_release, msg)
    result["success_comment"] = {
        "posted": comment_posted,
        "message": comment_message,
    }

    return result


def run_workflow_autopilot(
    jira_service: Any,
    release_key: str,
    profile_name: str = "auto",
    manual_confirmations: Optional[Dict[str, bool]] = None,
    *,
    post_success_comment: bool = False,
    dry_run: bool = False,
    max_steps: Optional[int] = None,
    post_transition_delay_sec: Optional[float] = None,
    stuck_threshold: int = 3,
) -> Dict[str, Any]:
    """
    Непрерывно: run_release_check → при ready_for_transition переход в next_allowed_transition,
    пока не terminal_stage, блокировка гейтами, ошибка Jira, лимит шагов или «застревание» статуса.

    Возвращает dict: ok, stop_reason, steps, last_result, message.
    stop_reason: terminal | blocked | jira_error | max_steps | stuck | dry_run_blocked | check_failed
    """
    safe_release = (release_key or "").strip().upper()
    if not safe_release:
        return {
            "ok": False,
            "stop_reason": "check_failed",
            "steps": [],
            "last_result": {},
            "message": "Не указан release_key.",
        }

    if dry_run:
        return {
            "ok": False,
            "stop_reason": "dry_run_blocked",
            "steps": [],
            "last_result": {},
            "message": "Автопилот недоступен в dry-run: без реальных переходов цикл не продвинет состояние Jira.",
        }

    manual = manual_confirmations or {}
    steps_log: List[Dict[str, Any]] = []

    result = run_release_check(
        jira_service,
        safe_release,
        profile_name,
        manual,
        post_success_comment=post_success_comment,
        dry_run=False,
    )
    if not result.get("success"):
        return {
            "ok": False,
            "stop_reason": "check_failed",
            "steps": steps_log,
            "last_result": result,
            "message": str(result.get("message") or "Ошибка проверки гейтов"),
        }

    project_key = result.get("project_key", "")
    profile = get_release_flow_profile(
        project_key=project_key,
        requested_profile=profile_name,
    )
    wf_order = profile.get("workflow_order") or []
    if max_steps is None:
        raw_cap = (os.getenv("RELEASE_AUTOFLOW_MAX_STEPS") or "").strip()
        max_steps = (
            int(raw_cap)
            if raw_cap.isdigit()
            else min(30, len(wf_order) + 5 if wf_order else 15)
        )
    max_steps = max(1, min(100, int(max_steps)))
    if post_transition_delay_sec is None:
        try:
            post_transition_delay_sec = float(
                os.getenv("RELEASE_AUTOFLOW_POST_TRANSITION_DELAY_SEC", "1.5")
            )
        except ValueError:
            post_transition_delay_sec = 1.5

    st_thr = max(1, int(stuck_threshold))

    while True:
        if result.get("terminal_stage"):
            return {
                "ok": True,
                "stop_reason": "terminal",
                "steps": steps_log,
                "last_result": result,
                "message": str(
                    result.get("terminal_reason") or "Финальный этап workflow."
                ),
            }

        if not result.get("ready_for_transition"):
            return {
                "ok": False,
                "stop_reason": "blocked",
                "steps": steps_log,
                "last_result": result,
                "message": "Гейты или ручные проверки блокируют переход.",
            }

        next_status = (result.get("next_allowed_transition") or "").strip()
        if not next_status:
            return {
                "ok": False,
                "stop_reason": "blocked",
                "steps": steps_log,
                "last_result": result,
                "message": "Следующий этап workflow не определён.",
            }

        if len(steps_log) >= max_steps:
            return {
                "ok": False,
                "stop_reason": "max_steps",
                "steps": steps_log,
                "last_result": result,
                "message": f"Достигнут лимит шагов автопилота ({max_steps}).",
            }

        stage_from = (result.get("current_stage") or "").strip()

        # Before PPSI coordination some Jira workflows require distribution registration.
        if next_status == "Согласование ППСИ":
            reg_fn = getattr(jira_service, "register_distribution", None)
            if callable(reg_fn):
                ok_reg, msg_reg = jira_service.register_distribution(safe_release)
                steps_log.append(
                    {
                        "from_stage": stage_from,
                        "to_status": "register_distribution",
                        "ok": bool(ok_reg),
                    }
                )
                if not ok_reg:
                    return {
                        "ok": False,
                        "stop_reason": "jira_error",
                        "steps": steps_log,
                        "last_result": result,
                        "message": str(msg_reg or "Ошибка регистрации дистрибутива"),
                    }

        ok_tr, msg_tr = jira_service.transition_issue_to_status(
            safe_release, next_status
        )
        steps_log.append(
            {
                "from_stage": stage_from,
                "to_status": next_status,
                "ok": bool(ok_tr),
            }
        )
        if not ok_tr:
            return {
                "ok": False,
                "stop_reason": "jira_error",
                "steps": steps_log,
                "last_result": result,
                "message": str(msg_tr or "Ошибка перехода в Jira"),
            }

        progressed = False
        for attempt in range(st_thr):
            time.sleep(post_transition_delay_sec * (attempt + 1))
            result = run_release_check(
                jira_service,
                safe_release,
                profile_name,
                manual,
                post_success_comment=post_success_comment,
                dry_run=False,
            )
            if not result.get("success"):
                return {
                    "ok": False,
                    "stop_reason": "check_failed",
                    "steps": steps_log,
                    "last_result": result,
                    "message": str(result.get("message") or "Ошибка проверки после перехода"),
                }
            cur = (result.get("current_stage") or "").strip()
            if cur != stage_from:
                progressed = True
                break

        if not progressed:
            return {
                "ok": False,
                "stop_reason": "stuck",
                "steps": steps_log,
                "last_result": result,
                "message": (
                    f"Статус в Jira не сменился после перехода в «{next_status}» "
                    f"(попыток ожидания: {st_thr})."
                ),
            }


def run_release_action(
    jira_service: Any,
    release_key: str,
    transition_id: Optional[str] = None,
    transition_name: Optional[str] = None,
    target_status: Optional[str] = None,
) -> tuple[bool, str]:
    """
    Выполнить переход релиза.
    Приоритет: target_status (статус назначения в Jira) → transition_id → transition_name.
    """
    safe_release = (release_key or "").strip().upper()
    if not safe_release:
        return False, "Не указан release_key."

    ts = (target_status or "").strip()
    if ts:
        return jira_service.transition_issue_to_status(safe_release, ts)
    if transition_id:
        return jira_service.transition_issue_by_id(safe_release, transition_id)
    if transition_name:
        return jira_service.transition_issue(safe_release, transition_name)
    return False, "Укажи target_status (рекомендуется), transition_id или transition_name."


def format_release_gate_report(result: Dict[str, Any]) -> str:
    """Форматирование отчёта по гейтам (совместимо с прежним format_release_gate_report)."""
    if not result.get("success"):
        return f"❌ {result.get('message', 'Ошибка оценки гейтов')}"

    lines: list = []
    lines.append("=" * 80)
    lines.append(f"🧭 GUIDED CYCLE: {result.get('release_key')}")
    lines.append("=" * 80)
    lines.append(f"Профиль: {result.get('profile_name')} | Проект: {result.get('project_key')}")
    lines.append(f"Текущий этап: {result.get('current_stage')}")
    lines.append(f"Следующий этап (статус workflow): {result.get('next_allowed_transition') or 'нет'}")
    rqg_qgm = result.get("rqg_qgm", {}) or {}
    if rqg_qgm.get("ok"):
        lines.append("RQG qgm: успешно")
    lines.append("")

    if result.get("terminal_stage"):
        reason = result.get("terminal_reason") or "Этап финальный: проверки не актуальны."
        lines.append(f"✅ {reason}")
        lines.append("=" * 80)
        return "\n".join(lines)

    lines.append(f"✅ Авто-гейты пройдены: {len(result.get('auto_passed', []))}")
    for gate in result.get("auto_passed", []):
        details = gate.get("details") or {}
        if gate.get("id") == "rqg_qgm" and details.get("warning_only"):
            lines.append(f"  - {gate.get('title')} (warning: endpoint недоступен, не блокирует)")
        elif gate.get("id") == "distribution_tab" and details.get(
            "registered_via_nexus_urls"
        ):
            lines.append(
                f"  - {gate.get('title')} — ок: в задаче есть прямые URL на артефакты "
                f"(Nexus/repository); отдельное поле «зарегистрирован»/КЭ не требуется"
            )
        elif gate.get("id") == "distribution_tab" and details.get("not_applicable"):
            lines.append(f"  - {gate.get('title')} (до ПСИ не проверяется)")
        else:
            lines.append(f"  - {gate.get('title')}")
    lines.append(f"❌ Авто-гейты провалены: {len(result.get('auto_failed', []))}")
    for gate in result.get("auto_failed", []):
        lines.append(f"  - {gate.get('title')}: {gate.get('details')}")
        gate_id = gate.get("id")
        if gate_id == "distribution_tab":
            lines.append(
                "    Что сделать: укажи ссылку(и) на дистрибутив в Nexus (ZIP) или заполни "
                "поля «зарегистрирован»/КЭ в Jira."
            )
        elif gate_id == "testing_recommendation":
            lines.append(
                "    Что сделать: в Jira в блоке «Отчёт о тестировании» статус «Рекомендация по отчёту ИФТ» "
                "должен быть «Рекомендован» (не «НЕ РЕКОМЕНДОВАН»). Сформируйте/обновите отчёт ИФТ в Jira."
            )
        elif gate_id == "nt_recommendation":
            lines.append("    Что сделать: НТ должна быть 'Не требуется' или 'Версия 2 РЕКОМЕНДОВАН'.")
        elif gate_id == "dt_recommendation":
            lines.append("    Что сделать: ДТ должна быть 'РЕКОМЕНДОВАН'.")
        elif gate_id == "rqg_qgm":
            lines.append(
                "    Что сделать: проверь ответ RQG (comalarest/rqgstatus по linkedIssues или fallback "
                "/rest/release/1/qgm). См. newui/docs/RQG.md."
            )
        elif gate_id == "story_bug_quality":
            lines.append("    Что сделать: закрой bug CT/IFT (только статус 'Закрыт/Closed').")
    lines.append("")

    auto_manual = result.get("manual_auto_ok") or []
    if auto_manual:
        lines.append(
            f"✅ Ручные проверки закрыты по данным Jira (подтверждение в инструменте не нужно): {len(auto_manual)}"
        )
        for check in auto_manual:
            lines.append(f"  - {check.get('id')}: {check.get('message')}")
            fp = (check.get("field_preview") or "").strip()
            if fp:
                lines.append(f"    Значение в задаче: {fp}")

    lines.append(f"📝 Ручные проверки pending (нужно действие от вас): {len(result.get('manual_pending', []))}")
    for check in result.get("manual_pending", []):
        cid = check.get("id") or ""
        lines.append(f"  - [{cid}] {check.get('title') or cid}")
        lines.append(f"    Проблема: {check.get('message')}")
        if cid == "decommission_distribution":
            lines.append(
                "    Что сделать: в карточке релиза заполнить поле «Дистрибутивы, выводимые из эксплуатации» "
                "ИЛИ в инструменте выполнить: confirm_manual_check(<релиз>, decommission_distribution, ok)."
            )
        elif cid in ("load_test_subtask", "author_supervision_subtask", "translations_subtask"):
            lines.append(
                "    Что сделать: закрыть соответствующую подзадачу в Jira (статус «Закрыт»/Closed) "
                "или убедиться, что подзадача с нужным текстом в summary существует."
            )
        else:
            lines.append(
                "    Что сделать: выполнить подтверждение в инструменте или устранить причину, указанную выше."
            )
    if result.get("auto_warnings"):
        lines.append("")
        lines.append(f"⚠️ ВНИМАНИЕ (рекомендации, не блокируют переход): {len(result.get('auto_warnings', []))}")
        for warn in result.get("auto_warnings", []):
            lines.append(f" - {warn.get('title')}")
            if warn.get("id") == "bug_quality":
                for reason in warn.get("details", {}).get("reasons", []):
                    lines.append(f"   * 🐛 {reason}")

    if result.get("manual_pending"):
        lines.append("")
        lines.append("  Команда подтверждения (если поле в Jira заполнить нельзя, а проверку нужно закрыть вручную):")
        lines.append(
            f"  confirm_manual_check({result.get('release_key')}, <check_id>, ok)  "
            f"— подставь check_id из списка выше (например decommission_distribution)."
        )
    if result.get("manual_done"):
        lines.append(f"✅ Подтверждено вручную: {len(result.get('manual_done', []))}")
        for check in result.get("manual_done", []):
            lines.append(f"  - {check.get('id')}: подтверждено")
    if result.get("manual_optional"):
        lines.append(f"ℹ️ Опциональные проверки: {len(result.get('manual_optional', []))}")
        for check in result.get("manual_optional", []):
            lines.append(f"  - {check.get('id')}: {check.get('message')}")
    lines.append("")

    if result.get("ready_for_transition"):
        lines.append("🚀 Готов к переходу по workflow.")
        sc = result.get("success_comment") or {}
        if sc.get("posted"):
            lines.append(f"💬 В Jira добавлен комментарий: «{SUCCESS_COMMENT_TEXT}»")
        elif sc.get("message") == "already posted":
            lines.append(f"💬 Комментарий «{SUCCESS_COMMENT_TEXT}» уже был в задаче (повторно не добавлялся).")
    else:
        lines.append("")
        lines.append("─── ИТОГ: ПОЧЕМУ НЕЛЬЗЯ ПЕРЕЙТИ ───")
        reasons: list[str] = []
        if result.get("auto_failed"):
            reasons.append(
                f"• Авто-гейты провалены ({len(result['auto_failed'])} шт.) — см. блок «❌ Авто-гейты провалены» выше."
            )
        if result.get("manual_pending"):
            ids = ", ".join(str(x.get("id")) for x in result["manual_pending"])
            reasons.append(
                f"• Не закрыты ручные проверки в инструменте: {ids}. "
                f"Пока хотя бы одна «pending» — переход по workflow блокируется."
            )
        if not (result.get("next_allowed_transition") or "").strip():
            reasons.append(
                "• Следующий этап workflow не определён (уже финальный статус или статус не входит в профиль)."
            )
        if not reasons:
            reasons.append("• См. детали выше (авто-гейты и ручные проверки).")
        for r in reasons:
            lines.append(r)
        lines.append("⛔ Переход заблокирован до устранения пунктов выше.")

    lines.append("=" * 80)
    return "\n".join(lines)
