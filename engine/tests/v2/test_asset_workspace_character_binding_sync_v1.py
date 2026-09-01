from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from engine.app import studio_v2
from engine.app.asset_workspace_character_v101 import decorate_asset_workspace_character_evidence
from engine.app.asset_workspace_v3 import ShotCharacterBinding
from engine.app.content_analysis_v2 import CharacterCandidate, ContentAnalysisRun


def _use_temp_database(monkeypatch, tmp_path: Path) -> None:
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


def _seed(monkeypatch, tmp_path: Path, *, with_binding: bool) -> str:
    _use_temp_database(monkeypatch, tmp_path)
    project_id = "PROJECT_BINDING_SYNC"
    with studio_v2.get_session() as session:
        session.add(studio_v2.Project(
            id=project_id,
            name="Binding Sync",
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
        session.add(studio_v2.Shot(
            id="SHOT_2",
            episode_id="EP_1",
            ordinal=2,
            start_us=800_000,
            end_us=3_640_000,
            duration_us=2_840_000,
            reference_clip_path=str(tmp_path / "shot_2.mp4"),
            status="READY",
        ))
        session.add(studio_v2.Character(
            id="CHAR_XURAN",
            project_id=project_id,
            name="徐然",
            status="MANUAL",
            metadata_json=json.dumps({"source_candidate_ids": ["CANDIDATE_XURAN"]}),
        ))
        session.add(ContentAnalysisRun(
            id="RUN_1",
            project_id=project_id,
            status="READY_WITH_WARNINGS",
            is_current=True,
            profile_version="f05-assets-v10.1-person-evidence-model-classification",
            component_status_json="{}",
            counts_json="{}",
        ))
        session.add(CharacterCandidate(
            id="CANDIDATE_XURAN",
            run_id="RUN_1",
            project_id=project_id,
            ordinal=1,
            auto_label="人物 001",
            track_count=0,
            shot_count=0,
            confidence=0.95,
            cover_path=None,
            evidence_json=json.dumps({
                "identity_status": "RESOLVED",
                "final_asset_eligible": True,
                "resolver": "person-evidence-model-classifier-v10.1",
                "shot_assignment_version": "v10.1-shot-character-assignment-1",
                "shot_presence_assignments": [],
            }),
        ))
        if with_binding:
            session.add(ShotCharacterBinding(
                id="SHOTCHAR_1",
                project_id=project_id,
                shot_id="SHOT_2",
                character_id="CHAR_XURAN",
                source="MANUAL",
                confidence=None,
                source_run_id="RUN_1",
                source_candidate_id="CANDIDATE_XURAN",
            ))
        session.commit()
    return project_id


def test_db_final_binding_repairs_asset_library_and_shot_matrix_together(monkeypatch, tmp_path: Path) -> None:
    project_id = _seed(monkeypatch, tmp_path, with_binding=True)
    workspace = {
        "project_id": project_id,
        "analysis": {"id": "RUN_1"},
        # Simulate a contradictory/stale API payload like the reported UI:
        # Asset Library and matrix are not allowed to keep different Final truth.
        "characters": [{
            "id": "CHAR_XURAN",
            "name": "徐然",
            "shot_ids": [],
            "shot_count": 0,
            "source_candidate_ids": ["CANDIDATE_XURAN"],
        }],
        "bindings_by_shot": {
            "SHOT_2": {"character_ids": [], "scene_id": "SCENE_1", "prop_ids": ["PROP_1"]},
        },
        "evidence_by_shot": {},
    }

    result = decorate_asset_workspace_character_evidence(workspace)

    assert result["characters"][0]["shot_ids"] == ["SHOT_2"]
    assert result["characters"][0]["shot_count"] == 1
    assert result["bindings_by_shot"]["SHOT_2"]["character_ids"] == ["CHAR_XURAN"]
    # Character reconciliation must not damage the other Final binding dimensions.
    assert result["bindings_by_shot"]["SHOT_2"]["scene_id"] == "SCENE_1"
    assert result["bindings_by_shot"]["SHOT_2"]["prop_ids"] == ["PROP_1"]


def test_stale_frontend_character_binding_is_removed_when_db_has_no_final_binding(monkeypatch, tmp_path: Path) -> None:
    project_id = _seed(monkeypatch, tmp_path, with_binding=False)
    workspace = {
        "project_id": project_id,
        "analysis": {"id": "RUN_1"},
        "characters": [{
            "id": "CHAR_XURAN",
            "name": "徐然",
            "shot_ids": ["SHOT_2"],
            "shot_count": 1,
            "source_candidate_ids": ["CANDIDATE_XURAN"],
        }],
        "bindings_by_shot": {
            "SHOT_2": {"character_ids": ["CHAR_XURAN"], "scene_id": None, "prop_ids": []},
        },
        "evidence_by_shot": {},
    }

    result = decorate_asset_workspace_character_evidence(workspace)

    assert result["characters"][0]["shot_ids"] == []
    assert result["characters"][0]["shot_count"] == 0
    assert result["bindings_by_shot"]["SHOT_2"]["character_ids"] == []
