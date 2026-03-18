from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol

from core import explain


class Assistant(Protocol):
    def reply(
        self,
        question: str,
        *,
        snapshot: Optional[Dict[str, Any]] = None,
        result: Optional[Dict[str, Any]] = None,
    ) -> str: ...

    def quick_summary(self, *, result: Dict[str, Any]) -> str: ...

    def quick_blockers(self, *, result: Dict[str, Any]) -> str: ...

    def quick_next_actions(self, *, result: Dict[str, Any]) -> str: ...


@dataclass
class RuleBasedAssistant:
    """
    Safe default assistant that does not require any external dependencies or network.
    It explains based on current snapshot/result only.
    """

    def reply(
        self,
        question: str,
        *,
        snapshot: Optional[Dict[str, Any]] = None,
        result: Optional[Dict[str, Any]] = None,
    ) -> str:
        return explain.answer(question, snapshot=snapshot, result=result)

    def quick_summary(self, *, result: Dict[str, Any]) -> str:
        return explain.summarize(result)

    def quick_blockers(self, *, result: Dict[str, Any]) -> str:
        return explain.explain_blockers(result)

    def quick_next_actions(self, *, result: Dict[str, Any]) -> str:
        return explain.next_actions(result)


def build_default_assistant() -> Assistant:
    return RuleBasedAssistant()

