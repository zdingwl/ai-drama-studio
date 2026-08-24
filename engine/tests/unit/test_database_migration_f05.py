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


def test_f05_revision_is_preserved_under_newer_database_head(tmp_path: Path) -> None:
    """F06+ 可以推进 Alembic head，但不能让 F05 表/迁移历史消失。"""

    database_path = init_database(tmp_path)
    with sqlite3.connect(database_path) as connection:
        current_head = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        f05_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='final_shots'"
        ).fetchone()
    assert current_head is not None
    assert current_head[0] >= "0006_create_final_shots"
    assert f05_table == ("final_shots",)
