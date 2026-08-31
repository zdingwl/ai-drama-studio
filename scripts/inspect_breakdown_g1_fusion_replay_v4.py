#!/usr/bin/env python3
"""Inspect completed-run G1 Fusion replay v4 without running providers or writing DB rows."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.app import breakdown_g1_fusion_replay_completed_v4 as completed
from engine.app import breakdown_g1_fusion_replay_v4 as replay


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only G1 Fusion replay v4")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = completed.replay_completed_run(args.run_id)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(replay.format_summary(payload))
        print(f"Window hint resolver: {replay.WINDOW_HINT_RESOLUTION_POLICY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
