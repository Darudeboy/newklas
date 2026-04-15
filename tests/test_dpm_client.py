import sys


sys.path.insert(0, "/Users/asklimenko/Downloads/agent/newui")


from core.dpm_client import DpmClient


class FakeDpm(DpmClient):
    def __init__(self, *, raos, rc_ids):
        # Do not call parent __init__ (no env / no session needed).
        self._raos = raos
        self._rc_ids = rc_ids

    def get_rao_list(self, fss_id: int):
        return self._raos

    def get_rc_ids(self, rao_id: int, version_search: str = ""):
        return self._rc_ids


def test_extract_ci_normalizes_to_cio():
    issue = {"fields": {"summary": "Релиз HumanSmartProfile(8553253)"}}
    assert DpmClient.extract_ci_from_release(issue) == "CI08553253"

    issue2 = {"fields": {"summary": "CI08553253"}}
    assert DpmClient.extract_ci_from_release(issue2) == "CI08553253"

    issue3 = {"fields": {"summary": "CIO8553253"}}
    assert DpmClient.extract_ci_from_release(issue3) == "CI08553253"


def test_normalize_base_url_from_frontend_link():
    raw = "https://sbrf-dpm.sigma.sbrf.ru/dpm/front/main/key/HRP"
    assert DpmClient._normalize_base_url(raw) == "https://sbrf-dpm.sigma.sbrf.ru"

    raw2 = "https://sbrf-dpm.sigma.sbrf.ru"
    assert DpmClient._normalize_base_url(raw2) == "https://sbrf-dpm.sigma.sbrf.ru"


def test_extract_front_app_key():
    raw = "https://sbrf-dpm.sigma.sbrf.ru/dpm/front/main/key/HRP"
    assert DpmClient._extract_front_app_key(raw) == "HRP"
    assert DpmClient._extract_front_app_key("https://sbrf-dpm.sigma.sbrf.ru") is None


def test_extract_app_id_from_front_html():
    html = '<html><script>window.__STATE__={"asId":394295,"key":"HRP"}</script></html>'
    assert DpmClient._extract_app_id_from_front_html(html, "HRP") == 394295

    html2 = '<div data-as-id="12345"></div>'
    assert DpmClient._extract_app_id_from_front_html(html2, "HRP") == 12345

    assert DpmClient._extract_app_id_from_front_html("<html></html>", "HRP") is None


def test_extract_services_from_front_html():
    html = "<div>app-human-smart-profile</div><div>app-human-smart-profile-sync</div>"
    services = DpmClient._extract_services_from_front_html(html)
    assert "app-human-smart-profile" in services
    assert "app-human-smart-profile-sync" in services

def test_build_auth_headers_accepts_bearer_and_raw_token():
    h1 = DpmClient._build_auth_headers("abc.def.ghi")
    assert h1["Authorization"] == "Bearer abc.def.ghi"

    h2 = DpmClient._build_auth_headers("Bearer abc.def.ghi")
    assert h2["Authorization"] == "Bearer abc.def.ghi"

    h3 = DpmClient._build_auth_headers("bearer abc.def.ghi")
    assert h3["Authorization"] == "Bearer abc.def.ghi"


def test_build_auth_headers_cookie_mode():
    cookie = "X-HRP-SessionLife=abc; TS016bbbe6=xyz"
    h = DpmClient._build_auth_headers(cookie)
    assert h.get("Cookie") == cookie
    assert "Authorization" not in h


def test_find_rc_for_service_fail_closed_on_multiple_matches():
    dpm = FakeDpm(
        raos=[{"id": 1, "name": "rao"}],
        rc_ids=[
            {"rc": 10, "version": "D-01.007.00_674"},
            {"rc": 11, "version": "D-01.007.00_674"},
        ],
    )
    rc_id, msg = dpm.find_rc_for_service(123, "D-01.007.00_674")
    assert rc_id is None
    assert "несколько rc" in msg.lower()


def test_find_rc_for_service_returns_single_match():
    dpm = FakeDpm(
        raos=[{"id": 1, "name": "rao"}],
        rc_ids=[
            {"rc": 10, "version": "D-01.007.00_674"},
            {"rc": 99, "version": "D-01.006.00_270"},
        ],
    )
    rc_id, msg = dpm.find_rc_for_service(123, "D-01.007.00_674")
    assert rc_id == 10
    assert "Найден RC" in msg


def test_find_rc_for_service_no_matches():
    dpm = FakeDpm(
        raos=[{"id": 1, "name": "rao"}],
        rc_ids=[{"rc": 99, "version": "D-01.006.00_270"}],
    )
    rc_id, msg = dpm.find_rc_for_service(123, "D-01.007.00_674")
    assert rc_id is None
    assert "не найден" in msg.lower()

