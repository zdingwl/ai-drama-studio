from __future__ import annotations

import pytest
from pydantic import ValidationError

from engine.app.target_localization_contract_v1 import TargetLocalizationBundleV1


def _payload() -> dict:
    return {
        "schema_version": "target-localization-v1",
        "project_id": "PROJECT_1",
        "source_fingerprint": "b" * 64,
        "target_language": "en-US",
        "target_region": "US",
        "scene_policy": "AUTO",
        "status": "READY",
        "target_character_count": 1,
        "scene_mapping_count": 1,
        "review_count": 0,
        "target_characters": [
            {
                "id": "TARGETCHAR_1",
                "project_id": "PROJECT_1",
                "source_character_id": "CHAR_1",
                "source_character_name": "林晚",
                "source_character_signature": "c" * 64,
                # Generated before an unrelated source-dialogue speaker correction.
                "source_fingerprint": "a" * 64,
                "target_language": "en-US",
                "target_region": "US",
                "target_name": "Emma Miller",
                "appearance_profile": "American woman in her mid-20s, professional appearance",
                "generation_prompt": "consistent American woman, mid-20s, professional",
                "confidence": 0.93,
                "status": "READY",
                "decision_source": "AI",
                "reference_assets": [],
                "created_at": "2026-09-02T00:00:00+00:00",
                "updated_at": "2026-09-02T00:00:00+00:00",
            }
        ],
        "scene_mappings": [
            {
                "id": "SCENELOCAL_1",
                "project_id": "PROJECT_1",
                "episode_id": "EP_1",
                "scene_key": "ASSET:SCENE_1",
                "source_scene_id": "SCENE_1",
                "source_scene_name": "客厅",
                "source_scene_signature": "d" * 64,
                # Same provenance rule as TargetCharacter: this is not the freshness key.
                "source_fingerprint": "a" * 64,
                "project_policy": "AUTO",
                "decision": "KEEP",
                "decision_source": "AI",
                "confidence": 0.92,
                "target_label": None,
                "target_description": None,
                "reason": "No localization required",
                "status": "READY",
                "created_at": "2026-09-02T00:00:00+00:00",
                "updated_at": "2026-09-02T00:00:00+00:00",
            }
        ],
    }


def test_unrelated_source_fingerprint_change_does_not_invalidate_target_plan() -> None:
    bundle = TargetLocalizationBundleV1.model_validate(_payload())

    assert bundle.source_fingerprint == "b" * 64
    assert bundle.target_characters[0].source_fingerprint == "a" * 64
    assert bundle.scene_mappings[0].source_fingerprint == "a" * 64


def test_relevant_scene_policy_mismatch_is_still_rejected() -> None:
    payload = _payload()
    payload["scene_mappings"][0]["project_policy"] = "KEEP"

    with pytest.raises(ValidationError, match="project policy is stale"):
        TargetLocalizationBundleV1.model_validate(payload)
