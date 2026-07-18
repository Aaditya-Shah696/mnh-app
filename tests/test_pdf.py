import io

from pypdf import PdfReader

from tests.conftest import make_record_payload


def _pdf_text(pdf: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf))
    return "\n".join(page.extract_text() for page in reader.pages)


def test_pdf_generation(client, patient):
    rid = client.post("/api/records", json=make_record_payload(patient["id"]))
    rid = rid.json()["id"]
    resp = client.get(f"/api/records/{rid}/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "discharge_Test_Patient" in resp.headers["content-disposition"]
    pdf = resp.content
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 2000
    text = _pdf_text(pdf)
    assert "Test Patient" in text
    assert "DISCHARGE CARD" in text
    assert "Acute gastroenteritis with dehydration" in text
    assert "ORS sachet" in text
    assert "DRAFT" not in text  # record is final
    client.delete(f"/api/records/{rid}")


def test_draft_watermark(client, patient):
    payload = make_record_payload(patient["id"], status="draft")
    rid = client.post("/api/records", json=payload).json()["id"]
    resp = client.get(f"/api/records/{rid}/pdf")
    assert "DRAFT" in _pdf_text(resp.content)
    client.delete(f"/api/records/{rid}")


def test_pdf_missing_record_404(client):
    assert client.get("/api/records/999999/pdf").status_code == 404
