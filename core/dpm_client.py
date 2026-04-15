"""
Клиент DPM (Deploy Pipeline Manager) — GraphQL API.

В UI DPM видно ключ приложения (например, `HRP`) и КЭ вида `CIO8553253`.
Критично: все операции должны быть строго привязаны к КЭ (и версии релиза),
чтобы исключить случайное воздействие на чужие сервисы.
"""

from __future__ import annotations

import logging
import os
import re
import warnings
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

warnings.filterwarnings("ignore")

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────
# Конфиг
# ────────────────────────────────────────────────────────────────
DPM_URL = (os.getenv("DPM_BASE_URL", "") or os.getenv("DPM_URL", "")).rstrip("/")
DPM_TOKEN = os.getenv("DPM_TOKEN", "")
DPM_VERIFY_SSL = os.getenv("DPM_VERIFY_SSL", "0").strip().lower() not in (
    "0",
    "false",
    "no",
    "off",
)

# Белый список допустимых этапов для запуска
ALLOWED_STAGES = {"ИФТ", "ПСИ"}


# ────────────────────────────────────────────────────────────────
# GraphQL запросы (восстановлены из DevTools)
# ────────────────────────────────────────────────────────────────

GQL_ENTITY_BY_KEY = """
query entityByKey($key: String) {
  entityByKey(key: $key) {
    id
    key
    type
    __typename
    ... on AutomatedSystem {
      multiApp { id key __typename }
      __typename
    }
    ... on FunctionalSubSystem {
      automatedSystem { id key __typename }
      __typename
    }
    ... on ReleaseActivityObject {
      isWithoutSync
      functionalSubSystem {
        id key
        automatedSystem { id key __typename }
        __typename
      }
      __typename
    }
    ... on MultiApp {
      automatedSystem { id key __typename }
      __typename
    }
  }
}
"""

GQL_FSS_VIEW_LIST = """
query FSSViewList($page: Page!, $filterName: String, $asId: BigInteger!,
                  $isFavorite: Boolean, $sorter: Sorter) {
  fssList(asId: $asId, page: $page, filterName: $filterName,
          isFavorite: $isFavorite, sorter: $sorter) {
    content {
      ...FssListItem
      __typename
    }
    __typename
    totalPages
  }
}

fragment FssListItem on FunctionalSubSystem {
  id
  name
  description
  key
  isFavorite
  logoUrl
  fssAccesses {
    canCreateRao
    canEditTargetedRoles
    canCreatePipeline
    __typename
  }
  __typename
}
"""

GQL_FSS_RAO_LIST = """
query fssRaoList($fssId: BigInteger!, $page: Page!, $filterName: String,
                 $sorter: Sorter) {
  raoList(fssId: $fssId, page: $page, filterName: $filterName,
          sorter: $sorter) {
    content {
      id
      name
      key
      state
      __typename
    }
    totalPages
    __typename
  }
}
"""

GQL_RAO_RC_IDS = """
query releaseActivityObjectRcIds(
  $id: BigInteger,
  $stepFilter: RcByStepFilter,
  $pipelineFilter: RcByPipelineFilter,
  $visible: Boolean,
  $releaseBranches: Boolean,
  $versions: [String],
  $rcVersionSearch: String,
  $rcSort: RcSort!,
  $startDate: Date,
  $endDate: Date
) {
  releaseActivityObject(id: $id) {
    id
    rcIds(
      stepFilter: $stepFilter
      pipelineFilter: $pipelineFilter
      releaseBranches: $releaseBranches
      visible: $visible
      versions: $versions
      rcVersionSearch: $rcVersionSearch
      rcSort: $rcSort
      startDate: $startDate
      endDate: $endDate
    ) {
      rc
      version
      pipelineIdentifier
      subRelease
      __typename
    }
    __typename
  }
}
"""

GQL_RC_LIST_VIEW = """
query rcListView($id: BigInteger) {
  releaseCandidate(id: $id) {
    id
    state
    version
    dpmRcSteps {
      id
      state
      order
      skipped
      stageOrder
      stepTemplate { id name color __typename }
      optional
      __typename
    }
    __typename
  }
}
"""

# Mutation для approve/execute этапа (варианты; DPM может отличаться)
GQL_APPROVE_STEP = """
mutation approveRcStep($id: BigInteger!) {
  approveRcStep(id: $id) {
    id
    state
    __typename
  }
}
"""

GQL_EXECUTE_STEP = """
mutation executeRcStep($id: BigInteger!) {
  executeRcStep(id: $id) {
    id
    state
    __typename
  }
}
"""


