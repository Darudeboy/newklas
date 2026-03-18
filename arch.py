import argparse
import requests
import urllib3
import logging
import os
from typing import Dict
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Отключаем SSL-предупреждения
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("architecture_field_fix.log")],
)

# Конфигурация
JIRA_URL = os.getenv("JIRA_URL", "https://jira.sberbank.ru")
JIRA_TOKEN = os.getenv("JIRA_TOKEN")

# Список доступных проектов
AVAILABLE_PROJECTS = {
    "1": {"key": "HRC", "name": "HRC - Human Resources Center"},
    "2": {"key": "HRM", "name": "HRM - Human Resource Management"},
    "3": {"key": "NEUROUI", "name": "NEUROUI - Neural UI"},
    "4": {"key": "SFILE", "name": "SFILE - Smart File"},
    "5": {"key": "SEARCHCS", "name": "SEARCHCS - Search Core"},
}


class ArchitectureFieldFixer:
    def __init__(self, jira_url: str, jira_token: str):
        self.jira_url = jira_url
        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": f"Bearer {jira_token}", "Content-Type": "application/json"}
        )
        self.architecture_field_id = None

    def get_architecture_field_id(self) -> str:
        """
        Автоматически определяет ID поля 'Архитектура' через Jira API
        """
        try:
            response = self.session.get(f"{self.jira_url}/rest/api/2/field", verify=False)
            response.raise_for_status()
            fields = response.json()

            # Ищем поле по названию (регистронезависимо)
            for field in fields:
                if field.get("custom") and "архитектур" in field.get("name", "").lower():
                    field_id = field["id"]
                    logging.info(
                        "✅ Найдено поле 'Архитектура': %s (ID: %s)",
                        field.get("name", ""),
                        field_id,
                    )
                    return field_id

            raise ValueError("❌ Не найдено поле 'Архитектура' в Jira")

        except Exception as e:
            logging.error("❌ Ошибка при получении полей Jira: %s", e)
            raise

    def find_and_fix_stories(
        self,
        project_key: str,
        fix_version: str,
        auto_confirm: bool = False,
    ) -> Dict[str, int]:
        """
        Находит Story по project + fixVersion и устанавливает
        поле Архитектура = "Не влияет на архитектуру"
        """
        try:
            if not self.architecture_field_id:
                self.architecture_field_id = self.get_architecture_field_id()

            jql = f'project = {project_key} AND fixVersion = "{fix_version}" AND issuetype = Story'
            params = {"jql": jql, "fields": "key,summary", "maxResults": 500}

            logging.info("🔍 Запрос к Jira: %s", jql)
            response = self.session.get(
                f"{self.jira_url}/rest/api/2/search", params=params, verify=False
            )
            response.raise_for_status()
            data = response.json()

            stories = data.get("issues", [])
            stats = {"total": len(stories), "need_fix": 0, "fixed": 0, "errors": 0}

            logging.info("✅ Найдено Story в %s: %s", fix_version, len(stories))

            if len(stories) == 0:
                return stats

            stories_list = []
            for issue in stories:
                issue_key = issue["key"]
                summary = issue["fields"].get("summary", "Без названия")
                stories_list.append((issue_key, summary))
                stats["need_fix"] += 1

            if not auto_confirm:
                # non-interactive usage in UI uses auto_confirm=True
                return stats

            for issue_key, summary in stories_list:
                success = False

                update_data1 = {
                    "fields": {
                        self.architecture_field_id: [
                            {"id": "271300", "value": "Не влияет на архитектуру"}
                        ]
                    }
                }
                response1 = self.session.put(
                    f"{self.jira_url}/rest/api/2/issue/{issue_key}",
                    json=update_data1,
                    verify=False,
                )
                if response1.status_code == 204:
                    success = True
                    stats["fixed"] += 1
                else:
                    update_data2 = {
                        "fields": {
                            self.architecture_field_id: [{"value": "Не влияет на архитектуру"}]
                        }
                    }
                    response2 = self.session.put(
                        f"{self.jira_url}/rest/api/2/issue/{issue_key}",
                        json=update_data2,
                        verify=False,
                    )
                    if response2.status_code == 204:
                        success = True
                        stats["fixed"] += 1
                    else:
                        update_data3 = {
                            "fields": {self.architecture_field_id: [{"id": "271300"}]}
                        }
                        response3 = self.session.put(
                            f"{self.jira_url}/rest/api/2/issue/{issue_key}",
                            json=update_data3,
                            verify=False,
                        )
                        if response3.status_code == 204:
                            success = True
                            stats["fixed"] += 1

                if not success:
                    stats["errors"] += 1

            return stats
        except Exception as e:
            logging.error("❌ Критическая ошибка: %s", e)
            raise


def _select_project() -> str:
    for key, project in AVAILABLE_PROJECTS.items():
        print(f"  {key}. {project['name']}")
    while True:
        choice = input("Введите номер проекта (1-5): ").strip()
        if choice in AVAILABLE_PROJECTS:
            return AVAILABLE_PROJECTS[choice]["key"]
        print("❌ Некорректный выбор. Попробуйте снова.")


def main() -> None:
    if not JIRA_TOKEN:
        raise ValueError("❌ Не найден JIRA_TOKEN в переменных окружения")

    parser = argparse.ArgumentParser(description="Проставление поля архитектуры по Story.")
    parser.add_argument("--project-key", dest="project_key", default="")
    parser.add_argument("--fix-version", dest="fix_version", default="")
    parser.add_argument("--yes", dest="auto_confirm", action="store_true")
    args = parser.parse_args()

    if args.project_key and args.fix_version:
        project_key = args.project_key.strip().upper()
        fix_version = args.fix_version.strip()
        auto_confirm = bool(args.auto_confirm)
    else:
        project_key = _select_project()
        fix_version = input("\nВведите fixVersion: ").strip()
        if not fix_version:
            raise ValueError("❌ fixVersion обязателен для запуска скрипта")
        auto_confirm = False

    fixer = ArchitectureFieldFixer(JIRA_URL, JIRA_TOKEN)
    fixer.find_and_fix_stories(project_key=project_key, fix_version=fix_version, auto_confirm=auto_confirm)


if __name__ == "__main__":
    main()
