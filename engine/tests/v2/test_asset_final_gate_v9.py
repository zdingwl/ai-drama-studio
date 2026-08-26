from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engine.app import asset_workspace_v3, studio_v2
from engine.app.asset_final_gate_v9 import apply_analysis_to_assets
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
    monkeypatch.setattr(asset_workspace_v3, "get_session", lambda: factory())


def seed_v9(monkeypatch, tmp_path: Path) -> tuple[str, str]:
    use_temp_database(monkeypatch, tmp_path)
    project = studio_v2.create_project(
        name="V9D Final Gate",
        source_language="zh-CN",
        target_language="en-US",
        target_region="US",
    )
    project_id = project["id"]
    run_id = "RUN_V9D"

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
        for ordinal in range(1, 5):
            session.add(studio_v2.Shot(
                id=f"SHOT_{ordinal}", episode_id="EP1", ordinal=ordinal,
                start_us=(ordinal - 1) * 1_000_000,
                end_us=ordinal * 1_000_000,
                duration_us=1_000_000,
                reference_clip_path=str(tmp_path / f"s{ordinal}.mp4"),
                thumbnail_path=None, keyframes_json="[]", status="READY",
            ))

        session.add(ContentAnalysisRun(
            id=run_id,
            project_id=project_id,
            status="READY_WITH_WARNINGS",
            is_current=True,
            profile_version="f05-assets-v9d-confirmed-person-gallery-final-gate",
            component_status_json=json.dumps({"characters": "READY"}),
            counts_json=json.dumps({"resolved_character_candidates": 1, "unresolved_character_candidates": 1}),
            completed_at=studio_v2.utcnow(),
        ))

        confirmed = {
            "identity_status": "RESOLVED",
            "final_asset_eligible": True,
            "profile": "f05-assets-v9c-person-gallery-anchor-first",
            "resolver": "person-gallery-anchor-first-v9c",
            "confirmed_gallery_images": 4,
            "confirmed_gallery_shots": 3,
            "face_images": 0,
        }
        unresolved = {
            "identity_status": "UNRESOLVED",
            "final_asset_eligible": False,
            "profile": "f05-assets-v9c-person-gallery-anchor-first",
            "resolver": "person-gallery-anchor-first-v9c",
        }
        session.add_all([
            CharacterCandidate(
                id="C_CONFIRMED", run_id=run_id, project_id=project_id, ordinal=1,
                auto_label="人物 001", track_count=3, shot_count=3, confidence=0.91,
                cover_path=None, evidence_json=json.dumps(confirmed),
            ),
            CharacterCandidate(
                id="C_UNRESOLVED", run_id=run_id, project_id=project_id, ordinal=2,
                auto_label="待解析人物 001", track_count=1, shot_count=1, confidence=0.65,
                cover_path=None, evidence_json=json.dumps(unresolved),
            ),
        ])

        # Confirmed Person Gallery intentionally has no visible face in any Track.
        for ordinal in range(1, 4):
            session.add(CharacterTrack(
                id=f"T_CONFIRMED_{ordinal}", run_id=run_id, candidate_id="C_CONFIRMED",
                shot_id=f"SHOT_{ordinal}", start_us=(ordinal - 1) * 1_000_000,
                end_us=(ordinal - 1) * 1_000_000 + 800_000,
                representative_source_us=(ordinal - 1) * 1_000_000 + 300_000,
                bbox_json="[10,10,100,300]", sample_count=6,
                face_visible=False, mean_face_score=None, body_evidence_score=0.90,
                evidence_json=json.dumps({"identity_status": "RESOLVED"}),
            ))
        session.add(CharacterTrack(
            id="T_UNRESOLVED", run_id=run_id, candidate_id="C_UNRESOLVED", shot_id="SHOT_4",
            start_us=3_000_000, end_us=3_700_000, representative_source_us=3_300_000,
            bbox_json="[20,20,90,260]", sample_count=4,
            face_visible=True, mean_face_score=0.92, body_evidence_score=0.80,
            evidence_json=json.dumps({"identity_status": "UNRESOLVED"}),
        ))
        session.commit()

    return project_id, run_id


def test_v9_confirmed_person_gallery_materializes_without_face(monkeypatch, tmp_path: Path) -> None:
    project_id, run_id = seed_v9(monkeypatch, tmp_path)

    workspace = apply_analysis_to_assets(project_id, run_id)

    assert len(workspace["characters"]) == 1
    character = workspace["characters"][0]
    assert character["name"] == "人物 001"
    assert character["metadata"]["identity_status"] == "RESOLVED"
    assert character["metadata"]["confirmed_gallery_shots"] == 3
    assert character["metadata"]["face_images"] == 0
    assert set(character["shot_ids"]) == {"SHOT_1", "SHOT_2", "SHOT_3"}
    assert workspace["bindings_by_shot"]["SHOT_4"]["character_ids"] == []


def test_v9_unresolved_with_visible_face_never_materializes(monkeypatch, tmp_path: Path) -> None:
    project_id, run_id = seed_v9(monkeypatch, tmp_path)

    workspace = apply_analysis_to_assets(project_id, run_id)

    names = {item["name"] for item in workspace["characters"]}
    assert "待解析人物 001" not in names


def test_v9_resolved_without_confirmed_gallery_provenance_fails_closed(monkeypatch, tmp_path: Path) -> None:
    project_id, run_id = seed_v9(monkeypatch, tmp_path)
    with studio_v2.get_session() as session:
        candidate = session.get(CharacterCandidate, "C_CONFIRMED")
        assert candidate is not None
        candidate.evidence_json = json.dumps({
            "identity_status": "RESOLVED",
            "final_asset_eligible": True,
            "profile": "f05-assets-v9c-person-gallery-anchor-first",
            # Missing resolver / confirmed gallery contract.
        })
        session.commit()

    workspace = apply_analysis_to_assets(project_id, run_id)

    assert workspace["characters"] == []


def test_v9_two_shot_gallery_cannot_bypass_final_gate(monkeypatch, tmp_path: Path) -> None:
    project_id, run_id = seed_v9(monkeypatch, tmp_path)
    with studio_v2.get_session() as session:
        candidate = session.get(CharacterCandidate, "C_CONFIRMED")
        assert candidate is not None
        evidence = json.loads(candidate.evidence_json)
        evidence["confirmed_gallery_shots"] = 2
        candidate.evidence_json = json.dumps(evidence)
        session.commit()

    workspace = apply_analysis_to_assets(project_id, run_id)

    assert workspace["characters"] == []
