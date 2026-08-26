from __future__ import annotations

from engine.app import media_v5, transvlm_runtime_v5


def test_transvlm_flow_log_reports_explicit_whole_video_stage() -> None:
    event = transvlm_runtime_v5._progress_from_log_line(
        "2026-08-26 10:00:00 INFO __main__: [flow] computing whole-video NeuFlow for original_resized.mp4"
    )

    assert event is not None
    percent, stage_key, message, current, total = event
    assert percent == 15.0
    assert stage_key == "transvlm"
    assert "NeuFlow" in message
    assert "整集光流" in message
    assert current is None
    assert total is None


def test_transvlm_window_log_maps_to_monotonic_runtime_progress() -> None:
    first = transvlm_runtime_v5._progress_from_log_line(
        "2026-08-26 10:10:00 INFO __main__: [window 1/20] 0.0-10.0 s"
    )
    middle = transvlm_runtime_v5._progress_from_log_line(
        "2026-08-26 10:12:00 INFO __main__: [window 10/20] 81.0-91.0 s, eta 120 s"
    )
    last = transvlm_runtime_v5._progress_from_log_line(
        "2026-08-26 10:14:00 INFO __main__: [window 20/20] 171.0-180.0 s"
    )

    assert first is not None and middle is not None and last is not None
    assert first[0] < middle[0] < last[0]
    assert first[3:] == (1, 20)
    assert middle[3:] == (10, 20)
    assert last[3:] == (20, 20)
    assert last[0] == 98.0


def test_transvlm_windows_plan_marks_flow_complete() -> None:
    event = transvlm_runtime_v5._progress_from_log_line(
        "2026-08-26 10:08:00 INFO __main__: [windows] original_resized.mp4: 180.00 s -> 20 window(s)"
    )

    assert event is not None
    assert event[0] == 55.0
    assert "NeuFlow 已完成" in event[2]
    assert event[3:] == (0, 20)


def test_media_v5_maps_runtime_progress_into_transvlm_slot() -> None:
    assert media_v5._map_transvlm_progress(0) == media_v5.TRANSVLM_PROGRESS_START
    assert media_v5._map_transvlm_progress(100) == media_v5.TRANSVLM_PROGRESS_END
    assert media_v5._map_transvlm_progress(50) == 36.0
