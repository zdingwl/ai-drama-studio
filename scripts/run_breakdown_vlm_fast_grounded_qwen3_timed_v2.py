#!/usr/bin/env python3
"""Timed Fast Grounded runner using Window Segment Contract v3.

The timing/generation instrumentation remains in the v1 timed runner. This thin entry only swaps
its Window analyzer module from compact-v2 to segment-v3 before execution. Exact-Shot grounding is
therefore byte-for-byte the same code path as the previous timed runner.
"""
from __future__ import annotations

import run_breakdown_vlm_fast_grounded_qwen3_timed as timed
import run_breakdown_vlm_window_segment_v3 as segment

# The timed runner intentionally references its global ``compact`` module at runtime. Rebinding it
# here changes only Window Context generation/normalization; Exact-Shot grounding stays unchanged.
timed.compact = segment


if __name__ == "__main__":
    raise SystemExit(timed.main())
