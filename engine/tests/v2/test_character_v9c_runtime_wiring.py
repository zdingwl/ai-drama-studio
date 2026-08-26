from __future__ import annotations

import engine.app.asset_analysis_progress_v4 as asset_progress
import engine.app.character_identity_v91 as identity_v91
import engine.app.character_visual_v2 as compat
from engine.app.character_runtime_v6 import runtime_status


def test_formal_character_compatibility_entry_uses_v91_identity() -> None:
    assert compat.cluster_candidates is identity_v91.resolve_global_identities


def test_runtime_profile_marks_v91_progressive_gallery() -> None:
    status = runtime_status()

    assert status["profile"] == "character-v9.1-person-gallery-progressive-anchor"
    assert status["identity"]["resolver"] == "person-gallery-progressive-v9.1"
    assert status["identity"]["v8_identity"] == "DISABLED"
    assert status["identity"]["v9c_single_seed_grouping"] == "DISABLED"
    assert status["features"]["single_total_embedding"] is False
    assert status["observation"]["whole_frame_identity_input"] is False
    assert status["gallery"]["single_seed_identity"] is False


def test_formal_asset_profile_marks_v91_final_gate() -> None:
    assert asset_progress.FORMAL_ASSET_PROFILE_VERSION == "f05-assets-v9.1-confirmed-person-gallery-final-gate"
    assert asset_progress.FORMAL_CHARACTER_COMPONENT_PROFILE == "V9_1_PROGRESSIVE_PERSON_GALLERY_FINAL_GATE"
