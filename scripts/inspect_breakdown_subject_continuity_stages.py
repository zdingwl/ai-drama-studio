#!/usr/bin/env python3
"""Print stage-by-stage anonymous subject continuity diagnostics for one completed Run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.app.breakdown_g1_subject_continuity_stage_diagnostics_v1 import format_summary, inspect_run


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only G1 anonymous-subject continuity stage diagnostics"
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--show-hints", type=int, default=8)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = inspect_run(args.run_id)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(format_summary(payload, show_hints=args.show_hints))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
