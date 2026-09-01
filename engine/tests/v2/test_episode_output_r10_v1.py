from __future__ import annotations

from pathlib import Path

import pytest

from engine.app import episode_output_v1 as episode_output


def test_subtitle_events_deduplicate_dialogue_spanning_generation_segments() -> None:
    segments = [
        {
            "dialogues": [{
                "target_dialogue_id": "TD_1",
                "global_start_us": 800_000,
                "global_end_us": 2_200_000,
                "final_text": "Hello there",
                "target_character_id": "TC_1",
                "target_character_name": "Alex",
            }],
        },
        {
            "dialogues": [{
                "target_dialogue_id": "TD_1",
                "global_start_us": 800_000,
                "global_end_us": 2_200_000,
                "final_text": "Hello there",
                "target_character_id": "TC_1",
                "target_character_name": "Alex",
            }],
        },
    ]

    events = episode_output._subtitle_events(segments)

    assert len(events) == 1
    assert events[0]["target_dialogue_id"] == "TD_1"
    assert events[0]["start_us"] == 800_000
    assert events[0]["end_us"] == 2_200_000
    assert events[0]["text"] == "Hello there"


def test_srt_writer_is_utf8_and_uses_target_timeline(tmp_path: Path) -> None:
    output = episode_output._write_srt(
        [{
            "target_dialogue_id": "TD_1",
            "start_us": 1_250_000,
            "end_us": 2_900_000,
            "text": "你好，世界",
        }],
        tmp_path / "subtitles.srt",
    )

    content = output.read_text(encoding="utf-8")
    assert "00:00:01,250 --> 00:00:02,900" in content
    assert "你好，世界" in content


def test_episode_timeline_rejects_unexplained_gap() -> None:
    with pytest.raises(episode_output.EpisodeAssemblyError, match="空洞"):
        episode_output._validate_timeline([
            {"target_start_us": 0, "target_end_us": 1_000_000},
            {"target_start_us": 1_400_000, "target_end_us": 2_000_000},
        ])


def test_episode_media_normalization_and_concat(tmp_path: Path) -> None:
    source_one = tmp_path / "source-1.mp4"
    source_two = tmp_path / "source-2.mp4"
    episode_output._run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=320x568:r=24:d=0.5",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=0.5",
        "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source_one),
    ])
    episode_output._run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=240x426:r=25:d=0.5",
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source_two),
    ])

    normalized_one = episode_output._normalize_segment(
        source_one, tmp_path / "normalized-1.mp4", width=320, height=568, duration_us=500_000
    )
    normalized_two = episode_output._normalize_segment(
        source_two, tmp_path / "normalized-2.mp4", width=320, height=568, duration_us=500_000
    )
    assembled = episode_output._concat_normalized(
        [normalized_one, normalized_two], tmp_path / "assembled.mp4"
    )

    assert episode_output._video_size(assembled) == (320, 568)
    assert episode_output._has_audio(assembled) is True
    actual = episode_output._duration_us(assembled)
    assert abs(actual - 1_000_000) <= 120_000


def test_r10_episode_output_routes_are_registered() -> None:
    from engine.app.main import app
    from engine.app.studio_v2 import Base

    paths = {route.path for route in app.routes}
    assert "/api/projects/{project_id}/outputs" in paths
    assert "/api/episodes/{episode_id}/final-video" in paths
    assert "/api/episodes/{episode_id}/subtitles" in paths
    assert "v2_episode_outputs" in Base.metadata.tables
