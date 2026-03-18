"""
Заглушка для совместимости с UI: экспорт JIRA_TOKEN.
Полная логика ArchitectureFieldFixer остаётся в старом проекте при необходимости.
"""
import os
from dotenv import load_dotenv

load_dotenv()
JIRA_TOKEN = os.getenv("JIRA_TOKEN", "")
