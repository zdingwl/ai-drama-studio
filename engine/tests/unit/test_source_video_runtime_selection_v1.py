from __future__ import annotations

from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app import source_video_understanding_provider_v1 as module


def _context() -> p2.P2RunContext:
    return p2.P2RunContext(
        run_id="RUN_1",
        project_id="PROJECT_1",
        episode_id="EPISODE_1",
        source_language="zh-CN",
        source_shot_revision_id="SHOTREV_1",
        audio_path=None,
        shots=(
            p2.P2ShotInput(
                revision_item_id="ITEM_1",
                original_shot_id="SHOT_1",
                ordinal=1,
                start_us=0,
                end_us=2_000_000,
                duration_us=2_000_000,
                reference_clip_path="/source/reference/shot-000001.mp4",
                thumbnail_path=None,
                keyframes=(),
            ),
        ),
    )


def _result(provider: str, model: str, status: str = "READY") -> p2.P2ProviderResult:
    return p2.P2ProviderResult(
        component="VLM",
        provider=provider,
        model=model,
        status=status,
        evidence=(),
        metadata={},
        warnings=(),
    )


class _FakeStableProvider:
    component = "VLM"
    model_name = "Qwen/Qwen3-VL-4B-Instruct"

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    def _runtime_config(self, source_language: str) -> object:
        return object()

    def _runtime_missing(self, config: object) -> tuple[str, ...]:
        return ()

    def analyze(self, context: p2.P2RunContext) -> p2.P2ProviderResult:
        return _result("qwen3-vl", self.model_name)


def test_production_visual_provider_prefers_ready_stable_4b_runtime(monkeypatch) -> None:
    monkeypatch.delenv(module.SOURCE_VIDEO_RUNTIME_MODE_ENV, raising=False)
    monkeypatch.setattr(module, "_FastGroundedQwenProvider", _FakeStableProvider)

    provider = module.Qwen38VideoUnderstandingProvider()
    result = provider.analyze(_context())

    assert result.status == "READY"
    assert result.provider == "qwen3-vl"
    assert result.model == "Qwen/Qwen3-VL-4B-Instruct"
    assert result.metadata["runtime_selection"] == "QWEN3VL4B"
    assert result.metadata["runtime_selection_mode"] == "AUTO_STABLE"
    assert result.metadata["provider_profile"] == module.STABLE_SOURCE_VIDEO_PROVIDER_PROFILE


def test_explicit_qwen38_mode_bypasses_stable_runtime(monkeypatch) -> None:
    monkeypatch.setenv(module.SOURCE_VIDEO_RUNTIME_MODE_ENV, "QWEN38")
    monkeypatch.setattr(module, "_FastGroundedQwenProvider", _FakeStableProvider)

    provider = module.Qwen38VideoUnderstandingProvider()
    monkeypatch.setattr(provider, "_analyze_qwen38", lambda context: _result("qwen38-video-understanding", module.DEFAULT_QWEN38_MODEL))
    result = provider.analyze(_context())

    assert result.status == "READY"
    assert result.provider == "qwen38-video-understanding"
    assert result.metadata["runtime_selection"] == "QWEN38"
    assert result.metadata["runtime_selection_mode"] == "QWEN38"


def test_auto_stable_falls_back_to_qwen38_when_stable_result_is_not_ready(monkeypatch) -> None:
    class _NotReadyStableProvider(_FakeStableProvider):
        def analyze(self, context: p2.P2RunContext) -> p2.P2ProviderResult:
            return _result("qwen3-vl", self.model_name, status="FAILED")

    monkeypatch.delenv(module.SOURCE_VIDEO_RUNTIME_MODE_ENV, raising=False)
    monkeypatch.setattr(module, "_FastGroundedQwenProvider", _NotReadyStableProvider)

    provider = module.Qwen38VideoUnderstandingProvider()
    monkeypatch.setattr(provider, "_analyze_qwen38", lambda context: _result("qwen38-video-understanding", module.DEFAULT_QWEN38_MODEL))
    result = provider.analyze(_context())

    assert result.status == "READY"
    assert result.metadata["runtime_selection"] == "QWEN38"
    assert any("returned FAILED" in warning for warning in result.warnings)
