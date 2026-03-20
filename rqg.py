import os
from typing import Any, Dict, List, Set, Optional


def _split_csv(value: str, fallback: List[str]) -> List[str]:
    raw = (value or "").strip()
    if not raw:
        return fallback
    return [part.strip() for part in raw.split(",") if part.strip()]


def _build_rqg_settings() -> Dict[str, List[str]]:
    return {
        "co_keywords": [s.lower() for s in _split_csv(os.getenv("RQG_CO_KEYWORDS", ""), ["цо", "co"])],
        "ift_keywords": [s.lower() for s in _split_csv(os.getenv("RQG_IFT_KEYWORDS", ""), ["ифт", "ift"])],
        "distribution_keywords": [
            s.lower() for s in _split_csv(os.getenv("RQG_DISTRIBUTION_KEYWORDS", ""), ["дистриб", "distrib", "release-notes", "install"])
        ],
        "co_statuses": [s.lower() for s in _split_csv(os.getenv("RQG_CO_ALLOWED_STATUSES", ""), ["done", "closed", "resolved", "выполнено", "закрыто"])],
        "ift_statuses": [s.lower() for s in _split_csv(os.getenv("RQG_IFT_ALLOWED_STATUSES", ""), ["done", "closed", "resolved", "выполнено", "закрыто"])],
        "distribution_statuses": [
            s.lower() for s in _split_csv(os.getenv("RQG_DISTRIBUTION_ALLOWED_STATUSES", ""), ["done", "closed", "resolved", "выполнено", "закрыто"])
        ],
    }


def _issue_summary(issue: dict) -> str:
    return (issue.get("fields", {}).get("summary") or "").strip()


def _issue_status(issue: dict) -> str:
    return (issue.get("fields", {}).get("status", {}).get("name") or "").strip()


def _issue_type(issue: dict) -> str:
    return (issue.get("fields", {}).get("issuetype", {}).get("name") or "").strip()


def _linked_issue_keys(issue: dict) -> List[str]:
    keys: List[str] = []
    for link in issue.get("fields", {}).get("issuelinks", []) or []:
        outward = link.get("outwardIssue")
        inward = link.get("inwardIssue")
        if outward and outward.get("key"):
            keys.append(outward["key"])
        if inward and inward.get("key"):
            keys.append(inward["key"])
    return list(set(keys))


def _contains_any(text: str, needles: List[str]) -> bool:
    lowered = (text or "").lower()
    return any(needle in lowered for needle in needles)


def _classify_related_issue(issue_key: str, issue: dict, settings: Dict[str, List[str]]) -> str:
    summary = _issue_summary(issue)
    combined = f"{issue_key} {summary}".lower()
    issue_type = _issue_type(issue).lower()

    if _contains_any(combined, settings["co_keywords"]):
        return "co"
    if _contains_any(combined, settings["ift_keywords"]):
        return "ift"
    if _contains_any(combined, settings["distribution_keywords"]) or "дистриб" in issue_type:
        return "distribution"
    return ""


def _has_distribution_attachment(story_issue: dict, distribution_keywords: List[str]) -> bool:
    attachments = story_issue.get("fields", {}).get("attachment", []) or []
    for attachment in attachments:
        filename = (attachment.get("filename") or "").lower()
        if _contains_any(filename, distribution_keywords):
            return True
    return False


