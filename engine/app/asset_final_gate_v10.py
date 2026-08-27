"""Formal Character V10/V10.1 Final Asset Gate.

The implementation keeps historical V9 compatibility in asset_final_gate_v9, while
this module is the only formal route entry for V10+ asset materialization.
"""
from engine.app.asset_final_gate_v9 import (  # noqa: F401
    FINAL_POLICY,
    FORMAL_RESOLVERS,
    _candidate_is_final_eligible,
    apply_analysis_to_assets,
)

# V10.1 keeps the same fail-closed Final Gate contract; only the upstream identity
# resolver changes how strong contaminated/substantial partial evidence can become a
# confirmed >=3-Shot Person identity.
FORMAL_RESOLVERS.add("person-evidence-model-classifier-v10.1")

__all__ = [
    "FINAL_POLICY",
    "FORMAL_RESOLVERS",
    "_candidate_is_final_eligible",
    "apply_analysis_to_assets",
]
