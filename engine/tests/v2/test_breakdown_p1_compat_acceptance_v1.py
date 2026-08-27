from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker

from engine.app import breakdown_serializer_v1, studio_v2
from engine.app.breakdown_models_v1 import BreakdownRun
from engine.app.shot_revision_v2 import ShotRevision


BREAKDOWN_TABLES = {
    "v2_breakdown_runs",
    "v2_scene_segment_drafts",
    "v2_shot_semantic_drafts",
    "v2_local_subjects",
    "v2_shot_local_subjects",
    "v2_timeline_events",
    "v2_timeline_event_subjects",
    "v2_draft_prop_hints",
    "v2_draft_prop_occurrences",
    "v2_breakdown_evidence_links",
}
SHOT_REVISION_TABLES = {"v2_shot_revisions", "v2_shot_revision_items"}


def configure_database(monkeypatch: pytest.MonkeyPatch, path: Path):
    engine = create_engine(
        f"sqlite:///{path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(studio_v2, "ENGINE", engine)
    monkeypatch.setattr(studio_v2, "SessionLocal", factory)
    return engine, factory


def test_empty_database_initializes_p1_schema_without_creating_business_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """P1.7：全新/空数据目录初始化只补 schema，不凭空创建 Project/Revision/Breakdown。"""

    engine, factory = configure_database(monkeypatch, tmp_path / "fresh studio.sqlite3")

    studio_v2.init_database()
    # 重复初始化必须保持 ADD-only / 幂等，Windows 首次启动和后续启动都安全。
    studio_v2.init_database()

    tables = set(inspect(engine).get_table_names())
    assert BREAKDOWN_TABLES <= tables
    assert SHOT_REVISION_TABLES <= tables

    with factory() as session:
        assert session.scalars(select(studio_v2.Project)).all() == []
        assert session.scalars(select(studio_v2.Episode)).all() == []
        assert session.scalars(select(studio_v2.Shot)).all() == []
        assert session.scalars(select(ShotRevision)).all() == []
        assert session.scalars(select(BreakdownRun)).all() == []


def test_pre_p1_historical_v2_database_upgrades_add_only_and_stays_readable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """P1.7：历史 V2 Project/Episode/Shot 在补 P1 表后数据不变，读取不会偷偷建 BASELINE。"""

    database_path = tmp_path / "历史 项目 studio.sqlite3"
    engine, factory = configure_database(monkeypatch, database_path)
    source_path = tmp_path / "原视频 ep01.mp4"
    reference_path = tmp_path / "旧参考 01.mp4"
    source_path.write_bytes(b"legacy-source")
    reference_path.write_bytes(b"legacy-reference")

    # 模拟 P1/ShotRevision 出现之前已经存在的正式 V2 数据库，而不是用当前 Base 预建新表。
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE v2_projects (
                id VARCHAR(64) PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                source_language VARCHAR(32) NOT NULL,
                target_language VARCHAR(32) NOT NULL,
                target_region VARCHAR(64) NOT NULL,
                project_format_version VARCHAR(16),
                created_at DATETIME,
                updated_at DATETIME
            )
        """))
        connection.execute(text("""
            CREATE TABLE v2_episodes (
                id VARCHAR(64) PRIMARY KEY,
                project_id VARCHAR(64) NOT NULL,
                title VARCHAR(200) NOT NULL,
                original_filename VARCHAR(255) NOT NULL,
                source_path TEXT NOT NULL,
                source_sha256 VARCHAR(64) NOT NULL,
                sort_order INTEGER NOT NULL,
                status VARCHAR(32) NOT NULL,
                duration_us INTEGER,
                width INTEGER,
                height INTEGER,
                fps FLOAT,
                created_at DATETIME,
                updated_at DATETIME
            )
        """))
        connection.execute(text("""
            CREATE TABLE v2_shots (
                id VARCHAR(64) PRIMARY KEY,
                episode_id VARCHAR(64) NOT NULL,
                ordinal INTEGER NOT NULL,
                start_us INTEGER NOT NULL,
                end_us INTEGER NOT NULL,
                duration_us INTEGER NOT NULL,
                reference_clip_path TEXT NOT NULL,
                thumbnail_path TEXT,
                keyframes_json TEXT,
                short_description TEXT,
                shot_type VARCHAR(64),
                camera_motion VARCHAR(64),
                status VARCHAR(32) NOT NULL,
                created_at DATETIME
            )
        """))
        connection.execute(
            text("""
                INSERT INTO v2_projects (
                    id, name, source_language, target_language, target_region, project_format_version
                ) VALUES (
                    'PROJECT_LEGACY', '历史项目', 'zh-CN', 'en-US', 'US', '2.0'
                )
            """)
        )
        connection.execute(
            text("""
                INSERT INTO v2_episodes (
                    id, project_id, title, original_filename, source_path, source_sha256,
                    sort_order, status, duration_us, width, height, fps
                ) VALUES (
                    'EPISODE_LEGACY', 'PROJECT_LEGACY', 'EP01', 'ep01.mp4', :source_path,
                    :sha256, 1, 'SHOTS_READY', 1000000, 720, 1280, 25.0
                )
            """),
            {"source_path": str(source_path), "sha256": "a" * 64},
        )
        connection.execute(
            text("""
                INSERT INTO v2_shots (
                    id, episode_id, ordinal, start_us, end_us, duration_us,
                    reference_clip_path, keyframes_json, short_description, status
                ) VALUES (
                    'SHOT_LEGACY', 'EPISODE_LEGACY', 1, 0, 1000000, 1000000,
                    :reference_path, '[]', '历史镜头', 'READY'
                )
            """),
            {"reference_path": str(reference_path)},
        )

    studio_v2.init_database()
    studio_v2.init_database()

    tables = set(inspect(engine).get_table_names())
    assert BREAKDOWN_TABLES <= tables
    assert SHOT_REVISION_TABLES <= tables

    with factory() as session:
        project = session.get(studio_v2.Project, "PROJECT_LEGACY")
        episode = session.get(studio_v2.Episode, "EPISODE_LEGACY")
        shot = session.get(studio_v2.Shot, "SHOT_LEGACY")
        assert project is not None and project.name == "历史项目"
        assert episode is not None and episode.source_path == str(source_path)
        assert shot is not None
        assert shot.start_us == 0 and shot.end_us == 1_000_000
        assert shot.reference_clip_path == str(reference_path)
        assert Path(shot.reference_clip_path).read_bytes() == b"legacy-reference"
        assert session.scalars(select(ShotRevision)).all() == []
        assert session.scalars(select(BreakdownRun)).all() == []

    # P1.4 读取历史项目必须是纯读取：无 Run 就返回空历史/None，不自动创建 BASELINE。
    assert breakdown_serializer_v1.list_breakdown_runs("EPISODE_LEGACY") == []
    assert breakdown_serializer_v1.get_current_breakdown("EPISODE_LEGACY") is None

    with factory() as session:
        assert session.scalars(select(ShotRevision)).all() == []
        assert session.scalars(select(BreakdownRun)).all() == []
