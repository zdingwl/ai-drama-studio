from __future__ import annotations

import json

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from engine.app import studio_v2
from engine.app.asset_workspace_v3 import ShotCharacterBinding, apply_analysis_to_assets
from engine.app.content_analysis_v2 import CharacterCandidate, CharacterTrack, ContentAnalysisRun


def test_same_candidate_multiple_tracks_in_one_shot_materializes_one_binding(monkeypatch, tmp_path) -> None:
    """V5 Track 可因遮挡在同一 Shot 分段，但 Final Character Binding 只能按 Shot 出现一次。"""

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

    project = studio_v2.create_project(
        name="V5 Binding 去重",
        source_language="zh-CN",
        target_language="en-US",
        target_region="US",
    )
    project_id = project["id"]
    run_id = "RUN_TRACK_DEDUP"
    candidate_id = f"{run_id}_CHAR"

    with studio_v2.get_session() as session:
        session.add(studio_v2.Episode(
            id="EPISODE_1",
            project_id=project_id,
            title="第一集",
            original_filename="e1.mp4",
            source_path=str(tmp_path / "e1.mp4"),
            source_sha256="a" * 64,
            sort_order=1,
            status="SHOTS_READY",
        ))
        session.add(studio_v2.Shot(
            id="SHOT_1",
            episode_id="EPISODE_1",
            ordinal=1,
            start_us=0,
            end_us=1_000_000,
            duration_us=1_000_000,
            reference_clip_path=str(tmp_path / "s1.mp4"),
            thumbnail_path=str(tmp_path / "s1.jpg"),
            keyframes_json="[]",
            status="READY",
        ))
        session.add(ContentAnalysisRun(
            id=run_id,
            project_id=project_id,
            status="READY",
            is_current=True,
            profile_version="f05-assets-v5-track-gallery",
            component_status_json=json.dumps({"characters": "READY"}),
            counts_json="{}",
            completed_at=studio_v2.utcnow(),
        ))
        session.add(CharacterCandidate(
            id=candidate_id,
            run_id=run_id,
            project_id=project_id,
            ordinal=1,
            auto_label="人物 001",
            track_count=2,
            shot_count=1,
            confidence=0.91,
            cover_path=None,
            evidence_json="{}",
        ))
        session.add_all([
            CharacterTrack(
                id=f"{run_id}_T1",
                run_id=run_id,
                candidate_id=candidate_id,
                shot_id="SHOT_1",
                start_us=0,
                end_us=550_000,
                representative_source_us=300_000,
                bbox_json="[0,0,10,10]",
                sample_count=4,
                face_visible=True,
                mean_face_score=0.90,
                body_evidence_score=0.80,
                evidence_json="{}",
            ),
            CharacterTrack(
                id=f"{run_id}_T2",
                run_id=run_id,
                candidate_id=candidate_id,
                shot_id="SHOT_1",
                start_us=600_000,
                end_us=950_000,
                representative_source_us=800_000,
                bbox_json="[2,2,12,12]",
                sample_count=3,
                face_visible=True,
                mean_face_score=0.88,
                body_evidence_score=0.82,
                evidence_json="{}",
            ),
        ])
        session.commit()

    workspace = apply_analysis_to_assets(project_id, run_id)
    character_id = workspace["characters"][0]["id"]

    assert workspace["bindings_by_shot"]["SHOT_1"]["character_ids"] == [character_id]

    with studio_v2.get_session() as session:
        evidence_track_count = session.scalar(
            select(func.count()).select_from(CharacterTrack).where(
                CharacterTrack.run_id == run_id,
                CharacterTrack.candidate_id == candidate_id,
                CharacterTrack.shot_id == "SHOT_1",
            )
        )
        final_binding_count = session.scalar(
            select(func.count()).select_from(ShotCharacterBinding).where(
                ShotCharacterBinding.project_id == project_id,
                ShotCharacterBinding.shot_id == "SHOT_1",
                ShotCharacterBinding.character_id == character_id,
            )
        )

    assert evidence_track_count == 2
    assert final_binding_count == 1
