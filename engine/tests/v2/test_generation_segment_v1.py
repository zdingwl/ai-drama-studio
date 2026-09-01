from __future__ import annotations

from pathlib import Path

import pytest

from engine.app.generation_segment_v1 import _h3_duration_us, _split_target_windows
from engine.app.h3_runtime_v1 import H3RuntimeManager
from engine.app.minimax_h3_provider_v1 import MiniMaxH3Provider
from engine.app.video_generation_provider_v1 import VideoGenerationRequestV1


def test_h3_duration_quantizes_to_supported_whole_seconds() -> None:
    assert _h3_duration_us(1_250_000) == 4_000_000
    assert _h3_duration_us(4_000_000) == 4_000_000
    assert _h3_duration_us(4_000_001) == 5_000_000
    assert _h3_duration_us(14_200_000) == 15_000_000
    assert _h3_duration_us(15_000_000) == 15_000_000
    with pytest.raises(ValueError):
        _h3_duration_us(15_000_001)


def test_long_target_shot_is_balanced_into_h3_sized_segments() -> None:
    windows = _split_target_windows(10_000_000, 16_000_000)
    assert windows == [(10_000_000, 18_000_000), (18_000_000, 26_000_000)]
    assert all(0 < end - start <= 15_000_000 for start, end in windows)

    windows = _split_target_windows(0, 31_000_000)
    assert len(windows) == 3
    assert windows[0][0] == 0
    assert windows[-1][1] == 31_000_000
    assert all(0 < end - start <= 15_000_000 for start, end in windows)


def test_runtime_rejects_invalid_h3_conditions_before_network_call() -> None:
    manager = H3RuntimeManager()
    with pytest.raises(ValueError):
        manager.submit_video(
            mode="FL2VA",
            prompt="test",
            conditions=[{"type": "video", "uri": "file:///tmp/reference.mp4", "role": "reference"}],
            duration_seconds=5,
        )
    with pytest.raises(ValueError):
        manager.submit_video(
            mode="REF2VA",
            prompt="test",
            conditions=[{"type": "audio", "uri": "file:///tmp/voice.wav", "role": "reference"}],
            duration_seconds=5,
        )


class FakeH3Runtime:
    def __init__(self) -> None:
        self.submitted: dict | None = None
        self.downloaded: tuple[str, str, Path] | None = None

    def status(self) -> dict:
        return {"runtime_profile": "FAKE", "ready": True}

    def submit_video(self, **kwargs):
        self.submitted = kwargs
        return {"id": "video_123", "status": "queued"}

    def get_video_status(self, mode: str, video_id: str) -> dict:
        assert mode == "REF2VA"
        assert video_id == "video_123"
        return {"id": video_id, "status": "completed"}

    def download_video(self, mode: str, video_id: str, destination: Path) -> Path:
        self.downloaded = (mode, video_id, destination)
        return destination


def test_minimax_provider_is_the_only_h3_specific_adapter() -> None:
    runtime = FakeH3Runtime()
    provider = MiniMaxH3Provider(runtime=runtime)  # type: ignore[arg-type]
    request = VideoGenerationRequestV1.model_validate({
        "mode": "REF2VA",
        "prompt": "same camera move, localized cast and dialogue",
        "conditions": [
            {"type": "video", "uri": "file:///tmp/reference.mp4", "role": "reference"},
            {"type": "image", "uri": "file:///tmp/character.png", "role": "character"},
        ],
        "duration_seconds": 7,
    })

    submission = provider.submit(request)
    assert submission.provider == "MINIMAX_H3_LOCAL"
    assert submission.external_job_id == "video_123"
    assert runtime.submitted == {
        "mode": "REF2VA",
        "prompt": request.prompt,
        "conditions": [
            {"type": "video", "uri": "file:///tmp/reference.mp4", "role": "reference"},
            {"type": "image", "uri": "file:///tmp/character.png", "role": "character"},
        ],
        "duration_seconds": 7,
        "short_edge": 768,
        "aspect_ratio": "auto",
        "seed": 0,
    }

    status = provider.get_status(mode="REF2VA", external_job_id="video_123")
    assert status.terminal is True
    assert status.succeeded is True
    assert status.failed is False

    destination = Path("output.mp4")
    assert provider.download(mode="REF2VA", external_job_id="video_123", destination=destination) == destination
    assert runtime.downloaded == ("REF2VA", "video_123", destination)


def test_provider_request_fails_closed_on_mode_condition_mismatch() -> None:
    with pytest.raises(ValueError):
        VideoGenerationRequestV1.model_validate({
            "mode": "FL2VA",
            "prompt": "test",
            "conditions": [{"type": "video", "uri": "file:///tmp/reference.mp4"}],
            "duration_seconds": 5,
        })
