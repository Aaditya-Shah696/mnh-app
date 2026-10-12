"""Encrypted backups of the database, attachments, and clinic config.

Design:
- AES-256 encrypted zip (pyzipper). The password lives in
  data/backup_password.txt; it is generated once on first backup and
  must also be written down somewhere OUTSIDE this computer, because a
  backup cannot be opened without it.
- The SQLite file is snapshotted with the sqlite3 backup API so the
  backup is consistent even while the app is writing.
- An in-app scheduler thread runs a backup when the newest one is older
  than config.BACKUP_INTERVAL_HOURS.
- Retention: the newest KEEP_BACKUPS archives are kept, older pruned.
- Point DISCHARGE_BACKUP_DIR at an external or synced drive so backups
  leave the machine.
"""
from __future__ import annotations

import json
import logging
import ntpath
import os
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pyzipper

from .. import config

logger = logging.getLogger(__name__)

KEEP_BACKUPS = 30
BACKUP_PREFIX = "discharge_backup_"
_backup_lock = threading.Lock()


def _password_file() -> Path:
    return config.DATA_DIR / "backup_password.txt"


def get_or_create_password() -> str:
    path = _password_file()
    if path.exists():
        password = path.read_text(encoding="utf-8").strip()
        if password:
            return password
    password = secrets.token_urlsafe(24)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(password + "\n")
    logger.warning(
        "Generated new backup password at %s. Write it down somewhere safe "
        "OUTSIDE this computer; backups cannot be opened without it.", path
    )
    return password


def _snapshot_db() -> bytes:
    """Consistent point-in-time copy of the SQLite DB via the backup API."""
    src = sqlite3.connect(config.DB_PATH)
    dest = sqlite3.connect(":memory:")
    try:
        src.backup(dest)
        return dest.serialize()
    finally:
        dest.close()
        src.close()


@contextmanager
def _interprocess_lock():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.DATA_DIR / ".backup.lock", "a+b") as handle:
        if os.name == "nt":
            import msvcrt

            while True:
                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    continue
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def list_backups() -> list[Path]:
    if not config.BACKUPS_DIR.exists():
        return []
    return sorted(config.BACKUPS_DIR.glob(f"{BACKUP_PREFIX}*.zip"))


def last_backup_time() -> datetime | None:
    backups = list_backups()
    if not backups:
        return None
    return datetime.fromtimestamp(backups[-1].stat().st_mtime)


def _archive_path() -> Path:
    while True:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = config.BACKUPS_DIR / f"{BACKUP_PREFIX}{stamp}.zip"
        if not path.exists():
            return path
        time.sleep(1)


def create_backup() -> Path:
    """Write an encrypted backup archive; returns its path."""
    with _backup_lock, _interprocess_lock():
        config.ensure_dirs()
        password = get_or_create_password()
        out_path = _archive_path()
        part_path = out_path.with_name(f".{out_path.name}.part")

        db_bytes = _snapshot_db()
        try:
            with pyzipper.AESZipFile(
                part_path, "w",
                compression=pyzipper.ZIP_DEFLATED,
                encryption=pyzipper.WZ_AES,
            ) as zf:
                zf.setpassword(password.encode("utf-8"))
                zf.writestr("discharge.db", db_bytes)
                clinic_path = config.DATA_DIR / "clinic.json"
                if clinic_path.exists():
                    zf.writestr("clinic.json", clinic_path.read_bytes())
                if config.ATTACHMENTS_DIR.exists():
                    for file in sorted(config.ATTACHMENTS_DIR.iterdir()):
                        if file.is_file():
                            zf.write(file, f"attachments/{file.name}")
                manifest = {
                    "created": datetime.now().isoformat(timespec="seconds"),
                    "app": "discharge-mnh",
                    "schema": "see alembic_version table inside discharge.db",
                }
                zf.writestr("manifest.json", json.dumps(manifest, indent=2))
            with open(part_path, "rb+") as handle:
                os.fsync(handle.fileno())
            os.replace(part_path, out_path)
        except BaseException:
            part_path.unlink(missing_ok=True)
            raise

        _prune_old()
        logger.info("Backup written: %s (%.1f MB)", out_path,
                    out_path.stat().st_size / 1e6)
        return out_path


def _prune_old() -> None:
    backups = list_backups()
    for old in backups[:-KEEP_BACKUPS]:
        try:
            old.unlink()
            logger.info("Pruned old backup %s", old.name)
        except OSError:
            logger.warning("Could not prune %s", old)


def safe_member_path(name: str) -> str:
    """Normalise an archive entry name to a relative POSIX path, or raise.

    Rejected on EVERY platform, not only where they would actually escape:
    drive-anchored names ("C:/...", "C:\\..."), and any ".." component.
    On Linux, `Path("target") / "C:/evil"` is merely a relative path inside
    target, so a containment check alone would accept an entry that on
    Windows resolves to C:\\evil. Our own archives never contain either
    form, so refusing them costs nothing. A leading slash is stripped:
    "/etc/x" restores to "target/etc/x", which is harmless.
    """
    clean = name.replace("\\", "/").lstrip("/")
    if ntpath.splitdrive(clean)[0]:
        raise ValueError(f"Unsafe path in archive: {name}")
    parts = clean.split("/")
    if not clean or any(part == ".." for part in parts):
        raise ValueError(f"Unsafe path in archive: {name}")
    return clean


def restore_backup(archive: Path, target_dir: Path, password: str) -> list[str]:
    """Extract a backup into target_dir and verify DB integrity.
    Returns the list of restored file names. Never writes into the live
    data directory; the caller chooses the target.

    Every entry path is resolved and checked to still be inside
    target_dir before writing. A string-prefix check alone is not
    enough: on Windows, `Path("target") / "C:/evil"` silently discards
    "target" and resolves to "C:/evil" because the joined segment looks
    like a drive-anchored absolute path. A crafted archive entry named
    "C:/Windows/..." (or a UNC path, or a "../.." traversal) would
    otherwise write outside target_dir entirely.
    """
    restored: list[str] = []
    target_dir = target_dir.resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    with pyzipper.AESZipFile(archive) as zf:
        zf.setpassword(password.encode("utf-8"))
        for name in zf.namelist():
            clean = safe_member_path(name)
            dest = (target_dir / clean).resolve()
            if dest != target_dir and target_dir not in dest.parents:
                raise ValueError(f"Unsafe path in archive: {name}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(name))
            restored.append(clean)

    db_file = target_dir / "discharge.db"
    if db_file.exists():
        con = sqlite3.connect(db_file)
        try:
            result = con.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            con.close()
        if result != "ok":
            raise RuntimeError(f"Restored database failed integrity check: {result}")
    return restored


def _scheduler_loop() -> None:
    while True:
        try:
            last = last_backup_time()
            due = (
                last is None
                or (datetime.now() - last).total_seconds()
                >= config.BACKUP_INTERVAL_HOURS * 3600
            )
            if due and config.DB_PATH.exists():
                create_backup()
        except Exception:  # noqa: BLE001
            logger.exception("Automatic backup failed")
        time.sleep(3600)


def start_backup_scheduler() -> None:
    threading.Thread(target=_scheduler_loop, daemon=True).start()
