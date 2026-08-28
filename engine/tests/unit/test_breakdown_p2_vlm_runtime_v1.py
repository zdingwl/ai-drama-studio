from __future__ import annotations

from pathlib import Path

import pytest

from engine.app.breakdown_p2_vlm_runtime_v1 import (
    Qwen3VLSemanticProvider,
    VLM_DRAFT_TEXT_LANGUAGE,
    VLM_PROMPT_PROFILE,
)


def test_default_runner_uses_strict_diagnostic_transport() -> None:
    provider = Qwen3VLSemanticProvider(inference_runner=lambda config, shots: ())
    assert provider.runner_script.name == "run_breakdown_vlm_qwen3_strict_reader.py"


def test_production_prompt_provenance_is_chinese_draft_v1() -> None:
    assert VLM_PROMPT_PROFILE == "breakdown-p2-vlm-zh-draft-v1"
    assert VLM_DRAFT_TEXT_LANGUAGE == "zh-CN"


def test_strict_runner_disables_qwen_torchvision_fallback() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    source = (repo_root / "scripts" / "run_breakdown_vlm_qwen3_strict_reader.py").read_text(
        encoding="utf-8"
    )
    assert 'vision_process.VIDEO_READER_BACKENDS["torchvision"] = backend' in source
    assert 'FORCE_QWENVL_VIDEO_READER' in source
    assert '_install_draft_prompt()' in source


def test_failure_detail_combines_type_and_message() -> None:
    detail = Qwen3VLSemanticProvider._clean_failure_detail({
        "status": "FAILED",
        "error_type": "RuntimeError",
        "error_detail": "TorchCodec could not decode the Reference Clip",
    })
    assert detail == "RuntimeError: TorchCodec could not decode the Reference Clip"


def test_subprocess_output_keeps_only_tail_lines() -> None:
    detail = Qwen3VLSemanticProvider._clean_subprocess_output(
        "line1\nline2\nline3\nline4\nRuntimeError: CUDA out of memory\n"
    )
    assert detail is not None
    assert "line1" not in detail
    assert "CUDA out of memory" in detail


def test_video_reader_override_reaches_qwen_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_DRAMA_P2_VLM_VIDEO_READER", "decord")
    monkeypatch.delenv("FORCE_QWENVL_VIDEO_READER", raising=False)
    provider = Qwen3VLSemanticProvider(inference_runner=lambda config, shots: ())
    config = provider._runtime_config("en")

    env = provider._subprocess_env(config)

    assert env["FORCE_QWENVL_VIDEO_READER"] == "decord"


def test_invalid_video_reader_override_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_DRAMA_P2_VLM_VIDEO_READER", "invalid-reader")
    provider = Qwen3VLSemanticProvider(inference_runner=lambda config, shots: ())
    config = provider._runtime_config("en")

    with pytest.raises(ValueError, match="decord/torchcodec/torchvision"):
        provider._subprocess_env(config)
