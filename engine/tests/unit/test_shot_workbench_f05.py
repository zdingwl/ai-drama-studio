from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from engine.app import shot_workbench as shot_workbench_module
from engine.app.shot_workbench import (
    FinalShotRecord,
    ShotWorkbenchError,
    ShotWorkbenchRecord,
    _merge_origin_ids,
    _validate_final_timeline,
    generate_final_shot_id,
    generate_shot_edit_set_id,
    render_workbench_frame,
)

NOW = datetime.now(timezone.utc)


def _shot(ordinal: int, start: int, end: int) -> FinalShotRecord:
    return FinalShotRecord(
        id=f"SHOT_{ordinal}",
        edit_set_id="SHOT_EDIT_test",
        project_id="PROJECT_test",
        ordinal=ordinal,
        final_start_us=start,
        final_end_us=end,
        duration_us=end - start,
        origin_kind="auto",
        origin_candidate_ids=(f"CANDIDATE_{ordinal}",),
        created_at=NOW,
        updated_at=NOW,
    )


def test_f05_business_ids_have_expected_prefix() -> None:
    assert generate_shot_edit_set_id().startswith("SHOT_EDIT_")
    assert generate_final_shot_id().startswith("SHOT_")


def test_final_timeline_accepts_continuous_half_open_ranges() -> None:
    shots = (_shot(1, 0, 800_000), _shot(2, 800_000, 3_640_000), _shot(3, 3_640_000, 5_000_000))
    _validate_final_timeline(shots=shots, source_start_us=0, source_end_us=5_000_000)


def test_final_timeline_rejects_gap() -> None:
    shots = (_shot(1, 0, 800_000), _shot(2, 900_000, 2_000_000))
    with pytest.raises(ShotWorkbenchError) as error:
        _validate_final_timeline(shots=shots, source_start_us=0, source_end_us=2_000_000)
    assert error.value.code == "SHOT_WORKBENCH_INVALID_RESULT"


def test_final_timeline_rejects_wrong_ordinal() -> None:
    first = _shot(1, 0, 1_000_000)
    second = FinalShotRecord(**{**first.__dict__, "id": "SHOT_2", "ordinal": 3, "final_start_us": 1_000_000, "final_end_us": 2_000_000, "duration_us": 1_000_000})
    with pytest.raises(ShotWorkbenchError):
        _validate_final_timeline(shots=(first, second), source_start_us=0, source_end_us=2_000_000)


def test_merge_origin_ids_preserves_order_and_removes_duplicates() -> None:
    assert _merge_origin_ids(("A", "B"), ("B", "C")) == ("A", "B", "C")


def test_render_workbench_frame_reuses_existing_cache_without_ffmpeg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """同一 Source 时间已有 JPEG 时必须直接复用，禁止再次启动 FFmpeg。"""

    source_time_us = 500_000
    workbench = ShotWorkbenchRecord(
        id="SHOT_EDIT_test",
        project_id="PROJECT_test",
        source_detection_id="DETECTION_test",
        status="confirmed",
        revision=2,
        source_start_us=0,
        source_end_us=1_000_000,
        created_at=NOW,
        updated_at=NOW,
        confirmed_at=NOW,
        shots=(_shot(1, 0, 1_000_000),),
    )

    cache_path = tmp_path / ".cache" / "f05" / "frames" / f"{source_time_us}.jpg"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_bytes(b"cached-jpeg")

    monkeypatch.setattr(shot_workbench_module, "_require_workbench", lambda *args, **kwargs: workbench)
    monkeypatch.setattr(shot_workbench_module, "get_workbench_proxy_path", lambda *args, **kwargs: tmp_path / "proxy.mp4")
    monkeypatch.setattr(shot_workbench_module, "_project_workspace", lambda *args, **kwargs: tmp_path)

    def _ffmpeg_must_not_run(*args, **kwargs):
        raise AssertionError("缓存命中时不应该再次调用 FFmpeg")

    monkeypatch.setattr(shot_workbench_module.subprocess, "run", _ffmpeg_must_not_run)

    result = render_workbench_frame(
        project_id="PROJECT_test",
        source_time_us=source_time_us,
        app_data_path=tmp_path,
    )

    assert result == cache_path
    assert result.read_bytes() == b"cached-jpeg"
