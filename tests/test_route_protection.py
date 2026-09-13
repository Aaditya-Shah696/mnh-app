"""Every /api route outside the public allowlist must refuse anonymous
requests, and admin-only routes must refuse staff. Walks the live route
table so a new router cannot be added unprotected without failing here."""
import pytest
from fastapi.routing import APIRoute

from app.main import PUBLIC_API_PATHS, app

ADMIN_ONLY = {
    ("DELETE", "/api/records/{record_id}"),
    ("POST", "/api/records/{record_id}/restore"),
    ("DELETE", "/api/patients/{patient_id}"),
    ("POST", "/api/patients/{patient_id}/restore"),
    ("POST", "/api/backup"),
    ("GET", "/api/users"),
    ("POST", "/api/users"),
    ("PATCH", "/api/users/{user_id}"),
    ("POST", "/api/users/{user_id}/reset-password"),
    ("GET", "/api/audit"),
    ("GET", "/api/audit/actions"),
}


def _walk(routes):
    """Yield every APIRoute, descending into included routers. FastAPI
    0.139+ keeps included routers as a wrapper object in app.routes."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
            continue
        inner = getattr(route, "original_router", None) or getattr(route, "router", None)
        if inner is not None and hasattr(inner, "routes"):
            yield from _walk(inner.routes)


def _api_routes():
    for route in _walk(app.routes):
        if not route.path.startswith("/api/"):
            continue
        for method in route.methods:
            if method in ("HEAD", "OPTIONS"):
                continue
            yield method, route.path


def test_route_walker_sees_every_router():
    paths = {p for _, p in _api_routes()}
    for expected in ("/api/auth/login", "/api/users", "/api/audit", "/api/patients",
                     "/api/records", "/api/match", "/api/backup", "/api/health"):
        assert expected in paths, expected
    assert len(paths) >= 20


def _fill(path: str) -> str:
    return path.replace("{record_id}", "1").replace("{patient_id}", "1").replace("{user_id}", "1")


@pytest.mark.parametrize("method,path", sorted(_api_routes()))
def test_anonymous_is_refused(anon_client, method, path):
    resp = anon_client.request(method, _fill(path), json={})
    if path in PUBLIC_API_PATHS:
        assert resp.status_code != 401, f"{method} {path} should be public"
    else:
        assert resp.status_code == 401, f"{method} {path} answered {resp.status_code} anonymously"
        assert resp.headers.get("cache-control") == "no-store"


@pytest.mark.parametrize("method,path", sorted(ADMIN_ONLY))
def test_staff_is_refused_on_admin_routes(staff_client, method, path):
    resp = staff_client.request(method, _fill(path), json={})
    assert resp.status_code == 403, f"{method} {path} answered {resp.status_code} for staff"


def test_admin_only_set_is_complete():
    """Any route that declares require_admin must be listed above, so the
    staff test actually covers it."""
    from app import auth

    declared = set()
    for route in _walk(app.routes):
        deps = [d.call for d in route.dependant.dependencies]
        for dep in route.dependant.dependencies:
            deps.extend(d.call for d in dep.dependencies)
        if auth.require_admin in deps:
            for method in route.methods - {"HEAD", "OPTIONS"}:
                declared.add((method, route.path))
    assert declared == ADMIN_ONLY


def test_public_paths_are_only_the_three():
    assert PUBLIC_API_PATHS == {"/api/health", "/api/auth/login", "/api/clinic"}
