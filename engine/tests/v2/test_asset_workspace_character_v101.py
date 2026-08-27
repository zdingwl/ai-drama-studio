from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engine.app import studio_v2
from engine.app.asset_workspace_character_v101 import decorate_asset_workspace_character_evidence
from engine.app.content_analysis_v2 import CharacterCandidate, CharacterTrack, ContentAnalysisRun


def _use_temp_database(monkeypatch, tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{(tmp_path / 'studio.sqlite3').as_posix()}", connect_args={"check_same_thread": False})
    studio_v2.Base.metadata.create_all(engine)
    monkeypatch.setattr(studio_v2, "ENGINE", engine)
    monkeypatch.setattr(studio_v2, "SessionLocal", sessionmaker(bind=engine, autoflush=False, expire_on_commit=False))


def _track(
    track_id: str,
    candidate_id: str,
    shot_id: str,
    *,
    face_visible: bool,
    recovery_score: float | None = None,
) -> CharacterTrack:
    recovery = None if recovery_score is None else {
        "source": "V10_1_TRACK_KNOWN_IDENTITY_RECOVERY",
        "target_candidate_id": candidate_id,
        "shot_id": shot_id,
        "score": recovery_score,
        "observation_count": 3,
    }
    return CharacterTrack(
        id=track_id,
        run_id="RUN_V101",
        candidate_id=candidate_id,
        shot_id=shot_id,
        start_us=0,
        end_us=500_000,
        representative_source_us=250_000,
        bbox_json="[0,0,100,200]",
        sample_count=3,
        face_visible=face_visible,
        mean_face_score=0.9 if face_visible else None,
        body_evidence_score=0.85,
        evidence_json=json.dumps({"identity_recovery": recovery}),
    )


def _seed(monkeypatch, tmp_path: Path) -> str:
    _use_temp_database(monkeypatch, tmp_path)
    project_id = "PROJECT_V101"
    with studio_v2.get_session() as session:
        session.add(studio_v2.Project(
            id=project_id,
            name="V10.1 Shot Evidence",
            source_language="zh-CN",
            target_language="en-US",
            target_region="US",
        ))
        session.add(studio_v2.Episode(
            id="EP_1",
            project_id=project_id,
            title="第一集",
            original_filename="e1.mp4",
            source_path=str(tmp_path / "e1.mp4"),
            source_sha256="a" * 64,
            sort_order=1,
            status="READY",
        ))
        for ordinal in range(1, 4):
            session.add(studio_v2.Shot(
                id=f"SHOT_{ordinal}",
                episode_id="EP_1",
                ordinal=ordinal,
                start_us=(ordinal - 1) * 1_000_000,
                end_us=ordinal * 1_000_000,
                duration_us=1_000_000,
                reference_clip_path=str(tmp_path / f"shot_{ordinal}.mp4"),
                status="READY",
            ))
        session.add(ContentAnalysisRun(
            id="RUN_V101",
            project_id=project_id,
            status="READY_WITH_WARNINGS",
            is_current=True,
            profile_version="f05-assets-v10.1-person-evidence-model-classification",
            component_status_json="{}",
            counts_json="{}",
        ))
        session.add(CharacterCandidate(
            id="RESOLVED_A",
            run_id="RUN_V101",
            project_id=project_id,
            ordinal=1,
            auto_label="人物 001",
            track_count=2,
            shot_count=2,
            confidence=0.94,
            cover_path=None,
            evidence_json=json.dumps({
                "identity_status": "RESOLVED",
                "final_asset_eligible": True,
                "resolver": "person-evidence-model-classifier-v10.1",
            }),
        ))
        session.add(CharacterCandidate(
            id="UNRESOLVED_B",
            run_id="RUN_V101",
            project_id=project_id,
            ordinal=2,
            auto_label="待解析人物 001",
            track_count=1,
            shot_count=1,
            confidence=0.41,
            cover_path=None,
            evidence_json=json.dumps({
                "identity_status": "UNRESOLVED",
                "final_asset_eligible": False,
                "resolver": "person-evidence-model-classifier-v10.1",
            }),
        ))
        session.add_all([
            _track("T_DIRECT", "RESOLVED_A", "SHOT_1", face_visible=True),
            _track("T_RECOVERED", "RESOLVED_A", "SHOT_2", face_visible=False, recovery_score=0.83),
            _track("T_PENDING", "UNRESOLVED_B", "SHOT_3", face_visible=False),
        ])
        session.commit()
    return project_id


def test_face_optional_recovered_track_is_visible_as_resolved_shot_evidence(monkeypatch, tmp_path: Path) -> None:
    project_id = _seed(monkeypatch, tmp_path)
    workspace = {
        "project_id": project_id,
        "analysis": {"id": "RUN_V101"},
        "characters": [{"id": "CHAR_A", "source_candidate_ids": ["RESOLVED_A"]}],
        "evidence_by_shot": {
            "SHOT_2": {"characters": [], "scene": {"candidate_id": "SCENE_A"}, "props": [{"candidate_id": "PROP_A"}]},
        },
    }

    result = decorate_asset_workspace_character_evidence(workspace)

    shot2 = result["evidence_by_shot"]["SHOT_2"]
    assert shot2["scene"] == {"candidate_id": "SCENE_A"}
    assert shot2["props"] == [{"candidate_id": "PROP_A"}]
    assert shot2["character_diagnostics"] == []
    assert shot2["characters"] == [{
        "candidate_id": "RESOLVED_A",
        "label": "人物 001",
        "confidence": 0.83,
        "cover_url": None,
        "final_asset_id": "CHAR_A",
        "identity_status": "RESOLVED",
        "face_required": False,
        "recovered_track": True,
        "confidence_source": "V10_1_TRACK_KNOWN_IDENTITY_RECOVERY",
        "recovery_source": "V10_1_TRACK_KNOWN_IDENTITY_RECOVERY",
    }]


def test_unresolved_track_stays_diagnostic_and_cannot_look_like_final_binding(monkeypatch, tmp_path: Path) -> None:
    project_id = _seed(monkeypatch, tmp_path)
    workspace = {
        "project_id": project_id,
        "analysis": {"id": "RUN_V101"},
        "characters": [{"id": "CHAR_A", "source_candidate_ids": ["RESOLVED_A"]}],
        "evidence_by_shot": {},
    }

    result = decorate_asset_workspace_character_evidence(workspace)

    shot3 = result["evidence_by_shot"]["SHOT_3"]
    assert shot3["characters"] == []
    pending = shot3["character_diagnostics"][0]
    assert pending["candidate_id"] == "UNRESOLVED_B"
    assert pending["identity_status"] == "UNRESOLVED"
    assert pending["final_asset_id"] is None
    assert pending["confidence"] is None
    assert pending["confidence_source"] == "UNRESOLVED_DIAGNOSTIC"
