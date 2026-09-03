from __future__ import annotations

from pathlib import Path
import sqlite3

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from engine.app import studio_v2, target_dialogue_v1
from scripts import migrate_target_dialogue_current_v1 as migration


def _temp_factory(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'studio_v2.sqlite3').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    studio_v2.Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _seed_project(factory, tmp_path: Path) -> tuple[str, str]:
    project_id = "PROJECT_CURRENT_HISTORY"
    episode_id = "EP_CURRENT_HISTORY"
    with factory() as session:
        session.add(studio_v2.Project(
            id=project_id,
            name="Current history migration",
            source_language="zh-CN",
            target_language="en-US",
            target_region="US",
        ))
        session.add(studio_v2.Episode(
            id=episode_id,
            project_id=project_id,
            title="第一集",
            original_filename="ep1.mp4",
            source_path=str(tmp_path / "ep1.mp4"),
            source_sha256="0" * 64,
            sort_order=1,
            status="READY",
        ))
        session.commit()
    return project_id, episode_id


def _dialogue(
    *,
    row_id: str,
    project_id: str,
    episode_id: str,
    source_key: str,
    fingerprint: str,
) -> target_dialogue_v1.TargetDialogue:
    return target_dialogue_v1.TargetDialogue(
        id=row_id,
        project_id=project_id,
        episode_id=episode_id,
        shot_key=f"{episode_id}:SHOT_1",
        source_dialogue_key=source_key,
        source_dialogue_signature="1" * 64,
        source_fingerprint=fingerprint,
        source_start_us=1_000_000,
        source_end_us=2_000_000,
        source_text="测试对白",
        target_language="en-US",
        target_region="US",
        decision_source="AI",
        status="READY",
        audio_status="PENDING",
    )


def test_rows_for_source_keys_filters_fingerprint_at_sql_boundary(tmp_path: Path) -> None:
    _engine, factory = _temp_factory(tmp_path)
    project_id, episode_id = _seed_project(factory, tmp_path)
    source_key = f"{episode_id}:RUN_2:DG:UTTERANCE_1"

    with factory() as session:
        session.add(_dialogue(
            row_id="TARGETDIALOGUE_HISTORY_SAME_KEY",
            project_id=project_id,
            episode_id=episode_id,
            source_key=source_key,
            fingerprint="0" * 64,
        ))
        session.commit()

        current_rows = target_dialogue_v1._rows_for_source_keys(
            session,
            project_id,
            {source_key},
            fingerprint="a" * 64,
        )
        historical_rows = target_dialogue_v1._rows_for_source_keys(
            session,
            project_id,
            {source_key},
            fingerprint="0" * 64,
        )

    assert current_rows == []
    assert [row.id for row in historical_rows] == ["TARGETDIALOGUE_HISTORY_SAME_KEY"]


def test_real_sqlite_inspection_keeps_history_but_counts_only_current(monkeypatch, tmp_path: Path) -> None:
    _engine, factory = _temp_factory(tmp_path)
    project_id, episode_id = _seed_project(factory, tmp_path)
    current_key = f"{episode_id}:RUN_2:DG:UTTERANCE_1"
    history_key = f"{episode_id}:REV_1:H1:D1"
    fingerprint = "a" * 64

    with factory() as session:
        session.add(_dialogue(
            row_id="TARGETDIALOGUE_HISTORY",
            project_id=project_id,
            episode_id=episode_id,
            source_key=history_key,
            fingerprint="0" * 64,
        ))
        session.add(_dialogue(
            row_id="TARGETDIALOGUE_CURRENT",
            project_id=project_id,
            episode_id=episode_id,
            source_key=current_key,
            fingerprint=fingerprint,
        ))
        session.commit()

    snapshot = {
        "project_id": project_id,
        "source_fingerprint": fingerprint,
        "source_dialogue_count": 1,
        "episodes": [{
            "episode_id": episode_id,
            "source_dialogue_utterances": [{"dialogue_group_id": current_key}],
        }],
    }
    monkeypatch.setattr(migration, "get_session", lambda: factory())
    monkeypatch.setattr(migration, "load_project_source_drama_snapshot_v1", lambda _project_id: snapshot)

    result = migration.inspect_project(project_id)

    assert result["persisted_target_dialogue_count"] == 2
    assert result["current_target_dialogue_count"] == 1
    assert result["historical_target_dialogue_count"] == 1
    assert result["historical_row_ids"] == ["TARGETDIALOGUE_HISTORY"]

    with factory() as session:
        ids = {
            row.id
            for row in session.scalars(
                select(target_dialogue_v1.TargetDialogue).where(
                    target_dialogue_v1.TargetDialogue.project_id == project_id
                )
            ).all()
        }
    assert ids == {"TARGETDIALOGUE_HISTORY", "TARGETDIALOGUE_CURRENT"}


def test_database_backup_is_a_consistent_copy(tmp_path: Path) -> None:
    database_path = tmp_path / "studio_v2.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample(value) VALUES ('before-migration')")
        connection.commit()

    backup_path = migration.backup_database(database_path)

    assert backup_path.is_file()
    assert backup_path != database_path
    with sqlite3.connect(backup_path) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone() == ("before-migration",)
