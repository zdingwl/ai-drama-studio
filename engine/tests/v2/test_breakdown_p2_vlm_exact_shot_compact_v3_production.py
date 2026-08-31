from engine.app import breakdown_p2_vlm_continuity_v1 as continuity
from engine.app import breakdown_p2_vlm_fast_grounded_instrumented_v3 as production


def test_production_vlm_routes_to_accepted_exact_shot_compact_v3() -> None:
    provider = continuity.Qwen3VLSemanticProvider()
    config = provider._runtime_config("zh-CN")

    assert issubclass(continuity.Qwen3VLSemanticProvider, production.Qwen3VLSemanticProvider)
    assert continuity.VLM_WINDOW_PROMPT_PROFILE == (
        "breakdown-p2-vlm-window-context-segment-index-zh-v4"
    )
    assert continuity.VLM_EXACT_SHOT_PROMPT_PROFILE == (
        "breakdown-p2-vlm-exact-shot-compact-reconstruction-zh-v3"
    )
    assert config.runner_script.name == "run_breakdown_vlm_fast_grounded_qwen3_timed_v5.py"


def test_production_exact_shot_limits_remain_unchanged() -> None:
    provider = continuity.Qwen3VLSemanticProvider()

    assert provider.grounding_batch_size == 5
    assert provider.exact_shot_max_pixels == 524288
    assert provider.grounding_max_new_tokens == 4096
