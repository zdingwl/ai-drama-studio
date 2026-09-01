from __future__ import annotations

from pathlib import Path

from engine.app.generation_attempt_v1 import _finalize_downloaded_output
from engine.app.h3_context_compiler_v1 import (
    _dialogue_body,
    _materialize_reference_video,
)
from engine.app.h3_context_contract_v1 import H3CompiledContextV1
from engine.app.h3_runtime_v1 import H3RuntimeManager


def test_runtime_builds_current_sglang_video_request_and_selects_task() -> None:
    runtime = H3RuntimeManager()

    text_only = runtime._request_body(  # noqa: SLF001 - contract acceptance
        mode="FL2VA",
        prompt="localized drama shot",
        conditions=[],
        duration_seconds=4,
        short_edge=768,
        aspect_ratio="9:16",
        seed=7,
    )
    assert text_only["model"] == "MiniMaxAI/MiniMax-H3"
    assert text_only["seconds"] == 4.0
    assert text_only["task"] == "t2va"
    assert text_only["target"]["short_edge"] == 768

    first_frame = runtime._request_body(  # noqa: SLF001 - contract acceptance
        mode="FL2VA",
        prompt="continue from the previous localized shot",
        conditions=[
            {
                "type": "image",
                "uri": "file:///tmp/first.jpg",
                "role": "first_frame",
                "frame_index": 0,
            }
        ],
        duration_seconds=6,
        short_edge=768,
        aspect_ratio="9:16",
        seed=8,
    )
    assert first_frame["task"] == "fl2va"
    assert first_frame["conditions"][0]["frame_index"] == 0

    reference = runtime._request_body(  # noqa: SLF001 - contract acceptance
        mode="REF2VA",
        prompt="reuse directing motion, replace cast",
        conditions=[
            {"type": "video", "uri": "file:///tmp/ref.mp4", "role": "source_directing_reference"}
        ],
        duration_seconds=7,
        short_edge=768,
        aspect_ratio="9:16",
        seed=9,
    )
    assert reference["task"] == "ref2va"


def test_compiled_context_keeps_first_frame_addressing() -> None:
    digest = "a" * 64
    context = H3CompiledContextV1.model_validate({
        "project_id": "P1",
        "episode_id": "E1",
        "segment_id": "S1",
        "segment_input_fingerprint": digest,
        "context_fingerprint": "b" * 64,
        "status": "READY",
        "reason": "ready",
        "mode": "FL2VA",
        "prompt": "For the target video, at 0.00 seconds into the target video, <Picture 1> is fully referenced.",
        "conditions": [
            {
                "type": "image",
                "role": "first_frame",
                "label": "<Picture 1>",
                "uri": "file:///tmp/first.jpg",
                "local_path": "/tmp/first.jpg",
                "sha256": "c" * 64,
                "source": "previous-generation-output",
                "frame_index": 0,
            }
        ],
        "request": {
            "mode": "FL2VA",
            "prompt": "For the target video, at 0.00 seconds into the target video, <Picture 1> is fully referenced.",
            "conditions": [
                {
                    "type": "image",
                    "uri": "file:///tmp/first.jpg",
                    "role": "first_frame",
                    "frame_index": 0,
                }
            ],
            "duration_seconds": 4,
        },
        "workspace_dir": "/tmp/context",
        "created_at": "2026-09-01T00:00:00+00:00",
    })
    assert context.request is not None
    assert context.request.conditions[0].frame_index == 0


def test_source_reference_is_materialized_without_source_audio(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    commands: list[list[str]] = []

    monkeypatch.setattr(
        "engine.app.h3_context_compiler_v1._resolve_local_path",
        lambda _project_id, _value: source,
    )

    def fake_ffmpeg(command: list[str], **_kwargs) -> None:
        commands.append(command)
        Path(command[-1]).write_bytes(b"silent-reference")

    monkeypatch.setattr("engine.app.h3_context_compiler_v1._run_ffmpeg", fake_ffmpeg)
    output = _materialize_reference_video(
        {
            "project_id": "P1",
            "reference_url": "/api/shots/SHOT1/reference",
            "reference_clip_start_offset_us": 250_000,
            "reference_clip_duration_us": 3_000_000,
        },
        tmp_path / "context",
    )
    assert output.is_file()
    assert "-an" in commands[0]
    assert "0:a?" not in commands[0]
    assert "fps=24" in commands[0]


def test_dialogue_prompt_uses_real_target_language() -> None:
    text = _dialogue_body(
        {
            "dialogues": [
                {
                    "target_character_id": "TC1",
                    "target_character_name": "Aiko",
                    "final_text": "行きましょう。",
                    "segment_start_offset_us": 500_000,
                    "speaker_visible": True,
                    "carried_from_previous_shot": False,
                }
            ]
        },
        {"TC1": "<Subject 1>"},
        target_language="ja-JP",
    )
    assert "<d>[Japanese] 行きましょう。</d>" in text
    assert "0.500 seconds" in text


def test_quantized_h3_output_is_trimmed_to_exact_target_duration(monkeypatch, tmp_path: Path) -> None:
    raw = tmp_path / "raw.mp4"
    final = tmp_path / "final.mp4"
    raw.write_bytes(b"four-second-h3-output")
    commands: list[list[str]] = []

    def fake_ffmpeg(command: list[str], **_kwargs) -> None:
        commands.append(command)
        Path(command[-1]).write_bytes(b"trimmed")

    monkeypatch.setattr("engine.app.generation_attempt_v1._run_ffmpeg", fake_ffmpeg)
    result = _finalize_downloaded_output(
        raw,
        final,
        post_trim_duration_us=1_250_000,
    )
    assert result == final
    assert final.read_bytes() == b"trimmed"
    assert "-t" in commands[0]
    assert commands[0][commands[0].index("-t") + 1] == "1.250000"


def test_main_registers_r7_and_r8_routes() -> None:
    from engine.app.main import app

    paths = {route.path for route in app.routes}
    assert "/api/projects/{project_id}/generation-segments" in paths
    assert "/api/projects/{project_id}/generation-segments/{segment_id}/h3-context/compile" in paths
    assert "/api/projects/{project_id}/tasks/h3-generate-ready" in paths
    assert "/api/projects/{project_id}/generation-attempts" in paths
    assert "/api/generation-attempts/{attempt_id}/video" in paths
