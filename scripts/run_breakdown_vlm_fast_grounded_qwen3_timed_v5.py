#!/usr/bin/env python3
"""Timed Fast Grounded candidate: accepted Window v4 + reconstruction-safe Exact-Shot compact v3.

Diagnostic-only until selected-batch real acceptance. Production provider routing is unchanged.
"""
from __future__ import annotations

from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_breakdown_vlm_fast_grounded_qwen3_timed as timed
import run_breakdown_vlm_window_segment_index_v4 as window_v4
import run_breakdown_vlm_exact_shot_compact_v3 as exact_v3

timed.compact = window_v4
timed.fast._grounding_adaptive = exact_v3.grounding_adaptive


if __name__ == "__main__":
    raise SystemExit(timed.main())
