import os
import subprocess
import sys
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app.database import Base

ROOT = Path(__file__).resolve().parent.parent


def _alembic(data_dir: Path, *args: str) -> str:
    env = dict(os.environ, DISCHARGE_DATA_DIR=str(data_dir))
    env.pop("DISCHARGE_DATABASE_URL", None)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ROOT / "alembic.ini"), *args],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_upgrade_matches_models_and_downgrade_round_trips(tmp_path):
    _alembic(tmp_path, "upgrade", "head")
    engine = create_engine(f"sqlite:///{tmp_path / 'discharge.db'}")
    try:
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        assert diff == []

        _alembic(tmp_path, "downgrade", "-1")
        columns = {c["name"] for c in inspect(engine).get_columns("discharge_records")}
        assert "diagnosis_codes" not in columns
        assert "record_vectors" in inspect(engine).get_table_names()

        _alembic(tmp_path, "downgrade", "b8d2e5f1c3a7")
        tables = inspect(engine).get_table_names()
        assert "record_vectors" not in tables and "login_failures" in tables
        assert "embedding" in {c["name"] for c in inspect(engine).get_columns("discharge_records")}

        _alembic(tmp_path, "downgrade", "base")
        _alembic(tmp_path, "upgrade", "head")
        assert {"login_failures", "record_vectors"} <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_record_vectors_migration_carries_existing_embeddings(tmp_path):
    """Embeddings written under the old single-column schema survive the
    upgrade (as stale "summary" vectors) and come back on downgrade."""
    import sqlite3

    _alembic(tmp_path, "upgrade", "b8d2e5f1c3a7")
    db_path = tmp_path / "discharge.db"
    blob = bytes(range(16)) * 96  # 384 float32s worth of bytes
    con = sqlite3.connect(db_path)
    try:
        con.execute("INSERT INTO patients (id, name, created_at, updated_at) "
                    "VALUES (1, 'Migration Child', '2026-01-01', '2026-01-01')")
        con.execute("INSERT INTO discharge_records (id, patient_id, status, embedding, embedding_model, "
                    "created_at, updated_at) VALUES (1, 1, 'final', ?, 'BAAI/bge-small-en-v1.5', "
                    "'2026-01-01', '2026-01-01')", (blob,))
        con.execute("INSERT INTO discharge_records (id, patient_id, status, created_at, updated_at) "
                    "VALUES (2, 1, 'draft', '2026-01-01', '2026-01-01')")
        con.commit()
    finally:
        con.close()

    _alembic(tmp_path, "upgrade", "head")
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute("SELECT record_id, section, model, text_hash, vector FROM record_vectors").fetchall()
        assert rows == [(1, "summary", "BAAI/bge-small-en-v1.5", "", blob)]
        columns = {r[1] for r in con.execute("PRAGMA table_info(discharge_records)")}
        assert "embedding" not in columns and "embedding_model" not in columns
    finally:
        con.close()

    _alembic(tmp_path, "downgrade", "b8d2e5f1c3a7")
    con = sqlite3.connect(db_path)
    try:
        assert con.execute("SELECT id, embedding, embedding_model FROM discharge_records ORDER BY id").fetchall() == [
            (1, blob, "BAAI/bge-small-en-v1.5"), (2, None, None),
        ]
    finally:
        con.close()
