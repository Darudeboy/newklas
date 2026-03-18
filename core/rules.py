"""
Чистые функции проверок (гейтов) по релизу. Без сетевых вызовов.
Все данные приходят через snapshot; порядок проверок сохранён.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional


def _norm(value: str) -> str:
    return (value or "").strip().lower()


def _is_terminal_stage(status_name: str) -> bool:
    """
    Terminal/final stage: checks are not applicable and must not block.

    Business rule (controlled redesign): for already approved/done releases
    we short-circuit evaluation to avoid false blockers.
    """
    s = _norm(status_name)
    if not s:
        return False
    if "утвержд" in s:
        return True
    terminal_markers = ("done", "closed", "resolved", "закры", "выполн", "готово")
    return any(marker in s for marker in terminal_markers)


def _is_ppsi_approval_stage(status_name: str) -> bool:
    # Exact business status name (source of truth).
    return _norm(status_name) == _norm("Утверждение ППСИ")


def _contains_any(text: str, keywords: List[str]) -> bool:
    lowered = _norm(text)
    return any(_norm(word) in lowered for word in (keywords or []))


def _status_in(status: str, allowed_statuses: List[str]) -> bool:
    status_norm = _norm(status)
    allowed = {_norm(item) for item in (allowed_statuses or [])}
    if status_norm in allowed:
        return True
    done_markers = ("done", "closed", "resolved", "выполн", "закры")
    if any(marker in status_norm for marker in done_markers):
        return True
    return False


def _status_exact_in(status: str, allowed_statuses: List[str]) -> bool:
    status_norm = _norm(status)
    allowed = {_norm(item) for item in (allowed_statuses or [])}
    return status_norm in allowed


def _extract_issue_text(issue: dict) -> str:
    fields = issue.get("fields", {}) or {}
    summary = str(fields.get("summary", ""))
    description = str(fields.get("description", ""))
    issue_type = str(fields.get("issuetype", {}).get("name", ""))
    return " ".join([summary, description, issue_type])


def _extract_issue_status(issue: dict) -> str:
    return str(issue.get("fields", {}).get("status", {}).get("name", "Unknown"))


def _extract_issue_type(issue: dict) -> str:
    return str(issue.get("fields", {}).get("issuetype", {}).get("name", ""))


def _value_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return " ".join(
            part for part in (_value_to_text(item) for item in value) if part
        )
    if isinstance(value, dict):
        preferred_keys = ("value", "name", "key", "url", "href", "title", "id")
        parts: List[str] = []
        for key in preferred_keys:
            if key in value:
                piece = _value_to_text(value.get(key))
                if piece:
                    parts.append(piece)
        if parts:
            return " ".join(parts)
        return str(value)
    return str(value)


def _has_meaningful_value(value: Any) -> bool:
    text = _value_to_text(value).strip().lower()
    if not text:
        return False
    return text not in {"none", "null", "n/a", "not set", "нет", "н/д", "-", "{}", "[]"}


def _find_issue_value_by_candidates(source: dict, candidates: List[str]) -> Any:
    for field_key in candidates or []:
        value = source.get(field_key)
        if _has_meaningful_value(value):
            return value
    return None


def _flatten_issue_fields(issue: dict) -> str:
    fields = issue.get("fields", {}) or {}
    rendered = issue.get("renderedFields", {}) or {}
    parts: List[str] = []
    for key, value in fields.items():
        parts.append(f"{key}:{value}")
    for key, value in rendered.items():
        parts.append(f"{key}:{value}")
    return " ".join(parts)


def _find_field_value_by_display_name(
    issue: dict,
    name_keywords: List[str],
    field_name_map: Optional[Dict[str, str]] = None,
) -> Any:
    fields = issue.get("fields", {}) or {}
    names = issue.get("names", {}) or {}
    if not isinstance(names, dict):
        return None
    # IMPORTANT: preserve keyword priority. Jira "names" iteration order is not stable
    # and overly broad keywords (e.g. "ифт") can match multiple fields.
    normalized_keywords = [_norm(x) for x in (name_keywords or []) if _norm(x)]
    for keyword in normalized_keywords:
        for field_id, display_name in names.items():
            display = _norm(str(display_name))
            if not display or keyword not in display:
                continue
            value = fields.get(field_id)
            if _has_meaningful_value(value):
                return value
    global_map = field_name_map or {}
    for keyword in normalized_keywords:
        for field_id, value in fields.items():
            display_name = _norm(str(global_map.get(field_id, "")))
            if not display_name or keyword not in display_name:
                continue
            if _has_meaningful_value(value):
                return value
    return None


def _is_before_stage(current_status: str, *, workflow_order: List[str], target_stage: str) -> bool:
    """
    True if current stage is before target stage in workflow_order.
    If order is unknown, falls back to heuristic by keyword.
    """
    cur = _norm(current_status)
    target = _norm(target_stage)
    if not cur or not target:
        return False
    order = [_norm(x) for x in (workflow_order or []) if _norm(x)]
    if target in order and cur in order:
        return order.index(cur) < order.index(target)
    # heuristic fallback
    if target in cur:
        return False
    # if workflow missing, assume "пси" is later than "стабил"
    if "пси" in target:
        return "пси" not in cur and any(x in cur for x in ("формир", "стабил"))
    return False


def _has_distribution_link(release_issue: dict, profile: dict) -> bool:
    fields = release_issue.get("fields", {}) or {}
    tab = profile.get("distribution_tab", {})
    value = _find_issue_value_by_candidates(fields, tab.get("link_fields", []))
    if value is None:
        value = _find_field_value_by_display_name(
            release_issue,
            tab.get("link_display_keywords", []),
        )
    if value is None:
        blob = _flatten_issue_fields(release_issue).lower()
        ke_markers = [_norm(x) for x in tab.get("ke_keywords", [])]
        has_ke = any(marker in blob for marker in ke_markers) if ke_markers else False
        if any(
            marker in blob for marker in ("дистриб", "distrib", "distribution", "artifact")
        ) and ("http://" in blob or "https://" in blob):
            return True
        if has_ke and ("http://" in blob or "https://" in blob):
            return True
        return False
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, dict):
        return bool(value)
    return True


def _is_distribution_registered(
    release_issue: dict,
    profile: dict,
    field_name_map: Optional[Dict[str, str]] = None,
) -> bool:
    fields = release_issue.get("fields", {}) or {}
    tab = profile.get("distribution_tab", {})
    value = _find_issue_value_by_candidates(
        fields, tab.get("registered_fields", [])
    )
    if value is None:
        value = _find_field_value_by_display_name(
            release_issue,
            tab.get("ke_keywords", []),
            field_name_map=field_name_map,
        )
    if isinstance(value, bool):
        return value
    if value is None:
        blob = _flatten_issue_fields(release_issue).lower()
        ke_markers = [_norm(x) for x in tab.get("ke_keywords", [])]
        has_ke = any(marker in blob for marker in ke_markers) if ke_markers else False
        has_registered = any(
            marker in blob for marker in ("зарегистр", "registered", "регистрац")
        )
        if has_ke and has_registered:
            return True
        if has_ke:
            negative_patterns = (
                r"кэ дистрибутива[^a-zа-я0-9]{0,20}(нет|н/д|n/a|none)",
                r"ke distribution[^a-z0-9]{0,20}(no|n/a|none|not set)",
            )
            if not any(
                re.search(p, blob, flags=re.IGNORECASE) for p in negative_patterns
            ):
                return True
        return False
    value_text = _value_to_text(value)
    if _contains_any(value_text, tab.get("registered_keywords", [])):
        return True
    if not re.search(
        r"\b(н/д|нет|none|n/a|not set)\b", value_text, flags=re.IGNORECASE
    ):
        return True
    return False


def _is_ift_recommended(release_issue: dict, profile: dict) -> bool:
    fields = release_issue.get("fields", {}) or {}
    rendered = release_issue.get("renderedFields", {}) or {}
    tab = profile.get("testing_tab", {})
    candidates = tab.get("ift_recommendation_fields", [])
    value = _find_issue_value_by_candidates(fields, candidates)
    if value is None:
        value = _find_issue_value_by_candidates(rendered, candidates)
    if value is None:
        value = _find_field_value_by_display_name(
            release_issue,
            tab.get("ift_display_keywords", []),
        )
    if value is None:
        blob = _flatten_issue_fields(release_issue).lower()
        has_label = "ифт" in blob or "ift" in blob
        has_recommended = "рекоменд" in blob or "recommended" in blob
        has_green = any(_norm(x) in blob for x in tab.get("green_keywords", []))
        if has_label and has_recommended and (has_green or has_recommended):
            return True
        html_blob = str(release_issue.get("renderedFields", {})).lower()
        html_blob = re.sub(r"<[^>]+>", " ", html_blob)
        html_blob = re.sub(r"\s+", " ", html_blob)
        if re.search(
            r"рекомендац[а-я\s]*по\s*отчет[а-я\s]*ифт.{0,400}рекомендован",
            html_blob,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            return True
        if re.search(
            r"ift.{0,200}recommend.{0,200}recommend",
            html_blob,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            return True
        return False
    keyword = (tab.get("ift_approved_keywords") or ["рекомендован"])[0]
    value_str = str(value)
    if _contains_any(value_str, [keyword]):
        return True
    return _contains_any(
        value_str, tab.get("ift_approved_keywords", ["рекоменд", "recommended"])
    )


def _is_recommendation_by_display_name(
    release_issue: dict,
    field_name_map: Dict[str, str],
    display_keywords: List[str],
    approved_keywords: List[str],
) -> bool:
    value = _find_field_value_by_display_name(
        release_issue,
        display_keywords,
        field_name_map=field_name_map,
    )
    if value is None:
        blob = _flatten_issue_fields(release_issue).lower()
        has_marker = any(_norm(k) in blob for k in (display_keywords or []))
        if has_marker:
            return _contains_any(blob, approved_keywords)
        return False
    return _contains_any(_value_to_text(value), approved_keywords)


def _is_recommendation_in_rendered(
    release_issue: dict,
    label_patterns: List[str],
    approved_keywords: List[str],
) -> bool:
    rendered = release_issue.get("renderedFields", {}) or {}
    fields = release_issue.get("fields", {}) or {}
    html_blob = " ".join(
        [
            str(rendered).lower(),
            str(fields.get("customfield_sber_test_html", "")).lower(),
            str(rendered.get("customfield_sber_test_html", "")).lower(),
        ]
    )
    html_blob = re.sub(r"<[^>]+>", " ", html_blob)
    html_blob = re.sub(r"\s+", " ", html_blob)
    for label in label_patterns or []:
        label_norm = _norm(label)
        if not label_norm:
            continue
        # Jira can render the testing block as a large table; the value can be far from the label.
        pattern = rf"{re.escape(label_norm)}.{{0,1200}}({'|'.join(re.escape(_norm(k)) for k in approved_keywords if _norm(k))})"
        if re.search(pattern, html_blob, flags=re.IGNORECASE | re.DOTALL):
            return True
    return False


def _evaluate_story(
    story_key: str,
    story_issue: dict,
    related_issues: List[dict],
    profile: dict,
) -> Dict[str, Any]:
    story_rules = profile.get("story_rules", {})
    done_statuses = profile.get("done_statuses", [])

    bt_ok = False
    arch_ok = False
    bt_details = "не найдено согласованное БТ"
    arch_details = "не найдена согласованная архитектура (или не требуется)"

    for issue in related_issues:
        key = issue.get("key", "")
        text = f"{key} {_extract_issue_text(issue)}"
        status = _extract_issue_status(issue)
        if _contains_any(text, story_rules.get("bt_keywords", [])) and _status_in(
            status, done_statuses
        ):
            bt_ok = True
            bt_details = f"{key} ({status})"
        if _contains_any(text, story_rules.get("arch_keywords", [])):
            if _status_in(status, done_statuses):
                arch_ok = True
                arch_details = f"{key} ({status})"
            else:
                arch_ok = False
                arch_details = f"{key} ({status})"

    if not arch_ok and "не найдена" in arch_details:
        arch_ok = True
        arch_details = "изменения архитектуры не обнаружены"

    ok = bt_ok and arch_ok
    return {
        "issue_key": story_key,
        "issue_type": "Story",
        "ok": ok,
        "details": {"bt": bt_details, "architecture": arch_details},
    }


def _evaluate_bug(
    bug_key: str, bug_issue: dict, profile: dict
) -> Dict[str, Any]:
    bug_rules = profile.get("bug_rules", {})
    text = f"{bug_key} {_extract_issue_text(bug_issue)}"
    status = _extract_issue_status(bug_issue)
    ok = True
    reason = "ok"
    if _contains_any(text, bug_rules.get("ct_ift_keywords", [])):
        ct_ift_allowed = bug_rules.get(
            "ct_ift_allowed_statuses", ["Закрыт", "Закрыто", "Closed"]
        )
        if not _status_exact_in(status, ct_ift_allowed):
            ok = False
            reason = f"Для CT/IFT требуется статус 'Закрыт/Closed', сейчас: {status}"
    if ok and _contains_any(text, bug_rules.get("prom_keywords", [])):
        prom_statuses = bug_rules.get("prom_expected_statuses", [])
        if not _status_in(status, prom_statuses):
            ok = False
            reason = f"Для ПРОМ ожидается 'Подтверждение выполнения', сейчас: {status}"
    return {
        "issue_key": bug_key,
        "issue_type": "Bug",
        "ok": ok,
        "details": {"status": status, "reason": reason},
    }


def _evaluate_manual_subtasks(
    release_issue: dict,
    related_issues: List[dict],
    profile: dict,
) -> List[Dict[str, Any]]:
    status_by_keyword: List[Dict[str, str]] = []
    all_issues = [release_issue] + related_issues
    for issue in all_issues:
        fields = issue.get("fields", {}) or {}
        for sub in fields.get("subtasks", []) or []:
            sub_summary = str(sub.get("fields", {}).get("summary", ""))
            sub_status = str(
                sub.get("fields", {}).get("status", {}).get("name", "Unknown")
            )
            status_by_keyword.append(
                {
                    "summary": sub_summary,
                    "status": sub_status,
                    "key": sub.get("key", ""),
                }
            )

    pending: List[Dict[str, Any]] = []
    for check in profile.get("manual_checks", []):
        keywords = check.get("keywords", [])
        required_statuses = check.get("required_statuses", [])
        if not keywords:
            pending.append(
                {
                    "id": check.get("id"),
                    "title": check.get("title"),
                    "status": "manual",
                    "message": "Требуется ручное подтверждение.",
                }
            )
            continue
        matched = [
            item
            for item in status_by_keyword
            if _contains_any(item.get("summary", ""), keywords)
        ]
        if not matched:
            pending.append(
                {
                    "id": check.get("id"),
                    "title": check.get("title"),
                    "status": "optional_missing",
                    "message": "Подзадача не найдена (проверь, требуется ли для проекта).",
                }
            )
            continue
        bad = [
            item
            for item in matched
            if not _status_exact_in(item.get("status", ""), required_statuses)
        ]
        if bad:
            pending.append(
                {
                    "id": check.get("id"),
                    "title": check.get("title"),
                    "status": "manual",
                    "message": f"Есть незакрытые подзадачи: {', '.join(x.get('key') or x.get('summary', '') for x in bad)}",
                }
            )
    return pending


def _distribution_from_related_issues(
    related_issues: List[dict],
) -> Dict[str, bool]:
    link_present = False
    registered = False
    dist_markers = ("дистриб", "distribution", "distrib", "release-notes", "install")
    approved_markers = ("утвержден", "approved", "согласован", "выполн", "закры")
    for issue in related_issues:
        fields = issue.get("fields", {}) or {}
        issue_type = str(fields.get("issuetype", {}).get("name", ""))
        summary = str(fields.get("summary", ""))
        status = str(fields.get("status", {}).get("name", ""))
        text = f"{issue_type} {summary}".lower()
        if any(marker in text for marker in dist_markers):
            link_present = True
            if any(marker in status.lower() for marker in approved_markers):
                registered = True
    return {"link_present": link_present, "registered": registered}


def _comment_text(comment: dict) -> str:
    body = comment.get("body", "")
    if isinstance(body, str):
        return body
    return str(body)


def _extract_rqg_comment_signals(comments: List[dict]) -> Dict[str, bool]:
    text_blob = "\n".join(_comment_text(c) for c in comments).lower()
    # Keep this intentionally permissive: the "RQG" button in Jira often leaves
    # different comment templates across projects/versions.
    rqg_markers = ("rqg", "qgm", "quality gate", "quality-gate")
    ok_markers = ("успеш", "пройден", "пройдены", "ok", "passed", "success")
    return {
        "rqg_success": "проверки rqg успешно выполнены" in text_blob
        or (
            any(m in text_blob for m in rqg_markers)
            and any(m in text_blob for m in ok_markers)
        ),
        "testing_completed": "запланированный объём тестирования: выполнен" in text_blob
        or "запланированный объем тестирования: выполнен" in text_blob,
        "no_critical_bugs": "открытые блокирующие и критичные дефекты: нет" in text_blob
        or "критичные дефекты: нет" in text_blob,
        "recommended_to_psi": "рекомендации по переводу на пси: рекомендован" in text_blob
        or ("рекомендован" in text_blob and "пси" in text_blob),
    }


def _next_transition(
    current_status: str, workflow_order: List[str]
) -> Optional[str]:
    normalized = [_norm(x) for x in workflow_order]
    current = _norm(current_status)
    if current not in normalized:
        return None
    idx = normalized.index(current)
    if idx >= len(workflow_order) - 1:
        return None
    return workflow_order[idx + 1]


def _parse_http_status_from_text(text: str) -> Optional[int]:
    match = re.search(r"HTTP\s+(\d{3})", text or "", re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def _is_qgm_technical_error(message: str) -> bool:
    msg = (message or "").lower()
    if "request failed" in msg:
        return True
    if "empty non-json body" in msg or "returned empty" in msg:
        return True
    if "timed out" in msg or "timeout" in msg:
        return True
    status = _parse_http_status_from_text(message or "")
    return status in {400, 401, 403, 404, 405, 429, 500, 502, 503, 504}


def _resolve_transition_id(
    profile: dict, next_status: Optional[str]
) -> Optional[str]:
    if not next_status:
        return None
    transition_ids = profile.get("transition_ids", {}) or {}
    transition_id = transition_ids.get(next_status)
    if transition_id is None:
        return None
    return str(transition_id)


def evaluate_gates(
    snapshot: Dict[str, Any],
    profile: dict,
) -> Dict[str, Any]:
    """
    Выполняет все проверки гейтов по snapshot и profile.
    Возвращает dict в формате, совместимом с evaluate_release_gates
    (manual_done=[] и manual_confirmations не применяются — это делает orchestrator).
    """
    release_issue = snapshot["release_issue"]
    related_issues = snapshot["related_issues"]
    story_related = snapshot.get("story_related") or {}
    field_name_map = snapshot.get("field_name_map") or {}
    qgm_ok = snapshot.get("qgm_ok", False)
    qgm_message = snapshot.get("qgm_message", "")
    qgm_payload = snapshot.get("qgm_payload") or {}
    comments = snapshot.get("comments") or []
    release_key = snapshot["release_key"]
    project_key = snapshot.get("project_key", "")

    current_status = _extract_issue_status(release_issue)
    if _is_ppsi_approval_stage(current_status):
        reason = (
            "Релиз уже в статусе 'Утверждение ППСИ': по процессу Jira все гейты пройдены, "
            "дополнительные проверки не требуются."
        )
        return {
            "success": True,
            "terminal_stage": True,
            "terminal_reason": reason,
            "release_key": release_key,
            "project_key": project_key,
            "profile_name": profile.get("name", "default"),
            "current_stage": current_status,
            "next_allowed_transition": None,
            "next_allowed_transition_id": None,
            "ready_for_transition": False,
            "auto_passed": [],
            "auto_failed": [],
            "auto_warnings": [],
            "manual_pending": [],
            "manual_optional": [],
            "manual_done": [],
            "story_results": [],
            "bug_results": [],
            "rqg_qgm": {
                "ok": snapshot.get("qgm_ok", False),
                "message": snapshot.get("qgm_message", ""),
                "payload": snapshot.get("qgm_payload") or {},
            },
        }
    if _is_terminal_stage(current_status):
        reason = f"Этап финальный ('{current_status}'): проверки не актуальны."
        return {
            "success": True,
            "terminal_stage": True,
            "terminal_reason": reason,
            "release_key": release_key,
            "project_key": project_key,
            "profile_name": profile.get("name", "default"),
            "current_stage": current_status,
            "next_allowed_transition": None,
            "next_allowed_transition_id": None,
            "ready_for_transition": False,
            "auto_passed": [],
            "auto_failed": [],
            "auto_warnings": [],
            "manual_pending": [],
            "manual_optional": [],
            "manual_done": [],
            "story_results": [],
            "bug_results": [],
            "rqg_qgm": {
                "ok": snapshot.get("qgm_ok", False),
                "message": snapshot.get("qgm_message", ""),
                "payload": snapshot.get("qgm_payload") or {},
            },
        }

    story_results: List[Dict[str, Any]] = []
    bug_results: List[Dict[str, Any]] = []

    for issue in related_issues:
        key = issue.get("key", "")
        issue_type = _extract_issue_type(issue).lower()
        if issue_type == "story":
            story_results.append(
                _evaluate_story(
                    key,
                    issue,
                    story_related.get(key, []),
                    profile,
                )
            )
        elif issue_type == "bug":
            bug_results.append(_evaluate_bug(key, issue, profile))

    auto_passed: List[Dict[str, Any]] = []
    auto_failed: List[Dict[str, Any]] = []
    auto_warnings: List[Dict[str, Any]] = []

    stories_ok = (
        all(item.get("ok") for item in story_results) if story_results else True
    )
    story_gate = {
        "id": "story_quality",
        "title": "Качество Story (наличие БТ и Архитектуры)",
        "ok": stories_ok,
        "details": {
            "stories_total": len(story_results),
            "stories_failed": len([x for x in story_results if not x.get("ok")]),
        },
    }
    (auto_passed if story_gate["ok"] else auto_failed).append(story_gate)

    bugs_ok = all(item.get("ok") for item in bug_results) if bug_results else True
    if not bugs_ok:
        bad_bugs = [x for x in bug_results if not x.get("ok")]
        bug_warning = {
            "id": "bug_quality",
            "title": "Баг в некорректном статусе - внимание",
            "ok": False,
            "details": {
                "bugs_total": len(bug_results),
                "bugs_failed": len(bad_bugs),
                "reasons": [
                    f"{b.get('issue_key')}: {b.get('details', {}).get('reason')}"
                    for b in bad_bugs
                ],
            },
        }
        auto_warnings.append(bug_warning)
    elif bug_results:
        auto_passed.append(
            {
                "id": "bug_quality",
                "title": "Статусы багов (CT/IFT/PROM)",
                "ok": True,
                "details": {"message": "Все баги в корректных статусах"},
            }
        )

    dist_link_ok = _has_distribution_link(release_issue, profile)
    dist_registered_ok = _is_distribution_registered(
        release_issue, profile, field_name_map=field_name_map
    )
    distribution_tab = profile.get("distribution_tab", {})
    dist_link_value = _find_field_value_by_display_name(
        release_issue,
        distribution_tab.get("link_display_keywords", []),
        field_name_map=field_name_map,
    )
    dist_ke_value = _find_field_value_by_display_name(
        release_issue,
        distribution_tab.get("ke_keywords", []),
        field_name_map=field_name_map,
    )
    recommendation_ok = _is_ift_recommended(release_issue, profile)
    testing_tab = profile.get("testing_tab", {})
    nt_recommendation_ok = _is_recommendation_by_display_name(
        release_issue,
        field_name_map=field_name_map,
        display_keywords=testing_tab.get("nt_display_keywords", []),
        approved_keywords=testing_tab.get("nt_approved_keywords", []),
    )
    if not nt_recommendation_ok:
        nt_recommendation_ok = _is_recommendation_in_rendered(
            release_issue,
            testing_tab.get("nt_display_keywords", []),
            testing_tab.get("nt_approved_keywords", []),
        )
    dt_recommendation_ok = _is_recommendation_by_display_name(
        release_issue,
        field_name_map=field_name_map,
        display_keywords=testing_tab.get("dt_display_keywords", []),
        approved_keywords=testing_tab.get("dt_approved_keywords", []),
    )
    if not dt_recommendation_ok:
        dt_recommendation_ok = _is_recommendation_in_rendered(
            release_issue,
            testing_tab.get("dt_display_keywords", []),
            testing_tab.get("dt_approved_keywords", []),
        )
    if not recommendation_ok:
        recommendation_ok = _is_recommendation_in_rendered(
            release_issue,
            testing_tab.get("ift_display_keywords", []),
            testing_tab.get("ift_approved_keywords", []),
        )

    rqg_actual_ok = False
    if qgm_ok and isinstance(qgm_payload, dict):
        rqg_info = (
            qgm_payload.get("rqgInfo", {})
            if isinstance(qgm_payload.get("rqgInfo"), dict)
            else {}
        )
        has_blockers = bool(
            rqg_info.get("hasBlockDataRqg1")
            or rqg_info.get("hasBlockDataRqg2")
            or rqg_info.get("hasBlockDataRqg3")
        )
        to_comment = str(qgm_payload.get("toComment", "")).lower()
        if not has_blockers and (
            "успешно" in to_comment or "success" in to_comment
        ):
            rqg_actual_ok = True
        elif not has_blockers and rqg_info:
            rqg_actual_ok = True

    if not rqg_actual_ok:
        comment_signals = _extract_rqg_comment_signals(comments)
        if comment_signals.get("rqg_success"):
            rqg_actual_ok = True

    dist_from_links = _distribution_from_related_issues(related_issues)
    dist_link_ok = dist_link_ok or dist_from_links["link_present"]
    dist_registered_ok = dist_registered_ok or dist_from_links["registered"]

    # Business rule: distribution registration becomes available only at "ПСИ".
    # Before PSI we must not block the transition by this gate.
    before_psi = _is_before_stage(
        current_status,
        workflow_order=profile.get("workflow_order", []),
        target_stage="ПСИ",
    )
    if before_psi:
        dist_gate = {
            "id": "distribution_tab",
            "title": "Вкладка Дистрибутивы",
            "ok": True,
            "details": {
                "not_applicable": True,
                "reason": "До этапа «ПСИ» регистрация дистрибутива недоступна — гейт не применяется.",
                "link_present": dist_link_ok,
                "registered": dist_registered_ok,
                "distribution_link_value": _value_to_text(dist_link_value)[:300],
                "distribution_ke_value": _value_to_text(dist_ke_value)[:300],
                "linked_distribution_issue": dist_from_links,
            },
        }
        auto_passed.append(dist_gate)
    else:
        dist_gate = {
            "id": "distribution_tab",
            "title": "Вкладка Дистрибутивы",
            "ok": dist_link_ok and dist_registered_ok,
            "details": {
                "link_present": dist_link_ok,
                "registered": dist_registered_ok,
                "distribution_link_value": _value_to_text(dist_link_value)[:300],
                "distribution_ke_value": _value_to_text(dist_ke_value)[:300],
                "linked_distribution_issue": dist_from_links,
            },
        }
        (auto_passed if dist_gate["ok"] else auto_failed).append(dist_gate)

    recommendation_gate = {
        "id": "testing_recommendation",
        "title": "Результаты тестирования / рекомендация ИФТ",
        "ok": recommendation_ok,
        "details": {"recommended": recommendation_ok},
    }
    (auto_passed if recommendation_gate["ok"] else auto_failed).append(
        recommendation_gate
    )

    nt_gate = {
        "id": "nt_recommendation",
        "title": "Рекомендация НТ",
        "ok": nt_recommendation_ok,
        "details": {"recommended": nt_recommendation_ok},
    }
    (auto_passed if nt_gate["ok"] else auto_failed).append(nt_gate)

    dt_gate = {
        "id": "dt_recommendation",
        "title": "Рекомендация ДТ",
        "ok": dt_recommendation_ok,
        "details": {"recommended": dt_recommendation_ok},
    }
    (auto_passed if dt_gate["ok"] else auto_failed).append(dt_gate)

    enforce_qgm = _norm(os.getenv("RELEASE_FLOW_ENFORCE_QGM", "false")) in {
        "1",
        "true",
        "yes",
        "y",
        "да",
    }
    rqg_warning_only = False
    rqg_gate_ok = rqg_actual_ok
    if (
        not rqg_actual_ok
        and not enforce_qgm
        and _is_qgm_technical_error(qgm_message)
    ):
        rqg_gate_ok = True
        rqg_warning_only = True

    rqg_gate = {
        "id": "rqg_qgm",
        "title": "RQG (qgm endpoint)",
        "ok": rqg_gate_ok,
        "details": {
            "ok": rqg_actual_ok,
            "http_ok": qgm_ok,
            "warning_only": rqg_warning_only,
            "message": qgm_message,
            "payload_preview": str(qgm_payload or {})[:400],
        },
    }
    (auto_passed if rqg_gate["ok"] else auto_failed).append(rqg_gate)

    manual_raw = _evaluate_manual_subtasks(
        release_issue, related_issues, profile
    )
    manual_pending = [
        item for item in manual_raw if item.get("status") != "optional_missing"
    ]
    manual_optional = [
        item for item in manual_raw if item.get("status") == "optional_missing"
    ]

    next_status = _next_transition(
        current_status, profile.get("workflow_order", [])
    )
    next_transition_id = _resolve_transition_id(profile, next_status)
    ready_for_transition = (
        len(auto_failed) == 0
        and len(manual_pending) == 0
        and bool(next_status)
    )

    return {
        "success": True,
        "release_key": release_key,
        "project_key": project_key,
        "profile_name": profile.get("name", "default"),
        "current_stage": current_status,
        "next_allowed_transition": next_status,
        "next_allowed_transition_id": next_transition_id,
        "ready_for_transition": ready_for_transition,
        "auto_passed": auto_passed,
        "auto_failed": auto_failed,
        "auto_warnings": auto_warnings,
        "manual_pending": manual_pending,
        "manual_optional": manual_optional,
        "manual_done": [],
        "story_results": story_results,
        "bug_results": bug_results,
        "rqg_qgm": {"ok": qgm_ok, "message": qgm_message, "payload": qgm_payload},
    }
