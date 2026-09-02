from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engine.app import studio_v2
from engine.app.asset_workspace_character_v101 import (
    _build_character_coverage,
    decorate_asset_workspace_character_evidence,
)
from engine.app.breakdown_models_v1 import (
    BreakdownRun,
    LocalSubject,
    SceneSegmentDraft,
    ShotLocalSubject,
    ShotSemanticDraft,
)
from engine.app.content_analysis_v2 import CharacterCandidate, CharacterTrack, ContentAnalysisRun
from engine.app.review_issue_sync_v1 import _character_coverage_problem
from engine.app.shot_revision_v2 import ShotRevision, ShotRevisionItem


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


def _seed_breakdown_people(project_id: str, *, shot_id: str, count: int, tmp_path: Path) -> None:
    with studio_v2.get_session() as session:
        session.add(ShotRevision(
            id="SHOTREV_1",
            episode_id="EP_1",
            revision=1,
            kind="AUTO",
            is_current=True,
            note="coverage test",
        ))
        session.add(ShotRevisionItem(
            id="SHOTREVITEM_1",
            revision_id="SHOTREV_1",
            original_shot_id=shot_id,
            ordinal=1,
            start_us=0,
            end_us=1_000_000,
            duration_us=1_000_000,
            reference_clip_path=str(tmp_path / "shot_1.mp4"),
            shot_status="READY",
        ))
        session.add(BreakdownRun(
            id="BREAKDOWN_1",
            project_id=project_id,
            episode_id="EP_1",
            source_shot_revision_id="SHOTREV_1",
            status="READY",
            is_current=True,
            schema_version="breakdown-draft-v1",
        ))
        session.add(SceneSegmentDraft(
            id="SEGMENT_1",
            run_id="BREAKDOWN_1",
            episode_id="EP_1",
            ordinal=1,
            source_start_us=0,
            source_end_us=1_000_000,
        ))
        session.add(ShotSemanticDraft(
            id="SHOTDRAFT_1",
            run_id="BREAKDOWN_1",
            scene_segment_id="SEGMENT_1",
            source_shot_revision_item_id="SHOTREVITEM_1",
            source_shot_id_snapshot=shot_id,
            shot_ordinal_snapshot=1,
            source_start_us=0,
            source_end_us=1_000_000,
        ))
        for ordinal in range(1, count + 1):
            subject_id = f"LOCAL_SUBJECT_{ordinal}"
            session.add(LocalSubject(
                id=subject_id,
                run_id="BREAKDOWN_1",
                scene_segment_id="SEGMENT_1",
                ordinal=ordinal,
                display_label=f"人物{ordinal}",
                first_seen_us=0,
                last_seen_us=1_000_000,
            ))
            session.add(ShotLocalSubject(
                id=f"SHOT_LOCAL_SUBJECT_{ordinal}",
                run_id="BREAKDOWN_1",
                shot_draft_id="SHOTDRAFT_1",
                local_subject_id=subject_id,
                first_seen_us=0,
                last_seen_us=1_000_000,
            ))
        session.commit()


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


