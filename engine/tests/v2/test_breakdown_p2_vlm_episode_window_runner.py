from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import run_breakdown_vlm_qwen3_episode_windows as runner


def shot(ordinal: int) -> dict[str, Any]:
    return {
        "revision_item_id": f"ITEM_{ordinal:02d}",
        "ordinal": ordinal,
        "window_start_seconds": float(ordinal - 1),
        "window_end_seconds": float(ordinal),
    }


def semantic(ordinal: int) -> dict[str, Any]:
    return {
        "scene": {
            "location_hint": "客厅",
            "interior_exterior": "INT",
            "time_of_day": "白天",
            "environment_description": "同一室内客厅",
        },
        "shot": {
            "summary": f"人物在客厅活动{ordinal}",
            "visual_description": "人物位于画面中央并观察前方",
            "shot_type_hint": "中景",
            "camera_motion_hint": "静止",
            "narrative_function_hint": "推进互动",
            "composition_hint": "人物居中",
        },
        "subjects": [],
        "events": [],
        "props": [],
    }


def compact_result(target_shots: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "window_summary": "人物在同一客厅连续活动",
        "scene_change_candidates": [],
        "subject_continuity_hints": [],
        "prop_continuity_hints": [],
        "shots": [
            {
                "revision_item_id": str(item["revision_item_id"]),
                "ordinal": int(item["ordinal"]),
                "scene_continuity": "SAME",
                "scene_basis": "CONTEXT",
                "context_note": "结合连续窗口判断仍在客厅",
                "semantic": semantic(int(item["ordinal"])),
            }
            for item in target_shots
        ],
    }


def test_generation_budget_is_bounded_for_structured_output() -> None:
    assert runner._generation_budget(4096, 3, compact=False) == 4096
    assert runner._generation_budget(4096, 10, compact=False) > 4096
    assert runner._generation_budget(4096, 100, compact=False) == runner._MAX_GENERATION_TOKENS
    assert runner._MAX_GENERATION_TOKENS <= 6144


def test_rapid_cut_window_skips_giant_json_and_uses_compact_batches(monkeypatch) -> None:
    shots = [shot(index) for index in range(1, 14)]
    window = {
        "window_id": "window-0001",
        "video_path": "unused-by-monkeypatch.mp4",
        "shots": shots,
    }
    calls: list[tuple[int, bool]] = []

    def fake_generate_once(**kwargs):
        target_shots = tuple(kwargs["target_shots"])
        compact = bool(kwargs["compact"])
        calls.append((len(target_shots), compact))
        return compact_result(target_shots)

    monkeypatch.setattr(runner, "_generate_once", fake_generate_once)
    monkeypatch.setattr(runner, "_cleanup_cuda", lambda: None)

    result = runner._analyze_window(
        model=object(),
        processor=object(),
        window=window,
        source_language="zh-CN",
        fps=2.0,
        max_new_tokens=4096,
        max_pixels=524288,
    )

    assert calls == [(6, True), (6, True), (1, True)]
    assert [item["revision_item_id"] for item in result["shots"]] == [
        item["revision_item_id"] for item in shots
    ]
    runner._validate_output(result, window)


def test_compact_batch_recursively_splits_on_structured_failure(monkeypatch) -> None:
    shots = [shot(index) for index in range(1, 7)]
    window = {
        "window_id": "window-0001",
        "video_path": "unused-by-monkeypatch.mp4",
        "shots": shots,
    }
    calls: list[tuple[int, bool]] = []

    def fake_generate_once(**kwargs):
        target_shots = tuple(kwargs["target_shots"])
        compact = bool(kwargs["compact"])
        calls.append((len(target_shots), compact))
        if not compact or len(target_shots) > 2:
            raise ValueError("fixture structured failure")
        return compact_result(target_shots)

    monkeypatch.setattr(runner, "_generate_once", fake_generate_once)
    monkeypatch.setattr(runner, "_cleanup_cuda", lambda: None)

    result = runner._analyze_window(
        model=object(),
        processor=object(),
        window=window,
        source_language="zh-CN",
        fps=2.0,
        max_new_tokens=4096,
        max_pixels=524288,
    )

    assert calls[0] == (6, False)
    assert (6, True) in calls
    assert all(size <= 6 for size, _compact in calls)
    assert any(size == 1 and compact for size, compact in calls)
    assert [item["revision_item_id"] for item in result["shots"]] == [
        item["revision_item_id"] for item in shots
    ]
    runner._validate_output(result, window)
