#!/usr/bin/env python3
"""Print/write a read-only Fast Grounded G1 real-acceptance snapshot for an existing Run."""
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect one completed Breakdown Run for Fast Grounded G1 local-real acceptance"
    )
    parser.add_argument("--run-id", required=True, help="existing BreakdownRun id")
    parser.add_argument("--output", help="optional JSON output path; default writes under the Run acceptance directory")
    parser.add_argument(
        "--stdout-only",
        action="store_true",
        help="print JSON only and do not write an acceptance artifact",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    studio_v2.init_database()
    snapshot = build_g1_acceptance_snapshot(args.run_id)
    if not args.stdout_only:
        path = write_g1_acceptance_snapshot(snapshot, output_path=args.output)
        snapshot = dict(snapshot)
        snapshot["artifact_path"] = str(path)
    print(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
