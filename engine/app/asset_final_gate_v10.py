"""Formal Character V10 Final Asset Gate.

The implementation keeps historical V9 compatibility in asset_final_gate_v9, while
this module is the only formal route entry for V10 asset materialization.
"""
from engine.app.asset_final_gate_v9 import (  # noqa: F401
    FINAL_POLICY,
    FORMAL_RESOLVERS,
    _candidate_is_final_eligible,
    apply_analysis_to_assets,
)

__all__ = [
    "FINAL_POLICY",
    "FORMAL_RESOLVERS",
    "_candidate_is_final_eligible",
    "apply_analysis_to_assets",
]
