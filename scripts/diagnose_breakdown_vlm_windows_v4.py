#!/usr/bin/env python3
"""Read-only Window-only diagnostic for the local-index Segment Contract v4 candidate.

This wrapper reuses the existing completed-Run diagnostic and temporarily injects the v4 timed
runner only for this process. It performs no DB/sidecar/Draft/Final writes and does not run
Exact-Shot grounding. Production provider routing is intentionally unchanged until v4 passes the
real Window-only gate.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
for candidate in (str(REPO_ROOT), str(SCRIPT_DIR)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import diagnose_breakdown_vlm_windows as base_diag
from engine.app import breakdown_p2_vlm_runtime_v1 as runtime

WINDOW_PROMPT_PROFILE = "breakdown-p2-vlm-window-context-segment-index-zh-v4"
V4_RUNNER = REPO_ROOT / "scripts" / "run_breakdown_vlm_fast_grounded_qwen3_timed_v3.py"


class _V4CandidateProvider(runtime.Qwen3VLSemanticProvider):
    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("runner_script", str(V4_RUNNER))
        super().__init__(*args, **kwargs)


def diagnose(run_id: str) -> dict:
    original = runtime.Qwen3VLSemanticProvider
    runtime.Qwen3VLSemanticProvider = _V4CandidateProvider
    try:
        payload = base_diag.diagnose(run_id)
    finally:
        runtime.Qwen3VLSemanticProvider = original
    payload = dict(payload)
    payload["candidate_window_prompt_profile"] = WINDOW_PROMPT_PROFILE
    return payload


def _summary(payload: dict) -> str:
    base = base_diag._window_summary(payload)
    lines = base.splitlines()
    insert_at = 2 if len(lines) >= 2 else len(lines)
    lines.insert(insert_at, f"Candidate Window profile: {WINDOW_PROMPT_PROFILE}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Window Context v4 candidate only against a completed frozen Breakdown Run"
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = diagnose(args.run_id)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_summary(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
