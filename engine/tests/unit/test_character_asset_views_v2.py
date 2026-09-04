from engine.app.character_assets_routes_v1 import (
    VIEW_SCHEMA_V2,
    VIEWS_LEGACY,
    VIEWS_V2,
    _views_for_receipt,
)


def test_new_character_reference_versions_use_front_three_quarter_side_back():
    assert VIEWS_V2 == ("front", "three_quarter", "side", "back")
    assert _views_for_receipt({"view_schema": VIEW_SCHEMA_V2}) == VIEWS_V2


def test_historical_character_reference_versions_keep_old_view_paths():
    assert _views_for_receipt({}) == VIEWS_LEGACY
    assert _views_for_receipt({"view_schema": "legacy-v1"}) == VIEWS_LEGACY
