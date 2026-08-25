from engine.app.inference_runtime_v41 import provider_plan


def test_character_runtime_prefers_cuda_when_available() -> None:
    providers = provider_plan(["CPUExecutionProvider", "CUDAExecutionProvider"], "auto")
    first = providers[0][0] if isinstance(providers[0], tuple) else providers[0]
    assert first == "CUDAExecutionProvider"
    assert "CPUExecutionProvider" in providers


def test_character_runtime_falls_back_to_cpu_without_cuda() -> None:
    assert provider_plan(["CPUExecutionProvider"], "auto") == ["CPUExecutionProvider"]


def test_character_runtime_allows_explicit_cpu_for_diagnostics() -> None:
    assert provider_plan(["CPUExecutionProvider", "CUDAExecutionProvider"], "cpu") == ["CPUExecutionProvider"]
