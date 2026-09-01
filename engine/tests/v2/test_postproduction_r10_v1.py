from __future__ import annotations

from pathlib import Path
import wave

import pytest

from engine.app import postproduction_v1 as post


def _write_wav(path: Path, *, seconds: int = 2, rate: int = 16_000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = bytearray()
        for index in range(seconds * rate):
            # Distinct first/second halves make trim behavior observable.
            sample = 1000 if index < rate else 3000
            frames += int(sample).to_bytes(2, byteorder="little", signed=True)
        handle.writeframes(bytes(frames))


def _segment(audio: Path, *, character_count: int = 1, speaker_visible: bool = True) -> dict:
    characters = [
        {
            "target_character_id": f"TC_{index}",
            "source_character_id": f"SC_{index}",
            "target_name": f"Character {index}",
            "appearance_profile": "profile",
            "generation_prompt": "prompt",
            "reference_assets": [],
        }
        for index in range(1, character_count + 1)
    ]
    return {
        "id": "GENSEG_TEST",
        "project_id": "PROJECT_TEST",
        "episode_id": "EP_TEST",
        "input_fingerprint": "a" * 64,
        "target_start_us": 5_000_000,
        "target_end_us": 7_000_000,
        "target_duration_us": 2_000_000,
        "target_characters": characters,
        "dialogues": [
            {
                "target_dialogue_id": "TD_1",
                "target_character_id": "TC_1",
                "target_character_name": "Character 1",
                "final_text": "hello",
                "audio_status": "READY",
                "audio_path": str(audio),
                "global_start_us": 4_000_000,
                "global_end_us": 6_000_000,
                "segment_start_offset_us": 0,
                "segment_end_offset_us": 1_000_000,
                "speaker_visible": speaker_visible,
            }
        ],
    }


def _selection() -> dict:
    return {"id": "SEL_1", "selected_attempt_id": "ATTEMPT_1", "generation_segment_id": "GENSEG_TEST"}


def test_single_visible_character_is_latentsync_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    audio = tmp_path / "dialogue.wav"
    video = tmp_path / "selected.mp4"
    _write_wav(audio)
    video.write_bytes(b"selected")
    monkeypatch.setattr(post, "selected_generation_output_v1", lambda *_args, **_kwargs: video)

    planned = post._plan_segment("PROJECT_TEST", _segment(audio), _selection(), None)

    assert planned["status"] == "READY"
    assert planned["lip_sync_mode"] == "LATENTSYNC_FULL_SEGMENT"
    assert planned["visible_speaker_ids"] == ["TC_1"]
    # Dialogue started one second before this GenerationSegment, so R10 must not replay sentence start.
    assert planned["dialogues"][0]["audio_trim_start_us"] == 1_000_000


def test_multi_face_visible_dialogue_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    audio = tmp_path / "dialogue.wav"
    video = tmp_path / "selected.mp4"
    _write_wav(audio)
    video.write_bytes(b"selected")
    monkeypatch.setattr(post, "selected_generation_output_v1", lambda *_args, **_kwargs: video)

    planned = post._plan_segment("PROJECT_TEST", _segment(audio, character_count=2), _selection(), None)

    assert planned["status"] == "REVIEW"
    assert planned["lip_sync_mode"] == "REVIEW_MULTI_FACE"
    assert "多人同框" in planned["reason"]


def test_offscreen_dialogue_skips_lipsync_but_keeps_audio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    audio = tmp_path / "dialogue.wav"
    video = tmp_path / "selected.mp4"
    _write_wav(audio)
    video.write_bytes(b"selected")
    monkeypatch.setattr(post, "selected_generation_output_v1", lambda *_args, **_kwargs: video)

    planned = post._plan_segment("PROJECT_TEST", _segment(audio, speaker_visible=False), _selection(), None)

    assert planned["status"] == "READY"
    assert planned["lip_sync_mode"] == "SKIP_NO_VISIBLE_DIALOGUE"
    assert planned["dialogues"][0]["audio_path"] == str(audio.resolve())


def test_dialogue_materializer_applies_cross_segment_trim(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    output = tmp_path / "trimmed.wav"
    _write_wav(source)
    post._materialize_dialogue_audio(
        [{
            "audio_path": str(source),
            "audio_trim_start_us": 1_000_000,
            "start_offset_us": 0,
            "end_offset_us": 500_000,
        }],
        500_000,
        output,
        sample_rate=16_000,
        stereo=False,
    )
    with wave.open(str(output), "rb") as handle:
        assert handle.getframerate() == 16_000
        assert handle.getnchannels() == 1
        first = int.from_bytes(handle.readframes(1), byteorder="little", signed=True)
    assert first > 2000


def test_r10_routes_are_registered() -> None:
    from engine.app.main import app

    paths = {route.path for route in app.routes}
    assert "/api/lip-sync/runtime" in paths
    assert "/api/projects/{project_id}/postproduction" in paths
    assert "/api/projects/{project_id}/tasks/postproduction" in paths
    assert "/api/postproduction-segments/{segment_id}/video" in paths


def test_latentsync_worker_import_does_not_import_model_stack() -> None:
    # The worker must be inspectable/configurable before the dedicated LatentSync env is ready.
    from scripts import latentsync_worker_v1 as worker

    assert worker.app.title == "AI Drama Studio LatentSync Worker"
    assert worker.CONFIG_REL.endswith("stage2_512.yaml")
