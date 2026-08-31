#!/usr/bin/env python3
"""Read-only Exact-Shot compact-v3 candidate diagnostic."""
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

import diagnose_breakdown_exact_shot_batches as base_diag
import run_breakdown_vlm_exact_shot_compact_v3 as exact_v3
from engine.app import breakdown_p2_vlm_runtime_v1 as runtime

CANDIDATE_RUNNER = REPO_ROOT / "scripts" / "run_breakdown_vlm_fast_grounded_qwen3_timed_v5.py"


class _CompactExactV3CandidateProvider(runtime.Qwen3VLSemanticProvider):
    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("runner_script", str(CANDIDATE_RUNNER))
        super().__init__(*args, **kwargs)


def diagnose(run_id: str, batch_numbers: tuple[int, ...]) -> dict:
    original = runtime.Qwen3VLSemanticProvider
    runtime.Qwen3VLSemanticProvider = _CompactExactV3CandidateProvider
    try:
        payload = base_diag.diagnose(run_id, batch_numbers)
    finally:
        runtime.Qwen3VLSemanticProvider = original
    result = dict(payload)
    result["candidate_exact_shot_profile"] = exact_v3.EXACT_SHOT_PROMPT_PROFILE
    return result


def _summary(payload: dict) -> str:
    base = base_diag._summary(payload)
    lines = base.splitlines()
    insert_at = 3 if len(lines) >= 3 else len(lines)
    lines.insert(insert_at, f"Candidate Exact-Shot profile: {exact_v3.EXACT_SHOT_PROMPT_PROFILE}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run reconstruction-safe compact Exact-Shot v3 candidate")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--batches", default="1")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = diagnose(args.run_id, base_diag._parse_batch_numbers(args.batches))
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_summary(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
