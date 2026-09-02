from __future__ import annotations

from pathlib import Path
import shutil
import wave

import pytest

from engine.app import background_audio_v1 as background
from engine.app import postproduction_audio_mix_v1 as enhancer


def _write_constant_wav(path: Path, *, seconds: float = 1.0, rate: int = 48_000, sample: int = 5000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_count = int(seconds * rate)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frame = int(sample).to_bytes(2, "little", signed=True) * 2
        handle.writeframes(frame * frame_count)


def _write_two_level_wav(path: Path, *, rate: int = 48_000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        low = int(1000).to_bytes(2, "little", signed=True) * 2
        high = int(5000).to_bytes(2, "little", signed=True) * 2
        handle.writeframes(low * rate)
        handle.writeframes(high * rate)


def _sample_at(path: Path, seconds: float) -> int:
    with wave.open(str(path), "rb") as handle:
        handle.setpos(min(handle.getnframes() - 1, int(seconds * handle.getframerate())))
        frame = handle.readframes(1)
    return int.from_bytes(frame[:2], "little", signed=True)


def test_dialogue_suppression_windows_convert_absolute_source_time_and_merge() -> None:
    profile = {
        "source_dialogue_pad_before_us": 100_000,
        "source_dialogue_pad_after_us": 200_000,
    }
    shot = {
        "source_dialogue": [
            {"start_us": 5_300_000, "end_us": 5_600_000},
            {"start_us": 5_650_000, "end_us": 5_800_000},
        ]
    }
    windows = background._dialogue_suppression_windows(
        shot,
        shot_start_us=5_000_000,
        shot_duration_us=2_000_000,
        profile=profile,
    )
    assert windows == [(200_000, 1_000_000)]


def test_atempo_chain_supports_extreme_timing_ratios() -> None:
    values = background._atempo_chain(0.125)
    product = 1.0
    for value in values:
        assert 0.5 <= value <= 2.0
        product *= value
    assert product == pytest.approx(0.125)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg required for R10.1 media acceptance")
def test_residual_source_dialogue_window_is_hard_muted(tmp_path: Path) -> None:
    source = tmp_path / "instrumental-raw.wav"
    output = tmp_path / "instrumental-safe.wav"
    _write_constant_wav(source)

    background._suppress_source_dialogue(source, [(200_000, 450_000)], output)

    assert abs(_sample_at(output, 0.30)) <= 8
    assert abs(_sample_at(output, 0.70)) > 1000


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg required for R10.1 media acceptance")
def test_split_target_segments_take_matching_source_shot_audio_window(tmp_path: Path) -> None:
    source = tmp_path / "safe-background.wav"
    output = tmp_path / "segment-2.wav"
    _write_two_level_wav(source)
    siblings = [
        {"id": "SEG_1", "shot_plan_id": "SHOTPLAN_1", "target_start_us": 0, "target_end_us": 2_000_000},
        {"id": "SEG_2", "shot_plan_id": "SHOTPLAN_1", "target_start_us": 2_000_000, "target_end_us": 4_000_000},
    ]

    background._conform_background_segment(
        source,
        segment={
            "id": "SEG_2",
            "shot_plan_id": "SHOTPLAN_1",
            "target_start_us": 2_000_000,
            "target_end_us": 4_000_000,
            "target_duration_us": 2_000_000,
        },
        siblings=siblings,
        source_duration_us=2_000_000,
        output=output,
    )

    # Segment 2 corresponds to the second half of the source Shot, so it must start from the high level.
    assert abs(_sample_at(output, 0.05)) > 3000
    with wave.open(str(output), "rb") as handle:
        assert abs(handle.getnframes() - 96_000) <= 16


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg required for R10.1 media acceptance")
def test_target_dialogue_and_safe_background_mix_materializes_exact_audio(tmp_path: Path) -> None:
    dialogue = tmp_path / "dialogue.wav"
    bed = tmp_path / "bed.wav"
    output = tmp_path / "mix.wav"
    _write_constant_wav(dialogue, seconds=1.0, sample=4000)
    _write_constant_wav(bed, seconds=1.0, sample=4000)

    result = background.mix_postproduction_audio_v1(
        dialogue_audio=dialogue,
        background_audio=bed,
        dialogues=[{"start_offset_us": 200_000, "end_offset_us": 700_000}],
        duration_us=1_000_000,
        output=output,
    )

    assert result == output
    assert output.is_file() and output.stat().st_size > 0
    with wave.open(str(output), "rb") as handle:
        assert handle.getframerate() == 48_000
        assert handle.getnchannels() == 2
        assert abs(handle.getnframes() - 48_000) <= 8


def test_background_runtime_unavailable_is_safe_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class Provider:
        provider_name = "TEST"

        def status(self):
            return {"ready": False, "error": "offline"}

        def separate_background(self, request):  # pragma: no cover - must never be called
            raise AssertionError("separator must not run while offline")

    result = background.prepare_safe_background_v1(
        "PROJECT_TEST",
        {"episode_id": "EP", "id": "SEG"},
        [],
        tmp_path,
        provider=Provider(),
    )
    assert result["status"] == "SKIPPED"
    assert result["mode"] == "TARGET_DIALOGUE_ONLY_FALLBACK"


def test_r10_1_wrapper_keeps_valid_r10_output_when_background_enhancement_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(enhancer, "run_ready_postproduction_v1", lambda *_args, **_kwargs: {
        "project_id": "PROJECT_TEST",
        "succeeded_now": 1,
        "failed": [],
        "plan": {
            "episodes": [{
                "segments": [{"generation_segment_id": "SEG_1", "status": "SUCCEEDED"}],
            }],
        },
    })
    monkeypatch.setattr(enhancer, "enhance_postproduction_segment_audio_v1", lambda *_args, **_kwargs: {
        "status": "FALLBACK",
        "reason": "separator offline",
    })

    result = enhancer.run_ready_postproduction_with_audio_mix_v1("PROJECT_TEST")

    assert result["succeeded_now"] == 1
    assert result["failed"] == []
    assert result["background_audio"]["enhanced_now"] == 0
    assert result["background_audio"]["fallback_count"] == 1


def test_audio_separator_worker_import_is_lazy() -> None:
    from scripts import audio_separator_worker_v1 as worker

    assert worker.app.title == "AI Drama Studio Audio Separator Worker"
    assert worker.DEFAULT_MODEL.endswith(".onnx")
    assert worker._separator_cache == {}


def test_audio_separator_runtime_checker_creates_valid_probe_wav(tmp_path: Path) -> None:
    from scripts import check_audio_separator_runtime as checker

    probe = tmp_path / "probe.wav"
    checker._write_probe_wav(probe, seconds=0.1, rate=16_000)

    with wave.open(str(probe), "rb") as handle:
        assert handle.getnchannels() == 2
        assert handle.getsampwidth() == 2
        assert handle.getframerate() == 16_000
        assert handle.getnframes() == 1_600


def test_r10_1_background_runtime_route_is_registered() -> None:
    from engine.app.main import app

    paths = {route.path for route in app.routes}
    assert "/api/background-audio/runtime" in paths
