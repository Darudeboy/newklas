# core: ядро логики релизов (Jira, Confluence, snapshot, rules, orchestrator)
from core.types import (
    ReleaseSnapshot,
    RuleResult,
    ReleaseDecision,
    RecommendationState,
    SubtaskState,
    BugState,
    StoryResult,
    ManualCheckItem,
)

try:
    from core.jira_client import JiraService
except ImportError:
    JiraService = None  # type: ignore[misc, assignment]

__all__ = [
    "ReleaseSnapshot",
    "RuleResult",
    "ReleaseDecision",
    "RecommendationState",
    "SubtaskState",
    "BugState",
    "StoryResult",
    "ManualCheckItem",
    "JiraService",
]