class DpmClient:
    """
    GraphQL-клиент DPM.

    Endpoint: {DPM_URL}/dpm/auth/dpm/graphql/{operationName}
    """

    def __init__(
        self,
        url: str = "",
        token: str = "",
        verify_ssl: bool = False,
    ) -> None:
        self.url = (url or DPM_URL).rstrip("/")
        self.token = token or DPM_TOKEN
        self.verify_ssl = verify_ssl if verify_ssl else DPM_VERIFY_SSL

        if not self.url:
            logger.warning("DPM_URL не настроен — интеграция с DPM недоступна")
        if not self.token:
            logger.warning("DPM_TOKEN не настроен — интеграция с DPM недоступна")

        self._session = requests.Session()
        retry = Retry(
            total=2,
            connect=2,
            read=2,
            status=0,
            backoff_factor=0.25,
            allowed_methods=frozenset(["POST"]),
            raise_on_status=False,
        )
        self._session.mount("https://", HTTPAdapter(max_retries=retry))
        self._session.mount("http://", HTTPAdapter(max_retries=retry))

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.token)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _graphql(
        self,
        operation_name: str,
        query: str,
        variables: Dict[str, Any],
    ) -> Dict[str, Any]:
        endpoint = f"{self.url}/dpm/auth/dpm/graphql/{operation_name}"
        payload = {"operationName": operation_name, "query": query, "variables": variables}
        resp = self._session.post(
            endpoint,
            headers=self._headers(),
            json=payload,
            timeout=30,
            verify=self.verify_ssl,
        )
        resp.raise_for_status()
        result = resp.json()
        if "errors" in result and result["errors"]:
            msg = "; ".join(e.get("message", str(e)) for e in (result["errors"] or []))
            raise RuntimeError(f"DPM GraphQL {operation_name}: {msg}")
        return result.get("data", {}) or {}

    # ──────────────────────────────────────
    #  Извлечение КЭ/версии из JIRA релиза
    # ──────────────────────────────────────
    @staticmethod
    def extract_ci_from_release(release_issue: Dict[str, Any]) -> Optional[str]:
        """
        Извлекает КЭ приложения из JIRA-задачи релиза.

        DPM использует формат `CIO<digits>` (буква O, а не ноль).
        Примеры источников в Jira:
        - поле «КЭ»: HumanSmartProfile(8553253)
        - header/контекст: CIO8553253
        """
        fields = release_issue.get("fields", {}) or {}
        rendered = release_issue.get("renderedFields", {}) or {}
        names_map = release_issue.get("names", {}) or {}

        def _normalize_ci(s: str) -> Optional[str]:
            t = (s or "").strip()
            if not t:
                return None
            # Allow CIO855..., CI0855..., CI0..., etc. Normalize to CIO + digits.
            m = re.search(r"\bCI[O0]?(\d{5,})\b", t, re.IGNORECASE)
            if m:
                return f"CIO{m.group(1)}"
            # HumanSmartProfile(8553253) -> CIO8553253
            m = re.search(r"\w+\((\d{5,})\)", t)
            if m:
                return f"CIO{m.group(1)}"
            return None

        # 0) Look for fields whose display name resembles "КЭ" (but avoid "ИТ-услуга")
        for field_id, field_val in fields.items():
            dn = (names_map.get(field_id, "") or "").strip().lower()
            if not dn:
                continue
            if ("кэ" in dn or "ке" in dn or dn == "ke") and ("услуг" not in dn):
                if isinstance(field_val, str):
                    v = _normalize_ci(field_val)
                    if v:
                        return v
                if isinstance(field_val, dict):
                    for sub_key in ("value", "name", "displayName", "key"):
                        sv = field_val.get(sub_key)
                        if isinstance(sv, str):
                            v = _normalize_ci(sv)
                            if v:
                                return v
                if isinstance(field_val, list):
                    for item in field_val:
                        if isinstance(item, str):
                            v = _normalize_ci(item)
                            if v:
                                return v
                        if isinstance(item, dict):
                            for sub_key in ("value", "name", "displayName"):
                                sv = item.get(sub_key)
                                if isinstance(sv, str):
                                    v = _normalize_ci(sv)
                                    if v:
                                        return v

        # 1) summary fallback
        summary = fields.get("summary", "") or ""
        v = _normalize_ci(summary)
        if v:
            return v

        # 2) any customfield that contains Name(digits)
        for field_id, field_val in fields.items():
            if not field_id.startswith("customfield_"):
                continue
            dn = (names_map.get(field_id, "") or "").strip().lower()
            if "услуг" in dn:
                continue
            if isinstance(field_val, str):
                v = _normalize_ci(field_val)
                if v:
                    return v
            if isinstance(field_val, dict):
                for sub_key in ("value", "name", "displayName"):
                    sv = field_val.get(sub_key)
                    if isinstance(sv, str):
                        v = _normalize_ci(sv)
                        if v:
                            return v

        # 3) renderedFields fallback
        for _, field_val in rendered.items():
            if isinstance(field_val, str):
                v = _normalize_ci(field_val)
                if v:
                    return v

        return None

    @staticmethod
    def extract_version_from_release(release_issue: Dict[str, Any]) -> Optional[str]:
        fields = release_issue.get("fields", {}) or {}
        for fv in fields.get("fixVersions", []) or []:
            if isinstance(fv, dict):
                name = (fv.get("name") or "").strip()
                if name:
                    return name
        summary = fields.get("summary", "") or ""
        m = re.search(r"\b([A-Z]-\d{2}\.\d{3}\.\d{2}[._]\d+)\b", summary)
        if m:
            return m.group(1)
        for _, val in fields.items():
            if isinstance(val, str):
                m = re.search(r"\b([A-Z]-\d{2}\.\d{3}\.\d{2}[._]\d+)\b", val)
                if m:
                    return m.group(1)
        return None

    # ──────────────────────────────────────
    #  GraphQL операции
    # ──────────────────────────────────────
    def entity_by_key(self, key: str) -> Optional[Dict[str, Any]]:
        data = self._graphql("entityByKey", GQL_ENTITY_BY_KEY, {"key": key})
        return data.get("entityByKey")

    def get_fss_list(self, as_id: int) -> List[Dict[str, Any]]:
        data = self._graphql(
            "FSSViewList",
            GQL_FSS_VIEW_LIST,
            {
                "asId": as_id,
                "page": {"size": 50, "page": 0},
                "filterName": "",
                "sorter": {"column": "NAME", "asc": True},
            },
        )
        return (data.get("fssList") or {}).get("content", []) or []

    def get_rao_list(self, fss_id: int) -> List[Dict[str, Any]]:
        data = self._graphql(
            "fssRaoList",
            GQL_FSS_RAO_LIST,
            {
                "fssId": fss_id,
                "page": {"size": 50, "page": 0},
                "filterName": "",
                "sorter": {"column": "NAME", "asc": True},
            },
        )
        return (data.get("raoList") or {}).get("content", []) or []

    def get_rc_ids(self, rao_id: int, version_search: str = "") -> List[Dict[str, Any]]:
        data = self._graphql(
            "releaseActivityObjectRcIds",
            GQL_RAO_RC_IDS,
            {
                "id": rao_id,
                "rcSort": {"asc": False, "column": "LAST_MODIFY_DATE"},
                "visible": True,
                "releaseBranches": True,
                "rcVersionSearch": version_search or None,
            },
        )
        return (data.get("releaseActivityObject") or {}).get("rcIds", []) or []

    def get_rc_details(self, rc_id: int) -> Optional[Dict[str, Any]]:
        data = self._graphql("rcListView", GQL_RC_LIST_VIEW, {"id": rc_id})
        return data.get("releaseCandidate")

    def approve_step(self, step_id: int) -> Tuple[bool, str]:
        try:
            data = self._graphql("approveRcStep", GQL_APPROVE_STEP, {"id": step_id})
            step = data.get("approveRcStep", {}) or {}
            return True, f"approve отправлен (state={step.get('state', '?')})"
        except Exception as e:
            logger.debug("approveRcStep failed: %s", e)
        try:
            data = self._graphql("executeRcStep", GQL_EXECUTE_STEP, {"id": step_id})
            step = data.get("executeRcStep", {}) or {}
            return True, f"execute отправлен (state={step.get('state', '?')})"
        except Exception as e:
            return False, f"DPM approve/execute error: {e}"

    # ──────────────────────────────────────
    #  Высокоуровневые операции
    # ──────────────────────────────────────
    def find_app_by_ci(self, ci_number: str) -> Tuple[Optional[Dict[str, Any]], str]:
        """
        Найти приложение/объект DPM по КЭ.

        На практике `entityByKey` принимает `CIO<digits>` (и иногда варианты).
        Пробуем последовательность ключей: exact, CIO-normalized, digits-only.
        """
        safe_ci = (ci_number or "").strip()
        if not safe_ci:
            return None, "Не указан номер КЭ (CI)."

        candidates: List[str] = []
        candidates.append(safe_ci)
        norm = self.extract_ci_from_release({"fields": {"summary": safe_ci}})
        if norm and norm not in candidates:
            candidates.append(norm)
        digits = re.sub(r"\D", "", safe_ci)
        if digits and digits not in candidates:
            candidates.append(digits)

        last_err: Optional[str] = None
        for key in candidates:
            try:
                entity = self.entity_by_key(key)
            except Exception as e:
                last_err = str(e)
                continue
            if not entity or not entity.get("id"):
                continue
            etype = entity.get("type", entity.get("__typename", "")) or ""
            ekey = entity.get("key", key)
            if "AutomatedSystem" in etype:
                return entity, f"Найдено приложение: {ekey} (id={entity['id']})"
            if "FunctionalSubSystem" in etype:
                as_info = entity.get("automatedSystem", {}) or {}
                if as_info.get("id"):
                    return as_info, (
                        f"По КЭ={safe_ci} найден микросервис {ekey}. "
                        f"Приложение: {as_info.get('key', '?')} (id={as_info['id']})"
                    )
                return entity, f"По КЭ={safe_ci} найден объект {ekey} (тип: {etype})"
            return entity, f"По КЭ={safe_ci} найден объект {ekey} (тип: {etype})"

        suffix = f" (последняя ошибка: {last_err})" if last_err else ""
        return None, (
            f"Приложение с КЭ={safe_ci} не найдено в DPM через entityByKey.{suffix}\n"
            f"Проверь, что КЭ имеет формат CIO<digits> и что токен DPM валиден."
        )

    def list_services(self, app_id: int) -> Tuple[List[Dict[str, Any]], str]:
        try:
            services = self.get_fss_list(app_id)
            if not services:
                return [], f"Микросервисы для приложения (id={app_id}) не найдены."
            return services, f"Найдено микросервисов: {len(services)}"
        except Exception as e:
            return [], f"Ошибка получения микросервисов: {e}"

    def find_rc_for_service(self, fss_id: int, release_version: str) -> Tuple[Optional[int], str]:
        safe_version = (release_version or "").strip()
        try:
            raos = self.get_rao_list(fss_id)
        except Exception as e:
            return None, f"Ошибка получения RAO для fss_id={fss_id}: {e}"
        if not raos:
            return None, f"RAO не найден для микросервиса (fss_id={fss_id})."
        rao = raos[0]
        rao_id = rao.get("id")
        rao_name = rao.get("name", "?")
        if not rao_id:
            return None, f"RAO найден ({rao_name}), но у него нет id."
        try:
            rc_list = self.get_rc_ids(int(rao_id), version_search=safe_version)
        except Exception as e:
            return None, f"Ошибка получения RC для RAO {rao_name} (id={rao_id}): {e}"
        if not rc_list:
            return None, f"Релизы для {rao_name} (RAO id={rao_id}) не найдены. Искали: {safe_version}"

        matches: list[tuple[str, Any]] = []
        for rc in rc_list:
            ver = str(rc.get("version", "") or "").strip()
            rc_id = rc.get("rc")
            if not ver or rc_id is None:
                continue
            # Prefer strict equality when possible; fall back to containment for alias-like versions.
            if safe_version == ver or (safe_version and (safe_version in ver or ver in safe_version)):
                matches.append((ver, rc_id))

        if not matches:
            versions_found = [str(r.get("version", "?")) for r in rc_list[:10]]
            return None, f"RC с версией «{safe_version}» не найден. Доступные: {', '.join(versions_found)}"

        if len(matches) > 1:
            sample = ", ".join(f"{v}(rc_id={rid})" for v, rid in matches[:5])
            return None, (
                f"Найдено несколько RC под версию «{safe_version}» для {rao_name} — "
                f"не запускаю (fail-closed).\n"
                f"Совпадения: {sample}"
            )

        ver, rc_id_any = matches[0]
        try:
            return int(rc_id_any), f"Найден RC: {ver} (rc_id={rc_id_any})"
        except Exception:
            return None, f"Найден RC {ver}, но rc_id некорректен: {rc_id_any}"

    def get_rc_stages(self, rc_id: int) -> Tuple[List[Dict[str, Any]], str]:
        try:
            rc = self.get_rc_details(rc_id)
        except Exception as e:
            return [], f"Ошибка получения деталей RC (rc_id={rc_id}): {e}"
        if not rc:
            return [], f"RC (rc_id={rc_id}) не найден."
        steps = rc.get("dpmRcSteps", []) or []
        version = rc.get("version", "?")
        state = rc.get("state", "?")
        if not steps:
            return [], f"Этапы конвейера {version} (rc_id={rc_id}) не найдены."
        return steps, f"RC: {version}, статус: {state}, этапов: {len(steps)}"

    def find_stage_steps(self, rc_id: int, target_stage: str) -> Tuple[List[Dict[str, Any]], str]:
        target = (target_stage or "").strip().upper()
        if target not in ALLOWED_STAGES:
            return [], f"Этап «{target}» не разрешён. Допустимые: {sorted(ALLOWED_STAGES)}"
        steps, msg = self.get_rc_stages(rc_id)
        if not steps:
            return [], msg
        matched = []
        for step in steps:
            tmpl = step.get("stepTemplate", {}) or {}
            name = str(tmpl.get("name", "")).strip()
            if target in name.upper():
                matched.append(step)
        if not matched:
            all_names = [str(((s.get("stepTemplate") or {}).get("name", "?"))) for s in steps]
            return [], f"{msg}\nЭтап «{target}» не найден. Шаги: {', '.join(all_names)}"
        return matched, f"{msg}\nНайдено шагов для «{target}»: {len(matched)}"

    def deploy_service_to_stage(
        self,
        *,
        fss_id: int,
        release_version: str,
        target_stage: str,
        dry_run: bool = False,
    ) -> Tuple[bool, str]:
        target = (target_stage or "").strip().upper()
        if target not in ALLOWED_STAGES:
            return False, f"Этап «{target}» не разрешён. Допустимые: {sorted(ALLOWED_STAGES)}"
        rc_id, find_msg = self.find_rc_for_service(fss_id, release_version)
        if not rc_id:
            return False, find_msg
        stage_steps, stage_msg = self.find_stage_steps(rc_id, target)
        if not stage_steps:
            return False, f"{find_msg}\n{stage_msg}"
        lines = [find_msg, stage_msg, ""]
        if dry_run:
            for step in stage_steps:
                tmpl = step.get("stepTemplate", {}) or {}
                lines.append(
                    f"  [DRY-RUN] {tmpl.get('name', '?')} — state={step.get('state', '?')}, step_id={step.get('id', '?')}"
                )
            return True, "\n".join(lines)
        all_ok = True
        for step in stage_steps:
            step_id = step.get("id")
            tmpl = step.get("stepTemplate", {}) or {}
            step_name = tmpl.get("name", "?")
            step_state = str(step.get("state", "") or "")
            if step_state in ("SUCCESS", "COMPLETED", "DONE"):
                lines.append(f"  ✅ {step_name} — уже выполнен ({step_state})")
                continue
            if step.get("skipped"):
                lines.append(f"  ⏭ {step_name} — пропущен")
                continue
            if not step_id:
                lines.append(f"  ⚠️ {step_name} — нет step_id, пропускаем")
                continue
            ok, approve_msg = self.approve_step(int(step_id))
            lines.append(f"  {'✅' if ok else '❌'} {step_name}: {approve_msg}")
            if not ok:
                all_ok = False
        return all_ok, "\n".join(lines)

    def get_status_for_service_release(self, fss_id: int, release_version: str) -> Tuple[bool, str]:
        rc_id, find_msg = self.find_rc_for_service(fss_id, release_version)
        if not rc_id:
            return False, find_msg
        steps, steps_msg = self.get_rc_stages(rc_id)
        if not steps:
            return False, f"{find_msg}\n{steps_msg}"
        lines = [find_msg, steps_msg, "", "Шаги конвейера:"]
        for step in steps:
            tmpl = step.get("stepTemplate", {}) or {}
            name = tmpl.get("name", "?")
            state = step.get("state", "?")
            skipped = bool(step.get("skipped", False))
            icon = (
                "✅"
                if state in ("SUCCESS", "COMPLETED", "DONE")
                else "🔄"
                if state in ("IN_PROGRESS", "RUNNING")
                else "⏭"
                if skipped
                else "⏳"
                if state in ("WAITING", "PENDING", "NOT_STARTED", "CREATED")
                else "❌"
                if state in ("FAILED", "ERROR")
                else "❓"
            )
            lines.append(f"  {icon} {name}: {state}")
        return True, "\n".join(lines)

    # ──────────────────────────────────────
    #  Утилиты для UI
    # ──────────────────────────────────────
    @staticmethod
    def format_service_name(svc: Dict[str, Any]) -> str:
        key = str(svc.get("key", ""))
        name = str(svc.get("name", ""))
        return f"{name} ({key})" if key and name else (name or key or str(svc.get("id", "???")))

    @staticmethod
    def get_service_id(svc: Dict[str, Any]) -> Optional[int]:
        sid = svc.get("id")
        if sid is None:
            return None
        try:
            return int(sid)
        except Exception:
            return None

