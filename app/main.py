from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .routers import backups, matches, patients, records
from .services import backup, embeddings

STATIC_DIR = Path(__file__).resolve().parent / "static"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.ensure_dirs()
    # Embed any records saved while the model was unavailable.
    embeddings.start_backfill_thread()
    # Daily encrypted backup while the app runs.
    backup.start_backup_scheduler()
    yield


app = FastAPI(title="MNH Discharge Records", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; object-src 'self'; base-uri 'self'",
    )
    return response


app.include_router(patients.router)
app.include_router(records.router)
app.include_router(matches.router)
app.include_router(backups.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/clinic")
def clinic() -> dict:
    return config.clinic_info()


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
