"""
Ассистент чата: GigaChat + fallback на rule-based explain.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from core import explain
from core.gigachat_client import GigaChatClient

SYSTEM_PROMPT = """Ты помощник по процессу релизов в Jira (гейты, статусы workflow).
Отвечай по-русски, кратко и по делу.
ВАЖНО: опирайся только на переданный «Контекст проверки». Не выдумывай статусы задач и не утверждай, что гейт пройден, если в контексте написано обратное.
Если контекста нет — скажи, что нужно сначала запустить проверку релиза во вкладке «Результаты»."""


def _compact_result_for_llm(result: Optional[Dict[str, Any]]) -> str:
    if not result:
        return "Проверка гейтов ещё не выполнялась (result пустой)."
    if not result.get("success"):
        return f"Ошибка проверки: {result.get('message', '')}"

    def _gates(items: List[Any]) -> str:
        out = []
        for g in items or []:
            if isinstance(g, dict):
                out.append(
                    f"  - {g.get('title', g.get('id', '?'))}: {g.get('details', '')}"
                )
        return "\n".join(out) if out else "  (нет)"

    lines = [
        f"release_key: {result.get('release_key')}",
        f"профиль: {result.get('profile_name')}",
        f"текущий этап (статус в Jira): {result.get('current_stage')}",
        f"следующий этап workflow: {result.get('next_allowed_transition')}",
        f"готов к переходу (все гейты ок): {result.get('ready_for_transition')}",
        f"terminal_stage: {result.get('terminal_stage')}",
        f"terminal_reason: {result.get('terminal_reason', '')}",
        "авто-гейты пройдены:",
        _gates(result.get("auto_passed")),
        "авто-гейты провалены:",
        _gates(result.get("auto_failed")),
        "ручные проверки (ожидают):",
        _gates(result.get("manual_pending")),
    ]
    return "\n".join(str(x) for x in lines)


class GigaChatAssistant:
    """
    Свободные вопросы в чате — через GigaChat (если включено и есть креды).
    Кнопки «Краткий summary» / блокеры — быстрые, без сети (explain).
    """

    def __init__(self, client: Optional[GigaChatClient] = None) -> None:
        self._client = client
        use = os.getenv("GIGACHAT_USE_FOR_CHAT", "1").strip().lower()
        self._giga_enabled = use not in ("0", "false", "no", "off")

    def gigachat_active(self) -> bool:
        return bool(
            self._giga_enabled
            and self._client
            and self._client.is_configured()
        )

    def reply(
        self,
        question: str,
        *,
        snapshot: Optional[Dict[str, Any]] = None,
        result: Optional[Dict[str, Any]] = None,
    ) -> str:
        q = (question or "").strip()
        if not q:
            return "Задай вопрос."

        if (
            self._giga_enabled
            and self._client
            and self._client.is_configured()
        ):
            ctx = _compact_result_for_llm(result)
            if snapshot and snapshot.get("release_key"):
                ctx = f"Ключ релиза в snapshot: {snapshot.get('release_key')}\n" + ctx
            user_block = f"Контекст проверки:\n{ctx}\n\nВопрос: {q}"
            ok, text = self._client.complete(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_block[:14000]},
                ],
                temperature=0.12,
            )
            if ok and text:
                return text
            fallback = explain.answer(q, snapshot=snapshot, result=result)
            err = text or "неизвестная ошибка"
            return (
                f"[GigaChat недоступен: {err}]\n\n"
                f"Локальный ответ:\n{fallback}"
            )

        return explain.answer(q, snapshot=snapshot, result=result)

    def quick_summary(self, *, result: Dict[str, Any]) -> str:
        return explain.summarize(result)

    def quick_blockers(self, *, result: Dict[str, Any]) -> str:
        return explain.explain_blockers(result)

    def quick_next_actions(self, *, result: Dict[str, Any]) -> str:
        return explain.next_actions(result)


def build_assistant() -> GigaChatAssistant:
    client = GigaChatClient.from_env()
    return GigaChatAssistant(client=client)
