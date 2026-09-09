from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

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


def _fact_video() -> ClaimGrounding:
    return ClaimGrounding(
        support_level=ClaimSupportLevel.FACT,
        video_time_ranges=[TimeRange(start_us=100_000, end_us=500_000)],
    )


def _semantic_with_world_rule(grounding: ClaimGrounding):
    return SimpleNamespace(
        overall_analysis=SimpleNamespace(
            story_background_grounding=_fact_video(),
            world_rules=["502 与 503 为相邻住户"],
            world_rule_groundings=[grounding],
        ),
        characters=[],
        relationships=[],
        scenes=[],
        key_props=[],
        story_events=[],
    )


def _base_semantic():
    return SimpleNamespace(
        overall_analysis=SimpleNamespace(
            story_background_grounding=_fact_video(),
            world_rules=[],
            world_rule_groundings=[],
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
    assert provider.profile["professional_skill_version"] == "1.1.0"
    assert provider.profile["grounding_contract"] == "grounded-source-truth-v2"
    assert provider.profile["prompt_version"] == "p7-source-bible-v2"


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
    assert provider.profile["professional_skill_version"] == "1.1.0"
    assert provider.profile["grounding_contract"] == "grounded-source-truth-v2"


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

    assert "source-video-understanding@1.1.0" in prompt
    assert "社会学泛化" in prompt
    assert "world_rules 不是社会常识列表" in prompt
    assert "UNKNOWN 不是已填写事实字段的通行证" in prompt
    assert "story_function=null" in prompt
    assert "grounded-source-truth-v2" in prompt
    assert "不是 P8 分镜表" in prompt
    assert "CURRENT P6" in prompt


def test_fact_grounding_requires_support() -> None:
    with pytest.raises(ValidationError, match="FACT"):
        ClaimGrounding(support_level=ClaimSupportLevel.FACT)


def test_inference_grounding_requires_support() -> None:
    with pytest.raises(ValidationError, match="INFERENCE"):
        ClaimGrounding(support_level=ClaimSupportLevel.INFERENCE)


def test_unknown_grounding_cannot_carry_support() -> None:
    with pytest.raises(ValidationError, match="UNKNOWN"):
        ClaimGrounding(
            support_level=ClaimSupportLevel.UNKNOWN,
            dialogue_evidence_ids=["dialogue-1"],
        )


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

    with pytest.raises(ValueError, match="support_level FACT"):
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


def test_story_background_cannot_publish_as_unknown() -> None:
    semantic = _base_semantic()
    semantic.overall_analysis.story_background_grounding = ClaimGrounding()

    with pytest.raises(ValueError, match="story_background.*support_level FACT"):
        validate_episode_understanding_grounding(semantic, _input())


def test_character_identity_cannot_publish_as_unknown() -> None:
    semantic = _base_semantic()
    semantic.characters = [SimpleNamespace(character_id="char-a", identity_grounding=ClaimGrounding())]

    with pytest.raises(ValueError, match=r"character\[char-a\].*support_level FACT"):
        validate_episode_understanding_grounding(semantic, _input())


def test_relationship_scene_and_event_require_fact_grounding() -> None:
    semantic = _base_semantic()
    semantic.relationships = [
        SimpleNamespace(source_character_id="a", target_character_id="b", grounding=ClaimGrounding())
    ]

    with pytest.raises(ValueError, match=r"relationship\[a->b\].*support_level FACT"):
        validate_episode_understanding_grounding(semantic, _input())

    semantic = _base_semantic()
    semantic.scenes = [SimpleNamespace(scene_id="scene-a", grounding=ClaimGrounding())]
    with pytest.raises(ValueError, match=r"scene\[scene-a\].*support_level FACT"):
        validate_episode_understanding_grounding(semantic, _input())

    semantic = _base_semantic()
    semantic.story_events = [SimpleNamespace(event_id="event-a", grounding=ClaimGrounding())]
    with pytest.raises(ValueError, match=r"story_event\[event-a\].*support_level FACT"):
        validate_episode_understanding_grounding(semantic, _input())


def test_prop_unknown_story_function_requires_null_and_fact_appearance() -> None:
    semantic = _base_semantic()
    semantic.key_props = [
        SimpleNamespace(
            prop_id="trash-bag",
            appearance_grounding=_fact_video(),
            story_function="侧面印证她倒垃圾时顺手拿走了花",
            story_function_grounding=ClaimGrounding(),
        )
    ]

    with pytest.raises(ValueError, match="story_function.*FACT/INFERENCE"):
        validate_episode_understanding_grounding(semantic, _input())


def test_prop_unknown_story_function_can_be_omitted() -> None:
    semantic = _base_semantic()
    semantic.key_props = [
        SimpleNamespace(
            prop_id="trash-bag",
            appearance_grounding=_fact_video(),
            story_function=None,
            story_function_grounding=ClaimGrounding(),
        )
    ]

    validate_episode_understanding_grounding(semantic, _input())
