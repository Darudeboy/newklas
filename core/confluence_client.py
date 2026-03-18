"""
Клиент Confluence. Минимальная обёртка.
Если в старом проекте Confluence используется только в bt3.py (JiraConfluenceSync),
здесь — тонкий слой или TODO для будущей интеграции.
"""
import logging
from typing import Any, Dict, List, Optional

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