def test_explicit_assignment_can_bind_character_without_candidate_track_in_that_shot(monkeypatch, tmp_path: Path) -> None:
    project_id = _seed(monkeypatch, tmp_path)
    with studio_v2.get_session() as session:
        candidate = session.get(CharacterCandidate, "RESOLVED_A")
        assert candidate is not None
        evidence = json.loads(candidate.evidence_json)
        evidence.update({
            "shot_assignment_version": "v10.1-shot-character-assignment-1",
            "shot_assignment_source": "V10_1_SHOT_CHARACTER_ASSIGNMENT",
            "shot_presence_assignments": [
                {
                    "shot_id": "SHOT_1",
                    "confidence": 0.94,
                    "mode": "DIRECT_IDENTITY",
                    "source": "V10_1_SHOT_CHARACTER_ASSIGNMENT",
                },
                {
                    "shot_id": "SHOT_3",
                    "confidence": 0.89,
                    "mode": "FACE_STRONG",
                    "source": "V10_1_SHOT_CHARACTER_ASSIGNMENT",
                },
            ],
        })
        candidate.evidence_json = json.dumps(evidence)
        session.commit()

    workspace = {
        "project_id": project_id,
        "analysis": {"id": "RUN_V101"},
        "characters": [{"id": "CHAR_A", "source_candidate_ids": ["RESOLVED_A"]}],
        "evidence_by_shot": {},
    }

    result = decorate_asset_workspace_character_evidence(workspace)

    # SHOT_2 has a historical RESOLVED_A Track but is intentionally absent from the
    # explicit assignment map, so it must not silently reappear as Character presence.
    assert result["evidence_by_shot"]["SHOT_2"]["characters"] == []
    shot3 = result["evidence_by_shot"]["SHOT_3"]
    assert shot3["characters"] == [{
        "candidate_id": "RESOLVED_A",
        "label": "人物 001",
        "confidence": 0.89,
        "cover_url": None,
        "final_asset_id": "CHAR_A",
        "identity_status": "RESOLVED",
        "face_required": False,
        "recovered_track": True,
        "confidence_source": "V10_1_SHOT_CHARACTER_ASSIGNMENT:FACE_STRONG",
        "recovery_source": "V10_1_SHOT_CHARACTER_ASSIGNMENT:FACE_STRONG",
    }]
    assert shot3["character_diagnostics"][0]["candidate_id"] == "UNRESOLVED_B"


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
    assert shot3["character_coverage"]["complete"] is False
    assert shot3["character_coverage"]["reason"] == "UNRESOLVED_PERSON"


def test_breakdown_people_without_complete_binding_are_not_auto_consistent(monkeypatch, tmp_path: Path) -> None:
    project_id = _seed(monkeypatch, tmp_path)
    _seed_breakdown_people(project_id, shot_id="SHOT_1", count=2, tmp_path=tmp_path)
    workspace = {
        "project_id": project_id,
        "analysis": {"id": "RUN_V101"},
        "characters": [{"id": "CHAR_A", "source_candidate_ids": ["RESOLVED_A"]}],
        "evidence_by_shot": {},
        "bindings_by_shot": {},
    }

    result = decorate_asset_workspace_character_evidence(workspace)
    coverage = result["evidence_by_shot"]["SHOT_1"]["character_coverage"]

    assert coverage["breakdown_person_count"] == 2
    assert coverage["visual_candidate_count"] == 1
    assert coverage["detected_person_count"] == 2
    assert coverage["bound_person_count"] == 0
    assert coverage["missing_person_count"] == 2
    assert coverage["complete"] is False
    assert coverage["reason"] == "NO_BINDING"


def test_two_detected_people_with_one_binding_are_partial_and_need_review() -> None:
    coverage = _build_character_coverage(
        breakdown_person_count=2,
        visual_candidate_count=2,
        bound_person_count=1,
        unresolved_person_count=0,
    )

    assert coverage["detected_person_count"] == 2
    assert coverage["bound_person_count"] == 1
    assert coverage["missing_person_count"] == 1
    assert coverage["complete"] is False
    assert coverage["reason"] == "PARTIAL_BINDING"
    assert _character_coverage_problem({"character_coverage": coverage}) == "镜头理解识别到 2 个人物，当前只绑定 1 个，需要确认缺失人物"


def test_character_coverage_is_complete_only_after_all_detected_people_are_bound() -> None:
    coverage = _build_character_coverage(
        breakdown_person_count=2,
        visual_candidate_count=2,
        bound_person_count=2,
        unresolved_person_count=0,
    )

    assert coverage["missing_person_count"] == 0
    assert coverage["complete"] is True
    assert coverage["reason"] == "COMPLETE"
    assert _character_coverage_problem({"character_coverage": coverage}) is None
