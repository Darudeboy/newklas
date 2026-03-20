"""
Сбор и нормализация данных по релизу для передачи в rules.
Все сетевые вызовы к Jira выполняются здесь; rules работают только с snapshot.
"""
import logging
from typing import Any, Dict, List, Optional

from core.types import is_jira_story_issue_type

logger = logging.getLogger(__name__)


def _get_linked_issue_keys(issue: dict) -> List[str]:
    keys: List[str] = []
    for link in issue.get("fields", {}).get("issuelinks", []) or []:
        outward = link.get("outwardIssue")
        inward = link.get("inwardIssue")
        if outward and outward.get("key"):
            keys.append(outward["key"])
        if inward and inward.get("key"):
            keys.append(inward["key"])
    return list(set(keys))


def _extract_issue_type(issue: dict) -> str:
    return str(
        issue.get("fields", {}).get("issuetype", {}).get("name", "")
    )


def _derive_business_project(
    release_issue: dict, related_issues: List[dict]
) -> str:
    for issue in related_issues:
        issue_type = _extract_issue_type(issue).lower()
        if is_jira_story_issue_type(_extract_issue_type(issue)) or issue_type in (
            "bug",
            "дефект",
        ):
            project_key = (
                str(issue.get("fields", {}).get("project", {}).get("key", ""))
                .strip()
                .upper()
            )
            if project_key:
                return project_key
    return (
        str(
            release_issue.get("fields", {}).get("project", {}).get("key", "")
        )
        .strip()
        .upper()
    )


def build_release_snapshot(
    jira_service: Any,
    release_key: str,
) -> Optional[Dict[str, Any]]:
    """
    Собирает все данные, нужные для оценки гейтов, в один снимок (dict).
    Возвращает None, если релиз не найден.
    """
    safe_release = (release_key or "").strip().upper()
    if not safe_release:
        return None

    release = jira_service.get_issue_details(
        safe_release,
        expand="issuelinks,renderedFields,names",
    )
    if not release:
        return None

    release.setdefault("fields", {})
    release.setdefault("renderedFields", {})

    sber_test_html = jira_service.get_sber_test_report(safe_release)
    if sber_test_html:
        release["fields"]["customfield_sber_test_html"] = sber_test_html
        release["renderedFields"]["customfield_sber_test_html"] = sber_test_html

    linked_keys = jira_service.get_linked_issues(safe_release)
    related_issues: List[dict] = []
    story_related: Dict[str, List[dict]] = {}

    for key in linked_keys:
        issue = jira_service.get_issue_details(key)
        if not issue:
            continue
        related_issues.append(issue)
        if is_jira_story_issue_type(_extract_issue_type(issue)):
            rel_keys = _get_linked_issue_keys(issue)
            story_related[key] = []
            for rk in rel_keys:
                ri = jira_service.get_issue_details(rk)
                if ri:
                    story_related[key].append(ri)

    field_name_map = jira_service.get_field_name_map()
    fetch_rqg = getattr(jira_service, "get_official_rqg_bundle", None)
    if callable(fetch_rqg):
        qgm_ok, qgm_message, qgm_payload = fetch_rqg(safe_release)
    else:
        qgm_ok, qgm_message, qgm_payload = jira_service.get_qgm_status(
            safe_release
        )
    comments = jira_service.get_issue_comments(safe_release)
    project_key = _derive_business_project(release, related_issues)

    return {
        "release_key": safe_release,
        "release_issue": release,
        "related_issues": related_issues,
        "story_related": story_related,
        "field_name_map": field_name_map,
        "sber_test_html": sber_test_html,
        "qgm_ok": qgm_ok,
        "qgm_message": qgm_message,
        "qgm_payload": qgm_payload or {},
        "comments": comments,
        "project_key": project_key,
    }
