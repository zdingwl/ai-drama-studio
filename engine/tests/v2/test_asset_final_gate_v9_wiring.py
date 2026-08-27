from __future__ import annotations

from engine.app import asset_final_gate_v9


def test_historical_v9_resolvers_remain_accepted() -> None:
    assert "person-gallery-anchor-first-v9c" in asset_final_gate_v9.FORMAL_RESOLVERS
    assert "person-gallery-progressive-v9.1" in asset_final_gate_v9.FORMAL_RESOLVERS
