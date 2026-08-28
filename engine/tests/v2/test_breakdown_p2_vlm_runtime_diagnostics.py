from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app import breakdown_p2_vlm_runtime_v1 as runtime


def test_failed_e2_result_promotes_subprocess_detail_to_first_warning() -> None:
    result = p2.P2ProviderResult(
        component="VLM",
        provider="qwen3-vl",
        model="fixture-model",
        status="FAILED",
        metadata={
            "subprocess_failure_detail": "P2-E2 FATAL RuntimeError: CUDA out of memory",
        },
        warnings=("P2-E2 VLM inference failed",),
    )

    diagnosed = runtime._with_e2_runtime_diagnostics(result)

    assert diagnosed.status == "FAILED"
    assert diagnosed.warnings[0] == (
        "P2-E2 runtime detail: P2-E2 FATAL RuntimeError: CUDA out of memory"
    )
    assert diagnosed.warnings[1] == "P2-E2 VLM inference failed"
    assert diagnosed.metadata == result.metadata


def test_failed_e2_result_promotes_window_failure_details() -> None:
    result = p2.P2ProviderResult(
        component="VLM",
        provider="qwen3-vl",
        model="fixture-model",
        status="FAILED",
        metadata={
            "window_failure_details": [
                "window-0001 structured output invalid/truncated",
                "window-0002 decord could not open Episode window",
            ],
        },
        warnings=("P2-E2 VLM produced no usable Shot semantics",),
    )

    diagnosed = runtime._with_e2_runtime_diagnostics(result)

    assert diagnosed.warnings[0].startswith("P2-E2 runtime detail: window-0001")
    assert "window-0002" in diagnosed.warnings[0]
