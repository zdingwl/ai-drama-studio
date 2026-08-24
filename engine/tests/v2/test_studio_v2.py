from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engine.app import studio_v2


def use_temp_database(monkeypatch, tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{(tmp_path / 'studio.sqlite3').as_posix()}", connect_args={"check_same_thread": False})
    studio_v2.Base.metadata.create_all(engine)
    monkeypatch.setattr(studio_v2, "ENGINE", engine)
    monkeypatch.setattr(studio_v2, "SessionLocal", sessionmaker(bind=engine, autoflush=False, expire_on_commit=False))
    monkeypatch.setattr(studio_v2, "workspace_root", lambda: tmp_path / "workspace")


def test_project_can_hold_multiple_ordered_episodes(monkeypatch, tmp_path: Path) -> None:
    use_temp_database(monkeypatch, tmp_path)
    project = studio_v2.create_project(
        name="重制测试",
        source_language="zh-CN",
        target_language="en-US",
        target_region="US",
    )
    assert project["project_format_version"] == "2.0"
    assert project["episodes"] == []

    # 直接创建两个 Episode，验证 V2 的核心关系与排序语义，不依赖真实媒体文件。
    with studio_v2.get_session() as session:
        session.add_all(
            [
                studio_v2.Episode(
                    id="EPISODE_A",
                    project_id=project["id"],
                    title="第一集",
                    original_filename="a.mp4",
                    source_path=str(tmp_path / "a.mp4"),
                    source_sha256="a" * 64,
                    sort_order=1,
                ),
                studio_v2.Episode(
                    id="EPISODE_B",
                    project_id=project["id"],
                    title="第二集",
                    original_filename="b.mp4",
                    source_path=str(tmp_path / "b.mp4"),
                    source_sha256="b" * 64,
                    sort_order=2,
                ),
            ]
        )
        session.commit()

    loaded = studio_v2.get_project(project["id"])
    assert loaded is not None
    assert [item["id"] for item in loaded["episodes"]] == ["EPISODE_A", "EPISODE_B"]

    reordered = studio_v2.reorder_episodes(project_id=project["id"], episode_ids=["EPISODE_B", "EPISODE_A"])
    assert [item["id"] for item in reordered] == ["EPISODE_B", "EPISODE_A"]
    assert [item["sort_order"] for item in reordered] == [1, 2]


def test_replace_shots_makes_reference_clip_first_class(monkeypatch, tmp_path: Path) -> None:
    use_temp_database(monkeypatch, tmp_path)
    project = studio_v2.create_project(name="Shot 测试", source_language="zh-CN", target_language="en-US", target_region="US")
    with studio_v2.get_session() as session:
        session.add(
            studio_v2.Episode(
                id="EPISODE_1",
                project_id=project["id"],
                title="第一集",
                original_filename="episode.mp4",
                source_path=str(tmp_path / "episode.mp4"),
                source_sha256="c" * 64,
                sort_order=1,
            )
        )
        session.commit()

    reference = tmp_path / "shot_0001.mp4"
    thumbnail = tmp_path / "shot_0001.jpg"
    shots = studio_v2.replace_shots(
        "EPISODE_1",
        [
            {
                "ordinal": 1,
                "start_us": 0,
                "end_us": 2_500_000,
                "duration_us": 2_500_000,
                "reference_clip_path": str(reference),
                "thumbnail_path": str(thumbnail),
                "keyframes_json": "[]",
                "short_description": None,
                "shot_type": None,
                "camera_motion": None,
                "status": "READY",
            }
        ],
    )
    assert shots[0]["duration_us"] == 2_500_000
    assert shots[0]["reference_url"].endswith("/reference")
    assert shots[0]["thumbnail_url"].endswith("/thumbnail")


def test_v2_schema_reserves_downstream_entities() -> None:
    table_names = set(studio_v2.Base.metadata.tables)
    assert {
        "v2_projects",
        "v2_episodes",
        "v2_preprocess",
        "v2_shots",
        "v2_characters",
        "v2_scenes",
        "v2_props",
        "v2_dialogues",
        "v2_assets",
        "v2_voices",
        "v2_generations",
    } <= table_names
