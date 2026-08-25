from __future__ import annotations

from sqlalchemy import func, select

from engine.app import studio_v2
from engine.app.asset_workspace_v3 import ShotCharacterBinding, apply_analysis_to_assets
from engine.app.content_analysis_v2 import CharacterTrack
from engine.tests.v2.test_asset_workspace_v3 import seed_analysis, seed_project


def test_same_candidate_multiple_tracks_in_one_shot_materializes_one_binding(monkeypatch, tmp_path) -> None:
    """V5 Track 可因遮挡在同一 Shot 分段，但 Final Character Binding 只能按 Shot 出现一次。"""

    project_id, _ = seed_project(monkeypatch, tmp_path)
    run_id = "RUN_TRACK_DEDUP"
    seed_analysis(project_id, run_id)

    # seed_analysis 已经有一条 RUN_TRACK_DEDUP_T1 → SHOT_1。
    # 再模拟同一个 Character Candidate 在同一 Shot 内遮挡后重新起 Track。
    with studio_v2.get_session() as session:
        session.add(CharacterTrack(
            id=f"{run_id}_T1_REENTER",
            run_id=run_id,
            candidate_id=f"{run_id}_CHAR",
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
        ))
        session.commit()

    workspace = apply_analysis_to_assets(project_id, run_id)

    character_id = workspace["characters"][0]["id"]
    assert workspace["bindings_by_shot"]["SHOT_1"]["character_ids"] == [character_id]

    with studio_v2.get_session() as session:
        evidence_track_count = session.scalar(select(func.count()).select_from(CharacterTrack).where(
            CharacterTrack.run_id == run_id,
            CharacterTrack.candidate_id == f"{run_id}_CHAR",
            CharacterTrack.shot_id == "SHOT_1",
        ))
        final_binding_count = session.scalar(select(func.count()).select_from(ShotCharacterBinding).where(
            ShotCharacterBinding.project_id == project_id,
            ShotCharacterBinding.shot_id == "SHOT_1",
            ShotCharacterBinding.character_id == character_id,
        ))

    assert evidence_track_count == 2
    assert final_binding_count == 1
