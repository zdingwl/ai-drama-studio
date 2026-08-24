from __future__ import annotations

import sqlite3
from pathlib import Path

import sqlalchemy as sa

from engine.app.core.database import init_database


def test_f06_migration_creates_character_detection_tables(tmp_path: Path) -> None:
    database_path = init_database(tmp_path)
    engine = sa.create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        inspector = sa.inspect(engine)
        names = set(inspector.get_table_names())
        assert {"character_detection_runs", "character_candidates", "character_tracks"}.issubset(names)

        run_columns = {item["name"]: item for item in inspector.get_columns("character_detection_runs")}
        assert run_columns["source_edit_set_id"]["nullable"] is False
        assert run_columns["source_edit_set_revision"]["nullable"] is False
        assert run_columns["is_current"]["nullable"] is False
        assert run_columns["error_code"]["nullable"] is True

        candidate_columns = {item["name"]: item for item in inspector.get_columns("character_candidates")}
        assert candidate_columns["centroid_embedding_blob"]["nullable"] is False
        assert candidate_columns["cluster_score"]["nullable"] is True

        track_columns = {item["name"]: item for item in inspector.get_columns("character_tracks")}
        assert track_columns["final_shot_id"]["nullable"] is False
        assert track_columns["track_embedding_blob"]["nullable"] is False
        assert track_columns["samples_json"]["nullable"] is False

        indexes = {item["name"]: item for item in inspector.get_indexes("character_detection_runs")}
        assert indexes["uq_character_detection_current_project"]["unique"] == 1
    finally:
        engine.dispose()


def test_f06_database_head_is_0007(tmp_path: Path) -> None:
    database_path = init_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    assert revision == ("0007_create_character_detection",)
