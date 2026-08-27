from __future__ import annotations

from engine.app import asset_analysis_progress_v4, asset_final_gate_v10, asset_routes_v3


def test_formal_asset_routes_use_v10_final_gate() -> None:
    assert asset_routes_v3.apply_analysis_to_assets is asset_final_gate_v10.apply_analysis_to_assets


def test_v10_and_v101_resolvers_are_accepted_by_formal_gate() -> None:
    assert "person-evidence-model-classifier-v10" in asset_final_gate_v10.FORMAL_RESOLVERS
    assert "person-evidence-model-classifier-v10.1" in asset_final_gate_v10.FORMAL_RESOLVERS


def test_formal_asset_profile_marks_v101() -> None:
    assert asset_analysis_progress_v4.FORMAL_ASSET_PROFILE_VERSION == "f05-assets-v10.1-person-evidence-model-classification"
    assert asset_analysis_progress_v4.FORMAL_CHARACTER_COMPONENT_PROFILE == "V10_1_PERSON_EVIDENCE_MODEL_CLASSIFICATION"
