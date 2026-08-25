from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from engine.app import studio_v2
from engine.app.asset_batch_v4 import batch_set_shot_bindings
from engine.app.asset_workspace_v3 import (
    AssetRevision,
    ShotCharacterBinding,
    ShotPropBinding,
    ShotSceneBinding,
)


def use_temp_database(monkeypatch, tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'studio.sqlite3').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    studio_v2.Base.metadata.create_all(engine)
    monkeypatch.setattr(studio_v2, "ENGINE", engine)
    monkeypatch.setattr(
        studio_v2,
        "SessionLocal",
        sessionmaker(bind=engine, autoflush=False, expire_on_commit=False),
    )
    monkeypatch.setattr(studio_v2, "workspace_root", lambda: tmp_path / "workspace")


def seed(monkeypatch, tmp_path: Path) -> tuple[str, str]:
    use_temp_database(monkeypatch, tmp_path)
    project = studio_v2.create_project(
        name="批量资产测试",
        source_language="zh-CN",
        target_language="en-US",
        target_region="US",
    )
    with studio_v2.get_session() as session:
        session.add(studio_v2.Episode(
            id="EPISODE_1",
            project_id=project["id"],
            title="第一集",
            original_filename="e1.mp4",
            source_path=str(tmp_path / "e1.mp4"),
            source_sha256="b" * 64,
            sort_order=1,
            status="SHOTS_READY",
        ))
        session.add_all([
            studio_v2.Shot(
                id="SHOT_1", episode_id="EPISODE_1", ordinal=1,
                start_us=0, end_us=1_000_000, duration_us=1_000_000,
                reference_clip_path=str(tmp_path / "s1.mp4"), thumbnail_path=None,
                keyframes_json="[]", status="READY",
            ),
            studio_v2.Shot(
                id="SHOT_2", episode_id="EPISODE_1", ordinal=2,
                start_us=1_000_000, end_us=2_000_000, duration_us=1_000_000,
                reference_clip_path=str(tmp_path / "s2.mp4"), thumbnail_path=None,
                keyframes_json="[]", status="READY",
            ),
        ])
        session.add(studio_v2.Character(id="CHAR_1", project_id=project["id"], name="人物 A", status="MANUAL", metadata_json="{}"))
        session.add(studio_v2.Scene(id="SCENE_A", project_id=project["id"], name="走廊", status="MANUAL", metadata_json="{}"))
        session.add(studio_v2.Scene(id="SCENE_B", project_id=project["id"], name="客厅", status="MANUAL", metadata_json="{}"))
        session.add(studio_v2.Prop(id="PROP_1", project_id=project["id"], name="手机", is_key_prop=True, metadata_json="{}"))
        session.flush()
        for shot_id in ("SHOT_1", "SHOT_2"):
            session.add(ShotCharacterBinding(
                id=f"CB_{shot_id}", project_id=project["id"], shot_id=shot_id,
                character_id="CHAR_1", source="MANUAL",
            ))
            session.add(ShotSceneBinding(
                id=f"SB_{shot_id}", project_id=project["id"], shot_id=shot_id,
                scene_id="SCENE_A", source="MANUAL",
            ))
            session.add(ShotPropBinding(
                id=f"PB_{shot_id}", project_id=project["id"], shot_id=shot_id,
                prop_id="PROP_1", source="MANUAL",
            ))
        session.commit()
    return project["id"], "SCENE_B"


def test_batch_scene_only_preserves_people_props_and_creates_one_revision(monkeypatch, tmp_path: Path) -> None:
    project_id, scene_b = seed(monkeypatch, tmp_path)

    workspace = batch_set_shot_bindings(
        project_id,
        ["SHOT_1", "SHOT_2"],
        apply_characters=False,
        character_ids=[],
        apply_scene=True,
        scene_id=scene_b,
        apply_props=False,
        prop_ids=[],
    )

    for shot_id in ("SHOT_1", "SHOT_2"):
        binding = workspace["bindings_by_shot"][shot_id]
        assert binding["character_ids"] == ["CHAR_1"]
        assert binding["scene_id"] == "SCENE_B"
        assert binding["prop_ids"] == ["PROP_1"]

    assert workspace["revision"]["kind"] == "MANUAL"
    with studio_v2.get_session() as session:
        revision_count = session.scalar(select(func.count(AssetRevision.id)).where(AssetRevision.project_id == project_id))
    assert revision_count == 1
