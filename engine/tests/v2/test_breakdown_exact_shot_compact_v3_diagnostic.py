from scripts import diagnose_breakdown_exact_shot_compact_v3 as diagnostic
from scripts import run_breakdown_vlm_exact_shot_compact_v3 as compact


def test_compact_v3_diagnostic_routes_to_timed_v5_candidate() -> None:
    provider = diagnostic._CompactExactV3CandidateProvider()
    config = provider._runtime_config("zh-CN")
    assert diagnostic.CANDIDATE_RUNNER.name == "run_breakdown_vlm_fast_grounded_qwen3_timed_v5.py"
    assert config.runner_script.name == "run_breakdown_vlm_fast_grounded_qwen3_timed_v5.py"
    assert compact.EXACT_SHOT_PROMPT_PROFILE == (
        "breakdown-p2-vlm-exact-shot-detector-recheck-zh-v5"
    )
