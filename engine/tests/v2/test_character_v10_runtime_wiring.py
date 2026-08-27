from __future__ import annotations

import engine.app.asset_analysis_progress_v4 as asset_progress
import engine.app.character_identity_v10 as identity_v10
import engine.app.character_visual_v2 as compat
from engine.app.character_runtime_v6 import runtime_status


def test_formal_character_compatibility_entry_uses_v10_identity() -> None:
    assert compat.cluster_candidates is identity_v10.resolve_global_identities


def test_runtime_profile_marks_capture_first_v10() -> None:
    status = runtime_status()

    assert status["profile"] == "character-v10-capture-first-model-classification"
    assert status["observation"]["capture_first"] is True
    assert status["observation"]["front_side_back_supported"] is True
    assert status["observation"]["preclassification_persistence"] is True
    assert status["gallery"]["formal_representatives"].startswith("classified model-usable")
    assert status["identity"]["resolver"] == "person-evidence-model-classifier-v10"
    assert status["identity"]["person_reid_role"].startswith("primary model signal")


def test_formal_asset_profile_marks_v10() -> None:
    assert asset_progress.FORMAL_ASSET_PROFILE_VERSION == "f05-assets-v10-person-evidence-model-classification"
    assert asset_progress.FORMAL_CHARACTER_COMPONENT_PROFILE == "V10_PERSON_EVIDENCE_MODEL_CLASSIFICATION"
