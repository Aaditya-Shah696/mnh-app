import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pyzipper
import pytest

from app import config
from app.services import backup
from tests.conftest import make_record_payload


def test_backup_and_restore_cycle(client, patient, tmp_path):
    rid = client.post("/api/records", json=make_record_payload(patient["id"])).json()["id"]

    archive = backup.create_backup()
    assert archive.exists()
    assert archive.stat().st_size > 1000

    password = backup.get_or_create_password()

    with pytest.raises(Exception):
        backup.restore_backup(archive, tmp_path / "bad", "not-the-password")

    restored = backup.restore_backup(archive, tmp_path / "good", password)
    assert "discharge.db" in restored

    con = sqlite3.connect(tmp_path / "good" / "discharge.db")
    try:
        count = con.execute(
            "SELECT COUNT(*) FROM discharge_records WHERE id=?", (rid,)
        ).fetchone()[0]
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        con.close()
    assert count == 1
    assert integrity == "ok"

    client.delete(f"/api/records/{rid}")


def test_backup_status_endpoint(client):
    backup.create_backup()
    status = client.get("/api/backup/status").json()
    assert status["backup_count"] >= 1
    assert status["last_backup"] is not None


def test_manual_backup_endpoint(client):
    resp = client.post("/api/backup")
    assert resp.status_code == 201
    assert resp.json()["file"].startswith("discharge_backup_")


@pytest.mark.parametrize("entry_name", [
    "C:/Windows/Temp/evil.txt",       # Windows drive-anchored absolute path
    "C:\\Windows\\Temp\\evil.txt",    # same, backslash form
    "../../../evil.txt",              # classic zip-slip traversal
])
def test_restore_rejects_path_escaping_entries(tmp_path, entry_name):
    """A crafted archive must never write outside the chosen target_dir.
    Path("target") / "C:/evil" silently discards "target" on Windows, so a
    naive prefix check is not enough - restore_backup must resolve() and
    verify containment."""
    password = "test-password"
    archive = tmp_path / "malicious.zip"
    with pyzipper.AESZipFile(
        archive, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES,
    ) as zf:
        zf.setpassword(password.encode("utf-8"))
        zf.writestr(entry_name, b"payload")

    target = tmp_path / "restore_target"
    with pytest.raises(ValueError, match="Unsafe path"):
        backup.restore_backup(archive, target, password)

    # Nothing should have been written outside the intended target.
    escaped = tmp_path / "evil.txt"
    assert not escaped.exists()


@pytest.mark.parametrize("bad", [
    "C:/Windows/Temp/evil.txt", "C:\\evil.txt", "c:evil.txt",
    "../evil.txt", "a/../../evil.txt", "..", "a/..", "",
])
def test_safe_member_path_rejects_on_every_platform(bad):
    """The guard is platform-independent: CI runs on Linux, where a
    drive-anchored name would otherwise be accepted as a relative path."""
    with pytest.raises(ValueError, match="Unsafe path"):
        backup.safe_member_path(bad)


@pytest.mark.parametrize("ok,expected", [
    ("discharge.db", "discharge.db"),
    ("attachments/x.pdf", "attachments/x.pdf"),
    ("attachments\\x.pdf", "attachments/x.pdf"),
    ("/etc/evil.txt", "etc/evil.txt"),
    ("a/./b", "a/./b"),
])
def test_safe_member_path_accepts_normal_entries(ok, expected):
    assert backup.safe_member_path(ok) == expected


def test_restore_contains_leading_slash_entries_inside_target(tmp_path):
    """A POSIX absolute-looking entry ("/etc/evil.txt") isn't a traversal
    once the leading slash is stripped - it must land safely inside
    target_dir rather than being silently dropped or raising."""
    password = "test-password"
    archive = tmp_path / "leading_slash.zip"
    with pyzipper.AESZipFile(
        archive, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES,
    ) as zf:
        zf.setpassword(password.encode("utf-8"))
        zf.writestr("/etc/evil.txt", b"payload")

    target = tmp_path / "restore_target"
    restored = backup.restore_backup(archive, target, password)

    assert restored == ["etc/evil.txt"]
    assert (target / "etc" / "evil.txt").read_bytes() == b"payload"
    assert not (tmp_path / "evil.txt").exists()


def _leftovers():
    return sorted(
        p.name for p in config.BACKUPS_DIR.iterdir()
        if not (p.name.startswith(backup.BACKUP_PREFIX) and p.suffix == ".zip")
    )


def test_archives_appear_atomically_and_failures_leave_nothing(monkeypatch):
    before = backup.list_backups()
    archive = backup.create_backup()
    assert archive in backup.list_backups()
    assert _leftovers() == []

    def explode(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(backup.json, "dumps", explode)
    with pytest.raises(RuntimeError, match="disk full"):
        backup.create_backup()
    assert _leftovers() == []
    assert len(backup.list_backups()) == len(before) + 1


def _child_env():
    return dict(
        os.environ,
        DISCHARGE_DATA_DIR=str(config.DATA_DIR),
        DISCHARGE_BACKUP_DIR=str(config.BACKUPS_DIR),
    )


def test_backups_in_separate_processes_never_overlap():
    root = Path(__file__).resolve().parent.parent
    holder = subprocess.Popen(
        [sys.executable, "-c", (
            "import sys, time; sys.path.insert(0, sys.argv[1]); "
            "from app.services import backup; "
            "ctx = backup._interprocess_lock(); ctx.__enter__(); "
            "print('locked', flush=True); time.sleep(2.5); ctx.__exit__(None, None, None)"
        ), str(root)],
        stdout=subprocess.PIPE, text=True, env=_child_env(),
    )
    try:
        assert holder.stdout.readline().strip() == "locked"
        started = time.monotonic()
        backup.create_backup()
        waited = time.monotonic() - started
    finally:
        holder.wait(timeout=30)
    assert holder.returncode == 0
    assert waited >= 1.5


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_password_file_is_owner_only(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    backup.get_or_create_password()
    mode = (tmp_path / "backup_password.txt").stat().st_mode & 0o777
    assert mode == 0o600


def test_restore_script_reads_the_password_from_a_file(tmp_path):
    archive = backup.create_backup()
    secret = tmp_path / "pw.txt"
    secret.write_text(backup.get_or_create_password() + "\n", encoding="utf-8")
    root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "restore_backup.py"), str(archive),
         str(tmp_path / "out"), "--password-file", str(secret)],
        capture_output=True, text=True, env=_child_env(),
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "out" / "discharge.db").exists()
    assert backup.get_or_create_password() not in result.stdout + result.stderr
