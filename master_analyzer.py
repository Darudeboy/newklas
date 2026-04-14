"""
Анализ PR в master по релизу и генерация Deploy plan в Confluence.
Совместимо с UI: ConfluenceDeployPlanGenerator(url, token, template_page_id),
MasterServicesAnalyzer(jira_service, confluence_generator).
"""
from __future__ import annotations

import html
import logging
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


def _repo_from_pr_url(url: str, title: str = "") -> str:
    """Извлекает имя репозитория/сервиса из URL PR."""
    u = (url or "").strip()
    if not u:
        t = (title or "").strip()
        return t[:120] if t else "unknown"
    low = u.lower()
    if "bitbucket" in low or "/scm/" in low or "stash" in low:
        m = re.search(r"/repos/([^/]+)/", u, re.IGNORECASE)
        if m:
            return m.group(1)
        m = re.search(r"/projects/[^/]+/repos/([^/]+)", u, re.IGNORECASE)
        if m:
            return m.group(1)
    if "github.com" in low or "gitlab" in low:
        m = re.search(r"[/:]([^/]+)/([^/]+?)(?:\.git)?(?:/|$)", u)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
    return u.split("/")[-1][:80] or "repo"


def _is_story_or_bug(issue_type: str) -> bool:
    n = (issue_type or "").strip().lower()
    return n in {"story", "bug", "история", "дефект"}


def _is_master_like_branch(branch_name: str) -> bool:
    n = (branch_name or "").strip().lower()
    return n.endswith("/master") or n in {"master", "main"} or n.endswith("/main")


