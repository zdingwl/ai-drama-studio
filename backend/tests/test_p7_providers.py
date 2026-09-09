from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.projects.enums import SourceUnderstandingProvider
from app.understanding.providers import (
    DoubaoSeedSourceEpisodeUnderstandingProvider,
    EpisodeUnderstandingInput,
    LocalQwenSourceEpisodeUnderstandingProvider,
    _prompt,
    build_source_episode_understanding_provider,
    validate_episode_understanding_grounding,
)
from app.understanding.schemas import ClaimGrounding, ClaimSupportLevel, TimeRange


def _input() -> EpisodeUnderstandingInput:
    return EpisodeUnderstandingInput(
        source_path=Path("/tmp/source.mp4"),
        source_filename="episode.mp4",
        mime_type="video/mp4",
        episode_id="episode-1",
        episode_order=1,
        duration_us=2_000_000,
        source_language="zh-CN",
        evidence_payload={
            "dialogue": [
                {"id": "dialogue-1", "start_us": 100_000, "end_us": 500_000, "text": "我们是邻居。"}
            ],
            "visual_text": [
                {"id": "ocr-1", "start_us": 100_000, "end_us": 500_000, "text": "502业主"}
            ],
        },
        shot_hints=[],
    )


def _semantic_with_world_rule(grounding: ClaimGrounding):
    return SimpleNamespace(
        overall_analysis=SimpleNamespace(
            story_background_grounding=ClaimGrounding(),
            world_rules=["502 与 503 为相邻住户"],
            world_rule_groundings=[grounding],
        ),
        characters=[],
        relationships=[],
        scenes=[],
        key_props=[],
        story_events=[],
    )


def test_p7_doubao_provider_profile_is_cloud_full_episode() -> None:
    settings = Settings(_env_file=None, p7_doubao_api_key="test-only")
    provider = build_source_episode_understanding_provider(
        settings,
        SourceUnderstandingProvider.DOUBAO_SEED_2_1_PRO_API,
    )

    assert isinstance(provider, DoubaoSeedSourceEpisodeUnderstandingProvider)
    assert provider.model_name == "doubao-seed-2-1-pro-260628"
    assert provider.profile["selection"] == "DOUBAO_SEED_2_1_PRO_API"
    assert provider.profile["mode"] == "CLOUD_API"
    assert provider.profile["video_input"] == "ARK_FILES_API_FULL_EPISODE"
    assert provider.profile["professional_skill_id"] == "source-video-understanding"
    assert provider.profile["professional_skill_version"] == "1.0.0"
    assert provider.profile["grounding_contract"] == "grounded-source-truth-v1"


def test_p7_local_qwen38_is_high_quality_choice() -> None:
    settings = Settings(_env_file=None)
    provider = build_source_episode_understanding_provider(
        settings,
        SourceUnderstandingProvider.QWEN3_8_27B_LOCAL,
    )

    assert isinstance(provider, LocalQwenSourceEpisodeUnderstandingProvider)
    assert provider.model_name == "Qwen/Qwen3.8-27B"
    assert provider.profile["selection"] == "QWEN3_8_27B_LOCAL"
    assert provider.profile["mode"] == "LOCAL_OPENAI_COMPATIBLE"
    assert provider.profile["video_input"] == "VLLM_FILE_URL_FULL_EPISODE"
    assert provider.profile["professional_skill_version"] == "1.0.0"


def test_p7_local_qwen3_vl_8b_is_low_footprint_choice() -> None:
    settings = Settings(_env_file=None)
    provider = build_source_episode_understanding_provider(
        settings,
        SourceUnderstandingProvider.QWEN3_VL_8B_THINKING_LOCAL,
    )

    assert isinstance(provider, LocalQwenSourceEpisodeUnderstandingProvider)
    assert provider.model_name == "Qwen/Qwen3-VL-8B-Thinking"
    assert provider.profile["selection"] == "QWEN3_VL_8B_THINKING_LOCAL"
    assert provider.profile["mode"] == "LOCAL_OPENAI_COMPATIBLE"
    assert provider.profile["video_input"] == "VLLM_FILE_URL_FULL_EPISODE"


def test_p7_prompt_is_driven_by_professional_skill_source_truth_rules() -> None:
    prompt = _prompt(_input())

    assert "source-video-understanding@1.0.0" in prompt
    assert "宁可 UNKNOWN" in prompt
    assert "社会学泛化" in prompt
    assert "world_rules 不是社会常识列表" in prompt
    assert "不是 P8 分镜表" in prompt
    assert "CURRENT P6" in prompt


def test_fact_grounding_requires_support() -> None:
    with pytest.raises(ValueError, match="FACT"):
        ClaimGrounding(support_level=ClaimSupportLevel.FACT)


def test_provider_grounding_rejects_non_current_evidence_id() -> None:
    semantic = _semantic_with_world_rule(
        ClaimGrounding(
            support_level=ClaimSupportLevel.FACT,
            dialogue_evidence_ids=["invented-dialogue"],
        )
    )

    with pytest.raises(ValueError, match="non-current Source Evidence"):
        validate_episode_understanding_grounding(semantic, _input())


def test_world_rule_must_be_confirmed_fact_not_inference() -> None:
    semantic = _semantic_with_world_rule(
        ClaimGrounding(
            support_level=ClaimSupportLevel.INFERENCE,
            video_time_ranges=[TimeRange(start_us=100_000, end_us=500_000)],
        )
    )

    with pytest.raises(ValueError, match="must be FACT"):
        validate_episode_understanding_grounding(semantic, _input())


def test_grounded_world_rule_accepts_current_evidence() -> None:
    semantic = _semantic_with_world_rule(
        ClaimGrounding(
            support_level=ClaimSupportLevel.FACT,
            dialogue_evidence_ids=["dialogue-1"],
            visual_text_evidence_ids=["ocr-1"],
        )
    )

    validate_episode_understanding_grounding(semantic, _input())
