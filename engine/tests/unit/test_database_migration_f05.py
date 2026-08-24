from __future__ import annotations

import sqlite3
from pathlib import Path

import sqlalchemy as sa

from engine.app.core.database import init_database


def test_f05_migration_creates_final_shot_tables(tmp_path: Path) -> None:
    database_path = init_database(tmp_path)
    engine = sa.create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        inspector = sa.inspect(engine)
        assert "shot_edit_sets" in inspector.get_table_names()
        assert "final_shots" in inspector.get_table_names()

        edit_columns = {column["name"]: column for column in inspector.get_columns("shot_edit_sets")}
        assert edit_columns["source_detection_id"]["nullable"] is False
        assert edit_columns["confirmed_at"]["nullable"] is True

        shot_columns = {column["name"]: column for column in inspector.get_columns("final_shots")}
        assert shot_columns["final_start_us"]["nullable"] is False
        assert shot_columns["origin_candidate_ids_json"]["nullable"] is False

        edit_uniques = inspector.get_unique_constraints("shot_edit_sets")
        assert any(item["column_names"] == ["project_id"] for item in edit_uniques)
        shot_uniques = inspector.get_unique_constraints("final_shots")
        assert any(item["column_names"] == ["edit_set_id", "ordinal"] for item in shot_uniques)
    finally:
        engine.dispose()


def test_f05_database_head_is_0006(tmp_path: Path) -> None:
    database_path = init_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    assert revision == ("0006_create_final_shots",)
