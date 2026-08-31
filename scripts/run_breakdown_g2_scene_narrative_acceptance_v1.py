#!/usr/bin/env python3
"""G2.3/G2.4 real-model acceptance runner.

This script is read-only with respect to project data. It:
1. loads one accepted BreakdownRun through the frozen serializer;
2. assembles the FINAL PASS deterministic Scene Timeline;
3. runs the local text-only Qwen Scene Narrative once for the whole Episode;
4. applies only validated title/story_summary overlay;
5. verifies every Shot object is structurally unchanged;
6. reports Scene-level safe runner diagnostics and a separate Narrative gate.

It does not open video/images and does not write Final Character/Scene/Prop assets.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

# Allow direct execution from repository root, e.g.
# ``python scripts/run_breakdown_g2_scene_narrative_acceptance_v1.py``.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.app.breakdown_scene_narrative_qwen3_v1 import Qwen3VLSceneTextLLM
from engine.app.breakdown_scene_narrative_v1 import (
    apply_scene_narrative_overlay_v1,
    organize_scene_timeline_narrative_v1,
)
from engine.app.breakdown_scene_timeline_assembler_v1 import assemble_scene_timeline_v1
from engine.app.breakdown_serializer_v1 import get_breakdown_run


DEFAULT_RUN_ID = "BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4"


def _shot_snapshot(timeline: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        shot
        for scene in timeline.get("scenes", [])
        for shot in scene.get("shots", [])
        if isinstance(shot, dict)
    ]


def _scene_snapshot(timeline: dict[str, Any]) -> list[dict[str, Any]]:
    return [scene for scene in timeline.get("scenes", []) if isinstance(scene, dict)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run G2.3/G2.4 real local-Qwen acceptance")
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    args = parser.parse_args()

    draft = get_breakdown_run(args.run_id)
    if draft is None:
        raise SystemExit(f"BreakdownRun not found: {args.run_id}")

    timeline = assemble_scene_timeline_v1(draft)
    before_shots = _shot_snapshot(timeline)
    before_scenes = _scene_snapshot(timeline)

    if timeline.get("scene_count") != 2:
        raise AssertionError(f"expected 2 scenes, got {timeline.get('scene_count')}")
    if timeline.get("shot_count") != 30:
        raise AssertionError(f"expected 30 shots, got {timeline.get('shot_count')}")
    if [len(scene.get("people", [])) for scene in before_scenes] != [2, 2]:
        raise AssertionError("expected Scene-local people counts [2, 2]")

    shot1 = before_scenes[0]["shots"][0]
    if shot1.get("people") != []:
        raise AssertionError("Shot0001 people must remain empty")
    shot1_props = [item.get("label") for item in shot1.get("props", []) if isinstance(item, dict)]
    for required_prop in ("蓝色玫瑰花束", "玻璃花瓶"):
        if required_prop not in shot1_props:
            raise AssertionError(f"Shot0001 missing required prop: {required_prop}")

    llm = Qwen3VLSceneTextLLM()
    preflight = llm.runtime_preflight()
    if preflight.get("status") != "READY":
        raise AssertionError(f"G2 local Qwen runtime not READY: {preflight}")

    overlay = organize_scene_timeline_narrative_v1(timeline, llm)
    diagnostics = llm.last_batch_diagnostics()
    applied = apply_scene_narrative_overlay_v1(timeline, overlay)
    after_shots = _shot_snapshot(applied)

    if before_shots != after_shots:
        raise AssertionError("Narrative overlay changed one or more frozen Shot objects")
    if applied.get("scene_count") != timeline.get("scene_count"):
        raise AssertionError("Narrative overlay changed scene_count")
    if applied.get("shot_count") != timeline.get("shot_count"):
        raise AssertionError("Narrative overlay changed shot_count")

    overlay_by_ordinal = {
        int(item.get("scene_ordinal")): item
        for item in overlay.get("scenes", [])
        if isinstance(item, dict) and item.get("scene_ordinal") is not None
    }
    expected_ordinals = [int(scene["ordinal"]) for scene in before_scenes]
    narrative_complete = True
    for ordinal in expected_ordinals:
        narrative = overlay_by_ordinal.get(ordinal) or {}
        if not narrative.get("readable_title") or not narrative.get("story_summary"):
            narrative_complete = False
        diagnostic = diagnostics.get(ordinal) or {}
        if diagnostic and str(diagnostic.get("status") or "").upper() != "READY":
            narrative_complete = False
    if overlay.get("status") != "READY":
        narrative_complete = False

    print("=== G2.3/G2.4 Real Local-Qwen Acceptance ===")
    print("run=", args.run_id)
    print("preflight=", json.dumps(preflight, ensure_ascii=False))
    print("runner_diagnostics=", json.dumps(diagnostics, ensure_ascii=False, sort_keys=True))
    print("scenes=", applied.get("scene_count"), "shots=", applied.get("shot_count"))
    print("people=", [len(scene.get("people", [])) for scene in _scene_snapshot(applied)])
    print("shot1_people=", shot1.get("people"))
    print("shot1_props=", shot1_props)
    print("overlay_status=", overlay.get("status"))
    print("warnings=", json.dumps(overlay.get("warnings", []), ensure_ascii=False))

    for before, after in zip(before_scenes, _scene_snapshot(applied)):
        ordinal = int(before["ordinal"])
        narrative = overlay_by_ordinal.get(ordinal, {})
        print(f"\n[Scene {ordinal}]")
        print("deterministic_title=", before.get("title"))
        print("narrative_title=", after.get("title"))
        print("deterministic_summary=", before.get("story_summary"))
        print("narrative_summary=", after.get("story_summary"))
        print("title_support=", (narrative.get("readable_title") or {}).get("support"))
        print("summary_support=", (narrative.get("story_summary") or {}).get("support"))
        print("runner_scene_status=", json.dumps(diagnostics.get(ordinal, {}), ensure_ascii=False))

    print("\nshot_objects_unchanged= YES")
    print("structure_gate= PASS")
    print("narrative_gate=", "PASS" if narrative_complete else "FAIL")
    print("acceptance_machine_gate=", "PASS" if narrative_complete else "FAIL")
    return 0 if narrative_complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
