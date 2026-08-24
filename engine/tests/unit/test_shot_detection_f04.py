from __future__ import annotations

import re
import uuid

import pytest

from engine.app.shot_detection import (
    CutEvent,
    ShotDetectionError,
    build_shot_candidates,
    generate_shot_detection_id,
)


def test_generate_shot_detection_id_is_uuid4_business_id() -> None:
    value = generate_shot_detection_id()

    assert re.fullmatch(r"SHOT_DETECTION_[0-9a-f]{32}", value)
    raw = value.removeprefix("SHOT_DETECTION_")
    assert uuid.UUID(hex=raw).version == 4


def test_generate_shot_detection_ids_do_not_repeat_in_sample() -> None:
    values = {generate_shot_detection_id() for _ in range(5_000)}
    assert len(values) == 5_000


def test_no_cut_generates_one_continuous_candidate() -> None:
    candidates = build_shot_candidates(
        detection_id="SHOT_DETECTION_" + "a" * 32,
        project_id="PROJECT_" + "b" * 32,
        cut_events=[],
        proxy_start_us=100_000,
        proxy_end_us=5_100_000,
        proxy_to_source_offset_us=900_000,
    )

    assert len(candidates) == 1
    shot = candidates[0]
    assert shot.ordinal == 1
    assert (shot.detected_proxy_start_us, shot.detected_proxy_end_us) == (100_000, 5_100_000)
    assert (shot.detected_start_us, shot.detected_end_us) == (1_000_000, 6_000_000)
    assert shot.duration_us == 5_000_000
    assert shot.end_boundary_kind == "video_end"
    assert shot.end_boundary_score is None


def test_multiple_cuts_cover_whole_range_without_gap_or_overlap() -> None:
    candidates = build_shot_candidates(
        detection_id="SHOT_DETECTION_" + "a" * 32,
        project_id="PROJECT_" + "b" * 32,
        cut_events=[
            CutEvent(proxy_time_us=2_000_000, boundary_score=0.91),
            CutEvent(proxy_time_us=4_500_000, boundary_score=0.83),
        ],
        proxy_start_us=0,
        proxy_end_us=7_000_000,
        proxy_to_source_offset_us=250_000,
    )

    assert len(candidates) == 3
    assert [shot.ordinal for shot in candidates] == [1, 2, 3]
    assert [
        (shot.detected_proxy_start_us, shot.detected_proxy_end_us)
        for shot in candidates
    ] == [(0, 2_000_000), (2_000_000, 4_500_000), (4_500_000, 7_000_000)]
    assert candidates[0].end_boundary_score == pytest.approx(0.91)
    assert candidates[1].end_boundary_score == pytest.approx(0.83)
    assert candidates[2].end_boundary_kind == "video_end"

    for current, following in zip(candidates, candidates[1:]):
        assert current.detected_proxy_end_us == following.detected_proxy_start_us
        assert current.detected_end_us == following.detected_start_us


def test_exact_duplicate_cut_keeps_highest_score() -> None:
    candidates = build_shot_candidates(
        detection_id="SHOT_DETECTION_" + "a" * 32,
        project_id="PROJECT_" + "b" * 32,
        cut_events=[
            CutEvent(proxy_time_us=2_000_000, boundary_score=0.61),
            CutEvent(proxy_time_us=2_000_000, boundary_score=0.94),
        ],
        proxy_start_us=0,
        proxy_end_us=4_000_000,
        proxy_to_source_offset_us=0,
    )

    assert len(candidates) == 2
    assert candidates[0].end_boundary_score == pytest.approx(0.94)


def test_nearby_cut_window_keeps_highest_score() -> None:
    candidates = build_shot_candidates(
        detection_id="SHOT_DETECTION_" + "a" * 32,
        project_id="PROJECT_" + "b" * 32,
        cut_events=[
            CutEvent(proxy_time_us=2_000_000, boundary_score=0.74),
            CutEvent(proxy_time_us=2_080_000, boundary_score=0.95),
            CutEvent(proxy_time_us=3_000_000, boundary_score=0.81),
        ],
        proxy_start_us=0,
        proxy_end_us=5_000_000,
        proxy_to_source_offset_us=0,
        min_boundary_gap_us=120_000,
    )

    assert len(candidates) == 3
    assert candidates[0].detected_proxy_end_us == 2_080_000
    assert candidates[0].end_boundary_score == pytest.approx(0.95)
    assert candidates[1].detected_proxy_end_us == 3_000_000


def test_events_at_or_outside_video_edges_are_ignored() -> None:
    candidates = build_shot_candidates(
        detection_id="SHOT_DETECTION_" + "a" * 32,
        project_id="PROJECT_" + "b" * 32,
        cut_events=[
            CutEvent(proxy_time_us=-1, boundary_score=0.99),
            CutEvent(proxy_time_us=0, boundary_score=0.99),
            CutEvent(proxy_time_us=1_000_000, boundary_score=0.8),
            CutEvent(proxy_time_us=2_000_000, boundary_score=0.99),
            CutEvent(proxy_time_us=2_000_001, boundary_score=0.99),
        ],
        proxy_start_us=0,
        proxy_end_us=2_000_000,
        proxy_to_source_offset_us=-500_000,
    )

    assert len(candidates) == 2
    assert candidates[0].detected_proxy_end_us == 1_000_000
    assert candidates[-1].detected_end_us == 1_500_000


def test_invalid_detection_range_fails_closed() -> None:
    with pytest.raises(ShotDetectionError) as error:
        build_shot_candidates(
            detection_id="SHOT_DETECTION_" + "a" * 32,
            project_id="PROJECT_" + "b" * 32,
            cut_events=[],
            proxy_start_us=1_000,
            proxy_end_us=1_000,
            proxy_to_source_offset_us=0,
        )

    assert error.value.code == "SHOT_DETECTION_INVALID_RESULT"
