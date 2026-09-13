"""Security headers, no-store, CSRF Origin check, docs disabled in production."""
from app import config, middleware


def test_security_headers_on_api_and_index(client):
    api = client.get("/api/health")
    assert api.headers["x-content-type-options"] == "nosniff"
    assert api.headers["x-frame-options"] == "DENY"
    assert api.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in api.headers["content-security-policy"]
    assert "camera=()" in api.headers["permissions-policy"]
    assert api.headers["cache-control"] == "no-store"

    index = client.get("/")
    assert index.status_code == 200
    assert "content-security-policy" in index.headers
    assert index.headers.get("cache-control") != "no-store"  # static shell may cache


def test_health_reports_running_commit(anon_client, monkeypatch):
    """CI verifies a deploy by comparing this to the pushed SHA."""
    import re

    from app import version

    body = anon_client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["version"] == version.GIT_SHA
    assert body["version"] == "unknown" or re.fullmatch(r"[0-9a-f]{40}", body["version"])
    # The deploy script sets DISCHARGE_GIT_SHA explicitly; it wins over git.
    monkeypatch.setenv("DISCHARGE_GIT_SHA", "f" * 40)
    assert version._detect() == "f" * 40


def test_pdf_is_no_store(client, patient):
    from tests.conftest import make_record_payload

    rid = client.post("/api/records", json=make_record_payload(patient["id"])).json()["id"]
    pdf = client.get(f"/api/records/{rid}/pdf")
    assert pdf.status_code == 200
    assert pdf.headers["cache-control"] == "no-store"


def test_cross_site_origin_rejected(client):
    r = client.post("/api/patients", json={"name": "Evil"},
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert "Cross-site" in r.json()["detail"]
    r = client.post("/api/patients", json={"name": "Evil"}, headers={"Origin": "null"})
    assert r.status_code == 403


def test_same_origin_and_public_origin_allowed(client):
    ok = client.post("/api/patients", json={"name": "Same Origin"},
                     headers={"Origin": "https://testserver"})
    assert ok.status_code == 201
    ok = client.post("/api/patients", json={"name": "Public Origin"},
                     headers={"Origin": config.PUBLIC_ORIGIN.upper()})
    assert ok.status_code == 201


def test_sec_fetch_site_cross_site_rejected(client):
    r = client.post("/api/patients", json={"name": "Evil"},
                    headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    ok = client.post("/api/patients", json={"name": "Fine"},
                     headers={"Sec-Fetch-Site": "same-origin"})
    assert ok.status_code == 201


def test_get_is_never_csrf_checked(client):
    r = client.get("/api/records", headers={"Origin": "https://evil.example"})
    assert r.status_code == 200


def test_login_itself_is_origin_checked(anon_client):
    from tests.conftest import ADMIN

    r = anon_client.post("/api/auth/login", json={
        "username": ADMIN["username"], "password": ADMIN["password"],
    }, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_origin_check_helper_direct():
    class Req:
        def __init__(self, headers):
            self.headers = headers
    assert middleware._origin_allowed(Req({}))
    assert middleware._origin_allowed(Req({"origin": "https://clinic.test", "host": "clinic.test"}))
    assert not middleware._origin_allowed(Req({"origin": "https://other.test", "host": "clinic.test"}))
    assert middleware._origin_allowed(Req({"sec-fetch-site": "none"}))
    assert not middleware._origin_allowed(Req({"sec-fetch-site": "same-site"}))


def test_docs_disabled_in_production(monkeypatch):
    """Rebuilding the app object with DISCHARGE_ENV=production drops /docs."""
    import importlib

    from app import config as cfg
    monkeypatch.setattr(cfg, "IS_PRODUCTION", True)
    import app.main as main_module
    importlib.reload(main_module)
    try:
        from fastapi.testclient import TestClient
        with TestClient(main_module.app, base_url="https://testserver") as c:
            assert c.get("/docs").status_code == 404
            assert c.get("/openapi.json").status_code == 404
            assert c.get("/api/health").status_code == 200
    finally:
        monkeypatch.setattr(cfg, "IS_PRODUCTION", False)
        importlib.reload(main_module)
