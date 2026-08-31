#!/usr/bin/env python3
"""Replay candidate G1 Scene/anonymous-subject Fusion from immutable sidecars only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.app.breakdown_g1_fusion_replay_v2 import format_summary
from engine.app.breakdown_g1_fusion_replay_completed_v2 import replay_completed_run


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only G1 Fusion replay; never runs ASR/OCR/VLM and never mutates a BreakdownRun."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--json", action="store_true", help="Print full JSON instead of compact summary.")
    args = parser.parse_args()

    payload = replay_completed_run(args.run_id)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(format_summary(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
