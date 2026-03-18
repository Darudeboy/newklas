"""
Конфигурация: Jira, Confluence, release flow.
Загрузка из .env, совместимость со старым проектом.
"""
import os
import json
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class JiraConfig:
    """Конфигурация для подключения к Jira."""

    def __init__(self, url=None, token=None, verify_ssl=False):
        self.url = url or os.getenv("JIRA_URL", "https://jira.sberbank.ru")
        self.token = token or os.getenv("JIRA_TOKEN", "")
        self.verify_ssl = verify_ssl

    @classmethod
    def load_from_file(cls, filepath: str) -> "JiraConfig":
        """Загрузка конфигурации из файла (deprecated, используется .env)."""
        return cls()

    def save_to_file(self, filepath: str) -> None:
        """Сохранение конфигурации в файл."""
        directory = os.path.dirname(filepath)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(
                {"url": self.url, "token": "***HIDDEN***", "verify_ssl": self.verify_ssl},
                f,
                indent=2,
            )


# Confluence
CONFLUENCE_URL = os.getenv("CONFLUENCE_URL", "https://confluence.sberbank.ru")
CONFLUENCE_TOKEN = os.getenv("CONFLUENCE_TOKEN")
CONFLUENCE_SPACE_KEY = os.getenv("CONFLUENCE_SPACE_KEY", "HRTECH")
CONFLUENCE_PARENT_PAGE_TITLE = os.getenv("CONFLUENCE_PARENT_PAGE_TITLE", "deploy plan 2k")
CONFLUENCE_TEMPLATE_PAGE_ID = os.getenv("CONFLUENCE_TEMPLATE_PAGE_ID", "18532011154")
TEAM_NAME = os.getenv("TEAM_NAME", "Команда")

# Release flow
RELEASE_FLOW_HOTFIX_PROJECTS = os.getenv("RELEASE_FLOW_HOTFIX_PROJECTS", "HOTFIX,HF")
RELEASE_FLOW_PROFILE_OVERRIDES = os.getenv("RELEASE_FLOW_PROFILE_OVERRIDES", "")


def validate_config() -> bool:
    """Проверка наличия обязательных параметров."""
    required_vars = {
        "JIRA_TOKEN": os.getenv("JIRA_TOKEN"),
        "CONFLUENCE_TOKEN": CONFLUENCE_TOKEN,
        "CONFLUENCE_TEMPLATE_PAGE_ID": CONFLUENCE_TEMPLATE_PAGE_ID,
    }
    missing = [k for k, v in required_vars.items() if not v]
    if missing:
        logger.error("Отсутствуют обязательные переменные в .env: %s", ", ".join(missing))
        return False
    logger.info("Конфигурация загружена из .env успешно")
    return True
