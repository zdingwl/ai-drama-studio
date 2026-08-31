from scripts import diagnose_breakdown_vlm_windows_v4 as diagnostic
from scripts import run_breakdown_vlm_window_segment_index_v4 as segment


def test_v4_candidate_uses_local_index_profile_and_timed_v3_runner() -> None:
    provider = diagnostic._V4CandidateProvider()
    config = provider._runtime_config("zh-CN")

    assert diagnostic.WINDOW_PROMPT_PROFILE == segment.WINDOW_CONTEXT_PROMPT_PROFILE
    assert diagnostic.WINDOW_PROMPT_PROFILE == (
        "breakdown-p2-vlm-window-context-segment-index-zh-v4"
    )
    assert config.runner_script.name == "run_breakdown_vlm_fast_grounded_qwen3_timed_v3.py"
