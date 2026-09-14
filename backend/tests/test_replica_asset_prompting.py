import pytest
from pydantic import ValidationError

from app.replica_pipeline.asset_prompting import (
    FLUX_ASSET_PROMPT_CONTRACT,
    FluxAssetPromptBatch,
    _compose_execution_prompt,
    _provider_prompt,
)
from app.target_assets.schemas import TargetAssetType


def test_character_execution_prompt_is_flux_specific_and_folds_avoidance_into_positive_prompt():
    prompt = _compose_execution_prompt(
        asset_type="CHARACTER",
        display_name="Maya Carter",
        visual_facts_en="A woman in her early thirties with an oval face, shoulder-length dark brown hair, a slim build, a navy wool coat and cream knit top.",
        avoid_en="multiple people, cropped feet, duplicate face, dramatic action pose",
        visual_style="写实电影感",
        target_region="US",
    )

    assert "Exactly one person" in prompt
    assert "Full body from head to shoes fully visible" in prompt
    assert "Plain seamless light-gray studio background" in prompt
    assert "Target region context: US" in prompt
    assert "multiple people, cropped feet" in prompt
    assert "No text" in prompt


def test_scene_and_prop_execution_prompts_force_asset_reference_composition():
    scene = _compose_execution_prompt(
        asset_type="SCENE",
        display_name="Apartment kitchen",
        visual_facts_en="A compact contemporary apartment kitchen with pale oak cabinets, matte stone counters, brushed steel fixtures and a fixed island.",
        avoid_en="people, characters, readable text, impossible architecture",
        visual_style="写实电影感",
        target_region="US",
    )
    prop = _compose_execution_prompt(
        asset_type="PROP",
        display_name="Leather briefcase",
        visual_facts_en="A medium-sized dark brown structured leather briefcase with brass hardware, a top handle and subtle edge wear.",
        avoid_en="hands, people, extra objects, duplicate bag",
        visual_style="写实电影感",
        target_region="US",
    )

    assert "Empty environment production reference image" in scene
    assert "No people, no characters" in scene
    assert "Wide establishing view" in scene
    assert "Exactly one isolated object" in prop
    assert "No hands and no people" in prop


def test_provider_prompt_separates_chinese_review_design_from_flux_execution_facts():
    prompt = _provider_prompt(
        specs=[
            {
                "asset_type": TargetAssetType.CHARACTER,
                "entity_id": "target:character:001",
                "display_name": "Maya Carter",
                "review_zh": "三十岁左右的美国女性律师，深棕色中长发，职业感克制，基础服装为深色羊毛外套。",
            }
        ],
        target_region="US",
        visual_style="写实电影感",
    )

    assert FLUX_ASSET_PROMPT_CONTRACT in prompt
    assert "visual_design_zh" in prompt
    assert "visual_facts_en" in prompt
    assert "不是视频提示词" in prompt
    assert "target:character:001" in prompt
    assert "不能漏项、重复、改 ID" in prompt


def test_structured_prompt_schema_rejects_uncontracted_fields():
    with pytest.raises(ValidationError):
        FluxAssetPromptBatch.model_validate(
            {
                "items": [
                    {
                        "target_entity_id": "target:character:001",
                        "visual_design_zh": "稳定人物视觉设计说明，包含脸型发型体态和基础服装。",
                        "visual_facts_en": "A stable full-body character identity with clearly defined face, hair, body type and base wardrobe for repeated reference generation.",
                        "avoid_en": "multiple people, cropped body, duplicate face, text and watermark",
                        "invented_story_fact": "not allowed",
                    }
                ]
            }
        )
