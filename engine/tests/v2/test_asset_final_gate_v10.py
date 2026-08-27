from __future__ import annotations

import json

from engine.app.asset_final_gate_v10 import _candidate_is_final_eligible
from engine.app.asset_final_gate_v9 import _shot_binding_confidence
from engine.app.content_analysis_v2 import CharacterCandidate, CharacterTrack


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


def character_track(*, recovery_score: float | None = None) -> CharacterTrack:
    recovery = None if recovery_score is None else {
        "source": "V10_1_TRACK_KNOWN_IDENTITY_RECOVERY",
        "target_candidate_id": "C_V10",
        "shot_id": "SHOT_TARGET",
        "score": recovery_score,
        "observation_count": 3,
    }
    return CharacterTrack(
        id="TRACK_TEST",
        run_id="RUN_V10",
        candidate_id="C_V10",
        shot_id="SHOT_TARGET",
        start_us=0,
        end_us=500_000,
        representative_source_us=250_000,
        bbox_json="[0,0,100,200]",
        sample_count=3,
        face_visible=False,
        mean_face_score=None,
        body_evidence_score=0.8,
        evidence_json=json.dumps({"identity_recovery": recovery}),
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


def test_confirmed_v101_risky_seed_identity_passes_same_fail_closed_gate() -> None:
    value = candidate({
        "identity_status": "RESOLVED",
        "final_asset_eligible": True,
        "profile": "f05-assets-v10.1-person-evidence-model-classification",
        "resolver": "person-evidence-model-classifier-v10.1",
        "confirmed_gallery_images": 3,
        "confirmed_gallery_shots": 3,
        "risky_seed_confirmation": True,
        "face_images": 0,
    })

    assert _candidate_is_final_eligible(
        value,
        run_profile="f05-assets-v10.1-person-evidence-model-classification",
        tracks=[],
    ) is True


def test_v10_unresolved_never_passes_final_gate() -> None:
    value = candidate({
        "identity_status": "UNRESOLVED",
        "final_asset_eligible": False,
        "profile": "f05-assets-v10.1-person-evidence-model-classification",
        "resolver": "person-evidence-model-classifier-v10.1",
        "confirmed_gallery_images": 10,
        "confirmed_gallery_shots": 8,
    })

    assert _candidate_is_final_eligible(
        value,
        run_profile="f05-assets-v10.1-person-evidence-model-classification",
        tracks=[],
    ) is False


def test_recovered_only_shot_uses_track_presence_confidence() -> None:
    value = candidate({})
    track = character_track(recovery_score=0.82)

    assert _shot_binding_confidence(value, [track]) == 0.82


def test_direct_track_keeps_identity_confidence_fallback() -> None:
    value = candidate({})
    track = character_track()

    assert _shot_binding_confidence(value, [track]) == 0.9


def test_direct_track_wins_over_recovered_fragment_in_same_shot() -> None:
    value = candidate({})
    direct = character_track()
    recovered = character_track(recovery_score=0.82)

    assert _shot_binding_confidence(value, [direct, recovered]) == 0.9
