import io

from app import config
from tests.conftest import make_record_payload


def _record_id(client, patient):
    return client.post("/api/records", json=make_record_payload(patient["id"])).json()["id"]


def test_upload_download_delete(client, patient):
    rid = _record_id(client, patient)
    content = b"%PDF-1.4 attachment bytes"
    up = client.post(
        f"/api/records/{rid}/attachments",
        files={"file": ("report.pdf", io.BytesIO(content), "application/pdf")},
    )
    assert up.status_code == 201
    aid = up.json()["id"]
    assert up.json()["original_name"] == "report.pdf"
    assert up.json()["size_bytes"] == len(content)

    down = client.get(f"/api/attachments/{aid}/download")
    assert down.status_code == 200
    assert down.content == content

    assert client.delete(f"/api/attachments/{aid}").status_code == 204
    assert client.get(f"/api/attachments/{aid}/download").status_code == 404
    client.delete(f"/api/records/{rid}")


def test_disallowed_type_rejected(client, patient):
    rid = _record_id(client, patient)
    resp = client.post(
        f"/api/records/{rid}/attachments",
        files={"file": ("evil.exe", io.BytesIO(b"MZ"), "application/x-msdownload")},
    )
    assert resp.status_code == 415
    client.delete(f"/api/records/{rid}")


def test_oversize_rejected(client, patient):
    # conftest caps attachments at 1 MB for tests
    rid = _record_id(client, patient)
    big = b"a" * (1024 * 1024 + 100)
    resp = client.post(
        f"/api/records/{rid}/attachments",
        files={"file": ("big.pdf", io.BytesIO(big), "application/pdf")},
    )
    assert resp.status_code == 413
    client.delete(f"/api/records/{rid}")


def test_upload_to_missing_record_404(client):
    resp = client.post(
        "/api/records/999999/attachments",
        files={"file": ("x.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
    )
    assert resp.status_code == 404


def test_deleting_record_removes_attachment_files_from_disk(client, patient):
    """Deleting a whole record must not leave lab reports/scans orphaned
    on disk after the DB rows are gone - those files are patient data."""
    rid = _record_id(client, patient)
    up = client.post(
        f"/api/records/{rid}/attachments",
        files={"file": ("scan.pdf", io.BytesIO(b"%PDF-1.4 scan"), "application/pdf")},
    )
    assert up.status_code == 201
    stored_path = config.ATTACHMENTS_DIR / _stored_name_of(client, rid, up.json()["id"])
    assert stored_path.exists()

    assert client.delete(f"/api/records/{rid}").status_code == 204
    assert not stored_path.exists()


def _stored_name_of(client, record_id, attachment_id):
    """The API never exposes stored_name directly (by design); recover it
    the same way a real client would - by resolving the download redirect
    target is not available in tests, so read it straight from the DB."""
    from app import models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        return db.get(models.Attachment, attachment_id).stored_name
    finally:
        db.close()
