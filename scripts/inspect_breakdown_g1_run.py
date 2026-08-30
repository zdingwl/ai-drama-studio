#!/usr/bin/env python3
"""Print/write a read-only Fast Grounded G1 real-acceptance snapshot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.app import studio_v2
from engine.app.breakdown_g1_acceptance_diagnostics_v1 import (
    build_g1_acceptance_snapshot,
    write_g1_acceptance_snapshot,
)
from engine.app.breakdown_g1_run_selector_v1 import resolve_g1_run_selection


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect one completed Fast Grounded Breakdown Run for G1 local-real acceptance"
    )
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--run-id", help="inspect this exact completed Fast Grounded BreakdownRun id")
    selector.add_argument(
        "--episode-id",
        help="auto-select this Episode's current READY-like Fast Grounded Run, newest fallback",
    )
    selector.add_argument(
        "--latest",
        action="store_true",
        help="auto-select the newest completed Fast Grounded Run in the local database",
    )
    parser.add_argument(
        "--output",
        help="optional JSON output path; default writes under the selected Run acceptance directory",
    )
    parser.add_argument(
        "--stdout-only",
        action="store_true",
        help="print JSON only and do not write an acceptance artifact",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    studio_v2.init_database()
    selection = resolve_g1_run_selection(
        run_id=args.run_id,
        episode_id=args.episode_id,
        latest=bool(args.latest),
    )
    snapshot = build_g1_acceptance_snapshot(selection.run_id)
    snapshot = dict(snapshot)
    snapshot["selection"] = selection.as_dict()
    if not args.stdout_only:
        path = write_g1_acceptance_snapshot(snapshot, output_path=args.output)
        snapshot["artifact_path"] = str(path)
    print(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
