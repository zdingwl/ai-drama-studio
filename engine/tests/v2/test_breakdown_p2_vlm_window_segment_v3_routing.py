from engine.app import breakdown_p2_vlm_fast_grounded_instrumented_v2 as instrumented
from engine.app import breakdown_p2_vlm_runtime_v1 as runtime


def test_production_runtime_routes_to_segment_v3_timed_runner() -> None:
    provider = runtime.Qwen3VLSemanticProvider()
    config = provider._runtime_config("zh-CN")

    assert issubclass(runtime.Qwen3VLSemanticProvider, instrumented.Qwen3VLSemanticProvider)
    assert instrumented.WINDOW_PROMPT_PROFILE == "breakdown-p2-vlm-window-context-segment-zh-v3"
    assert config.runner_script.name == "run_breakdown_vlm_fast_grounded_qwen3_timed_v2.py"
