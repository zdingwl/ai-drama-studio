from __future__ import annotations

from engine.app.breakdown_p2_vlm_runtime_v1 import Qwen3VLSemanticProvider


def test_default_runner_uses_diagnostic_transport() -> None:
    provider = Qwen3VLSemanticProvider(inference_runner=lambda config, shots: ())
    assert provider.runner_script.name == "run_breakdown_vlm_qwen3_diagnostic.py"


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
