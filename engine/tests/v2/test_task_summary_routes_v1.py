from __future__ import annotations

from engine.app.task_summary_routes_v1 import _summarize_result, _summarize_task


def test_task_result_summary_keeps_workspace_status_and_strips_heavy_payload() -> None:
    result = {
        "mode": "sequential",
        "results": [
            {
                "episode_id": "EPISODE_001",
                "status": "READY",
                "shot_count": 12,
                "media": {
                    "frames": [1, 2, 3],
                    "probe": "x" * 10000,
                },
            },
            {
                "episode_id": "EPISODE_002",
                "status": "FAILED",
                "error": "ffmpeg decode failed",
                "diagnostics": {"stderr": "x" * 10000},
            },
        ],
        "debug": {"large": "x" * 10000},
    }

    assert _summarize_result(result) == {
        "mode": "sequential",
        "results": [
            {
                "episode_id": "EPISODE_001",
                "status": "READY",
                "shot_count": 12,
            },
            {
                "episode_id": "EPISODE_002",
                "status": "FAILED",
                "error": "ffmpeg decode failed",
            },
        ],
    }


def test_task_summary_preserves_task_metadata_and_replaces_only_result() -> None:
    task = {
        "id": "TASK_001",
        "project_id": "PROJECT_001",
        "episode_id": None,
        "task_type": "BATCH_SHOTS",
        "title": "批量拉片",
        "status": "READY_WITH_WARNINGS",
        "progress_mode": "determinate",
        "progress_percent": 100.0,
        "stage_key": "ready",
        "stage_label": "完成",
        "current_item": "EP02",
        "current_index": 2,
        "total_items": 2,
        "message": "完成",
        "error_message": None,
        "result": {
            "mode": "sequential",
            "results": [
                {
                    "episode_id": "EPISODE_002",
                    "status": "FAILED",
                    "error": "boom",
                    "huge_internal_payload": "x" * 10000,
                },
            ],
        },
        "created_at": "2026-09-03T00:00:00+00:00",
        "started_at": "2026-09-03T00:00:01+00:00",
        "updated_at": "2026-09-03T00:00:02+00:00",
        "completed_at": "2026-09-03T00:00:02+00:00",
    }

    summary = _summarize_task(task)

    assert summary["id"] == task["id"]
    assert summary["status"] == task["status"]
    assert summary["progress_percent"] == task["progress_percent"]
    assert summary["result"] == {
        "mode": "sequential",
        "results": [
            {
                "episode_id": "EPISODE_002",
                "status": "FAILED",
                "error": "boom",
            },
        ],
    }
