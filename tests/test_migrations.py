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
        assert "login_failures" not in inspect(engine).get_table_names()

        _alembic(tmp_path, "downgrade", "base")
        _alembic(tmp_path, "upgrade", "head")
        assert "login_failures" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
