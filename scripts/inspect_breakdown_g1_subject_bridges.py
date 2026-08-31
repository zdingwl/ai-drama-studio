#!/usr/bin/env python3
"""Explain anonymous LocalSubject fragment bridge evidence for one completed G1 replay Run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.app.breakdown_g1_subject_bridge_diagnostics_v1 import format_summary, inspect_run


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only G1 subject bridge diagnostics; no providers and no DB/Final writes."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--scene", type=int, default=None, help="Optional candidate Scene ordinal to print.")
    parser.add_argument("--top", type=int, default=15, help="Maximum bridge candidates per Scene.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    payload = inspect_run(args.run_id)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(format_summary(payload, scene_ordinal=args.scene, top=args.top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
