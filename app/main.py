from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import auth, config, middleware, version
from .routers import audit as audit_router
from .routers import auth as auth_router
from .routers import backups, matches, patients, records, users
from .services import backup, embeddings

STATIC_DIR = Path(__file__).resolve().parent / "static"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.ensure_dirs()
    auth.warn_if_insecure_config()
    # Embed any records saved while the model was unavailable.
    embeddings.start_backfill_thread()
    # Daily encrypted backup while the app runs.
    backup.start_backup_scheduler()
    # Drop sessions that can never authenticate again.
    auth.start_session_pruner()
    yield


app = FastAPI(
    title="MNH Discharge Records",
    version="0.2.0",
    lifespan=lifespan,
    # Interactive API docs are a convenience for development only.
    docs_url=None if config.IS_PRODUCTION else "/docs",
    redoc_url=None if config.IS_PRODUCTION else "/redoc",
    openapi_url=None if config.IS_PRODUCTION else "/openapi.json",
)

middleware.install(app)

# Every API router below declares its own auth dependency; tests walk the
# route table to prove that nothing outside PUBLIC_API_PATHS answers
# without a session.
app.include_router(auth_router.router)
app.include_router(users.router)
app.include_router(audit_router.router)
app.include_router(patients.router)
app.include_router(records.router)
app.include_router(matches.router)
app.include_router(backups.router)

PUBLIC_API_PATHS = frozenset({"/api/health", "/api/auth/login", "/api/clinic"})


@app.get("/api/health")
def health() -> dict:
    """Liveness plus the running commit, so CI can verify a deployment
    landed. The SHA of a private repository reveals nothing useful."""
    return {"status": "ok", "version": version.GIT_SHA}


@app.get("/api/clinic")
def clinic() -> dict:
    """Letterhead details. Public: the login page shows the clinic name."""
    return config.clinic_info()


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
