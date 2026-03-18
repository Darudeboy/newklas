"""
Клиент Jira API. Вся логика обращений к Jira собрана здесь.
Перенесено из service.py с сохранением поведения и интерфейса (JiraService).
"""
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import requests
import warnings

from config import JiraConfig

warnings.filterwarnings("ignore")


def _jira_response_error_hint(response: Any) -> str:
    """Краткий текст из тела ответа Jira (errorMessages / errors / сырой фрагмент)."""
    if response is None:
        return ""
    try:
        j = response.json()
    except Exception:
        try:
            text = (getattr(response, "text", None) or "").strip()
            return text[:600] if text else ""
        except Exception:
            return ""
    parts: List[str] = []
    for m in j.get("errorMessages") or []:
        if m:
            parts.append(str(m))
    errs = j.get("errors") or {}
    if isinstance(errs, dict) and errs:
        for k, v in errs.items():
            parts.append(f"{k}: {v}")
    if parts:
        return "; ".join(parts)[:800]
    try:
        text = (getattr(response, "text", None) or "").strip()
        return text[:600] if text else ""
    except Exception:
        return ""


class JiraService:
    """Сервис для работы с Jira API."""

    def __init__(self, config: JiraConfig):
        self.config = config
        self._jira: Optional[Any] = None
        self._link_types_cache: Optional[Dict[str, dict]] = None
        self._field_name_map_cache: Optional[Dict[str, str]] = None
        self.logger = logging.getLogger(self.__class__.__name__)

    @property
    def jira(self) -> Any:
        """Ленивая инициализация подключения к Jira."""
        if self._jira is None:
            try:
                from atlassian import Jira  # type: ignore
            except Exception as e:
                raise ModuleNotFoundError(
                    "Не установлен пакет atlassian-python-api. "
                    "Установи зависимости: pip install -r requirements.txt"
                ) from e
            self._jira = Jira(
                url=self.config.url,
                token=self.config.token,
                verify_ssl=self.config.verify_ssl,
            )
        return self._jira

    def test_connection(self) -> Tuple[bool, str]:
        """Проверка подключения к Jira."""
        try:
            self.jira.myself()
            return True, "Подключение успешно установлено"
        except Exception as e:
            return False, f"Ошибка подключения: {str(e)}"

    def get_link_types(self) -> Dict[str, dict]:
        """Получение типов связей с кэшированием."""
        if self._link_types_cache is None:
            try:
                link_types = self.jira.get_issue_link_types()
                self._link_types_cache = {lt["name"]: lt for lt in link_types}
            except Exception as e:
                self.logger.error("Ошибка получения типов связей: %s", e)
                self._link_types_cache = {}
        return self._link_types_cache

    def get_linked_issues(self, release_key: str) -> List[str]:
        """Получение связанных задач."""
        try:
            url = f"/rest/api/2/issue/{release_key}?expand=renderedFields,issuelinks"
            response = self.jira.get(url)
            linked_keys: List[str] = []
            for link in response.get("fields", {}).get("issuelinks", []):
                if "outwardIssue" in link:
                    linked_keys.append(link["outwardIssue"]["key"])
                elif "inwardIssue" in link:
                    linked_keys.append(link["inwardIssue"]["key"])
            return list(set(linked_keys))
        except Exception as e:
            self.logger.error("Не удалось получить связи для %s: %s", release_key, e)
            return []

    def search_issues(self, jql: str, limit: int = 500) -> List[dict]:
        """Поиск задач по JQL."""
        try:
            data = self.jira.jql(jql, limit=limit)
            return data.get("issues", [])
        except Exception as e:
            self.logger.error("Ошибка поиска задач: %s", e)
            raise

    def create_issue_link(self, from_issue: str, to_issue: str, link_type: str) -> bool:
        """Создание связи между задачами."""
        try:
            url = "/rest/api/2/issueLink"
            payload = {
                "type": {"name": link_type},
                "inwardIssue": {"key": from_issue},
                "outwardIssue": {"key": to_issue},
            }
            response = self.jira.post(url, data=payload, advanced_mode=True)
            return response.status_code == 201
        except Exception as e:
            self.logger.error("Ошибка создания связи %s -> %s: %s", from_issue, to_issue, e)
            return False

    def delete_issue_link(self, link_id: str) -> bool:
        """Удаление связи."""
        try:
            response = self.jira.delete(
                f"/rest/api/2/issueLink/{link_id}", advanced_mode=True
            )
            return response.status_code == 204
        except Exception as e:
            self.logger.error("Ошибка удаления связи %s: %s", link_id, e)
            return False

    def get_issue_details(
        self,
        issue_key: str,
        fields: Optional[str] = None,
        expand: str = "issuelinks",
    ) -> Optional[dict]:
        """Получение детальной информации о задаче."""
        try:
            params: List[str] = []
            if expand:
                params.append(f"expand={expand}")
            if fields:
                params.append(f"fields={fields}")
            query = f"?{'&'.join(params)}" if params else ""
            return self.jira.get(f"/rest/api/2/issue/{issue_key}{query}")
        except Exception as e:
            self.logger.error("Ошибка получения информации о %s: %s", issue_key, e)
            return None

    def get_issue_remote_links(self, issue_key: str) -> List[dict]:
        """Получение удаленных ссылок задачи (включая PR-ссылки)."""
        try:
            response = self.jira.get(
                f"/rest/api/2/issue/{issue_key}/remotelink"
            )
            if isinstance(response, list):
                return response
            return []
        except Exception as e:
            self.logger.error(
                "Ошибка получения remote links для %s: %s", issue_key, e
            )
            return []

    def get_issue_comments(self, issue_key: str) -> List[dict]:
        """Получение комментариев Jira-задачи."""
        try:
            response = self.jira.get(
                f"/rest/api/2/issue/{issue_key}/comment"
            )
            comments = (
                response.get("comments", [])
                if isinstance(response, dict)
                else []
            )
            return comments if isinstance(comments, list) else []
        except Exception as e:
            self.logger.error(
                "Ошибка получения комментариев для %s: %s", issue_key, e
            )
            return []

    def add_issue_comment(self, issue_key: str, body: str) -> Tuple[bool, str]:
        """Добавляет комментарий к задаче."""
        safe_key = (issue_key or "").strip().upper()
        text = (body or "").strip()
        if not safe_key:
            return False, "Не указан issue_key"
        if not text:
            return False, "Комментарий пустой"
        try:
            response = self.jira.post(
                f"/rest/api/2/issue/{safe_key}/comment",
                data={"body": text},
                advanced_mode=True,
            )
            if response.status_code in (200, 201):
                return True, "Комментарий добавлен"
            return False, f"Jira вернул код {response.status_code} при добавлении комментария"
        except Exception as e:
            self.logger.error("Ошибка добавления комментария для %s: %s", safe_key, e)
            return False, f"Ошибка добавления комментария: {e}"

    def has_recent_comment(
        self,
        issue_key: str,
        marker: str,
        lookback: int = 20,
    ) -> bool:
        """Проверяет, есть ли среди последних комментариев маркер (анти-спам)."""
        safe_key = (issue_key or "").strip().upper()
        mark = (marker or "").strip()
        if not safe_key or not mark:
            return False
        try:
            comments = self.get_issue_comments(safe_key)
            if not comments:
                return False
            for item in (comments[-lookback:] if lookback > 0 else comments):
                body = item.get("body", "")
                body_text = body if isinstance(body, str) else str(body)
                if mark in body_text:
                    return True
            return False
        except Exception:
            return False

    def get_field_name_map(self) -> Dict[str, str]:
        """Карта field_id -> display name из Jira."""
        if self._field_name_map_cache is not None:
            return self._field_name_map_cache
        try:
            fields = self.jira.get("/rest/api/2/field")
            if not isinstance(fields, list):
                self._field_name_map_cache = {}
                return self._field_name_map_cache
            result: Dict[str, str] = {}
            for item in fields:
                if not isinstance(item, dict):
                    continue
                field_id = str(item.get("id", "")).strip()
                field_name = str(item.get("name", "")).strip()
                if field_id:
                    result[field_id] = field_name
            self._field_name_map_cache = result
            return result
        except Exception as e:
            self.logger.error("Ошибка получения списка полей Jira: %s", e)
            self._field_name_map_cache = {}
            return self._field_name_map_cache

    def get_dev_status_prs(self, issue_id: str) -> List[dict]:
        """Получение PR из панели Development (Stash/Bitbucket интеграция)."""
        try:
            url = (
                f"/rest/dev-status/latest/issue/detail"
                f"?issueId={issue_id}"
                f"&applicationType=stash&dataType=pullrequest"
            )
            response = self.jira.get(url)
            prs: List[dict] = []
            for detail in (response or {}).get("detail", []):
                for pr in detail.get("pullRequests", []):
                    prs.append(pr)
            return prs
        except Exception as e:
            self.logger.error(
                "Ошибка получения dev-status PR для issue %s: %s",
                issue_id,
                e,
            )
            return []

    def get_available_transitions(self, issue_key: str) -> List[dict]:
        """Получение доступных переходов статуса для задачи."""
        try:
            response = self.jira.get(
                f"/rest/api/2/issue/{issue_key}/transitions"
            )
            return response.get("transitions", [])
        except Exception as e:
            self.logger.error(
                "Ошибка получения переходов для %s: %s", issue_key, e
            )
            return []

    def get_issue_id(self, issue_key: str) -> Optional[str]:
        """Возвращает numeric issueId Jira для ключа задачи."""
        safe_key = (issue_key or "").strip().upper()
        if not safe_key:
            return None
        issue = self.get_issue_details(safe_key)
        if not issue:
            return None
        issue_id = str(issue.get("id", "")).strip()
        return issue_id or None

    def get_sber_test_report(self, issue_key: str) -> str:
        """
        Получает HTML блока 'Отчет о тестировании' из plugin endpoint.
        """
        safe_key = (issue_key or "").strip().upper()
        endpoint = (
            f"{self.config.url.rstrip('/')}"
            f"/rest/sber-test-report/1.0/sber-test-report/rqgiftstatushtml"
        )
        params = {"issueKey": safe_key}
        headers = {
            "Accept": "text/html, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Authorization": f"Bearer {self.config.token}",
        }
        try:
            response = requests.get(
                endpoint,
                params=params,
                headers=headers,
                timeout=20,
                verify=self.config.verify_ssl,
            )
            if response.status_code == 200:
                return response.text or ""
            self.logger.error(
                "sber-test-report HTTP %s for %s: %s",
                response.status_code,
                safe_key,
                (response.text or "")[:200],
            )
        except Exception as e:
            self.logger.error(
                "Failed to fetch sber-test-report for %s: %s", safe_key, e
            )
        return ""

    def get_qgm_status(self, issue_key: str) -> Tuple[bool, str, Optional[dict]]:
        """
        Получение RQG-данных по endpoint:
        /rest/release/1/qgm?issueId=<numeric_issue_id>
        """
        safe_issue = (issue_key or "").strip().upper()
        issue_id = self.get_issue_id(safe_issue)
        if not issue_id:
            return (
                False,
                f"Не удалось определить issueId для {safe_issue}",
                None,
            )

        endpoint = f"{self.config.url.rstrip('/')}/rest/release/1/qgm"
        params = {"issueId": issue_id}
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Authorization": f"Bearer {self.config.token}",
            "X-Requested-With": "XMLHttpRequest",
            "X-Atlassian-Token": "no-check",
        }

        try:
            response = requests.post(
                url=endpoint,
                params=params,
                headers=headers,
                timeout=30,
                verify=self.config.verify_ssl,
            )
            if 200 <= response.status_code < 300:
                try:
                    payload = response.json()
                    if isinstance(payload, dict):
                        return True, "QGM OK (POST)", payload
                except Exception:
                    text = (response.text or "").strip()
                    if text:
                        return (
                            True,
                            "QGM OK (POST non-json)",
                            {"raw_text": text},
                        )
                    return (
                        False,
                        "QGM failed: POST returned empty non-json body",
                        None,
                    )

            response_json = requests.post(
                url=endpoint,
                params=params,
                json={"issueId": int(issue_id)},
                headers={**headers, "Content-Type": "application/json"},
                timeout=30,
                verify=self.config.verify_ssl,
            )
            if 200 <= response_json.status_code < 300:
                try:
                    payload = response_json.json()
                    if isinstance(payload, dict):
                        return True, "QGM OK (POST+JSON)", payload
                except Exception:
                    text = (response_json.text or "").strip()
                    if text:
                        return (
                            True,
                            "QGM OK (POST+JSON non-json)",
                            {"raw_text": text},
                        )

            response_get = requests.get(
                url=endpoint,
                params=params,
                headers=headers,
                timeout=30,
                verify=self.config.verify_ssl,
            )
            if 200 <= response_get.status_code < 300:
                try:
                    payload = response_get.json()
                    if isinstance(payload, dict):
                        return True, "QGM OK (GET)", payload
                except Exception:
                    text = (response_get.text or "").strip()
                    if text:
                        return (
                            True,
                            "QGM OK (GET non-json)",
                            {"raw_text": text},
                        )

            return (
                False,
                f"QGM failed: POST HTTP {response.status_code}, "
                f"POST+JSON HTTP {response_json.status_code}, "
                f"GET HTTP {response_get.status_code}",
                None,
            )
        except Exception as e:
            self.logger.error(
                "Ошибка QGM endpoint для issue=%s: %s", safe_issue, e
            )
            return False, f"QGM failed: POST error: {e}", None

    def transition_issue(
        self, issue_key: str, target_status: str
    ) -> Tuple[bool, str]:
        """Перевод задачи в целевой статус по названию статуса."""
        try:
            transitions = self.get_available_transitions(issue_key)
            if not transitions:
                return False, f"Для {issue_key} не найдено доступных переходов"

            target = (target_status or "").strip().lower()
            if not target:
                return False, "Целевой статус не указан"

            matched_transition = None
            for transition in transitions:
                name = transition.get("name", "")
                if name.lower() == target:
                    matched_transition = transition
                    break
            if not matched_transition:
                for transition in transitions:
                    name = transition.get("name", "")
                    if target in name.lower():
                        matched_transition = transition
                        break

            if not matched_transition:
                options = ", ".join(
                    t.get("name", "Unknown") for t in transitions
                )
                return (
                    False,
                    f"Переход '{target_status}' не найден. Доступно: {options}",
                )

            payload = {"transition": {"id": matched_transition["id"]}}
            response = self.jira.post(
                f"/rest/api/2/issue/{issue_key}/transitions",
                data=payload,
                advanced_mode=True,
            )
            success = response.status_code in (200, 204)
            if success:
                return (
                    True,
                    f"{issue_key} переведена в статус "
                    f"'{matched_transition.get('name')}'",
                )
            hint = _jira_response_error_hint(response)
            msg = (
                f"Jira вернул код {response.status_code} при переводе {issue_key}"
            )
            if hint:
                msg += f". {hint}"
            return (False, msg)
        except Exception as e:
            self.logger.error(
                "Ошибка перевода %s в '%s': %s",
                issue_key,
                target_status,
                e,
            )
            return False, f"Ошибка перевода статуса: {e}"

    @staticmethod
    def _norm_status_label(name: str) -> str:
        return re.sub(r"\s+", " ", (name or "").strip().lower())

    @staticmethod
    def find_transition_to_status(
        transitions: List[dict], target_status: str
    ) -> Optional[dict]:
        """
        Находит переход, у которого to.name совпадает с целевым статусом workflow.
        Ориентация на статус назначения, а не на id или имя кнопки перехода.
        """
        want = JiraService._norm_status_label(target_status)
        if not want:
            return None
        for t in transitions or []:
            to = t.get("to") or {}
            to_name = JiraService._norm_status_label(to.get("name") or "")
            if to_name == want:
                return t
        return None

    def transition_issue_to_status(
        self, issue_key: str, target_status: str
    ) -> Tuple[bool, str]:
        """
        Перевод в целевой статус по имени статуса назначения (поле to в API transitions).
        Не использует захардкоженные transition id.
        """
        safe_key = (issue_key or "").strip().upper()
        if not safe_key:
            return False, "Не указан issue_key"
        ts = (target_status or "").strip()
        if not ts:
            return False, "Не указан целевой статус"
        try:
            transitions = self.get_available_transitions(safe_key)
            if not transitions:
                return (
                    False,
                    f"Для {safe_key} нет доступных переходов (проверь права и ключ).",
                )
            matched = self.find_transition_to_status(transitions, ts)
            if not matched:
                opts = "; ".join(
                    f"«{(t.get('to') or {}).get('name', '?')}» "
                    f"(кнопка: {t.get('name', '?')})"
                    for t in transitions
                )
                return (
                    False,
                    f"Из текущего статуса нет перехода в «{ts}» для {safe_key}. "
                    f"Куда можно перейти: {opts}. Сверь названия в workflow_order с Jira.",
                )
            tid = matched.get("id")
            if tid is None:
                return False, "Jira не вернула id перехода"
            response = self.jira.post(
                f"/rest/api/2/issue/{safe_key}/transitions",
                data={"transition": {"id": str(tid)}},
                advanced_mode=True,
            )
            if response.status_code in (200, 204):
                to_name = (matched.get("to") or {}).get("name") or ts
                return (
                    True,
                    f"{safe_key} переведён в статус «{to_name}» "
                    f"(действие «{matched.get('name', '')}»)",
                )
            hint = _jira_response_error_hint(response)
            msg = (
                f"Jira вернул код {response.status_code} при переходе в «{ts}» "
                f"({safe_key})"
            )
            if hint:
                msg += f". {hint}"
            if response.status_code >= 500:
                msg += (
                    " — часто это post-function/плагин в Jira. Попробуй тот же переход в UI."
                )
            return (False, msg)
        except Exception as e:
            self.logger.error(
                "Ошибка перевода %s в статус «%s»: %s", safe_key, ts, e
            )
            return False, f"Ошибка перехода в статус: {e}"

    def transition_issue_by_id(
        self, issue_key: str, transition_id: str
    ) -> Tuple[bool, str]:
        """Перевод задачи по transition ID."""
        safe_key = (issue_key or "").strip().upper()
        safe_transition_id = str(transition_id or "").strip()
        if not safe_key or not safe_transition_id:
            return False, "Не указан issue_key или transition_id"
        try:
            transitions = self.get_available_transitions(safe_key)
            allowed_ids = {str(t.get("id")) for t in transitions if t.get("id") is not None}
            if transitions and safe_transition_id not in allowed_ids:
                opts = ", ".join(
                    f"{t.get('name', '?')} (id {t.get('id')})" for t in transitions
                )
                return (
                    False,
                    f"Переход id {safe_transition_id} сейчас недоступен для {safe_key}. "
                    f"Доступно: {opts}. Обнови статус релиза в Jira или transition_ids в профиле.",
                )

            response = self.jira.post(
                f"/rest/api/2/issue/{safe_key}/transitions",
                data={"transition": {"id": safe_transition_id}},
                advanced_mode=True,
            )
            if response.status_code in (200, 204):
                return (
                    True,
                    f"{safe_key} переведена по transition id {safe_transition_id}",
                )
            hint = _jira_response_error_hint(response)
            msg = (
                f"Jira вернул код {response.status_code} для transition id "
                f"{safe_transition_id}"
            )
            if hint:
                msg += f". {hint}"
            if response.status_code >= 500:
                msg += (
                    " — обычно это сбой на стороне Jira (post-function, ScriptRunner, "
                    "обязательные поля в workflow). Попробуй перевести задачу вручную в UI "
                    "или обратись к админу Jira."
                )
            return (False, msg)
        except Exception as e:
            self.logger.error(
                "Ошибка перевода %s по transition id %s: %s",
                safe_key,
                safe_transition_id,
                e,
            )
            return False, f"Ошибка перевода по transition id: {e}"

    @staticmethod
    def normalize_status(status: str) -> str:
        return (status or "").strip().lower()

    def status_in(self, status: str, allowed_statuses: List[str]) -> bool:
        normalized = self.normalize_status(status)
        allowed = {
            self.normalize_status(item) for item in (allowed_statuses or [])
        }
        return normalized in allowed

    def collect_release_related_issues(
        self,
        release_key: str,
        max_depth: int = 2,
    ) -> Dict[str, dict]:
        """Собирает релиз и связанные задачи (BFS по ссылкам/сабтаскам)."""
        discovered: Dict[str, dict] = {}
        queue: List[Tuple[str, int]] = [
            ((release_key or "").strip().upper(), 0)
        ]
        while queue:
            issue_key, depth = queue.pop(0)
            if not issue_key or issue_key in discovered or depth > max_depth:
                continue
            issue = self.get_issue_details(issue_key)
            if not issue:
                continue
            discovered[issue_key] = issue

            fields = issue.get("fields", {}) or {}
            for sub in fields.get("subtasks", []) or []:
                sub_key = sub.get("key")
                if sub_key and sub_key not in discovered:
                    queue.append((sub_key, depth + 1))

            for link in fields.get("issuelinks", []) or []:
                outward = (link.get("outwardIssue") or {}).get("key")
                inward = (link.get("inwardIssue") or {}).get("key")
                for linked in (outward, inward):
                    if linked and linked not in discovered:
                        queue.append((linked, depth + 1))
        return discovered