def analyze_rqg_for_release(jira_service, release_key: str, max_depth: int = 2) -> Dict:
    settings = _build_rqg_settings()
    release = jira_service.get_issue_details(release_key)
    if not release:
        return {"success": False, "message": f"Релиз {release_key} не найден"}

    stories: List[str] = []
    gl = getattr(jira_service, "get_linked_issue_keys_consists_of", None)
    if callable(gl):
        for k in gl(release_key):
            issue = jira_service.get_issue_details(k)
            if issue and _issue_type(issue).lower() == "story":
                stories.append(k)
        stories = sorted(set(stories))

    if not stories:
        # Fallback: BFS по связям и сабтаскам (набор может не совпасть с кнопкой RQG в Jira).
        discovered: Set[str] = set()
        queue: List[tuple[str, int]] = [(release_key, 0)]

        while queue:
            issue_key, depth = queue.pop(0)
            if issue_key in discovered or depth > max_depth:
                continue
            discovered.add(issue_key)

            issue = jira_service.get_issue_details(issue_key)
            if not issue:
                continue

            for subtask in issue.get("fields", {}).get("subtasks", []) or []:
                sub_key = subtask.get("key")
                if sub_key and sub_key not in discovered:
                    queue.append((sub_key, depth + 1))

            for linked_key in _linked_issue_keys(issue):
                if linked_key not in discovered:
                    queue.append((linked_key, depth + 1))

        discovered.discard(release_key)

        for issue_key in sorted(discovered):
            issue = jira_service.get_issue_details(issue_key)
            if not issue:
                continue
            if _issue_type(issue).lower() == "story":
                stories.append(issue_key)

    story_results: List[Dict] = []
    failed = 0

    for story_key in stories:
        story_issue = jira_service.get_issue_details(story_key)
        if not story_issue:
            continue

        related_items = []
        for related_key in _linked_issue_keys(story_issue):
            related_issue = jira_service.get_issue_details(related_key)
            if not related_issue:
                continue
            related_type = _classify_related_issue(related_key, related_issue, settings)
            if related_type:
                related_items.append({
                    "key": related_key,
                    "type": related_type,
                    "status": _issue_status(related_issue),
                    "summary": _issue_summary(related_issue),
                })

        co_items = [x for x in related_items if x["type"] == "co"]
        ift_items = [x for x in related_items if x["type"] == "ift"]
        dist_items = [x for x in related_items if x["type"] == "distribution"]

        co_ok = bool(co_items) and all((x["status"] or "").lower() in settings["co_statuses"] for x in co_items)
        ift_ok = bool(ift_items) and all((x["status"] or "").lower() in settings["ift_statuses"] for x in ift_items)

        has_dist_attachment = _has_distribution_attachment(story_issue, settings["distribution_keywords"])
        dist_issue_ok = bool(dist_items) and all(
            (x["status"] or "").lower() in settings["distribution_statuses"] for x in dist_items
        )
        distribution_ok = has_dist_attachment or dist_issue_ok

        story_ok = co_ok and ift_ok and distribution_ok
        if not story_ok:
            failed += 1

        story_results.append({
            "story_key": story_key,
            "story_summary": _issue_summary(story_issue),
            "co_items": co_items,
            "ift_items": ift_items,
            "distribution_items": dist_items,
            "distribution_attachment_found": has_dist_attachment,
            "co_ok": co_ok,
            "ift_ok": ift_ok,
            "distribution_ok": distribution_ok,
            "ok": story_ok,
        })

    passed = len(story_results) - failed
    return {
        "success": True,
        "release_key": release_key,
        "total_stories": len(story_results),
        "passed_stories": passed,
        "failed_stories": failed,
        "story_results": story_results,
        "settings": settings,
    }


# Порядок и подписи как в модальном окне Jira «Отклонения от требований RQG»
_KKP_ORDER: List[str] = [
    "kkpSqg",
    "kkpDyna",
    "kkpMpack",
    "kkpSonar",
    "kkpDataReady",
    "kkpMlv",
    "kkpApi",
    "kkpAiAr",
    "kkpDataModel",
    "kkpMqg",
    "kkpNsi",
]

_KKP_LABELS: Dict[str, str] = {
    "kkpSqg": "Security Quality Gate (SQG)",
    "kkpDyna": "DYNA Quality Gate",
    "kkpMpack": "Quality Gate доверенный M-pack",
    "kkpSonar": "QG.CI.1 Static Code Analysis",
    "kkpDataReady": "Data Ready Quality Gate",
    "kkpMlv": "QG MLV",
    "kkpApi": "API Quality Gate",
    "kkpAiAr": "QG AI/AR",
    "kkpDataModel": "Data Model QG",
    "kkpMqg": "MQG",
    "kkpNsi": "NSI QG",
}


def _distributive_messages_from_block(v: Any) -> List[str]:
    if not isinstance(v, dict):
        return []
    dists = v.get("distributives") or []
    if not isinstance(dists, list):
        return []
    out: List[str] = []
    seen: Set[str] = set()
    for d in dists:
        if isinstance(d, dict):
            msg = (d.get("key") or d.get("message") or "").strip()
        elif isinstance(d, str):
            msg = d.strip()
        else:
            msg = ""
        if msg and msg not in seen:
            seen.add(msg)
            out.append(msg)
    return out


def _gate_sections_human(rqg_info: Dict[str, Any]) -> List[tuple[str, List[str]]]:
    """Секции (заголовок как в Jira, список уникальных сообщений)."""
    if not isinstance(rqg_info, dict):
        return []
    sections: List[tuple[str, List[str]]] = []
    used: Set[str] = set()
    for k in _KKP_ORDER:
        if k in used:
            continue
        v = rqg_info.get(k)
        msgs = _distributive_messages_from_block(v)
        if not msgs:
            continue
        label = _KKP_LABELS.get(k, k)
        sections.append((label, msgs))
        used.add(k)
    for k, v in sorted(rqg_info.items()):
        if not str(k).startswith("kkp") or k in used:
            continue
        msgs = _distributive_messages_from_block(v)
        if msgs:
            sections.append((_KKP_LABELS.get(k, k), msgs))
            used.add(k)
    return sections


def _format_rqg_info_compact(ri: Dict[str, Any]) -> List[str]:
    """Краткий текст по одной задаче (без технических флагов)."""
    lines: List[str] = []
    sections = _gate_sections_human(ri)
    if not sections:
        return lines

    flat: List[str] = []
    for _title, msgs in sections:
        flat.extend(msgs)
    unique_all: List[str] = []
    seen: Set[str] = set()
    for m in flat:
        if m not in seen:
            seen.add(m)
            unique_all.append(m)

    if len(unique_all) == 1:
        lines.append("Блокирующие проверки RQG")
        lines.append(f"  • {unique_all[0]}")
        return lines

    lines.append("Блокирующие проверки RQG")
    for title, msgs in sections:
        lines.append(f"  {title}")
        for m in msgs:
            lines.append(f"    • {m}")
    return lines


