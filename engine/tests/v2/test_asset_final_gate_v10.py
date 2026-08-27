from __future__ import annotations

import json

from engine.app.asset_final_gate_v10 import _candidate_is_final_eligible
from engine.app.content_analysis_v2 import CharacterCandidate


def candidate(evidence: dict[str, object]) -> CharacterCandidate:
    return CharacterCandidate(
        id="C_V10",
        run_id="RUN_V10",
        project_id="PROJECT_V10",
        ordinal=1,
        auto_label="人物 001",
        track_count=3,
        shot_count=3,
        confidence=0.9,
        cover_path=None,
        evidence_json=json.dumps(evidence),
    )


def test_confirmed_v10_model_identity_passes_without_face_tracks() -> None:
    value = candidate({
        "identity_status": "RESOLVED",
        "final_asset_eligible": True,
        "profile": "f05-assets-v10-person-evidence-model-classification",
        "resolver": "person-evidence-model-classifier-v10",
        "confirmed_gallery_images": 4,
        "confirmed_gallery_shots": 3,
        "face_images": 0,
    })

    assert _candidate_is_final_eligible(
        value,
        run_profile="f05-assets-v10-person-evidence-model-classification",
        tracks=[],
    ) is True


def test_v10_unresolved_never_passes_final_gate() -> None:
    value = candidate({
        "identity_status": "UNRESOLVED",
        "final_asset_eligible": False,
        "profile": "f05-assets-v10-person-evidence-model-classification",
        "resolver": "person-evidence-model-classifier-v10",
        "confirmed_gallery_images": 10,
        "confirmed_gallery_shots": 8,
    })

    assert _candidate_is_final_eligible(
        value,
        run_profile="f05-assets-v10-person-evidence-model-classification",
        tracks=[],
    ) is False
