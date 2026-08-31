from engine.app import breakdown_p2_vlm_fast_grounded_instrumented_v2 as instrumented
from engine.app import breakdown_p2_vlm_runtime_v1 as runtime
from scripts import run_breakdown_vlm_window_segment_index_v4 as segment


def test_production_runtime_routes_to_segment_index_v4_timed_runner() -> None:
    provider = runtime.Qwen3VLSemanticProvider()
    config = provider._runtime_config("zh-CN")

    assert issubclass(runtime.Qwen3VLSemanticProvider, instrumented.Qwen3VLSemanticProvider)
    assert instrumented.WINDOW_PROMPT_PROFILE == segment.WINDOW_CONTEXT_PROMPT_PROFILE
    assert instrumented.WINDOW_PROMPT_PROFILE == (
        "breakdown-p2-vlm-window-context-segment-index-zh-v4"
    )
    assert config.runner_script.name == "run_breakdown_vlm_fast_grounded_qwen3_timed_v3.py"
