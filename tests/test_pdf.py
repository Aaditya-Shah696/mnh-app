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


def test_pdf_exam_block_and_ward(client, patient):
    rid = client.post("/api/records", json=make_record_payload(
        patient["id"], pallor="yes",
    )).json()["id"]
    text = _pdf_text(client.get(f"/api/records/{rid}/pdf").content)
    assert "WARD" in text and "T/1" in text
    assert "IPD NUMBER" in text
    # All six signs print as pertinent negatives; ticked ones as Yes
    for label in ("PALLOR", "ICTERUS", "RASH", "CYANOSIS", "MENINGEAL", "DEHYDRATION"):
        assert label in text, label
    assert "Yes" in text and "No" in text
    assert "Others" in text
    assert "Systemic examination" in text
    assert "Throat findings:" in text
    assert "General examination:" in text
    client.delete(f"/api/records/{rid}")


def test_pdf_section_order(client, patient):
    """Diagnosis, then history, then examination findings - in that order,
    with the signs grouped under "Others" and the free-text exam fields
    grouped under "Systemic examination"."""
    rid = client.post("/api/records", json=make_record_payload(patient["id"])).json()["id"]
    text = _pdf_text(client.get(f"/api/records/{rid}/pdf").content)
    assert "Presenting complaints" not in text
    diag_pos = text.index("Diagnosis")
    history_pos = text.index("History")
    exam_pos = text.index("Examination findings")
    others_pos = text.index("Others")
    systemic_pos = text.index("Systemic examination")
    assert diag_pos < history_pos < exam_pos < others_pos < systemic_pos
    client.delete(f"/api/records/{rid}")


def test_pdf_warning_signs_always_printed(client, patient):
    rid = client.post("/api/records", json=make_record_payload(
        patient["id"], status="draft",
    )).json()["id"]
    text = _pdf_text(client.get(f"/api/records/{rid}/pdf").content)
    assert "Warning signs" in text
    assert "seek medical care immediately" in text
    assert "sooner if any of these appear" in text
    client.delete(f"/api/records/{rid}")


def test_pdf_letterhead_phone_allergies_gone(client, patient):
    rid = client.post("/api/records", json=make_record_payload(patient["id"])).json()["id"]
    text = _pdf_text(client.get(f"/api/records/{rid}/pdf").content)
    assert "Mahavir Nursing Home" not in text  # letterhead replaced by blank space
    assert "PHONE" not in text
    assert "ALLERGIES" not in text
    assert "WARD / BED" not in text
    client.delete(f"/api/records/{rid}")


def test_draft_watermark(client, patient):
    payload = make_record_payload(patient["id"], status="draft")
    rid = client.post("/api/records", json=payload).json()["id"]
    resp = client.get(f"/api/records/{rid}/pdf")
    assert "DRAFT" in _pdf_text(resp.content)
    client.delete(f"/api/records/{rid}")


def test_pdf_missing_record_404(client):
    assert client.get("/api/records/999999/pdf").status_code == 404
