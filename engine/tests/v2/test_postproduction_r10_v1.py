from __future__ import annotations

from pathlib import Path
import shutil
import wave

import pytest

from engine.app import postproduction_lipsync_v1 as lip_windows
from engine.app import postproduction_v1 as post
from engine.app.review_issue_v1 import DOMAIN_EDITED_ISSUE_TYPES


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


def test_multi_face_compile_is_ready_for_background_locator_not_sync_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio = tmp_path / "dialogue.wav"
    video = tmp_path / "selected.mp4"
    _write_wav(audio)
    video.write_bytes(b"selected")
    monkeypatch.setattr(post, "selected_generation_output_v1", lambda *_args, **_kwargs: video)

    planned = post._plan_segment("PROJECT_TEST", _segment(audio, character_count=2), _selection(), None)

    assert planned["status"] == "READY"
    assert planned["lip_sync_mode"] == "LATENTSYNC_TARGET_FACE_ROI"
    assert planned["lip_sync_windows"] == []
    assert "进入 R10 后期" in planned["reason"]


def test_multi_face_locator_unique_target_becomes_roi_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio = tmp_path / "dialogue.wav"
    video = tmp_path / "selected.mp4"
    _write_wav(audio)
    video.write_bytes(b"selected-video")
    segment = _segment(audio, character_count=2)
    dialogues, waiting = post._dialogue_payload("PROJECT_TEST", segment)
    assert waiting is False

    monkeypatch.setattr(
        lip_windows,
        "_reference_identities",
        lambda _characters, speaker_ids: {speaker_id: [{"path": f"{speaker_id}.jpg"}] for speaker_id in speaker_ids},
    )
    monkeypatch.setattr(
        lip_windows,
        "locate_target_speaker_face_v1",
        lambda **_kwargs: {
            "status": "READY",
            "reason": "unique target",
            "crop_box": [20, 30, 160, 180],
            "median_similarity": 0.61,
        },
    )

    result = lip_windows.plan_lip_sync_v1(
        project_id="PROJECT_TEST",
        segment=segment,
        selected_video=video,
        dialogues=dialogues,
    )

    assert result["status"] == "READY"
    assert result["mode"] == "LATENTSYNC_TARGET_FACE_ROI"
    assert len(result["windows"]) == 1
    assert result["windows"][0]["crop_box"] == [20, 30, 160, 180]
    assert result["windows"][0]["locator_status"] == "READY"


def test_multi_face_locator_ambiguity_fails_closed_to_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio = tmp_path / "dialogue.wav"
    video = tmp_path / "selected.mp4"
    _write_wav(audio)
    video.write_bytes(b"selected-video")
    segment = _segment(audio, character_count=2)
    dialogues, _waiting = post._dialogue_payload("PROJECT_TEST", segment)

    monkeypatch.setattr(
        lip_windows,
        "_reference_identities",
        lambda _characters, speaker_ids: {speaker_id: [{"path": f"{speaker_id}.jpg"}] for speaker_id in speaker_ids},
    )
    monkeypatch.setattr(
        lip_windows,
        "locate_target_speaker_face_v1",
        lambda **_kwargs: {
            "status": "REVIEW",
            "reason": "target face winner margin too small",
            "median_similarity": 0.43,
        },
    )

    result = lip_windows.plan_lip_sync_v1(
        project_id="PROJECT_TEST",
        segment=segment,
        selected_video=video,
        dialogues=dialogues,
    )

    assert result["status"] == "REVIEW"
    assert result["mode"] == "REVIEW_MULTI_FACE"
    assert "winner margin" in result["reason"]


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
    if shutil.which("ffmpeg") is None:
        pytest.skip("FFmpeg is not installed in this lightweight test environment")

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


def test_lip_sync_qc_is_domain_edited_issue() -> None:
    assert "LIP_SYNC_QC" in DOMAIN_EDITED_ISSUE_TYPES


def test_r10_routes_are_registered() -> None:
    from engine.app.main import app

    paths = {route.path for route in app.routes}
    assert "/api/lip-sync/runtime" in paths
    assert "/api/projects/{project_id}/postproduction" in paths
    assert "/api/projects/{project_id}/tasks/postproduction" in paths
    assert "/api/projects/{project_id}/postproduction-segments/{segment_id}/retry-lip-sync" in paths
    assert "/api/postproduction-segments/{segment_id}/video" in paths


def test_latentsync_worker_import_does_not_import_model_stack() -> None:
    # The worker must be inspectable/configurable before the dedicated LatentSync env is ready.
    from scripts import latentsync_worker_v1 as worker

    assert worker.app.title == "AI Drama Studio LatentSync Worker"
    assert worker.CONFIG_REL.endswith("stage2_512.yaml")
