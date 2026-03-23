"""
Анализ PR в master по релизу и генерация Deploy plan в Confluence.
Совместимо с UI: ConfluenceDeployPlanGenerator(url, token, template_page_id),
MasterServicesAnalyzer(jira_service, confluence_generator).
"""
from __future__ import annotations

import html
import logging
import re
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


def merge_deploy_plan_into_template_storage(
    template_storage: str,
    *,
    release_header_html: str,
    services_section_html: str,
) -> Optional[str]:
    """
    Встраивает две секции в template_storage:
    - <h1>Deploy plan: ...</h1> + блок <p>...Команда...</p>
    - секция <h2>Сервисы (влитые в master)</h2> + таблица + note
    """
    if not template_storage:
        return None

    # 1) Release header: h1 + следующий <p>...</p>
    header_re = re.compile(
        r"<h1>\s*deploy\s*plan\s*:.*?</h1>\s*<p>.*?</p>",
        flags=re.DOTALL | re.IGNORECASE,
    )
    tmp, n1 = header_re.subn(release_header_html, template_storage, count=1)
    if n1 < 1:
        return None

    # 2) Services section: h2.. до note с "Сгенерировано инструментом Blast."
    services_re = re.compile(
        r"<h2>\s*сервисы\s*\(влитые\s*в\s*master\)\s*</h2>.*?"
        r"<p>\s*<em>\s*сгенерировано\s+инструментом\s+blast\.\s*</em>\s*</p>",
        flags=re.DOTALL | re.IGNORECASE,
    )
    services_tmp, n2 = services_re.subn(
        services_section_html, tmp, count=1
    )
    if n2 < 1:
        return None

    return services_tmp

    def generate_deploy_plan(
        self,
        analysis_result: Dict[str, Any],
        space_key: str,
        parent_page_title: str,
        team_name: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Создаёт или обновляет страницу Deploy plan.
        """
        try:
            cf = self._client()
        except Exception as e:
            return {"success": False, "message": str(e), "details": ""}

        rk = (analysis_result.get("release_key") or "").strip().upper()
        summary = html.escape(
            str(analysis_result.get("release_summary") or "N/A")
        )
        services: List[str] = list(analysis_result.get("services") or [])
        team = html.escape(str(team_name or ""))
        space = (space_key or "").strip()

        if not rk:
            return {"success": False, "message": "Нет release_key в analysis_result", "details": ""}
        if not space:
            return {"success": False, "message": "Не указан space_key", "details": ""}

        page_title = f"[{rk}] Deploy plan"

        rows: List[str] = []
        for i, svc in enumerate(services, 1):
            s = html.escape(str(svc))
            rows.append(f"<tr><td>{i}</td><td>{s}</td></tr>")
        table = (
            "<table><thead><tr><th>#</th><th>Сервис / репозиторий</th></tr></thead>"
            f"<tbody>{''.join(rows) if rows else '<tr><td colspan=\"2\">Нет сервисов</td></tr>'}</tbody></table>"
        )

        release_header_html = f"""
<h1>Deploy plan: {html.escape(rk)}</h1>
<p><strong>Релиз:</strong> {html.escape(rk)}<br/>
<strong>Название:</strong> {summary}<br/>
<strong>Команда:</strong> {team}</p>
""".strip()

        services_section_html = f"""
<h2>Сервисы (влитые в master)</h2>
{table}
<p><em>Сгенерировано инструментом Blast.</em></p>
""".strip()

        # Try to preserve the Confluence template structure (labels/macros/wrappers).
        body = ""
        tpl_storage, tpl_labels = self._get_template_storage_and_labels()
        if isinstance(tpl_storage, str) and tpl_storage:
            merged = merge_deploy_plan_into_template_storage(
                tpl_storage,
                release_header_html=release_header_html,
                services_section_html=services_section_html,
            )
            if isinstance(merged, str) and merged.strip():
                body = merged

        # Fallback: current “generate full body” approach.
        if not body:
            body = (release_header_html + "\n" + services_section_html).strip()

        parent_id: Optional[str] = None
        if parent_page_title:
            try:
                parent = cf.get_page_by_title(space, parent_page_title)
                if parent and isinstance(parent, dict):
                    parent_id = str(parent.get("id", "")) or None
            except Exception as e:
                logger.warning("Не найдена родительская страница %s: %s", parent_page_title, e)

        try:
            existing = cf.get_page_by_title(space, page_title, expand="body.storage")
            if existing and isinstance(existing, dict):
                pid = existing["id"]
                cf.update_page(
                    pid,
                    page_title,
                    body,
                    representation="storage",
                    minor_edit=False,
                )
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
            # Best-effort: if API supports labels argument, preserve template labels.
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
                "details": getattr(e, "response", b"")[:500] if hasattr(e, "response") else "",
            }


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
