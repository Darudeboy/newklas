from __future__ import annotations

from typing import Any, Dict, List, Optional


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _gate_title(item: dict) -> str:
    title = _safe_str(item.get("title"))
    return title or _safe_str(item.get("id")) or "check"


def summarize(result: Dict[str, Any]) -> str:
    if not result:
        return "Нет данных: сначала запусти проверку."
    if not result.get("success"):
        return f"Ошибка: {result.get('message') or 'проверка неуспешна'}"

    release_key = _safe_str(result.get("release_key")) or "-"
    current_stage = _safe_str(result.get("current_stage")) or "-"
    next_stage = _safe_str(result.get("next_allowed_transition")) or "нет"
    ready = bool(result.get("ready_for_transition"))
    auto_failed = result.get("auto_failed") or []
    manual_pending = result.get("manual_pending") or []
    warnings = result.get("auto_warnings") or []

    lines: List[str] = []
    lines.append(f"Релиз: {release_key}")
    lines.append(f"Текущий этап: {current_stage}")
    lines.append(f"Следующий этап: {next_stage}")
    lines.append(f"Готов к переходу: {'ДА' if ready else 'НЕТ'}")
    lines.append(
        "Сводка: "
        f"blockers={len(auto_failed) + len(manual_pending)}, "
        f"warnings={len(warnings)}"
    )
    return "\n".join(lines)


def explain_blockers(result: Dict[str, Any]) -> str:
    if not result:
        return "Нет данных: сначала запусти проверку."
    if not result.get("success"):
        return f"Ошибка: {result.get('message') or 'проверка неуспешна'}"

    auto_failed = result.get("auto_failed") or []
    manual_pending = result.get("manual_pending") or []
    if not auto_failed and not manual_pending:
        return "Блокеров нет: авто-гейты и ручные проверки пройдены."

    lines: List[str] = []
    if auto_failed:
        lines.append("Авто-блокеры:")
        for item in auto_failed:
            details = item.get("details")
            lines.append(f"- {_gate_title(item)}: {details}")
    if manual_pending:
        lines.append("")
        lines.append("Ручные проверки (нужно подтвердить):")
        for item in manual_pending:
            lines.append(
                f"- {item.get('id')}: {item.get('message') or item.get('title')}"
            )
    return "\n".join(lines).strip()


def next_actions(result: Dict[str, Any]) -> str:
    if not result:
        return "Нет данных: сначала запусти проверку."
    if not result.get("success"):
        return "Сначала устрани ошибку проверки и повтори запуск."

    next_stage = _safe_str(result.get("next_allowed_transition"))
    next_id = _safe_str(result.get("next_allowed_transition_id"))
    ready = bool(result.get("ready_for_transition"))
    manual_pending = result.get("manual_pending") or []
    auto_failed = result.get("auto_failed") or []

    lines: List[str] = []
    if auto_failed:
        lines.append("1) Разблокируй авто-гейты (см. «Объясни блокеры»).")
    if manual_pending:
        lines.append("2) Подтверди ручные проверки (выбери check_id и отметь OK/FAIL).")
    if ready and next_stage:
        suffix = f" (transition id: {next_id})" if next_id else ""
        lines.append(f"3) Можно безопасно выполнить переход -> '{next_stage}'{suffix}.")
    elif next_stage:
        lines.append(
            f"3) Следующий этап по workflow: '{next_stage}', но сейчас переход заблокирован."
        )
    else:
        lines.append("3) Следующий этап не определён (вне workflow или финальный статус).")
    return "\n".join(lines).strip()


def answer(
    question: str, snapshot: Optional[Dict[str, Any]], result: Optional[Dict[str, Any]]
) -> str:
    q = (question or "").strip().lower()
    if not q:
        return "Задай вопрос или выбери быстрый сценарий."

    res = result or {}
    if any(token in q for token in ("summary", "свод", "кратко")):
        return summarize(res)
    if any(token in q for token in ("blocker", "блокер", "почему", "что мешает")):
        return explain_blockers(res)
    if any(token in q for token in ("дальше", "next", "что делать", "рекоменд")):
        return next_actions(res)
    if any(token in q for token in ("статус", "stage", "этап")):
        return summarize(res)

    base = summarize(res) if res else "Нет результата проверки."
    return (
        base
        + "\n\n"
        + "Я пока работаю в stub-режиме без LLM. Могу объяснить блокеры, дать next actions или сделать краткий summary."
    )

