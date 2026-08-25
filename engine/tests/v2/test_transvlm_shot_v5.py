from __future__ import annotations

import json
from pathlib import Path

from engine.app import media_v5, transvlm_runtime_v5


def test_transvlm_jsonl_parser_converts_seconds_to_microseconds(tmp_path: Path) -> None:
    output = tmp_path / "out.jsonl"
    output.write_text(
        json.dumps(
            {
                "video": "demo.mp4",
                "segments": [
                    {"start_time": 0.8, "end_time": 0.9},
                    {"start_time": 3.2, "end_time": 3.6},
                ],
            }
        ) + "\n",
        encoding="utf-8",
    )

    segments = transvlm_runtime_v5._parse_output(output)

    assert [(item.start_us, item.end_us) for item in segments] == [
        (800_000, 900_000),
        (3_200_000, 3_600_000),
    ]


def test_hard_like_transition_uses_strongest_source_frame_break() -> None:
    pts = tuple(index * 40_000 for index in range(30))
    visual = [0.0] + [0.04] * 29
    visual[23] = 0.91  # 920ms，真正 hard cut。
    segment = transvlm_runtime_v5.TransVLMTransition(start_us=800_000, end_us=900_000)

    result = media_v5._resolve_transition(segment, pts, visual)

    assert result is not None
    assert result.kind == "HARD_LIKE"
    assert result.cut_us == 920_000
    assert result.source_frame_index == 23
    assert result.visual_score == 0.91


def test_gradual_transition_uses_segment_midpoint_on_source_pts() -> None:
    pts = tuple(index * 40_000 for index in range(100))
    visual = [0.0] + [0.08] * 99
    segment = transvlm_runtime_v5.TransVLMTransition(start_us=1_000_000, end_us=1_800_000)

    result = media_v5._resolve_transition(segment, pts, visual)

    assert result is not None
    assert result.kind == "GRADUAL"
    assert result.cut_us == 1_400_000
    assert result.transition_start_us == 1_000_000
    assert result.transition_end_us == 1_800_000


def test_multiple_segments_resolve_to_unique_sorted_cut_frames() -> None:
    pts = tuple(index * 40_000 for index in range(100))
    visual = [0.0] + [0.05] * 99
    visual[10] = 0.8
    visual[50] = 0.9
    segments = [
        transvlm_runtime_v5.TransVLMTransition(360_000, 440_000),
        transvlm_runtime_v5.TransVLMTransition(1_960_000, 2_040_000),
    ]

    result = media_v5._resolve_transitions(segments, pts, visual)

    assert [item.cut_us for item in result] == [400_000, 2_000_000]


def test_wide_transition_is_flagged_for_quick_review() -> None:
    pts = tuple(index * 40_000 for index in range(200))
    visual = [0.0] + [0.05] * 199
    segment = transvlm_runtime_v5.TransVLMTransition(2_000_000, 4_000_000)

    result = media_v5._resolve_transition(segment, pts, visual)

    assert result is not None
    assert result.kind == "GRADUAL"
    assert result.review_reasons
