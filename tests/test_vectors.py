"""The per-section vector store and its in-memory index, against the REAL
local embedding model. The only thing simulated is the model being
unavailable, to exercise the failure path."""

from sqlalchemy import select

from app import models
from app.database import SessionLocal
from app.services import embeddings
from tests.conftest import make_record_payload


def _vectors(record_id: int) -> dict[str, models.RecordVector]:
    db = SessionLocal()
    try:
        rows = db.scalars(select(models.RecordVector).where(models.RecordVector.record_id == record_id)).all()
        for row in rows:
            db.expunge(row)
        return {row.section: row for row in rows}
    finally:
        db.close()


def test_section_texts_cover_each_part_of_the_card():
    payload = make_record_payload(1)
    texts = embeddings.section_texts(payload)
    assert set(texts) == {"summary", "examination", "investigations", "course"}
    assert texts["summary"].startswith("Acute gastroenteritis with dehydration\nLoose stools")
    assert "IV RL 1 L 8 hourly 2 days" in texts["summary"]
    assert "Respiratory system: Clear, equal air entry" in texts["examination"]
    assert "Signs present: dehydration" in texts["examination"]
    assert "pallor" not in texts["examination"]  # absent signs are not embedded
    assert texts["investigations"] == "CBC normal"
    assert texts["course"] == "IV fluids, improved"
    empty = embeddings.section_texts({"diagnosis": "  ", "treatment_items": []})
    assert empty == {}


def test_unchanged_sections_are_not_re_embedded(client, patient):
    rid = client.post("/api/records", json=make_record_payload(patient["id"])).json()["id"]
    before = _vectors(rid)

    client.put(f"/api/records/{rid}", json=make_record_payload(patient["id"]))
    same = _vectors(rid)
    for section, row in before.items():
        assert same[section].vector == row.vector
        assert same[section].updated_at == row.updated_at

    client.put(f"/api/records/{rid}", json=make_record_payload(
        patient["id"], course_in_hospital="Required IV ondansetron, tolerated feeds by day 2",
    ))
    after = _vectors(rid)
    assert after["course"].text_hash != before["course"].text_hash
    assert after["course"].vector != before["course"].vector
    assert after["summary"].vector == before["summary"].vector


def test_clearing_a_section_removes_its_vector(client, patient):
    rid = client.post("/api/records", json=make_record_payload(patient["id"])).json()["id"]
    client.put(f"/api/records/{rid}", json=make_record_payload(patient["id"], investigations=None))
    assert "investigations" not in _vectors(rid)


def test_model_failure_drops_stale_vectors_and_backfill_restores(client, patient, monkeypatch):
    rid = client.post("/api/records", json=make_record_payload(patient["id"])).json()["id"]
    kept = _vectors(rid)["summary"].vector

    def unavailable(texts):
        raise embeddings.EmbeddingUnavailable("model offline (simulated)")

    monkeypatch.setattr(embeddings, "embed_texts", unavailable)
    resp = client.put(f"/api/records/{rid}", json=make_record_payload(
        patient["id"], course_in_hospital="Course rewritten while the model was offline",
    ))
    assert resp.status_code == 200  # saving never fails because embedding failed
    vectors = _vectors(rid)
    assert "course" not in vectors  # never left describing the old text
    assert vectors["summary"].vector == kept  # unchanged text kept its vector

    monkeypatch.undo()
    assert embeddings.backfill_missing_vectors() >= 1
    assert "course" in _vectors(rid)


def test_backfill_replaces_migrated_rows_without_a_text_hash(client, patient):
    rid = client.post("/api/records", json=make_record_payload(patient["id"])).json()["id"]
    db = SessionLocal()
    try:
        for row in db.scalars(select(models.RecordVector).where(models.RecordVector.record_id == rid)):
            if row.section == "summary":
                row.text_hash = ""  # how the migration copies the old column in
            else:
                db.delete(row)
        db.commit()
    finally:
        db.close()
    embeddings.backfill_missing_vectors()
    vectors = _vectors(rid)
    assert set(vectors) == {"summary", "examination", "investigations", "course"}
    assert all(len(v.text_hash) == 64 for v in vectors.values())


def test_index_follows_commits_soft_delete_and_restore(client, patient):
    payload = make_record_payload(
        patient["id"], diagnosis="Scorpion sting with autonomic storm",
        history="Stung on the foot while playing, profuse sweating and vomiting",
    )
    rid = client.post("/api/records", json=payload).json()["id"]
    db = SessionLocal()
    try:
        query = embeddings.embed_text(embeddings.record_text(payload))
        assert embeddings.rank_similar(db, query, limit=1)[0][0] == rid  # visible straight after commit

        client.delete(f"/api/records/{rid}")
        assert rid not in [i for i, _ in embeddings.rank_similar(db, query, limit=50)]

        client.post(f"/api/records/{rid}/restore")
        assert embeddings.rank_similar(db, query, limit=1)[0][0] == rid
    finally:
        db.close()


def test_rank_similar_filters_and_excludes(client, patient):
    draft = client.post("/api/records", json=make_record_payload(
        patient["id"], diagnosis="Rat bite fever", status="draft")).json()["id"]
    final = client.post("/api/records", json=make_record_payload(
        patient["id"], diagnosis="Rat bite fever")).json()["id"]
    db = SessionLocal()
    try:
        vec = embeddings.embed_text("Rat bite fever")
        only_final = embeddings.rank_similar(
            db, vec, limit=100, where=(models.DischargeRecord.status == "final",))
        ids = [i for i, _ in only_final]
        assert final in ids and draft not in ids
        assert final not in [i for i, _ in embeddings.rank_similar(
            db, vec, limit=100, exclude_record_id=final)]
    finally:
        db.close()


def test_corrupt_vector_is_skipped_not_fatal(client, patient):
    rid = client.post("/api/records", json=make_record_payload(patient["id"])).json()["id"]
    db = SessionLocal()
    try:
        row = db.get(models.RecordVector, (rid, "summary"))
        row.vector = b"\x00" * 12  # three floats: not this model's dimension
        row.text_hash = ""          # and marked stale, as a repair would find it
        db.commit()
        results = embeddings.rank_similar(db, embeddings.embed_text("gastroenteritis"), limit=500)
        assert rid not in [i for i, _ in results]
        assert results  # every other record still answers
    finally:
        db.close()
    embeddings.backfill_missing_vectors()
    assert len(_vectors(rid)["summary"].vector) > 12


def test_best_section_scores_reports_the_section(client, patient):
    rid = client.post("/api/records", json=make_record_payload(
        patient["id"], investigations="Lumbar puncture: CSF pleocytosis, low glucose, high protein",
    )).json()["id"]
    db = SessionLocal()
    try:
        best = embeddings.best_section_scores(
            db, embeddings.embed_text("Lumbar puncture: CSF pleocytosis, low glucose, high protein"),
            ("summary", "investigations"),
        )
        score, section = best[rid]
        assert section == "investigations" and score > 0.95
    finally:
        db.close()


def test_needs_refresh_detects_missing_stale_and_current():
    from app import config

    record = models.DischargeRecord(diagnosis="Measles", treatment_items=[])
    assert embeddings.needs_refresh(record)  # no vectors yet
    vector = models.RecordVector(section="summary", model="other-model",
                                 text_hash=embeddings.text_hash("Measles"), vector=b"")
    record.vectors.append(vector)
    assert embeddings.needs_refresh(record)  # another model
    vector.model = config.EMBEDDING_MODEL
    assert not embeddings.needs_refresh(record)
    record.diagnosis = "Measles with pneumonia"
    assert embeddings.needs_refresh(record)  # text changed
