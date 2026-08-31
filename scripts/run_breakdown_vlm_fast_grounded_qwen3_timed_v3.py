#!/usr/bin/env python3
"""Timed Fast Grounded runner using Window local-index Segment Contract v4.

The timing/generation instrumentation and Exact-Shot path remain in the existing timed runner.
This entry only swaps the Window analyzer module to the v4 local-index adapter before execution.
"""
from __future__ import annotations

from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_breakdown_vlm_fast_grounded_qwen3_timed as timed
import run_breakdown_vlm_window_segment_index_v4 as segment

# The timed runner references its global ``compact`` analyzer at runtime. Rebinding that module here
# changes only Window Context generation/normalization; Exact-Shot grounding stays unchanged.
timed.compact = segment


if __name__ == "__main__":
    raise SystemExit(timed.main())
