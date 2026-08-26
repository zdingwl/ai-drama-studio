from __future__ import annotations

from engine.app import asset_analysis_progress_v4, asset_final_gate_v9, asset_routes_v3


def test_formal_asset_routes_use_v9d_final_gate() -> None:
    assert asset_routes_v3.apply_analysis_to_assets is asset_final_gate_v9.apply_analysis_to_assets


def test_formal_asset_profile_marks_v91_final_gate() -> None:
    assert asset_analysis_progress_v4.FORMAL_ASSET_PROFILE_VERSION == (
        "f05-assets-v9.1-confirmed-person-gallery-final-gate"
    )
    assert asset_analysis_progress_v4.FORMAL_CHARACTER_COMPONENT_PROFILE == (
        "V9_1_PROGRESSIVE_PERSON_GALLERY_FINAL_GATE"
    )