def format_official_rqg_payload_block(payload: Optional[Dict[str, Any]]) -> str:
    """Краткий блок по ответу comalarest/qgm — как модалка Jira, без лишней техники."""
    if not isinstance(payload, dict) or not payload:
        return ""
    lines: List[str] = []
    lines.append("Отклонения от требований релизных Quality Gates")
    lines.append("")

    per = payload.get("perLinkedIssue")
    wrote = False
    if isinstance(per, dict) and per:
        for lk in sorted(per.keys()):
            raw = per.get(lk) or {}
            ri = raw.get("rqgInfo") if isinstance(raw.get("rqgInfo"), dict) else {}
            body = _format_rqg_info_compact(ri)
            if not body:
                continue
            wrote = True
            lines.append(lk)
            lines.extend(body)
            lines.append("")
    if not wrote:
        ri = payload.get("rqgInfo") if isinstance(payload.get("rqgInfo"), dict) else {}
        body = _format_rqg_info_compact(ri)
        if body:
            lines.extend(body)
            lines.append("")
        else:
            return ""

    return "\n".join(lines).rstrip() + "\n"


def trigger_rqg_button(jira_service, release_key: str, button_name: Optional[str] = None) -> Dict:
    """Проверяет RQG: по умолчанию comalarest+linkedIssues как в Jira, иначе /rest/release/1/qgm."""
    safe_release = (release_key or "").strip().upper()
    fetch = getattr(jira_service, "get_official_rqg_bundle", None)
    if callable(fetch):
        ok, message, payload = fetch(safe_release)
        label = "RQG"
    else:
        ok, message, payload = jira_service.get_qgm_status(safe_release)
        label = "QGM"
    return {
        "success": ok,
        "release_key": safe_release,
        "transition_name": label,
        "message": message,
        "qgm_payload": payload or {},
    }


def format_rqg_report(result: Dict) -> str:
    if not result.get("success"):
        return f"❌ RQG: {result.get('message', 'Неизвестная ошибка')}"

    lines: List[str] = []
    lines.append("=" * 80)
    lines.append(f"🛡 RQG ОТЧЕТ: {result['release_key']}")
    lines.append("=" * 80)
    lines.append(f"Story проверено: {result['total_stories']}")
    lines.append(f"✅ Пройдено: {result['passed_stories']}")
    lines.append(f"❌ Не пройдено: {result['failed_stories']}")
    lines.append("")

    if result["total_stories"] == 0:
        lines.append(
            "⚠️ Story для эвристики ЦО/ИФТ/дистрибутив не найдены "
            "(проверь связи «consists of» / обход графа). Официальный RQG — в блоке выше."
        )
        return "\n".join(lines)

    for story in result["story_results"]:
        mark = "✅" if story["ok"] else "❌"
        lines.append(f"{mark} {story['story_key']} — {_short(story['story_summary'])}")
        lines.append(f"   ЦО: {'OK' if story['co_ok'] else 'FAIL'} | ИФТ: {'OK' if story['ift_ok'] else 'FAIL'} | Дистрибутив: {'OK' if story['distribution_ok'] else 'FAIL'}")
        if not story["co_ok"]:
            lines.append("   - ЦО: не найдено или статус не соответствует")
        if not story["ift_ok"]:
            lines.append("   - ИФТ: не найдено или статус не соответствует")
        if not story["distribution_ok"]:
            lines.append("   - Дистрибутив: не найдено вложение/связанный элемент с допустимым статусом")
        lines.append("")

    lines.append("Примечание:")
    lines.append("- Правила RQG можно настроить через .env (RQG_*).")
    lines.append("=" * 80)
    return "\n".join(lines)


def _short(text: str, limit: int = 70) -> str:
    if len(text or "") <= limit:
        return text or ""
    return f"{text[:limit - 3]}..."


def run_rqg_check(
    jira_service,
    release_key: str,
    max_depth: int = 2,
    trigger_button: bool = True,
    button_name: Optional[str] = None,
) -> str:
    lines: List[str] = []

    if trigger_button:
        trigger_result = trigger_rqg_button(jira_service, release_key, button_name=button_name)
        if trigger_result["success"]:
            lines.append(
                f"✅ Данные RQG получены: {trigger_result['release_key']}"
            )
        else:
            lines.append(
                f"⚠️ RQG endpoint не выполнен "
                f"('{trigger_result['transition_name']}'): {trigger_result['message']}"
            )
            lines.append("   Анализ продолжен автоматически, но RQG endpoint вернул ошибку.")
        lines.append("")
        block = format_official_rqg_payload_block(
            trigger_result.get("qgm_payload") if isinstance(trigger_result.get("qgm_payload"), dict) else None
        )
        if block.strip():
            lines.append(block)

    result = analyze_rqg_for_release(jira_service=jira_service, release_key=release_key, max_depth=max_depth)
    lines.append(format_rqg_report(result))
    return "\n".join(lines)
