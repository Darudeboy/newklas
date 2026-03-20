"""
Dataclass-модели для нормализованного release snapshot и результата проверок.
Сохранена совместимость с текущим форматом dict, возвращаемым evaluate_release_gates.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional

# Jira REST возвращает issuetype.name на языке инстанса (напр. «История» вместо Story).
JIRA_STORY_TYPE_ALIASES: FrozenSet[str] = frozenset(
    {
        "story",
        "история",
        "user story",
    }
)


def is_jira_story_issue_type(name: Optional[str]) -> bool:
    """True, если тип задачи — Story (EN/RU и распространённые варианты)."""
    n = (name or "").strip().lower()
    return n in JIRA_STORY_TYPE_ALIASES


@dataclass
class RuleResult:
    """Результат одной проверки (гейта)."""
    id: str
    title: str
    ok: bool
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SubtaskState:
    """Состояние подзадачи для ручных проверок."""
    summary: str
    status: str
    key: str = ""


@dataclass
class ManualCheckItem:
    """Элемент ручной проверки (pending/optional_missing/done)."""
    id: str
    title: str
    status: str  # "manual" | "optional_missing" | ...
    message: str = ""


@dataclass
class StoryResult:
    """Результат оценки Story (БТ, архитектура)."""
    issue_key: str
    issue_type: str = "Story"
    ok: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BugState:
    """Результат оценки Bug (CT/IFT/PROM статусы)."""
    issue_key: str
    issue_type: str = "Bug"
    ok: bool = True
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RecommendationState:
    """Состояние рекомендации (ИФТ/НТ/ДТ)."""
    recommended: bool = False


@dataclass
class PsiState:
    """Состояние по ПСИ (если используется)."""
    recommended: bool = False


@dataclass
class ReleaseSnapshot:
    """
    Нормализованный снимок данных по релизу для передачи в rules.
    Собирается snapshot_builder из Jira без выполнения проверок.
    """
    release_key: str
    release_issue: Dict[str, Any]
    related_issues: List[Dict[str, Any]]
    field_name_map: Dict[str, str]
    sber_test_html: str = ""
    qgm_ok: bool = False
    qgm_message: str = ""
    qgm_payload: Optional[Dict[str, Any]] = None
    comments: List[Dict[str, Any]] = field(default_factory=list)
    project_key: str = ""


@dataclass
class ReleaseDecision:
    """
    Итоговое решение по релизу после проверки гейтов.
    Может быть сериализовано в тот же dict, что возвращает evaluate_release_gates.
    """
    success: bool
    release_key: str = ""
    message: str = ""
    project_key: str = ""
    profile_name: str = "default"
    current_stage: str = ""
    next_allowed_transition: Optional[str] = None
    next_allowed_transition_id: Optional[str] = None
    ready_for_transition: bool = False
    auto_passed: List[Dict[str, Any]] = field(default_factory=list)
    auto_failed: List[Dict[str, Any]] = field(default_factory=list)
    auto_warnings: List[Dict[str, Any]] = field(default_factory=list)
    manual_pending: List[Dict[str, Any]] = field(default_factory=list)
    manual_optional: List[Dict[str, Any]] = field(default_factory=list)
    manual_done: List[Dict[str, Any]] = field(default_factory=list)
    story_results: List[Dict[str, Any]] = field(default_factory=list)
    bug_results: List[Dict[str, Any]] = field(default_factory=list)
    rqg_qgm: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Совместимость с форматом, ожидаемым format_release_gate_report и UI."""
        return {
            "success": self.success,
            "release_key": self.release_key,
            "message": self.message,
            "project_key": self.project_key,
            "profile_name": self.profile_name,
            "current_stage": self.current_stage,
            "next_allowed_transition": self.next_allowed_transition,
            "next_allowed_transition_id": self.next_allowed_transition_id,
            "ready_for_transition": self.ready_for_transition,
            "auto_passed": self.auto_passed,
            "auto_failed": self.auto_failed,
            "auto_warnings": self.auto_warnings,
            "manual_pending": self.manual_pending,
            "manual_optional": self.manual_optional,
            "manual_done": self.manual_done,
            "story_results": self.story_results,
            "bug_results": self.bug_results,
            "rqg_qgm": self.rqg_qgm,
        }
