from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from engine.app import episode_output_v1 as episode_output
from engine.app import postproduction_routes_v1 as postproduction_routes


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


def test_get_episode_output_uses_read_only_compile(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, bool]] = []

    def fake_compile(project_id: str, *, persist: bool = True) -> dict[str, object]:
        calls.append((project_id, persist))
        return {"episodes": []}

    monkeypatch.setattr(episode_output, "compile_episode_outputs_v1", fake_compile)

    assert episode_output.get_episode_output_v1("PROJECT_READ_ONLY", "EP_1") is None
    assert calls == [("PROJECT_READ_ONLY", False)]


def test_episode_subtitle_requires_current_succeeded_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    subtitle = tmp_path / "subtitles.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
    monkeypatch.setattr(
        episode_output,
        "get_episode_output_v1",
        lambda _project_id, _episode_id: {
            "status": "READY",
            "subtitle_path": str(subtitle),
        },
    )

    assert episode_output.episode_output_subtitle_v1("PROJECT_READ_ONLY", "EP_1") is None


def test_output_get_routes_use_read_only_plans(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, bool | None]] = []

    def fake_post_plan(project_id: str) -> dict[str, object]:
        calls.append(("postproduction", project_id, False))
        return {}

    def fake_output_plan(project_id: str, *, persist: bool = True) -> dict[str, object]:
        calls.append(("outputs", project_id, persist))
        return {}

    monkeypatch.setattr(postproduction_routes, "get_postproduction_plan_v1", fake_post_plan)
    monkeypatch.setattr(postproduction_routes, "compile_episode_outputs_v1", fake_output_plan)

    assert postproduction_routes.api_get_postproduction("PROJECT_READ_ONLY") == {}
    assert postproduction_routes.api_get_episode_outputs("PROJECT_READ_ONLY") == {}
    assert calls == [
        ("postproduction", "PROJECT_READ_ONLY", False),
        ("outputs", "PROJECT_READ_ONLY", False),
    ]


def test_episode_media_normalization_and_concat(tmp_path: Path) -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("FFmpeg/FFprobe are not installed in this lightweight test environment")

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
