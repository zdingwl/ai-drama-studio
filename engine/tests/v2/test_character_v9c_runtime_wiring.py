from __future__ import annotations

import engine.app.asset_analysis_progress_v4 as asset_progress
import engine.app.character_identity_v9c as identity_v9c
import engine.app.character_visual_v2 as compat
from engine.app.character_runtime_v6 import runtime_status


def test_formal_character_compatibility_entry_uses_v9c_identity() -> None:
    assert compat.cluster_candidates is identity_v9c.resolve_global_identities


def test_runtime_profile_marks_v9c_and_disables_v8_identity() -> None:
    status = runtime_status()

    assert status["profile"] == "character-v9c-person-gallery-anchor-first"
    assert status["identity"]["resolver"] == "V9C Person Gallery Anchor-first Confirm-then-Absorb"
    assert status["identity"]["v8_identity"] == "DISABLED"
    assert status["features"]["single_total_embedding"] is False
    assert status["observation"]["whole_frame_identity_input"] is False


def test_formal_asset_profile_marks_v9c() -> None:
    assert asset_progress.FORMAL_ASSET_PROFILE_VERSION == "f05-assets-v9c-person-gallery-anchor-first"
    assert asset_progress.FORMAL_CHARACTER_COMPONENT_PROFILE == "V9C_PERSON_GALLERY_ANCHOR_FIRST"
