from __future__ import annotations

import json

from engine.app.asset_final_gate_v9 import _candidate_is_final_eligible
from engine.app.content_analysis_v2 import CharacterCandidate


def candidate(evidence: dict[str, object]) -> CharacterCandidate:
    return CharacterCandidate(
        id="C_V91",
        run_id="RUN_V91",
        project_id="P1",
        ordinal=1,
        auto_label="人物 001",
        track_count=3,
        shot_count=3,
        confidence=0.9,
        cover_path=None,
        evidence_json=json.dumps(evidence),
    )


def test_v91_confirmed_gallery_is_final_eligible_without_face_tracks() -> None:
    value = candidate({
        "identity_status": "RESOLVED",
        "final_asset_eligible": True,
        "profile": "f05-assets-v9.1-confirmed-person-gallery-final-gate",
        "resolver": "person-gallery-progressive-v9.1",
        "confirmed_gallery_images": 3,
        "confirmed_gallery_shots": 3,
        "face_images": 0,
    })

    assert _candidate_is_final_eligible(
        value,
        run_profile="f05-assets-v9.1-confirmed-person-gallery-final-gate",
        tracks=[],
    ) is True


def test_v91_unknown_resolver_fails_closed() -> None:
    value = candidate({
        "identity_status": "RESOLVED",
        "final_asset_eligible": True,
        "profile": "f05-assets-v9.1-confirmed-person-gallery-final-gate",
        "resolver": "some-unknown-resolver",
        "confirmed_gallery_images": 99,
        "confirmed_gallery_shots": 99,
    })

    assert _candidate_is_final_eligible(
        value,
        run_profile="f05-assets-v9.1-confirmed-person-gallery-final-gate",
        tracks=[],
    ) is False
