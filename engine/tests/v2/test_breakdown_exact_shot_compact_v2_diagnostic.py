from scripts import diagnose_breakdown_exact_shot_compact_v2 as diagnostic
from scripts import run_breakdown_vlm_exact_shot_compact_v2 as exact_v2


def test_compact_exact_diagnostic_routes_candidate_runner_only() -> None:
    provider = diagnostic._CompactExactCandidateProvider()
    config = provider._runtime_config("zh-CN")

    assert exact_v2.EXACT_SHOT_PROMPT_PROFILE == (
        "breakdown-p2-vlm-exact-shot-compact-zh-v2"
    )
    assert config.runner_script.name == "run_breakdown_vlm_fast_grounded_qwen3_timed_v4.py"
