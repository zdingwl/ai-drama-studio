from app.replica_pipeline.localized_storyboard import (
    LocalizationProviderInput,
    _assert_chinese,
    _batched_payloads,
    _merge_semantics,
)
from app.core.errors import AppError
import pytest
from app.replica_pipeline.schemas import LocalizedStoryboardSemantic


def _payload() -> LocalizationProviderInput:
    shots = [
        {
            "shot_anchor_id": f"shot-{index}",
            "character_ids": ["character-1"],
            "scene_ids": ["scene-1"],
            "prop_ids": ["prop-1"],
            "dialogue": [{"utterance_id": f"line-{index}", "delivery": "ON_SCREEN"}],
        }
        for index in range(31)
    ]
    view = {
        "characters": [{"source_character_id": "character-1", "name": "甲"}],
        "scenes": [{"source_scene_id": "scene-1", "name": "房间"}],
        "props": [{"source_prop_id": "prop-1", "name": "花"}],
        "dialogue": [
            {
                "utterance_id": f"line-{index}",
                "utterance_number": index + 1,
                "text": f"台词 {index}",
                "language": "zh-CN",
                "speaker_character_id": "character-1",
            }
            for index in range(31)
        ],
        "shots": shots,
    }
    return LocalizationProviderInput(
        target_language="en-US",
        target_region="US",
        scene_strategy="LOCALIZE",
        visual_style="写实电影感",
        source_view=view,
        expected_character_ids=("character-1",),
        expected_scene_ids=("scene-1",),
        expected_prop_ids=("prop-1",),
        expected_dialogue_ids=tuple(f"line-{index}" for index in range(31)),
        expected_shot_ids=tuple(f"shot-{index}" for index in range(31)),
    )


def test_localization_batches_bound_remote_shot_count_and_preserve_coverage() -> None:
    batches = _batched_payloads(_payload())

    assert [len(batch.expected_shot_ids) for batch in batches] == [8, 8, 8, 7]
    assert {item for batch in batches for item in batch.expected_shot_ids} == {
        f"shot-{index}" for index in range(31)
    }
    assert {item for batch in batches for item in batch.expected_dialogue_ids} == {
        f"line-{index}" for index in range(31)
    }


def test_localization_batch_semantics_merge_to_exact_full_contract() -> None:
    payload = _payload()
    semantics = []
    for batch in _batched_payloads(payload):
        semantics.append(LocalizedStoryboardSemantic.model_validate({
            "characters": [{"source_character_id": item, "localized_name": "Alex", "identity_description_zh": "本土化后的核心人物身份", "appearance_description_zh": "稳定清晰的人物外形设定"} for item in batch.expected_character_ids],
            "scenes": [{"source_scene_id": item, "localized_name": "Home", "setting_description_zh": "符合目标地区的住宅空间", "visual_description_zh": "稳定清晰的室内视觉环境"} for item in batch.expected_scene_ids],
            "props": [{"source_prop_id": item, "localized_name": "Flowers", "function_description_zh": "推动冲突发展的关键道具", "visual_description_zh": "稳定清晰的花束视觉外观"} for item in batch.expected_prop_ids],
            "dialogue": [{"utterance_id": item, "target_dialogue": "Localized dialogue", "target_dialogue_zh": "这是目标对白的中文翻译"} for item in batch.expected_dialogue_ids],
            "shots": [{"shot_anchor_id": item, "localized_visual_description_zh": "这是本土化后的镜头画面描述", "camera_description_zh": "这是供审核理解的镜头语言说明"} for item in batch.expected_shot_ids],
        }))

    merged = _merge_semantics(payload, semantics)

    assert len(merged.characters) == 1
    assert len(merged.dialogue) == 31
    assert len(merged.shots) == 31


def test_short_chinese_dialogue_translation_is_valid_but_non_chinese_is_not() -> None:
    _assert_chinese("目标对白中文翻译", "行", minimum_cjk=1)
    with pytest.raises(AppError):
        _assert_chinese("目标对白中文翻译", "OK", minimum_cjk=1)