class ConfluenceDeployPlanGenerator:
    """Создание/обновление страницы Deploy plan в Confluence."""

    def __init__(
        self,
        confluence_url: str,
        confluence_token: str,
        template_page_id: str,
        verify_ssl: bool = False,
    ):
        self.confluence_url = (confluence_url or "").rstrip("/")
        self.confluence_token = confluence_token or ""
        self.template_page_id = (template_page_id or "").strip()
        self.verify_ssl = verify_ssl
        self._confluence: Any = None
        self._template_storage_cache: Optional[str] = None
        self._template_labels_cache: Optional[List[str]] = None
        self._template_loaded: bool = False

    def _client(self) -> Any:
        if self._confluence is not None:
            return self._confluence
        if not self.confluence_url or not self.confluence_token:
            raise ValueError("CONFLUENCE_URL и CONFLUENCE_TOKEN обязательны")
        from atlassian import Confluence

        self._confluence = Confluence(
            url=self.confluence_url,
            token=self.confluence_token,
            verify_ssl=self.verify_ssl,
        )
        return self._confluence

    def _get_template_storage_and_labels(self) -> tuple[Optional[str], Optional[List[str]]]:
        """
        Загружает body.storage и labels из страницы-конфлюэнс-шаблона.
        Кешируется, чтобы не долбить API при каждом update.
        """
        if self._template_loaded:
            return self._template_storage_cache, self._template_labels_cache

        self._template_loaded = True
        if not self.template_page_id:
            return None, None

        try:
            cf = self._client()
            pid_raw = self.template_page_id
            pid: Any = int(pid_raw) if pid_raw.isdigit() else pid_raw

            page_by_id = getattr(cf, "page_by_id", None) or getattr(cf, "get_page_by_id", None)
            if not callable(page_by_id):
                logger.warning(
                    "Confluence: нет метода page_by_id/get_page_by_id — нельзя загрузить шаблон %s",
                    self.template_page_id,
                )
                return None, None

            # atlassian-python-api обычно возвращает body.storage.value + metadata.labels
            tpl = page_by_id(
                pid,
                expand="body.storage,metadata.labels",
            )
            if not isinstance(tpl, dict):
                return None, None

            storage = (
                (tpl.get("body") or {}).get("storage", {}).get("value")
                if isinstance(tpl.get("body"), dict)
                else None
            )
            labels_raw = (tpl.get("metadata") or {}).get("labels") if isinstance(tpl.get("metadata"), dict) else None
            labels: Optional[List[str]] = None
            if isinstance(labels_raw, list):
                # Иногда labels приходят как [{"prefix":"global","label":"..."}]; иногда строками.
                tmp: List[str] = []
                for item in labels_raw:
                    if isinstance(item, str):
                        tmp.append(item)
                    elif isinstance(item, dict):
                        lbl = item.get("label") or item.get("name")
                        if isinstance(lbl, str) and lbl.strip():
                            tmp.append(lbl.strip())
                labels = tmp or None

            self._template_storage_cache = storage
            self._template_labels_cache = labels
            return storage, labels
        except Exception as e:
            logger.warning("Не удалось загрузить template_page_id=%s: %s", self.template_page_id, e)
            return None, None

    def generate_deploy_plan(
        self,
        analysis_result: Dict[str, Any],
        space_key: str,
        parent_page_title: str,
        team_name: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Создаёт или обновляет страницу Deploy plan в Confluence.

        Методу необходимо быть внутри ConfluenceDeployPlanGenerator.
        """
        try:
            cf = self._client()
        except Exception as e:
            return {"success": False, "message": str(e), "details": ""}

        rk = (analysis_result.get("release_key") or "").strip().upper()
        summary_raw = str(analysis_result.get("release_summary") or "N/A")
        summary = html.escape(summary_raw)
        services: List[str] = list(analysis_result.get("services") or [])
        team = html.escape(str(team_name or ""))
        space = (space_key or "").strip()

        if not rk:
            return {"success": False, "message": "Нет release_key в analysis_result", "details": ""}
        if not space:
            return {"success": False, "message": "Не указан space_key", "details": ""}

        page_title = f"[{rk}] Deploy plan"

        release_date_iso = extract_release_date_iso(summary_raw)
        release_date_human = format_ru_date(release_date_iso) if release_date_iso else ""

        # Rows for template tables where the column "Компонент" must contain service name.
        install_rows_html = build_component_table_rows(
            services,
            team_label="Команда",
            default_work="Update+migration+deploy",
            date_text=release_date_human or release_date_iso or "",
        )
        rollback_rows_html = build_component_table_rows(
            services,
            team_label="Команда",
            default_work="откат на предыдущую стабильную версию",
            date_text=release_date_human or release_date_iso or "",
        )

        # Preserve Confluence template structure by merging into template storage when possible.
        body = ""
        tpl_storage, tpl_labels = self._get_template_storage_and_labels()
        if isinstance(tpl_storage, str) and tpl_storage:
            merged = merge_deploy_plan_into_template_storage(
                tpl_storage,
                release_key=rk,
                install_rows_html=install_rows_html,
                rollback_rows_html=rollback_rows_html,
            )
            if isinstance(merged, str) and merged.strip():
                body = merged

        # Fallback: generate full body.
        if not body:
            # Template missing/unavailable: render minimal in the expected column layout.
            body = (
                f"<h2>Релиз</h2>\n"
                f"<ac:structured-macro ac:name=\"jira\"><ac:parameter ac:name=\"key\">{html.escape(rk)}</ac:parameter></ac:structured-macro>\n"
                f"<h2>План установки</h2>\n"
                f"<table><thead><tr>"
                f"<th></th><th>Команда</th><th>Компонент</th><th>Работы</th><th>Дата и время начала</th><th>Примечания</th>"
                f"</tr></thead><tbody>{install_rows_html}</tbody></table>\n"
                f"<h2>План отката</h2>\n"
                f"<table><thead><tr>"
                f"<th></th><th>Команда</th><th>Компонент</th><th>Работы</th><th>Дата и время начала</th><th>Примечания</th>"
                f"</tr></thead><tbody>{rollback_rows_html}</tbody></table>\n"
            ).strip()

        parent_id: Optional[str] = None
        if parent_page_title:
            try:
                parent = cf.get_page_by_title(space, parent_page_title)
                if parent and isinstance(parent, dict):
                    parent_id = str(parent.get("id", "")) or None
            except Exception as e:
                logger.warning(
                    "Не найдена родительская страница %s: %s", parent_page_title, e
                )

        try:
            existing = cf.get_page_by_title(
                space, page_title, expand="body.storage"
            )
            if existing and isinstance(existing, dict):
                pid = existing["id"]
                cf.update_page(
                    pid,
                    page_title,
                    body,
                    representation="storage",
                    minor_edit=False,
                )
                self._ensure_labels(cf, pid, tpl_labels)
                page_url = f"{self.confluence_url}/pages/viewpage.action?pageId={pid}"
                return {
                    "success": True,
                    "page_url": page_url,
                    "page_title": page_title,
                    "message": "Страница обновлена",
                }

            create_kw: Dict[str, Any] = {
                "space": space,
                "title": page_title,
                "body": body,
                "representation": "storage",
            }
            # Best-effort: preserve labels from template when API supports it.
            if tpl_labels:
                create_kw["labels"] = tpl_labels
            if parent_id:
                create_kw["parent_id"] = parent_id

            new_page = cf.create_page(**create_kw)
            if not new_page or not isinstance(new_page, dict):
                return {
                    "success": False,
                    "message": "Confluence не вернул данные страницы",
                    "details": "",
                }
            pid = new_page.get("id")
            self._ensure_labels(cf, pid, tpl_labels)
            page_url = f"{self.confluence_url}/pages/viewpage.action?pageId={pid}"
            return {
                "success": True,
                "page_url": page_url,
                "page_title": page_title,
                "message": "Страница создана",
            }
        except Exception as e:
            logger.exception("Confluence deploy plan: %s", e)
            return {
                "success": False,
                "message": str(e),
                "details": getattr(e, "response", b"")[:500]
                if hasattr(e, "response")
                else "",
            }

    def _ensure_labels(self, cf: Any, page_id: Any, labels: Optional[List[str]]) -> None:
        """
        Some Confluence APIs ignore `labels=` on create_page; also labels can be absent on template.
        Best-effort: ensure each template label is set on the target page.
        """
        if not page_id or not labels:
            return
        set_label = getattr(cf, "set_page_label", None)
        if not callable(set_label):
            return
        for lbl in labels:
            if isinstance(lbl, str) and lbl.strip():
                try:
                    set_label(page_id, lbl.strip())
                except Exception:
                    pass


def replace_section_by_anchor(
    storage: str,
    *,
    anchor_start_regex: str,
    anchor_end_regex: str,
    new_section: str,
) -> tuple[str, bool]:
    """
    Замена секции в storage по диапазону между anchor_start_regex и anchor_end_regex.
    Если якоря не найдены — storage возвращается как есть, success=False.
    """
    if not isinstance(storage, str) or not storage:
        return storage, False

    # DOTALL + ленивый квантификатор: заменяем ровно один диапазон между стартом и концом.
    pattern = re.compile(
        rf"({anchor_start_regex}).*?({anchor_end_regex})",
        flags=re.DOTALL | re.IGNORECASE,
    )
    m = pattern.search(storage)
    if not m:
        return storage, False

    replaced = pattern.sub(r"\1" + new_section + r"\2", storage, count=1)
    return replaced, True


def build_component_table_rows(
    services: List[str],
    *,
    team_label: str = "Команда",
    default_work: str = "Update+migration+deploy",
    date_text: str = "",
) -> str:
    """
    Генерирует <tr> строки для таблицы шаблона Deploy plan.
    Ожидаемый формат колонок (как на эталонном скрине):
    [#] [Команда] [Компонент] [Работы] [Дата и время начала] [Примечания]
    """
    rows: List[str] = []
    safe_team = html.escape(team_label or "Команда")
    safe_work = html.escape(default_work or "")
    safe_date = html.escape(date_text or "")
    for i, svc in enumerate(services or [], 1):
        component = html.escape(str(svc))
        rows.append(
            "<tr>"
            f"<td>{i}</td>"
            f"<td>{safe_team}</td>"
            f"<td>{component}</td>"
            f"<td>{safe_work}</td>"
            f"<td>{safe_date}</td>"
            "<td></td>"
            "</tr>"
        )
    if not rows:
        rows.append(
            "<tr><td colspan=\"6\">Нет сервисов</td></tr>"
        )
    return "".join(rows)


def extract_release_date_iso(summary_raw: str) -> Optional[str]:
    """
    Extracts YYYY-MM-DD from typical release summary like '... Релиз-2025-02-07 ...'.
    """
    text = (summary_raw or "").strip()
    if not text:
        return None
    m = re.search(r"\b(?:релиз-)?(20\d{2}-\d{2}-\d{2})\b", text, flags=re.IGNORECASE)
    if not m:
        return None
    return m.group(1)


def format_ru_date(iso_yyyy_mm_dd: str) -> Optional[str]:
    """
    Formats '2025-02-07' as '07 февр. 2025 г.' to match Confluence UI convention.
    """
    raw = (iso_yyyy_mm_dd or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.strptime(raw, "%Y-%m-%d").date()
    except Exception:
        return raw
    months = {
        1: "янв.",
        2: "февр.",
        3: "мар.",
        4: "апр.",
        5: "мая",
        6: "июн.",
        7: "июл.",
        8: "авг.",
        9: "сент.",
        10: "окт.",
        11: "нояб.",
        12: "дек.",
    }
    return f"{dt.day:02d} {months.get(dt.month, '')} {dt.year} г.".strip()


def merge_deploy_plan_into_template_storage(
    template_storage: str,
    *,
    release_key: str,
    install_rows_html: str,
    rollback_rows_html: str,
) -> Optional[str]:
    """
    Встраивает данные в template_storage, сохраняя макросы/таблицы шаблона.
    - В блоке «Релиз» оставляем только Jira-макрос (key = release_key).
    - В таблицах «План установки» и «План отката» (колонка «Компонент») заменяем строки (tbody),
      сохраняя заголовки таблиц и прочие макросы шаблона.
    """
    if not template_storage:
        return None

    def _insert_near_top(storage: str, snippet: str) -> str:
        # Try to insert right after the first opening container tag to keep template wrappers.
        m = re.search(r"<(div|body|section)\b[^>]*>", storage, flags=re.IGNORECASE)
        if m:
            i = m.end()
            return storage[:i] + "\n" + snippet + "\n" + storage[i:]
        return snippet + "\n" + storage

    def _replace_or_insert_block_by_heading(
        storage: str,
        *,
        heading_re: re.Pattern[str],
        block_end_re: re.Pattern[str],
        new_block: str,
        insert_after_re: Optional[re.Pattern[str]] = None,
    ) -> tuple[str, bool]:
        """
        Replace a block starting at heading_re until block_end_re.
        If not found, insert new_block either after insert_after_re (if provided) or near top.
        """
        m = heading_re.search(storage)
        if not m:
            if insert_after_re:
                anchor = insert_after_re.search(storage)
                if anchor:
                    i = anchor.end()
                    return storage[:i] + "\n" + new_block + "\n" + storage[i:], False
            return _insert_near_top(storage, new_block), False

        start = m.start()
        after_heading = m.end()
        end_m = block_end_re.search(storage, pos=after_heading)
        end = end_m.start() if end_m else len(storage)
        return storage[:start] + new_block + "\n" + storage[end:], True

    tmp = template_storage

    # 1) Update Jira macro key for the release block: replace the first jira macro key parameter.
    safe_key = html.escape((release_key or "").strip().upper())
    jira_key_re = re.compile(
        r"(?is)(<ac:structured-macro\b[^>]*ac:name=\"jira\"[^>]*>[\s\S]*?<ac:parameter\b[^>]*ac:name=\"key\"[^>]*>)([^<]*)(</ac:parameter>)"
    )
    tmp, n_key = jira_key_re.subn(r"\1" + safe_key + r"\3", tmp, count=1)
    if n_key < 1:
        # If template has no macro at all, insert the minimal release block near top.
        tmp = _insert_near_top(
            tmp,
            f"<h2>Релиз</h2>\n<ac:structured-macro ac:name=\"jira\"><ac:parameter ac:name=\"key\">{safe_key}</ac:parameter></ac:structured-macro>",
        )

    # 2) Replace rows inside tables under headings "План установки" and "План отката".
    table_re = re.compile(r"(?is)<table\b[^>]*>[\s\S]*?</table>")
    component_header_re = re.compile(r"(?is)<th\b[^>]*>\s*компонент\s*</th>")

    def _replace_rows_in_table(table_html: str, rows_html: str) -> Optional[str]:
        m_tbody = re.search(r"(?is)<tbody\b[^>]*>([\s\S]*?)</tbody>", table_html)
        if not m_tbody:
            return None
        tbody_inner = m_tbody.group(1)
        # Keep all leading header rows (<tr> containing <th>).
        all_rows = re.findall(r"(?is)<tr\b[^>]*>[\s\S]*?</tr>", tbody_inner)
        kept: List[str] = []
        for row in all_rows:
            if re.search(r"(?is)<th\b", row):
                kept.append(row)
            else:
                break
        new_inner = "".join(kept) + (rows_html or "")
        return table_html[: m_tbody.start(1)] + new_inner + table_html[m_tbody.end(1) :]

    def _replace_first_component_table_after_heading(storage: str, heading_text: str, rows_html: str) -> tuple[str, bool]:
        # Find heading and then first table with component header after it.
        heading_re = re.compile(r"(?is)<h2\b[^>]*>\s*" + re.escape(heading_text) + r"\s*</h2>")
        m_head = heading_re.search(storage)
        start_pos = m_head.end() if m_head else 0
        for m_tbl in table_re.finditer(storage, pos=start_pos):
            tbl = m_tbl.group(0)
            if not component_header_re.search(tbl):
                continue
            replaced = _replace_rows_in_table(tbl, rows_html)
            if not replaced:
                continue
            new_storage = storage[: m_tbl.start()] + replaced + storage[m_tbl.end() :]
            return new_storage, True
        return storage, False

    out = tmp
    out, ok_install = _replace_first_component_table_after_heading(out, "План установки", install_rows_html)
    out, ok_rollback = _replace_first_component_table_after_heading(out, "План отката", rollback_rows_html)

    # If headings weren't found, fall back to replacing the first and second component tables in the page.
    if not ok_install or not ok_rollback:
        component_tables: List[tuple[int, int, str]] = []
        for m_tbl in table_re.finditer(out):
            tbl = m_tbl.group(0)
            if component_header_re.search(tbl):
                component_tables.append((m_tbl.start(), m_tbl.end(), tbl))
        if component_tables:
            if not ok_install and len(component_tables) >= 1:
                s, e, tbl = component_tables[0]
                repl = _replace_rows_in_table(tbl, install_rows_html)
                if repl:
                    out = out[:s] + repl + out[e:]
                    ok_install = True
            if not ok_rollback and len(component_tables) >= 2:
                s, e, tbl = component_tables[1]
                repl = _replace_rows_in_table(tbl, rollback_rows_html)
                if repl:
                    out = out[:s] + repl + out[e:]
                    ok_rollback = True

    if not ok_install:
        fallback_install = (
            "<h2>План установки</h2>\n"
            "<table><thead><tr>"
            "<th></th><th>Команда</th><th>Компонент</th><th>Работы</th><th>Дата и время начала</th><th>Примечания</th>"
            "</tr></thead><tbody>"
            + (install_rows_html or "")
            + "</tbody></table>"
        )
        out = _insert_near_top(out, fallback_install)
    if not ok_rollback:
        fallback_rb = (
            "<h2>План отката</h2>\n"
            "<table><thead><tr>"
            "<th></th><th>Команда</th><th>Компонент</th><th>Работы</th><th>Дата и время начала</th><th>Примечания</th>"
            "</tr></thead><tbody>"
            + (rollback_rows_html or "")
            + "</tbody></table>"
        )
        out = _insert_near_top(out, fallback_rb)

    return out


class MasterServicesAnalyzer:
    """Собирает PR по Story/Bug релиза; сервисы = репозитории из merged PR в master."""

    def __init__(self, jira_service: Any, confluence_generator: ConfluenceDeployPlanGenerator):
        self.jira_service = jira_service
        self.confluence_generator = confluence_generator

    def analyze_release(self, release_key: str) -> Dict[str, Any]:
        from release_pr_status import _collect_prs_deep

        rk = (release_key or "").strip().upper()
        if not rk:
            return {
                "success": False,
                "message": "Не указан ключ релиза",
                "release_key": "",
                "release_summary": "",
                "total_tasks": 0,
                "total_prs": 0,
                "services": [],
                "pr_details": [],
            }

        release = self.jira_service.get_issue_details(rk)
        if not release:
            return {
                "success": False,
                "message": f"Релиз {rk} не найден",
                "release_key": rk,
                "release_summary": "",
                "total_tasks": 0,
                "total_prs": 0,
                "services": [],
                "pr_details": [],
            }

        rel_summary = str(
            release.get("fields", {}).get("summary", "") or ""
        )
        linked = self.jira_service.get_linked_issues(rk)
        if not linked:
            return {
                "success": True,
                "message": "В релизе нет связанных задач",
                "release_key": rk,
                "release_summary": rel_summary,
                "total_tasks": 0,
                "total_prs": 0,
                "services": [],
                "pr_details": [],
            }

        total_tasks = 0
        all_prs: List[Dict[str, str]] = []
        pr_details: List[Dict[str, str]] = []
        services_ordered: List[str] = []
        seen_svc: Set[str] = set()

        for key in linked:
            issue = self.jira_service.get_issue_details(key)
            if not issue:
                continue
            itype = str(
                issue.get("fields", {}).get("issuetype", {}).get("name", "")
            )
            if not _is_story_or_bug(itype):
                continue
            total_tasks += 1
            prs = _collect_prs_deep(self.jira_service, key)
            all_prs.extend(prs)

            for pr in prs:
                status = (pr.get("status") or "").strip()
                if status != "Merged":
                    continue
                src = pr.get("source", "")
                target = pr.get("target_branch") or ""
                if src == "dev-status" and target and not _is_master_like_branch(
                    target
                ):
                    continue
                url = pr.get("url", "") or ""
                title = pr.get("title", "") or ""
                svc = _repo_from_pr_url(url, title)
                if not svc or svc == "unknown":
                    continue
                pr_details.append(
                    {
                        "issue": key,
                        "service": svc,
                        "status": "merged_to_master",
                    }
                )
                if svc not in seen_svc:
                    seen_svc.add(svc)
                    services_ordered.append(svc)

        msg = (
            f"Задач Story/Bug: {total_tasks}, PR (всего собрано): {len(all_prs)}, "
            f"в master (merged): {len(services_ordered)} сервисов"
        )
        return {
            "success": True,
            "message": msg,
            "release_key": rk,
            "release_summary": rel_summary,
            "total_tasks": total_tasks,
            "total_prs": len(all_prs),
            "services": services_ordered,
            "pr_details": pr_details,
        }

    def generate_deploy_plan(
        self,
        analysis_result: Optional[Dict[str, Any]] = None,
        space_key: str = "",
        parent_page_title: str = "",
        team_name: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        data = analysis_result or kwargs.get("analysis_result") or {}
        return self.confluence_generator.generate_deploy_plan(
            data,
            space_key=space_key or kwargs.get("space_key", ""),
            parent_page_title=parent_page_title
            or kwargs.get("parent_page_title", ""),
            team_name=team_name or kwargs.get("team_name", ""),
        )
