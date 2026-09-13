"""HTTP middleware: security headers, no-store on the API, and the CSRF
Origin check.

CSRF reasoning: the UI is a same-origin SPA with a SameSite=Strict cookie.
Browsers always send `Origin` on cross-site non-GET requests and modern
ones send `Sec-Fetch-Site` on everything, so refusing a mismatching
Origin (or a non-same-origin Sec-Fetch-Site) blocks every cross-site
write without token plumbing. Requests carrying neither header come from
non-browser clients (tests, scripts) that cannot be CSRF'd and are allowed.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import config

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; object-src 'self'; base-uri 'self'; frame-ancestors 'none'; "
    "form-action 'self'"
)


def _origin_allowed(request: Request) -> bool:
    origin = request.headers.get("origin")
    if origin is not None:
        origin = origin.strip().lower().rstrip("/")
        if origin == "null":
            return False
        if config.PUBLIC_ORIGIN and origin == config.PUBLIC_ORIGIN:
            return True
        host = (request.headers.get("host") or "").strip().lower()
        return bool(host) and urlsplit(origin).netloc == host
    fetch_site = request.headers.get("sec-fetch-site")
    if fetch_site is not None:
        return fetch_site.strip().lower() in ("same-origin", "none")
    return True


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def csrf_origin_check(request: Request, call_next):
        if (
            request.method not in SAFE_METHODS
            and request.url.path.startswith("/api/")
            and not _origin_allowed(request)
        ):
            return JSONResponse(
                status_code=403, content={"detail": "Cross-site request rejected"}
            )
        return await call_next(request)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "no-referrer")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        h.setdefault("Content-Security-Policy", CSP)
        if request.url.path.startswith("/api/"):
            # Patient data must never sit in a browser or proxy cache.
            h["Cache-Control"] = "no-store"
            h.setdefault("Pragma", "no-cache")
        return response
