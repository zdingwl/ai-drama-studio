#!/usr/bin/env python3
"""Timed Fast Grounded candidate: accepted Window v4 + Exact-Shot compact v2.

This entry is diagnostic-only until real selected-batch acceptance. It keeps the existing timed
instrumentation, swaps Window Context to the accepted local-index v4 adapter, and swaps only the
Exact-Shot grounding function to the compact-v2 adapter. No production provider points here yet.
"""
from __future__ import annotations

from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_breakdown_vlm_fast_grounded_qwen3_timed as timed
import run_breakdown_vlm_window_segment_index_v4 as window_v4
import run_breakdown_vlm_exact_shot_compact_v2 as exact_v2

# Accepted production Window contract.
timed.compact = window_v4
# Candidate Exact-Shot contract only. The timed runner calls this global function at runtime.
timed.fast._grounding_adaptive = exact_v2.grounding_adaptive


if __name__ == "__main__":
    raise SystemExit(timed.main())
