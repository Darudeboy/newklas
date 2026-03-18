"""
Клиент GigaChat (Sber HR IFT): OAuth password + completion API.
Креды и URL — из .env (совместимо с прежним ui.py).
"""
from __future__ import annotations

import json
import logging
import os
import time
import warnings
from typing import Any, Dict, List, Optional, Tuple

import requests
import urllib3

logger = logging.getLogger(__name__)


class GigaChatClient:
    def __init__(
        self,
        *,
        username: str,
        password: str,
        person_id: str,
        client_id: str,
        model: str,
        token_url: str,
        api_url: str,
        verify_ssl: bool = False,
    ) -> None:
        self._username = (username or "").strip()
        self._password = password or ""
        self.person_id = (person_id or "").strip()
        self.client_id = (client_id or "").strip() or "fakeuser"
        self.model = (model or "").strip() or "GigaChat-2-Max"
        self.token_url = (token_url or "").strip()
        self.api_url = (api_url or "").strip()
        self.verify_ssl = verify_ssl
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    @classmethod
    def from_env(cls) -> "GigaChatClient":
        verify = os.getenv("GIGACHAT_VERIFY_SSL", "").lower() in (
            "1",
            "true",
            "yes",
        )
        return cls(
            username=os.getenv("GIGACHAT_USERNAME", "") or "",
            password=os.getenv("GIGACHAT_PASSWORD", "") or "",
            person_id=os.getenv(
                "GIGACHAT_PERSON_ID",
                "91ed8888-bff4-4d61-a72d-310db2eeaa37",
            ),
            client_id=os.getenv("GIGACHAT_CLIENT_ID", "fakeuser"),
            model=os.getenv("GIGACHAT_MODEL", "GigaChat-2-Max"),
            token_url=os.getenv(
                "GIGACHAT_TOKEN_URL",
                "https://hr-ift.sberbank.ru/auth/realms/PAOSberbank/protocol/openid-connect/token",
            ),
            api_url=os.getenv(
                "GIGACHAT_API_URL",
                "https://hr-ift.sberbank.ru/api-web/neurosearchbar/api/v1/gigachat/completion",
            ),
            verify_ssl=verify,
        )

    def is_configured(self) -> bool:
        return bool(
            self._username
            and self._password
            and self.token_url
            and self.api_url
            and self.person_id
        )

    def _ensure_token(self) -> Tuple[bool, str]:
        if self._access_token and time.time() < self._token_expires_at:
            return True, ""
        if not self.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "x-hrp-person-id": self.person_id,
            "User-Agent": "newui-gigachat/1.0",
            "Accept": "*/*",
        }
        payload = {
            "grant_type": "password",
            "username": self._username,
            "password": self._password,
            "client_id": self.client_id,
        }
        try:
            r = requests.post(
                self.token_url,
                data=payload,
                headers=headers,
                verify=self.verify_ssl,
                timeout=30,
            )
        except Exception as e:
            logger.exception("GigaChat token request failed")
            return False, str(e)
        if r.status_code != 200:
            return False, f"token HTTP {r.status_code}: {(r.text or '')[:300]}"
        try:
            data = r.json()
        except Exception:
            return False, "token: не JSON"
        self._access_token = data.get("access_token")
        if not self._access_token:
            return False, "token: нет access_token"
        exp = int(data.get("expires_in", 1800))
        self._token_expires_at = time.time() + max(60, exp - 60)
        return True, ""

    def complete(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.15,
        timeout: int = 120,
    ) -> Tuple[bool, str]:
        """
        messages: [{"role":"system"|"user"|"assistant", "content":"..."}, ...]
        Возвращает (ok, текст_ответа_или_ошибка).
        """
        if not self.is_configured():
            return False, "GigaChat: задай GIGACHAT_USERNAME и GIGACHAT_PASSWORD в .env"
        ok, err = self._ensure_token()
        if not ok:
            return False, f"GigaChat токен: {err}"
        if not self.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "personId": self.person_id,
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        try:
            r = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                verify=self.verify_ssl,
                timeout=timeout,
            )
        except Exception as e:
            logger.exception("GigaChat completion failed")
            return False, str(e)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}: {(r.text or '')[:500]}"
        try:
            data = r.json()
        except Exception:
            return False, "ответ не JSON"
        choices = data.get("choices") or []
        if not choices:
            return False, json.dumps(data, ensure_ascii=False)[:400]
        content = (choices[0].get("message") or {}).get("content") or ""
        return True, (content or "").strip()
