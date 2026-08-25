from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from engine.app import asset_workspace_v3, studio_v2
from engine.app.asset_final_gate_v6 import apply_analysis_to_assets
from engine.app.content_analysis_v2 import CharacterCandidate, CharacterTrack, ContentAnalysisRun


def use_temp_database(monkeypatch, tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'studio.sqlite3').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    studio_v2.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(studio_v2, "ENGINE", engine)
    monkeypatch.setattr(studio_v2, "SessionLocal", factory)
    monkeypatch.setattr(studio_v2, "workspace_root", lambda: tmp_path / "workspace")
    # asset_workspace_v3 import 了 get_session 函数对象；显式指回临时 DB，避免测试碰正式数据库。
    monkeypatch.setattr(asset_workspace_v3, "get_session", lambda: factory())


def seed(monkeypatch, tmp_path: Path) -> tuple[str, str]:
    use_temp_database(monkeypatch, tmp_path)
    project = studio_v2.create_project(
        name="V6 Final Gate",
        source_language="zh-CN",
        target_language="en-US",
        target_region="US",
    )
    project_id = project["id"]
    run_id = "RUN_V6"
    with studio_v2.get_session() as session:
        session.add(studio_v2.Episode(
            id="EP1",
            project_id=project_id,
            title="第一集",
            original_filename="ep1.mp4",
            source_path=str(tmp_path / "ep1.mp4"),
            source_sha256="a" * 64,
            sort_order=1,
            status="SHOTS_READY",
        ))
        session.add_all([
            studio_v2.Shot(
                id="SHOT_1", episode_id="EP1", ordinal=1,
                start_us=0, end_us=1_000_000, duration_us=1_000_000,
                reference_clip_path=str(tmp_path / "s1.mp4"), thumbnail_path=None,
                keyframes_json="[]", status="READY",
            ),
            studio_v2.Shot(
                id="SHOT_2", episode_id="EP1", ordinal=2,
                start_us=1_000_000, end_us=2_000_000, duration_us=1_000_000,
                reference_clip_path=str(tmp_path / "s2.mp4"), thumbnail_path=None,
                keyframes_json="[]", status="READY",
            ),
        ])
        session.add(ContentAnalysisRun(
            id=run_id,
            project_id=project_id,
            status="READY_WITH_WARNINGS",
            is_current=True,
            profile_version="f05-assets-v6-global-identity",
            component_status_json=json.dumps({"characters": "READY"}),
            counts_json=json.dumps({"resolved_character_candidates": 1, "unresolved_character_candidates": 1}),
            completed_at=studio_v2.utcnow(),
        ))
        session.add_all([
            CharacterCandidate(
                id="C_RESOLVED", run_id=run_id, project_id=project_id, ordinal=1,
                auto_label="人物 001", track_count=1, shot_count=1, confidence=0.95,
                cover_path=None,
                evidence_json=json.dumps({"identity_status": "RESOLVED", "final_asset_eligible": True}),
            ),
            CharacterCandidate(
                id="C_UNRESOLVED", run_id=run_id, project_id=project_id, ordinal=2,
                auto_label="待解析人物 001", track_count=1, shot_count=1, confidence=0.72,
                cover_path=None,
                evidence_json=json.dumps({"identity_status": "UNRESOLVED", "final_asset_eligible": False}),
            ),
        ])
        # 两条 Track 都真实看到了脸；区别只在 Global Identity 是否足够稳定。
        session.add_all([
            CharacterTrack(
                id="T_RESOLVED", run_id=run_id, candidate_id="C_RESOLVED", shot_id="SHOT_1",
                start_us=0, end_us=800_000, representative_source_us=300_000,
                bbox_json="[10,10,100,300]", sample_count=6, face_visible=True,
                mean_face_score=0.94, body_evidence_score=0.90,
                evidence_json=json.dumps({"identity_status": "RESOLVED"}),
            ),
            CharacterTrack(
                id="T_UNRESOLVED", run_id=run_id, candidate_id="C_UNRESOLVED", shot_id="SHOT_2",
                start_us=1_000_000, end_us=1_400_000, representative_source_us=1_200_000,
                bbox_json="[20,20,90,260]", sample_count=1, face_visible=True,
                mean_face_score=0.91, body_evidence_score=0.82,
                evidence_json=json.dumps({"identity_status": "UNRESOLVED"}),
            ),
        ])
        session.commit()
    return project_id, run_id


def test_unresolved_face_fragment_is_kept_as_evidence_but_not_materialized(monkeypatch, tmp_path: Path) -> None:
    project_id, run_id = seed(monkeypatch, tmp_path)

    workspace = apply_analysis_to_assets(project_id, run_id)

    assert len(workspace["characters"]) == 1
    assert workspace["characters"][0]["name"] == "人物 001"
    assert len(workspace["bindings_by_shot"]["SHOT_1"]["character_ids"]) == 1
    assert workspace["bindings_by_shot"]["SHOT_2"]["character_ids"] == []

    # Final Gate 不能为了跳过物化而篡改不可变 Evidence。
    with studio_v2.get_session() as session:
        unresolved_track = session.scalar(select(CharacterTrack).where(CharacterTrack.id == "T_UNRESOLVED"))
        assert unresolved_track is not None
        assert unresolved_track.face_visible is True
        unresolved_candidate = session.get(CharacterCandidate, "C_UNRESOLVED")
        assert unresolved_candidate is not None
        assert json.loads(unresolved_candidate.evidence_json)["identity_status"] == "UNRESOLVED"
