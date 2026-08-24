from __future__ import annotations

import sqlite3
from pathlib import Path

import sqlalchemy as sa

from engine.app.core.database import init_database


def test_f04_migration_creates_detection_tables_and_constraints(tmp_path: Path) -> None:
    database_path = init_database(tmp_path)
    engine = sa.create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        inspector = sa.inspect(engine)
        assert "shot_detection_runs" in inspector.get_table_names()
        assert "shot_candidates" in inspector.get_table_names()

        run_columns = {column["name"]: column for column in inspector.get_columns("shot_detection_runs")}
        assert run_columns["detector_name"]["nullable"] is False
        assert run_columns["proxy_sha256_snapshot"]["nullable"] is False
        assert run_columns["proxy_start_us"]["nullable"] is True
        assert run_columns["analyzed_frame_count"]["nullable"] is True

        candidate_columns = {column["name"]: column for column in inspector.get_columns("shot_candidates")}
        assert candidate_columns["ordinal"]["nullable"] is False
        assert candidate_columns["end_boundary_score"]["nullable"] is True

        run_uniques = inspector.get_unique_constraints("shot_detection_runs")
        assert any(constraint["column_names"] == ["project_id"] for constraint in run_uniques)

        candidate_uniques = inspector.get_unique_constraints("shot_candidates")
        assert any(
            constraint["column_names"] == ["detection_id", "ordinal"]
            for constraint in candidate_uniques
        )
    finally:
        engine.dispose()


def test_f04_database_head_is_0005(tmp_path: Path) -> None:
    database_path = init_database(tmp_path)

    with sqlite3.connect(database_path) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()

    assert revision == ("0005_create_shot_detection",)
