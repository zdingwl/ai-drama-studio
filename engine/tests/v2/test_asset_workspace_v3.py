from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from engine.app import studio_v2
from engine.app.asset_workspace_v3 import (
    AssetRevision,
    apply_analysis_to_assets,
    create_asset,
    merge_assets,
    restore_asset_revision,
    set_shot_bindings,
    split_asset,
)
from engine.app.content_analysis_v2 import (
    CharacterCandidate,
    CharacterTrack,
    ContentAnalysisRun,
    PropCandidate,
    SceneCandidate,
    ShotPropEvidence,
    ShotSceneEvidence,
)


def use_temp_database(monkeypatch, tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{(tmp_path / 'studio.sqlite3').as_posix()}", connect_args={"check_same_thread": False})
    studio_v2.Base.metadata.create_all(engine)
    monkeypatch.setattr(studio_v2, "ENGINE", engine)
    monkeypatch.setattr(studio_v2, "SessionLocal", sessionmaker(bind=engine, autoflush=False, expire_on_commit=False))
    monkeypatch.setattr(studio_v2, "workspace_root", lambda: tmp_path / "workspace")


def seed_project(monkeypatch, tmp_path: Path) -> tuple[str, list[str]]:
    use_temp_database(monkeypatch, tmp_path)
    project = studio_v2.create_project(name="资产测试", source_language="zh-CN", target_language="en-US", target_region="US")
    with studio_v2.get_session() as session:
        session.add(studio_v2.Episode(
            id="EPISODE_1", project_id=project["id"], title="第一集", original_filename="e1.mp4",
            source_path=str(tmp_path / "e1.mp4"), source_sha256="a" * 64, sort_order=1, status="SHOTS_READY",
        ))
        session.add_all([
            studio_v2.Shot(
                id="SHOT_1", episode_id="EPISODE_1", ordinal=1, start_us=0, end_us=1_000_000, duration_us=1_000_000,
                reference_clip_path=str(tmp_path / "s1.mp4"), thumbnail_path=str(tmp_path / "s1.jpg"), keyframes_json="[]", status="READY",
            ),
            studio_v2.Shot(
                id="SHOT_2", episode_id="EPISODE_1", ordinal=2, start_us=1_000_000, end_us=2_000_000, duration_us=1_000_000,
                reference_clip_path=str(tmp_path / "s2.mp4"), thumbnail_path=str(tmp_path / "s2.jpg"), keyframes_json="[]", status="READY",
            ),
        ])
        session.commit()
    return project["id"], ["SHOT_1", "SHOT_2"]


def seed_analysis(project_id: str, run_id: str, *, label: str = "人物 001") -> None:
    with studio_v2.get_session() as session:
        for old in session.scalars(select(ContentAnalysisRun).where(ContentAnalysisRun.project_id == project_id)).all():
            old.is_current = False
        session.add(ContentAnalysisRun(
            id=run_id, project_id=project_id, status="READY", is_current=True, profile_version="test-assets",
            component_status_json=json.dumps({"characters": "READY", "scenes": "READY", "props": "READY"}),
            counts_json="{}", completed_at=studio_v2.utcnow(),
        ))
        session.add(CharacterCandidate(
            id=f"{run_id}_CHAR", run_id=run_id, project_id=project_id, ordinal=1, auto_label=label,
            track_count=2, shot_count=2, confidence=0.91, cover_path=None, evidence_json="{}",
        ))
        session.add_all([
            CharacterTrack(
                id=f"{run_id}_T1", run_id=run_id, candidate_id=f"{run_id}_CHAR", shot_id="SHOT_1",
                start_us=0, end_us=1_000_000, representative_source_us=500_000, bbox_json="[0,0,10,10]",
                sample_count=4, face_visible=True, mean_face_score=0.9, body_evidence_score=0.8, evidence_json="{}",
            ),
            CharacterTrack(
                id=f"{run_id}_T2", run_id=run_id, candidate_id=f"{run_id}_CHAR", shot_id="SHOT_2",
                start_us=1_000_000, end_us=2_000_000, representative_source_us=1_500_000, bbox_json="[0,0,10,10]",
                sample_count=4, face_visible=False, mean_face_score=None, body_evidence_score=0.88, evidence_json="{}",
            ),
        ])
        session.add(SceneCandidate(
            id=f"{run_id}_SCENE", run_id=run_id, project_id=project_id, ordinal=1,
            auto_label="公寓走廊", shot_count=2, cover_path=None, evidence_json="{}",
        ))
        session.add_all([
            ShotSceneEvidence(id=f"{run_id}_SS1", run_id=run_id, shot_id="SHOT_1", scene_candidate_id=f"{run_id}_SCENE", confidence=0.9),
            ShotSceneEvidence(id=f"{run_id}_SS2", run_id=run_id, shot_id="SHOT_2", scene_candidate_id=f"{run_id}_SCENE", confidence=0.9),
        ])
        session.add(PropCandidate(
            id=f"{run_id}_PROP", run_id=run_id, project_id=project_id, ordinal=1,
            auto_label="蓝玫瑰", confidence=0.86, evidence_json="{}",
        ))
        session.add(ShotPropEvidence(
            id=f"{run_id}_SP1", run_id=run_id, shot_id="SHOT_1", prop_candidate_id=f"{run_id}_PROP", confidence=0.86, bbox_json=None,
        ))
        session.commit()


def test_analysis_becomes_final_assets_and_shot_bindings(monkeypatch, tmp_path: Path) -> None:
    project_id, _ = seed_project(monkeypatch, tmp_path)
    seed_analysis(project_id, "RUN_1")

    workspace = apply_analysis_to_assets(project_id, "RUN_1")

    assert workspace["status"] == "READY"
    assert workspace["revision"]["kind"] == "AUTO"
    assert len(workspace["characters"]) == 1
    assert len(workspace["scenes"]) == 1
    assert len(workspace["props"]) == 1
    assert len(workspace["bindings_by_shot"]["SHOT_1"]["character_ids"]) == 1
    assert workspace["bindings_by_shot"]["SHOT_1"]["scene_id"] is not None
    assert len(workspace["bindings_by_shot"]["SHOT_1"]["prop_ids"]) == 1
    # SHOT_2 虽然 face_visible=False，但它只能作为 body/服装辅助接到已有 face-anchored 人物，而不是自己造人物。
    assert workspace["bindings_by_shot"]["SHOT_2"]["character_ids"] == workspace["bindings_by_shot"]["SHOT_1"]["character_ids"]


def test_manual_binding_revision_snapshots_new_state(monkeypatch, tmp_path: Path) -> None:
    project_id, _ = seed_project(monkeypatch, tmp_path)
    seed_analysis(project_id, "RUN_1")
    workspace = apply_analysis_to_assets(project_id, "RUN_1")
    scene_id = workspace["scenes"][0]["id"]

    workspace = set_shot_bindings(project_id, "SHOT_1", character_ids=[], scene_id=scene_id, prop_ids=[])

    assert workspace["revision"]["kind"] == "MANUAL"
    assert workspace["bindings_by_shot"]["SHOT_1"]["character_ids"] == []
    assert workspace["bindings_by_shot"]["SHOT_1"]["prop_ids"] == []
    with studio_v2.get_session() as session:
        revision = session.get(AssetRevision, workspace["revision"]["id"])
        snapshot = json.loads(revision.snapshot_json)
    shot1_character_bindings = [item for item in snapshot["bindings"]["characters"] if item["shot_id"] == "SHOT_1"]
    assert shot1_character_bindings == []


def test_new_ai_run_does_not_overwrite_manual_revision(monkeypatch, tmp_path: Path) -> None:
    project_id, _ = seed_project(monkeypatch, tmp_path)
    seed_analysis(project_id, "RUN_1", label="人物 A")
    workspace = apply_analysis_to_assets(project_id, "RUN_1")
    workspace = set_shot_bindings(
        project_id, "SHOT_1",
        character_ids=workspace["bindings_by_shot"]["SHOT_1"]["character_ids"],
        scene_id=workspace["bindings_by_shot"]["SHOT_1"]["scene_id"], prop_ids=[],
    )
    manual_revision_id = workspace["revision"]["id"]

    seed_analysis(project_id, "RUN_2", label="人物 B")
    protected = apply_analysis_to_assets(project_id, "RUN_2")

    assert protected["revision"]["id"] == manual_revision_id
    assert protected["revision"]["kind"] == "MANUAL"
    assert protected["stale"] is True

    adopted = apply_analysis_to_assets(project_id, "RUN_2", force=True)
    assert adopted["revision"]["kind"] == "AUTO"
    assert adopted["revision"]["source_run_id"] == "RUN_2"
    assert adopted["characters"][0]["name"] == "人物 B"


def test_merge_split_and_restore_keep_revision_history(monkeypatch, tmp_path: Path) -> None:
    project_id, _ = seed_project(monkeypatch, tmp_path)
    seed_analysis(project_id, "RUN_1")
    workspace = apply_analysis_to_assets(project_id, "RUN_1")
    original_revision = workspace["revision"]

    workspace = create_asset(project_id, "character", "手工人物 A", shot_id="SHOT_1")
    a_id = next(item["id"] for item in workspace["characters"] if item["name"] == "手工人物 A")
    workspace = create_asset(project_id, "character", "手工人物 B", shot_id="SHOT_2")
    b_id = next(item["id"] for item in workspace["characters"] if item["name"] == "手工人物 B")

    workspace = merge_assets(project_id, "character", [a_id, b_id], target_id=a_id)
    merged = next(item for item in workspace["characters"] if item["id"] == a_id)
    assert set(merged["shot_ids"]) == {"SHOT_1", "SHOT_2"}

    workspace = split_asset(project_id, "character", a_id, ["SHOT_2"], new_name="拆分人物")
    assert any(item["name"] == "拆分人物" and item["shot_ids"] == ["SHOT_2"] for item in workspace["characters"])
    assert workspace["revision"]["kind"] == "MANUAL"

    restored = restore_asset_revision(original_revision["id"])
    assert restored["revision"]["kind"] == "RESTORE"
    assert restored["revision"]["source_revision_id"] == original_revision["id"]
    assert len(restored["revisions"]) >= 6
