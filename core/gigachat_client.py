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
from requests.adapters import HTTPAdapter
from requests.utils import get_environ_proxies, should_bypass_proxies
from urllib3.util.retry import Retry

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

    def _should_trust_env_proxies(self) -> bool:
        """
        requests.Session.trust_env controls usage of HTTP(S)_PROXY, NO_PROXY, etc.
        In some корпоративные сети доступ к hr-ift.* возможен только через proxy,
        поэтому это поведение делаем настраиваемым.
        """
        v = (os.getenv("GIGACHAT_TRUST_ENV", "") or "").strip().lower()
        if v in ("0", "false", "no", "off"):
            return False
        if v in ("1", "true", "yes", "on"):
            return True
        # Default: trust environment (safer for corporate networks).
        return True

    def _effective_proxies_for_url(self, url: str) -> Dict[str, str]:
        """
        Return proxies that will be used for the given URL.
        Supports explicit overrides via:
        - GIGACHAT_HTTPS_PROXY / GIGACHAT_HTTP_PROXY
        - GIGACHAT_NO_PROXY
        If overrides are not set, falls back to standard env proxy discovery (when trust_env=True).
        """
        overrides: Dict[str, str] = {}
        https_p = (os.getenv("GIGACHAT_HTTPS_PROXY", "") or "").strip()
        http_p = (os.getenv("GIGACHAT_HTTP_PROXY", "") or "").strip()
        no_p = (os.getenv("GIGACHAT_NO_PROXY", "") or "").strip()
        if https_p:
            overrides["https"] = https_p
        if http_p:
            overrides["http"] = http_p
        # requests honors NO_PROXY via environment; we keep it compatible by copying into process env
        # when user provided GIGACHAT_NO_PROXY.
        if no_p:
            os.environ["NO_PROXY"] = no_p
            os.environ["no_proxy"] = no_p
        if overrides:
            return overrides
        if not self._should_trust_env_proxies():
            return {}
        try:
            return dict(get_environ_proxies(url))
        except Exception:
            return {}

    def _proxy_debug_hint(self, url: str) -> str:
        trust = self._should_trust_env_proxies()
        proxies = self._effective_proxies_for_url(url)
        no_proxy = os.getenv("NO_PROXY") or os.getenv("no_proxy") or ""
        bypass = False
        try:
            bypass = should_bypass_proxies(url, no_proxy=no_proxy) if trust else True
        except Exception:
            bypass = False
        # Keep the hint short; we only need enough to see whether a proxy is involved.
        https_p = proxies.get("https") or ""
        http_p = proxies.get("http") or ""
        parts = [
            f"trust_env={'True' if trust else 'False'}",
            f"proxy_https={'set' if bool(https_p) else 'empty'}",
            f"proxy_http={'set' if bool(http_p) else 'empty'}",
            f"no_proxy={'set' if bool(no_proxy.strip()) else 'empty'}",
            f"bypass={'True' if bypass else 'False'}",
        ]
        return ", ".join(parts)

    def _ensure_token(self) -> Tuple[bool, str]:
        if self._access_token and time.time() < self._token_expires_at:
            return True, ""
        if not self.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        # Mimic Insomnia as close as possible (some gateways are picky).
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "x-hrp-person-id": self.person_id,
            "User-Agent": os.getenv("GIGACHAT_TOKEN_USER_AGENT", "insomnia/8.6.1"),
            "Accept": "*/*",
            "Connection": "close",
        }
        cookies = {"KEYCLOAK_LOCALE": "ru"}
        payload = {
            "grant_type": "password",
            "username": self._username,
            "password": self._password,
            "client_id": self.client_id,
        }
        try:
            s = requests.Session()
            # Retries help with flaky gateways / occasional resets.
            retry = Retry(
                total=3,
                connect=3,
                read=2,
                status=0,
                backoff_factor=0.5,
                allowed_methods=frozenset(["POST"]),
                raise_on_status=False,
            )
            s.mount("https://", HTTPAdapter(max_retries=retry))
            s.mount("http://", HTTPAdapter(max_retries=retry))
            s.trust_env = self._should_trust_env_proxies()
            proxies = self._effective_proxies_for_url(self.token_url)
            r = s.post(
                self.token_url,
                data=payload,
                headers=headers,
                cookies=cookies,
                proxies=proxies or None,
                verify=self.verify_ssl,
                timeout=60,
            )
        except Exception as e:
            logger.exception("GigaChat token request failed")
            return False, f"{e} ({self._proxy_debug_hint(self.token_url)})"
        if r.status_code != 200:
            return False, f"token HTTP {r.status_code}: {(r.text or '')[:300]} ({self._proxy_debug_hint(self.token_url)})"
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
            "Connection": "close",
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        try:
            s = requests.Session()
            s.trust_env = self._should_trust_env_proxies()
            proxies = self._effective_proxies_for_url(self.api_url)
            r = s.post(
                self.api_url,
                headers=headers,
                json=payload,
                proxies=proxies or None,
                verify=self.verify_ssl,
                timeout=timeout,
            )
        except Exception as e:
            logger.exception("GigaChat completion failed")
            return False, f"{e} ({self._proxy_debug_hint(self.api_url)})"
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}: {(r.text or '')[:500]} ({self._proxy_debug_hint(self.api_url)})"
        try:
            data = r.json()
        except Exception:
            return False, "ответ не JSON"
        choices = data.get("choices") or []
        if not choices:
            return False, json.dumps(data, ensure_ascii=False)[:400]
        content = (choices[0].get("message") or {}).get("content") or ""
        return True, (content or "").strip()
