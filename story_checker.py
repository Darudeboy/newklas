"""
Проверка Story в составе релиза по правилам story_requirements.md
(соответствует логике scripts/release_checker.py на 23.10.2026).

Связи: consist of / is part of / consists of.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from core.types import is_jira_story_issue_type
from release_pr_status import _collect_prs_from_issue

# --- Поля Jira (из требований) ---
FIELD_NEW_FUNC = "customfield_24000"
FIELD_NEED_NT = "customfield_18400"
FIELD_EPIC_LINK = "customfield_10006"
FIELD_REQUIREMENTS = "customfield_21100"
FIELD_ARCH_CHANGES = "customfield_23700"
FIELD_STORY_POINTS = "customfield_10002"

CONTOUR_LABELS = {"web", "back", "mobile"}
YES_NO = {"да", "нет", "yes", "no"}

CLOSED_TASK_STATUSES = {
    "closed",
    "закрыта",
    "закрыто",
    "resolved",
    "решена",
    "решено",
    "cancelled",
    "отменён",
    "отменен",
}
CLOSED_ARCH_STATUSES = CLOSED_TASK_STATUSES | {
    "done",
    "готово",
    "выполнено",
}
UAT_OR_DONE = {"ready for uat", "uat", "done", "готово", "выполнено"}

MOBILE_CE_CODES = {
    "CI02257858",  # HRP-ios
    "CI02935717",  # HRP-Android
    "CI03521872",  # HRP.iOS МП.МП-iPAD
    "CI06355438",  # HRP. SberTab
}

ALLOWED_TESTERS = {
    "Абдуллаев Магомедэмин Шамильевич",
    "Годунова Дарья Алексеевна",
    "Гулиев Руслан Иса оглы",
    "Калашников Андрей Романович",
    "Канаев Леонид Олегович",
    "Меркуленков Дмитрий Игоревич",
    "Лакутин Роман Денисович",
    "Метляев Игорь Андреевич",
    "Петрунин Никита Анатольевич",
    "Приколотина Евгения Александровна",
    "Симиник Даниил Григорьевич",
    "Федоров Никита Андреевич",
    "Чиж Мария Михайловна",
    "Синица Захар Алексеевич",
    "Абдулгалимов Гамзат Абусуньянович",
}

WORKLOG_EXEMPT_TESTERS = {
    "Метляев Игорь Андреевич",
    "Никонов Александр Алексеевич",
}

ALLOWED_ARCHITECTURE_CLOSERS = {
    "Черешнев Антон Олегович",
    "Абдуллин Нурали Нуриевич",
    "Базаева Тамара Виталиевна",
    "Калашникова Екатерина Рашидовна",
    "Куданов Александр Андреевич",
    "Куренков Николай Николаевич",
    "Матвеев Антон Анатольевич",
    "Махмудов Джамбулат Рамизович",
    "Абдуллаев Магомед Русланович",
    "Плохотнюк Анна Дмитриевна",
}

TEST_TIME_LIMITS_DAYS = {
    "HRM": 6.9,
    "HRC": 6.9,
    "SFILE": 6.9,
    "NEUROUI": 6.325,
    "HRPPA": 4.14,
    "PERFREVIEW": 5.98,
    "HRPASSIST": 11.5,
}

TEST_STATUSES_FOR_TIME = {
    "ready for ift",
    "ift",
    "ready for uat",
    "uat",
}


def _norm(text: Any) -> str:
    return str(text or "").strip().lower()


def _display_name(person: Any) -> str:
    if isinstance(person, dict):
        return str(
            person.get("displayName")
            or person.get("name")
            or person.get("key")
            or ""
        ).strip()
    return str(person or "").strip()


def _field_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        for key in ("value", "name", "displayName", "key", "label", "id"):
            if value.get(key) not in (None, ""):
                return str(value.get(key)).strip()
        return str(value)
    if isinstance(value, list):
        parts = [_field_text(v) for v in value]
        return ", ".join(p for p in parts if p)
    return str(value).strip()


def _has_http_link(text: str) -> bool:
    return bool(re.search(r"https?://\S+", text or "", re.IGNORECASE))


def _labels(fields: dict) -> Set[str]:
    raw = fields.get("labels") or []
    return {_norm(x) for x in raw if x}


def _issue_type_name(issue: dict) -> str:
    return str(
        (issue.get("fields") or {}).get("issuetype", {}).get("name") or ""
    ).strip()


def _issue_status_name(issue: dict) -> str:
    return str(
        (issue.get("fields") or {}).get("status", {}).get("name") or ""
    ).strip()


def _project_key(issue: dict) -> str:
    fields = issue.get("fields") or {}
    project = fields.get("project") or {}
    key = str(project.get("key") or "").strip().upper()
    if key:
        return key
    issue_key = str(issue.get("key") or "")
    if "-" in issue_key:
        return issue_key.split("-", 1)[0].upper()
    return ""


def _is_task_type(issue_type: str) -> bool:
    n = _norm(issue_type)
    return n in {"task", "задача"}


def _link_type_blob(link: dict) -> str:
    lt = link.get("type") or {}
    return " ".join(
        [
            str(lt.get("name") or ""),
            str(lt.get("inward") or ""),
            str(lt.get("outward") or ""),
        ]
    ).lower()


def _is_consist_of_link(link: dict) -> bool:
    blob = _link_type_blob(link)
    return (
        "consist" in blob
        or "is part of" in blob
        or "является частью" in blob
        or "состоит из" in blob
    )


def _linked_keys_by_consist(issue: dict) -> List[str]:
    keys: List[str] = []
    for link in (issue.get("fields") or {}).get("issuelinks") or []:
        if not _is_consist_of_link(link):
            continue
        for side in ("outwardIssue", "inwardIssue"):
            rel = link.get(side) or {}
            key = rel.get("key")
            if key:
                keys.append(str(key).strip().upper())
    return list(dict.fromkeys(keys))


def _find_ce_values(fields: dict, field_name_map: Dict[str, str]) -> List[str]:
    """Ищет значения КЭ по имени поля (КЭ / CI / конфигурацион)."""
    found: List[str] = []
    for field_id, name in (field_name_map or {}).items():
        n = _norm(name)
        if not (
            n == "кэ"
            or n.startswith("кэ ")
            or "конфигурацион" in n
            or n in {"ci", "кэ релиза", "конфигурационные единицы"}
        ):
            continue
        raw = fields.get(field_id)
        if raw in (None, "", [], {}):
            continue
        text = _field_text(raw)
        if text:
            found.extend([p.strip() for p in re.split(r"[,;\n]+", text) if p.strip()])
        if isinstance(raw, list):
            for item in raw:
                code = ""
                if isinstance(item, dict):
                    code = str(
                        item.get("key")
                        or item.get("value")
                        or item.get("name")
                        or ""
                    ).strip()
                else:
                    code = str(item).strip()
                if code and code not in found:
                    found.append(code)
    # Часто КЭ кодируются как CI######## — подхватим и из любых customfield списков
    if not found:
        for key, raw in fields.items():
            if not str(key).startswith("customfield_"):
                continue
            blob = _field_text(raw)
            for m in re.findall(r"\bCI\d{5,}\b", blob, flags=re.IGNORECASE):
                if m.upper() not in {x.upper() for x in found}:
                    found.append(m.upper())
    return found


def _requirements_blob(fields: dict) -> str:
    return _field_text(fields.get(FIELD_REQUIREMENTS))


def _section_fixed_with_link(blob: str, section_keywords: List[str]) -> bool:
    """Ищет в блоке требований секцию со статусом «Зафиксировано» и ссылкой."""
    text = blob or ""
    if not text:
        return False
    low = text.lower()
    for kw in section_keywords:
        idx = low.find(kw.lower())
        if idx < 0:
            continue
        window = text[idx : idx + 500]
        if "зафиксировано" in window.lower() and _has_http_link(window):
            return True
    # fallback: весь блок
    if any(kw.lower() in low for kw in section_keywords):
        return "зафиксировано" in low and _has_http_link(text)
    return False


def _architecture_status(blob: str) -> str:
    low = (blob or "").lower()
    if "не меняется" in low:
        return "unchanged"
    if "утверждена" in low or "утверждено" in low:
        return "approved"
    return "unknown"


def _arch_changes_values(fields: dict) -> List[str]:
    raw = fields.get(FIELD_ARCH_CHANGES)
    if raw is None:
        return []
    if isinstance(raw, list):
        return [_field_text(x) for x in raw if _field_text(x)]
    text = _field_text(raw)
    return [text] if text else []


def _first_uat_or_done_time(histories: List[dict]) -> Optional[datetime]:
    first: Optional[datetime] = None
    for hist in histories or []:
        created = hist.get("created")
        try:
            ts = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
        except Exception:
            continue
        for item in hist.get("items") or []:
            if _norm(item.get("field")) != "status":
                continue
            to_s = _norm(item.get("toString"))
            if to_s in UAT_OR_DONE:
                if first is None or ts < first:
                    first = ts
    return first


def _field_changed_after(
    histories: List[dict], field_ids: Set[str], after: datetime
) -> bool:
    for hist in histories or []:
        created = hist.get("created")
        try:
            ts = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
        except Exception:
            continue
        if ts <= after:
            continue
        for item in hist.get("items") or []:
            fid = str(item.get("fieldId") or item.get("field") or "")
            if fid in field_ids or _norm(item.get("field")) in {
                _norm(x) for x in field_ids
            }:
                return True
            # Jira иногда пишет человекочитаемое имя
            fname = _norm(item.get("field"))
            if "требован" in fname or "архитектурн" in fname:
                return True
    return False


def _subtasks(issue: dict) -> List[dict]:
    return list((issue.get("fields") or {}).get("subtasks") or [])


def _author_of_last_close(
    jira_service, sub_key: str, allowed_statuses: Set[str]
) -> Tuple[bool, str]:
    histories = jira_service.get_issue_changelog(sub_key)
    last_author = ""
    last_ts: Optional[datetime] = None
    for hist in histories or []:
        created = hist.get("created")
        try:
            ts = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
        except Exception:
            ts = None
        author = _display_name(hist.get("author"))
        for item in hist.get("items") or []:
            if _norm(item.get("field")) != "status":
                continue
            to_s = _norm(item.get("toString"))
            if to_s not in allowed_statuses:
                continue
            if last_ts is None or (ts and ts >= last_ts):
                last_ts = ts
                last_author = author
    return bool(last_author), last_author


def _tester_comments(comments: List[dict]) -> List[str]:
    found: List[str] = []
    allowed_l = {_norm(x) for x in ALLOWED_TESTERS}
    for c in comments or []:
        author = _display_name(c.get("author"))
        if _norm(author) in allowed_l:
            found.append(author)
    # unique preserve order
    out: List[str] = []
    seen: Set[str] = set()
    for name in found:
        key = _norm(name)
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def _has_worklog_by(worklogs: List[dict], author_name: str) -> bool:
    want = _norm(author_name)
    for wl in worklogs or []:
        if _norm(_display_name(wl.get("author"))) == want:
            try:
                if int(wl.get("timeSpentSeconds") or 0) > 0:
                    return True
            except Exception:
                if wl.get("timeSpent"):
                    return True
    return False


def _linked_test_cases(issue: dict) -> List[dict]:
    """Прямые связи на тест-кейсы проекта HRPQA."""
    cases: List[dict] = []
    for link in (issue.get("fields") or {}).get("issuelinks") or []:
        for side in ("outwardIssue", "inwardIssue"):
            rel = link.get(side)
            if not isinstance(rel, dict):
                continue
            key = str(rel.get("key") or "").upper()
            if not key.startswith("HRPQA-"):
                continue
            fields = rel.get("fields") or {}
            itype = str((fields.get("issuetype") or {}).get("name") or "")
            status = str((fields.get("status") or {}).get("name") or "")
            cases.append({"key": key, "type": itype, "status": status, "fields": fields})
    return cases


def _test_case_kind(fields: dict, field_name_map: Dict[str, str]) -> str:
    """Вид тестирования ТК — по имени поля или тексту."""
    for fid, name in (field_name_map or {}).items():
        if "вид тестир" in _norm(name) or _norm(name) == "вид тестирования":
            return _field_text(fields.get(fid))
    blob = " ".join(_field_text(v) for v in fields.values() if v)
    low = blob.lower()
    if "новый функционал" in low:
        return "Новый функционал"
    if "регресс" in low:
        return "Регресс"
    return ""


def _story_has_own_pr(jira_service, story_issue: dict, story_key: str) -> bool:
    """PR должен быть связан с самой Story (не только с дочерней Task)."""
    prs = _collect_prs_from_issue(jira_service, story_issue, story_key)
    return bool(prs)


def _detect_gigacode_usage(prs: List[dict], comments: List[dict]) -> bool:
    blob_parts = []
    for pr in prs or []:
        blob_parts.append(pr.get("title") or "")
        blob_parts.append(pr.get("url") or "")
    for c in comments or []:
        body = c.get("body", "")
        blob_parts.append(body if isinstance(body, str) else str(body))
    blob = " ".join(blob_parts).lower()
    return "gigacode" in blob or "giga code" in blob or "gigachat code" in blob


def _has_aifixed_label(fields: dict) -> bool:
    return "aifixed" in _labels(fields)


def _status_time_days(histories: List[dict], statuses: Set[str]) -> float:
    """Суммарное пребывание в статусах (дни). Упрощённо по парам status→status."""
    events: List[Tuple[datetime, str]] = []
    for hist in histories or []:
        created = hist.get("created")
        try:
            ts = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
        except Exception:
            continue
        for item in hist.get("items") or []:
            if _norm(item.get("field")) != "status":
                continue
            to_s = _norm(item.get("toString"))
            events.append((ts, to_s))
    events.sort(key=lambda x: x[0])
    if not events:
        return 0.0
    total = 0.0
    for i, (ts, status) in enumerate(events):
        if status not in statuses:
            continue
        end = events[i + 1][0] if i + 1 < len(events) else datetime.now(ts.tzinfo)
        total += max((end - ts).total_seconds(), 0) / 86400.0
    return total


def _ok(check_id: str, title: str, detail: str = "") -> Dict[str, Any]:
    return {
        "id": check_id,
        "title": title,
        "ok": True,
        "blocking": True,
        "detail": detail,
    }


def _fail(
    check_id: str,
    title: str,
    detail: str = "",
    *,
    blocking: bool = True,
) -> Dict[str, Any]:
    return {
        "id": check_id,
        "title": title,
        "ok": False,
        "blocking": blocking,
        "detail": detail,
    }


def _warn(check_id: str, title: str, detail: str = "") -> Dict[str, Any]:
    return _fail(check_id, title, detail, blocking=False)


def evaluate_story(
    jira_service,
    story_issue: dict,
    *,
    release_issue: dict,
    release_ce: List[str],
    skip_ce_check: bool,
    field_name_map: Dict[str, str],
    dry_run: bool = True,
) -> Dict[str, Any]:
    story_key = str(story_issue.get("key") or "").upper()
    fields = story_issue.get("fields") or {}
    summary = str(fields.get("summary") or "")
    status = _issue_status_name(story_issue)
    project = _project_key(story_issue)
    release_summary = str(
        (release_issue.get("fields") or {}).get("summary") or ""
    )
    labels = _labels(fields)
    checks: List[Dict[str, Any]] = []

    # 1. Описание
    description = fields.get("description")
    desc_text = _field_text(description)
    if desc_text:
        checks.append(_ok("description", "Описание", "заполнено"))
    else:
        checks.append(_fail("description", "Описание", "пусто"))

    # 2. Контур
    contour = labels & CONTOUR_LABELS
    if contour:
        checks.append(_ok("contour", "Контур", ", ".join(sorted(contour))))
    else:
        checks.append(
            _fail("contour", "Контур", "нет лейбла web/back/mobile")
        )

    # 3. Новая функциональность
    new_func = _norm(_field_text(fields.get(FIELD_NEW_FUNC)))
    if new_func in YES_NO:
        checks.append(_ok("new_func", "Новая функциональность", new_func))
    else:
        checks.append(
            _fail(
                "new_func",
                "Новая функциональность",
                f"ожидается Да/Нет, сейчас: {new_func or 'пусто'}",
            )
        )

    # 4. Требуется НТ
    need_nt = _norm(_field_text(fields.get(FIELD_NEED_NT)))
    if need_nt in YES_NO:
        checks.append(_ok("need_nt", "Требуется НТ", need_nt))
    else:
        checks.append(
            _fail(
                "need_nt",
                "Требуется НТ",
                f"ожидается Да/Нет, сейчас: {need_nt or 'пусто'}",
            )
        )

    # 5. Epic Link
    epic = _field_text(fields.get(FIELD_EPIC_LINK))
    if epic:
        checks.append(_ok("epic", "Epic Link", epic))
    else:
        checks.append(_fail("epic", "Epic Link", "не заполнен"))

    # 6. КЭ
    if skip_ce_check:
        checks.append(_ok("ce", "КЭ", "проверка отключена (mobile-релиз)"))
    else:
        story_ce = _find_ce_values(fields, field_name_map)
        if not story_ce:
            checks.append(_fail("ce", "КЭ", "поле не заполнено"))
        else:
            release_set = {x.upper() for x in release_ce}
            missing = [c for c in story_ce if c.upper() not in release_set]
            if missing and release_set:
                checks.append(
                    _fail(
                        "ce",
                        "КЭ",
                        f"нет в релизе: {', '.join(missing)}",
                    )
                )
            elif not release_set:
                checks.append(
                    _warn(
                        "ce",
                        "КЭ",
                        "КЭ Story заполнены, но КЭ релиза не удалось определить",
                    )
                )
            else:
                checks.append(_ok("ce", "КЭ", ", ".join(story_ce)))

    # 7–9. Блок требований + архитектура
    req_blob = _requirements_blob(fields)
    if _section_fixed_with_link(
        req_blob, ["бизнес-требован", "бизнес требования", "business"]
    ):
        checks.append(_ok("bt", "Бизнес-требования", "Зафиксировано + ссылка"))
    else:
        checks.append(
            _fail(
                "bt",
                "Бизнес-требования",
                "нужно «Зафиксировано» со ссылкой",
            )
        )

    if _section_fixed_with_link(
        req_blob, ["функциональн", "functional", "фр", "fr"]
    ):
        checks.append(
            _ok("fr", "Функциональное решение", "Зафиксировано + ссылка")
        )
    else:
        checks.append(
            _fail(
                "fr",
                "Функциональное решение",
                "нужно «Зафиксировано» со ссылкой",
            )
        )

    arch_status = _architecture_status(req_blob)
    arch_vals = _arch_changes_values(fields)
    arch_vals_low = [_norm(v) for v in arch_vals]
    only_no_impact = arch_vals_low == ["не влияет на архитектуру"] or (
        len(arch_vals_low) == 1 and "не влияет на архитектуру" in arch_vals_low[0]
    )
    has_no_impact = any("не влияет на архитектуру" in v for v in arch_vals_low)
    has_other = any(
        v and "не влияет на архитектуру" not in v for v in arch_vals_low
    )

    if arch_status == "unchanged":
        if only_no_impact or (has_no_impact and not has_other):
            checks.append(
                _ok("architecture", "Архитектура", "Не меняется / не влияет")
            )
        else:
            checks.append(
                _fail(
                    "architecture",
                    "Архитектура",
                    "при «Не меняется» допустимо только «Не влияет на архитектуру»",
                )
            )
    elif arch_status == "approved":
        if _has_http_link(req_blob) and has_other and not has_no_impact:
            checks.append(
                _ok("architecture", "Архитектура", "Утверждена + изменения")
            )
        else:
            checks.append(
                _fail(
                    "architecture",
                    "Архитектура",
                    "нужны ссылка и допустимые изменения без «Не влияет…»",
                )
            )
    else:
        checks.append(
            _fail(
                "architecture",
                "Архитектура",
                "статус не «Не меняется»/«Утверждена» или блок пуст",
            )
        )

    # 10. Срок заполнения требований (после Ready for UAT / UAT / Done)
    histories = jira_service.get_issue_changelog(story_key)
    first_uat = _first_uat_or_done_time(histories)
    if first_uat and _field_changed_after(
        histories, {FIELD_REQUIREMENTS, FIELD_ARCH_CHANGES}, first_uat
    ):
        maturity = _norm(status) in UAT_OR_DONE
        detail = (
            "поля требований/архитектуры менялись после перехода в Ready for UAT/UAT/Done"
        )
        checks.append(_fail("req_freeze", "Срок заполнения требований", detail))
        if maturity:
            checks.append(
                _fail(
                    "maturity_metric",
                    "Метрика зрелости",
                    "изменение требований после UAT влияет на метрику модели зрелости",
                )
            )
    else:
        checks.append(
            _ok(
                "req_freeze",
                "Срок заполнения требований",
                "нарушений не найдено"
                if first_uat
                else "ещё не было перехода в UAT/Done",
            )
        )

    # 11. Сабтаска «Анализ архитектуры»
    arch_sub_ok = False
    arch_sub_detail = "сабтаска не найдена"
    for st in _subtasks(story_issue):
        st_summary = str((st.get("fields") or {}).get("summary") or st.get("summary") or "")
        if _norm(st_summary) != _norm("Анализ архитектуры"):
            continue
        st_key = str(st.get("key") or "")
        if not st_key:
            continue
        st_full = jira_service.get_issue_details(st_key) or st
        st_status = _norm(_issue_status_name(st_full))
        if st_status not in CLOSED_ARCH_STATUSES:
            arch_sub_detail = f"{st_key}: статус {st_status or '?'}"
            continue
        closed_ok, author = _author_of_last_close(
            jira_service, st_key, CLOSED_ARCH_STATUSES
        )
        if closed_ok and _norm(author) in {_norm(x) for x in ALLOWED_ARCHITECTURE_CLOSERS}:
            arch_sub_ok = True
            arch_sub_detail = f"{st_key} закрыл(а) {author}"
            break
        arch_sub_detail = (
            f"{st_key}: закрытие автором «{author or '?'}» не из разрешённого списка"
        )
    if arch_sub_ok:
        checks.append(_ok("arch_subtask", "Анализ архитектуры", arch_sub_detail))
    else:
        checks.append(_fail("arch_subtask", "Анализ архитектуры", arch_sub_detail))

    # 12–13. Комментарий тестировщика + списание времени
    comments = jira_service.get_issue_comments(story_key)
    testers = _tester_comments(comments)
    if testers:
        checks.append(
            _ok("tester_comment", "Комментарий тестировщика", ", ".join(testers))
        )
    else:
        checks.append(
            _fail(
                "tester_comment",
                "Комментарий тестировщика",
                "нет комментария от разрешённого тестировщика",
            )
        )

    story_worklogs = jira_service.get_issue_worklogs(story_key)
    # связанные тестовые Task
    related_keys = _linked_keys_by_consist(story_issue)
    related_worklogs: List[dict] = list(story_worklogs)
    for rk in related_keys:
        rel = jira_service.get_issue_details(rk)
        if not rel:
            continue
        if _is_task_type(_issue_type_name(rel)) and (
            "тест" in _norm((rel.get("fields") or {}).get("summary"))
            or "test" in _norm((rel.get("fields") or {}).get("summary"))
        ):
            related_worklogs.extend(jira_service.get_issue_worklogs(rk))

    missing_wl: List[str] = []
    for tester in testers:
        exempt = _norm(tester) in {_norm(x) for x in WORKLOG_EXEMPT_TESTERS}
        if exempt and project != "HRC":
            continue
        if not _has_worklog_by(related_worklogs, tester):
            missing_wl.append(tester)
    if not testers:
        checks.append(
            _warn("worklog", "Списание времени", "нет тестировщиков для проверки")
        )
    elif missing_wl:
        checks.append(
            _fail(
                "worklog",
                "Списание времени",
                "нет списания у: " + ", ".join(missing_wl),
            )
        )
    else:
        checks.append(_ok("worklog", "Списание времени", "есть у комментировавших"))

    # 14–16. Тест-кейсы HRPQA
    cases = _linked_test_cases(story_issue)
    # если в issuelinks нет полей — догрузим
    enriched: List[dict] = []
    for case in cases:
        full = jira_service.get_issue_details(case["key"]) or {}
        f = full.get("fields") or case.get("fields") or {}
        enriched.append(
            {
                "key": case["key"],
                "status": str((f.get("status") or {}).get("name") or case.get("status") or ""),
                "fields": f,
            }
        )
    if not enriched:
        checks.append(
            _fail(
                "test_cases",
                "Тестовое покрытие",
                "нет прямо связанных ТК из HRPQA",
            )
        )
    else:
        checks.append(
            _ok(
                "test_cases",
                "Тестовое покрытие",
                ", ".join(c["key"] for c in enriched),
            )
        )
        bad_status = [
            c["key"] for c in enriched if _norm(c["status"]) != "approved"
        ]
        if bad_status:
            checks.append(
                _fail(
                    "test_status",
                    "Статусы тест-кейсов",
                    "не Approved: " + ", ".join(bad_status),
                )
            )
        else:
            checks.append(_ok("test_status", "Статусы тест-кейсов", "все Approved"))

        expected_kind = (
            "новый функционал"
            if new_func in {"да", "yes"}
            else "регресс"
            if new_func in {"нет", "no"}
            else ""
        )
        if expected_kind:
            bad_kind: List[str] = []
            for c in enriched:
                kind = _norm(_test_case_kind(c["fields"], field_name_map))
                if expected_kind not in kind:
                    bad_kind.append(f"{c['key']}({kind or '?'})")
            if bad_kind:
                checks.append(
                    _fail(
                        "test_kind",
                        "Вид тестирования ТК",
                        f"ожидалось «{expected_kind}»: " + ", ".join(bad_kind),
                    )
                )
            else:
                checks.append(
                    _ok("test_kind", "Вид тестирования ТК", expected_kind)
                )

    # 17. PR на самой Story (необязательный этап → warning)
    if _story_has_own_pr(jira_service, story_issue, story_key):
        checks.append(_ok("pr", "PR на Story", "найден"))
    else:
        checks.append(
            _warn(
                "pr",
                "PR на Story",
                "PR не связан с самой Story (необязательно)",
            )
        )

    # 18. GigaCode / AIFIXED
    story_prs = _collect_prs_from_issue(jira_service, story_issue, story_key)
    for rk in related_keys:
        rel = jira_service.get_issue_details(rk)
        if rel and _is_task_type(_issue_type_name(rel)):
            story_prs.extend(_collect_prs_from_issue(jira_service, rel, rk))
    used_gc = _detect_gigacode_usage(story_prs, comments)
    if used_gc:
        if _has_aifixed_label(fields):
            checks.append(_ok("aifixed", "GigaCode / AIFIXED", "лейбл есть"))
        else:
            if dry_run:
                checks.append(
                    _fail(
                        "aifixed",
                        "GigaCode / AIFIXED",
                        "обнаружен GigaCode, нужен лейбл AIFIXED (dry-run: не добавляем)",
                    )
                )
            else:
                # best-effort: добавить лейбл через REST
                try:
                    current = list(fields.get("labels") or [])
                    if "AIFIXED" not in current and "aifixed" not in {
                        _norm(x) for x in current
                    }:
                        current.append("AIFIXED")
                        jira_service.jira.put(
                            f"/rest/api/2/issue/{story_key}",
                            data={"fields": {"labels": current}},
                        )
                    checks.append(
                        _ok("aifixed", "GigaCode / AIFIXED", "лейбл добавлен")
                    )
                except Exception as e:
                    checks.append(
                        _fail(
                            "aifixed",
                            "GigaCode / AIFIXED",
                            f"не удалось добавить AIFIXED: {e}",
                        )
                    )
    else:
        checks.append(_ok("aifixed", "GigaCode / AIFIXED", "GigaCode не обнаружен"))

    # Cloud-релиз
    if "cloud" in _norm(release_summary):
        if "пульс_внешний_рынок" in labels:
            checks.append(
                _ok("cloud_label", "Cloud-релиз", "лейбл Пульс_внешний_рынок")
            )
        else:
            checks.append(
                _fail(
                    "cloud_label",
                    "Cloud-релиз",
                    "нужен лейбл Пульс_внешний_рынок",
                )
            )

    # SBRPPL
    if project == "SBRPPL":
        if "пульс_3лица" in labels or "#пульс_3лица" in labels:
            checks.append(_ok("sbrppl_label", "SBRPPL лейбл", "Пульс_3лица"))
        else:
            checks.append(
                _fail(
                    "sbrppl_label",
                    "SBRPPL лейбл",
                    "нужен лейбл #Пульс_3лица",
                )
            )
        sp = fields.get(FIELD_STORY_POINTS)
        if sp is None or sp == "":
            checks.append(_fail("story_points", "Story Points", "не заполнены"))
        else:
            checks.append(_ok("story_points", "Story Points", str(sp)))

    # Task в составе Story
    for rk in related_keys:
        rel = jira_service.get_issue_details(rk)
        if not rel:
            continue
        if not _is_task_type(_issue_type_name(rel)):
            continue
        st = _norm(_issue_status_name(rel))
        if st not in CLOSED_TASK_STATUSES:
            checks.append(
                _fail(
                    f"task_closed_{rk}",
                    f"Task {rk}",
                    f"статус «{_issue_status_name(rel)}» — должна быть закрыта/решена/отменена",
                )
            )
        else:
            checks.append(_ok(f"task_closed_{rk}", f"Task {rk}", "закрыта"))
        if _project_key(rel) == project:
            epic_t = _field_text((rel.get("fields") or {}).get(FIELD_EPIC_LINK))
            if not epic_t:
                checks.append(
                    _fail(
                        f"task_epic_{rk}",
                        f"Epic Link Task {rk}",
                        "обязателен для Task того же проекта",
                    )
                )

    # Время тестирования (неблокирующее)
    limit = TEST_TIME_LIMITS_DAYS.get(project)
    if limit is not None:
        days = _status_time_days(histories, TEST_STATUSES_FOR_TIME)
        if days > limit:
            checks.append(
                _warn(
                    "test_time",
                    "Время тестирования",
                    f"{days:.2f} дн. > предела {limit} (неблокирующе)",
                )
            )
        else:
            checks.append(
                _ok(
                    "test_time",
                    "Время тестирования",
                    f"{days:.2f} дн. (предел {limit})",
                )
            )

    blocking_failed = [c for c in checks if not c["ok"] and c.get("blocking", True)]
    warnings = [c for c in checks if not c["ok"] and not c.get("blocking", True)]
    return {
        "key": story_key,
        "summary": summary,
        "status": status,
        "project": project,
        "ok": not blocking_failed,
        "checks": checks,
        "blocking_failed": len(blocking_failed),
        "warnings": len(warnings),
    }


def _release_is_mobile(release_issue: dict, release_ce: List[str]) -> bool:
    labels = _labels(release_issue.get("fields") or {})
    if "mobile" in labels:
        return True
    ce_up = {c.upper() for c in release_ce}
    return bool(ce_up & MOBILE_CE_CODES)


def _collect_release_stories(jira_service, release_key: str) -> List[str]:
    stories: List[str] = []
    gl = getattr(jira_service, "get_linked_issue_keys_consists_of", None)
    if callable(gl):
        for k in gl(release_key):
            issue = jira_service.get_issue_details(k)
            if issue and is_jira_story_issue_type(_issue_type_name(issue)):
                stories.append(str(k).upper())
    if stories:
        return sorted(set(stories))

    # fallback: все связи + фильтр Story
    for k in jira_service.get_linked_issues(release_key) or []:
        issue = jira_service.get_issue_details(k)
        if issue and is_jira_story_issue_type(_issue_type_name(issue)):
            stories.append(str(k).upper())
    return sorted(set(stories))


def analyze_stories_for_release(
    jira_service,
    release_key: str,
    *,
    dry_run: bool = True,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Dict[str, Any]:
    rk = (release_key or "").strip().upper()
    if not rk:
        return {"success": False, "message": "Не указан ключ релиза"}

    release = jira_service.get_issue_details(rk)
    if not release:
        return {"success": False, "message": f"Релиз {rk} не найден"}

    field_name_map = {}
    if hasattr(jira_service, "get_field_name_map"):
        try:
            field_name_map = jira_service.get_field_name_map() or {}
        except Exception:
            field_name_map = {}

    release_fields = release.get("fields") or {}
    release_ce = _find_ce_values(release_fields, field_name_map)
    skip_ce = _release_is_mobile(release, release_ce)

    story_keys = _collect_release_stories(jira_service, rk)
    if progress_callback:
        progress_callback(0.05, f"Story в составе: {len(story_keys)}")

    results: List[Dict[str, Any]] = []
    total = max(len(story_keys), 1)
    for idx, sk in enumerate(story_keys, start=1):
        issue = jira_service.get_issue_details(
            sk,
            expand="issuelinks,changelog",
        )
        if not issue:
            results.append(
                {
                    "key": sk,
                    "summary": "",
                    "status": "",
                    "ok": False,
                    "checks": [
                        _fail("load", "Загрузка", "не удалось получить задачу")
                    ],
                    "blocking_failed": 1,
                    "warnings": 0,
                }
            )
            continue
        # changelog уже может быть в expand; evaluate тоже запросит при необходимости
        item = evaluate_story(
            jira_service,
            issue,
            release_issue=release,
            release_ce=release_ce,
            skip_ce_check=skip_ce,
            field_name_map=field_name_map,
            dry_run=dry_run,
        )
        results.append(item)
        if progress_callback:
            progress_callback(idx / total, f"Проверена {sk}")

    ok_count = sum(1 for r in results if r.get("ok"))
    fail_count = len(results) - ok_count
    warn_count = sum(int(r.get("warnings") or 0) for r in results)

    return {
        "success": True,
        "release_key": rk,
        "release_summary": str(release_fields.get("summary") or ""),
        "skip_ce_check": skip_ce,
        "stories_total": len(results),
        "stories_ok": ok_count,
        "stories_failed": fail_count,
        "warnings_total": warn_count,
        "stories": results,
    }


def format_story_check_report(report: Dict[str, Any]) -> str:
    if not report.get("success"):
        return f"❌ Ошибка: {report.get('message', 'неизвестная ошибка')}"

    lines: List[str] = []
    lines.append("=" * 80)
    lines.append(f"📋 ПРОВЕРКА STORY: {report.get('release_key', '-')}")
    lines.append("=" * 80)
    if report.get("release_summary"):
        lines.append(report["release_summary"])
    lines.append(
        f"Всего: {report.get('stories_total', 0)} | "
        f"OK: {report.get('stories_ok', 0)} | "
        f"С ошибками: {report.get('stories_failed', 0)} | "
        f"Предупреждений: {report.get('warnings_total', 0)}"
    )
    if report.get("skip_ce_check"):
        lines.append("КЭ: проверка отключена (мобильный релиз)")
    lines.append("")

    stories = report.get("stories") or []
    if not stories:
        lines.append("⚠️ В составе релиза не найдено Story (consist of / is part of).")
        lines.append("=" * 80)
        return "\n".join(lines)

    for story in stories:
        mark = "✅" if story.get("ok") else "❌"
        lines.append(
            f"{mark} {story.get('key')} [{story.get('status') or '?'}] — "
            f"{story.get('summary') or ''}"
        )
        for check in story.get("checks") or []:
            if check.get("ok"):
                icon = "  ✓"
            elif check.get("blocking", True):
                icon = "  ✗"
            else:
                icon = "  !"
            detail = check.get("detail") or ""
            suffix = f" — {detail}" if detail else ""
            lines.append(f"{icon} {check.get('title')}{suffix}")
        lines.append("")

    lines.append("=" * 80)
    return "\n".join(lines)
