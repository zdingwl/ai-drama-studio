#!/usr/bin/env python3
"""Explicitly materialize a validated G2 Narrative overlay for the Scene Timeline read API.

This is intentionally not a GET/API side effect and is not appended to the frozen G1 P2 pipeline.
The command consumes one completed Breakdown Run, invokes the accepted local G2 text runtime once,
passes the result through frozen G2.3/G2.4 validation, then atomically stores the validated overlay.
"""
from __future__ import annotations

import argparse
import json

from engine.app.breakdown_scene_narrative_qwen3_v1 import Qwen3VLSceneTextLLM
from engine.app.breakdown_scene_narrative_v1 import organize_scene_timeline_narrative_v1
from engine.app.breakdown_scene_timeline_assembler_v1 import assemble_scene_timeline_v1
from engine.app.breakdown_scene_timeline_result_v1 import (
    assert_scene_timeline_ready_draft_v1,
    persist_scene_narrative_overlay_v1,
)
from engine.app.breakdown_serializer_v1 import get_breakdown_run


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize G2 Scene Timeline Narrative for one completed Run")
    parser.add_argument("run_id")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default=None)
    parser.add_argument("--max-new-tokens", type=int, default=None)
    args = parser.parse_args()

    draft = get_breakdown_run(args.run_id)
    if draft is None:
        raise LookupError("Breakdown Run 不存在")
    assert_scene_timeline_ready_draft_v1(draft)
    timeline = assemble_scene_timeline_v1(draft)

    llm = Qwen3VLSceneTextLLM(
        device=args.device,
        max_new_tokens=args.max_new_tokens,
    )
    preflight = llm.runtime_preflight()
    if preflight["status"] != "READY":
        raise RuntimeError("G2 本地 Qwen Scene Narrative runtime 未配置完整")

    overlay = organize_scene_timeline_narrative_v1(timeline, llm)
    artifact_path = persist_scene_narrative_overlay_v1(draft, overlay)

    scenes = overlay.get("scenes") if isinstance(overlay, dict) else None
    scene_rows = scenes if isinstance(scenes, list) else []
    title_count = sum(
        1 for item in scene_rows
        if isinstance(item, dict) and isinstance(item.get("readable_title"), dict)
    )
    summary_count = sum(
        1 for item in scene_rows
        if isinstance(item, dict) and isinstance(item.get("story_summary"), dict)
    )
    warnings = overlay.get("warnings") if isinstance(overlay, dict) else None

    print(json.dumps(
        {
            "run_id": args.run_id,
            "scene_count": len(scene_rows),
            "accepted_title_count": title_count,
            "accepted_summary_count": summary_count,
            "warning_count": len(warnings) if isinstance(warnings, list) else 0,
            "artifact_path": str(artifact_path),
            "runtime_profile": preflight.get("profile"),
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
