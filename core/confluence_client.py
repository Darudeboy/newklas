"""
Клиент Confluence. Минимальная обёртка.
Если в старом проекте Confluence используется только в bt3.py (JiraConfluenceSync),
здесь — тонкий слой или TODO для будущей интеграции.
"""
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


class ConfluenceClient:
    """
    Минимальный клиент Confluence.
    TODO: при необходимости перенести сюда логику из bt3.JiraConfluenceSync
    (get_release_links_direct остаётся в Jira; create_page/update_page — сюда).
    """

    def __init__(
        self,
        url: str = "",
        token: str = "",
        space: str = "",
        verify_ssl: bool = False,
    ):
        self.url = url
        self.token = token
        self.space = space
        self.verify_ssl = verify_ssl
        self._client: Any = None
        self._session: Optional[requests.Session] = None

    def ensure_client(self) -> None:
        """Ленивая инициализация Confluence API (atlassian-python-api)."""
        if self._client is not None:
            return
        try:
            from atlassian import Confluence
            self._client = Confluence(
                url=self.url,
                token=self.token,
                verify_ssl=self.verify_ssl,
            )
        except ImportError:
            logger.warning("atlassian-python-api не установлен; Confluence недоступен")
            self._client = None
        except Exception as e:
            logger.error("Ошибка инициализации Confluence: %s", e)
            self._client = None

    def _ensure_session(self) -> Optional[requests.Session]:
        if self._session is not None:
            return self._session
        base = (self.url or "").rstrip("/")
        token = (self.token or "").strip()
        if not base or not token:
            return None
        s = requests.Session()
        # Confluence PAT typically works as Bearer.
        s.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }
        )
        self._session = s
        return self._session

    def _absolute(self, path: str) -> str:
        base = (self.url or "").rstrip("/")
        p = (path or "").strip()
        if not p.startswith("/"):
            p = "/" + p
        return base + p

    def get_content_by_id_expanded(
        self,
        page_id: str,
        *,
        expand: str = "metadata.labels,children.attachment,body.storage,version",
    ) -> Optional[Dict[str, Any]]:
        """
        Возвращает страницу Confluence как /rest/api/content/{id}?expand=...
        (как в approve-job логе: body.storage + labels + attachments + version).
        """
        pid = (page_id or "").strip()
        if not pid:
            return None
        s = self._ensure_session()
        if not s:
            return None
        try:
            url = self._absolute(f"/rest/api/content/{pid}")
            resp = s.get(url, params={"expand": expand}, verify=self.verify_ssl, timeout=30)
            if resp.status_code != 200:
                logger.warning("Confluence content %s: HTTP %s", pid, resp.status_code)
                return None
            data = resp.json()
            return data if isinstance(data, dict) else None
        except Exception as e:
            logger.warning("Confluence content %s: %s", pid, e)
            return None

    def get_comala_status(
        self,
        page_id: str,
        *,
        expand: str = "state",
    ) -> Optional[Dict[str, Any]]:
        """
        Comala status endpoint (как в approve-job): /rest/cw/1/content/{id}/status?expand=state
        """
        pid = (page_id or "").strip()
        if not pid:
            return None
        s = self._ensure_session()
        if not s:
            return None
        try:
            url = self._absolute(f"/rest/cw/1/content/{pid}/status")
            resp = s.get(url, params={"expand": expand}, verify=self.verify_ssl, timeout=30)
            if resp.status_code != 200:
                logger.warning("Comala status %s: HTTP %s", pid, resp.status_code)
                return None
            data = resp.json()
            return data if isinstance(data, dict) else None
        except Exception as e:
            logger.warning("Comala status %s: %s", pid, e)
            return None

    def export_comala_workflow_activity(
        self,
        page_id: str,
    ) -> Optional[str]:
        """
        Экспорт активности workflow (как в approve-job):
        /plugins/adhocworkflows/exportworkflowpageactivity.action?pageId=...

        Возвращает текст (обычно CSV/HTML), либо None.
        """
        pid = (page_id or "").strip()
        if not pid:
            return None
        s = self._ensure_session()
        if not s:
            return None
        try:
            url = self._absolute("/plugins/adhocworkflows/exportworkflowpageactivity.action")
            resp = s.get(url, params={"pageId": pid}, verify=self.verify_ssl, timeout=30)
            if resp.status_code != 200:
                logger.warning("Comala export %s: HTTP %s", pid, resp.status_code)
                return None
            text = resp.text
            return text if isinstance(text, str) and text.strip() else None
        except Exception as e:
            logger.warning("Comala export %s: %s", pid, e)
            return None

    @staticmethod
    def extract_page_id(url: str) -> Optional[str]:
        """
        Достаёт pageId из типовых Confluence URL:
        - ...viewpage.action?pageId=123
        - ...pageId=123
        - /rest/api/content/123
        """
        u = (url or "").strip()
        if not u:
            return None
        m = re.search(r"[?&]pageId=(\d+)", u, flags=re.IGNORECASE)
        if m:
            return m.group(1)
        m = re.search(r"/rest/api/content/(\d+)", u, flags=re.IGNORECASE)
        if m:
            return m.group(1)
        return None

    @staticmethod
    def normalize_labels_from_content(payload: Dict[str, Any]) -> List[str]:
        labels_raw = (payload.get("metadata") or {}).get("labels") if isinstance(payload.get("metadata"), dict) else None
        out: List[str] = []
        if isinstance(labels_raw, list):
            for item in labels_raw:
                if isinstance(item, str) and item.strip():
                    out.append(item.strip())
                elif isinstance(item, dict):
                    name = item.get("label") or item.get("name")
                    if isinstance(name, str) and name.strip():
                        out.append(name.strip())
        return out

    @staticmethod
    def normalize_attachments_from_content(payload: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Возвращает список вложений [{"id": "...", "title": "...", "filename": "..."}]
        из children.attachment.results[].
        """
        children = payload.get("children") or {}
        attach = children.get("attachment") if isinstance(children, dict) else None
        results = attach.get("results") if isinstance(attach, dict) else None
        out: List[Dict[str, str]] = []
        if isinstance(results, list):
            for item in results:
                if not isinstance(item, dict):
                    continue
                out.append(
                    {
                        "id": str(item.get("id", "") or ""),
                        "title": str(item.get("title", "") or ""),
                        "filename": str(item.get("title", "") or ""),
                    }
                )
        return out

    def get_page_by_title(self, space_key: str, title: str) -> Optional[Dict[str, Any]]:
        """Поиск страницы по заголовку в пространстве."""
        self.ensure_client()
        if not self._client:
            return None
        try:
            return self._client.get_page_by_title(space_key, title)
        except Exception as e:
            logger.error("Ошибка get_page_by_title: %s", e)
            return None

    def create_page(
        self,
        space_key: str,
        title: str,
        content: str,
        parent_id: Optional[str] = None,
        representation: str = "storage",
    ) -> Optional[Dict[str, Any]]:
        """Создание страницы."""
        self.ensure_client()
        if not self._client:
            return None
        try:
            return self._client.create_page(
                space_key,
                title,
                content,
                parent_id=parent_id or "",
                representation=representation,
            )
        except Exception as e:
            logger.error("Ошибка create_page: %s", e)
            return None

    def update_page(
        self,
        page_id: str,
        title: str,
        content: str,
        representation: str = "storage",
        minor_edit: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Обновление страницы."""
        self.ensure_client()
        if not self._client:
            return None
        try:
            return self._client.update_page(
                page_id,
                title,
                content,
                representation=representation,
                minor_edit=minor_edit,
            )
        except Exception as e:
            logger.error("Ошибка update_page: %s", e)
            return None
