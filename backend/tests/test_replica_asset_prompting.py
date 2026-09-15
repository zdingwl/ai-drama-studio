import pytest

from app.core.errors import AppError
from app.replica_pipeline.asset_images import (
    CHARACTER_HEIGHT,
    CHARACTER_WIDTH,
    ComfyUIZImageTurboRuntime,
    _entity_specs,
)
from app.replica_pipeline.asset_prompting import validate_authored_asset_batch
from app.replica_pipeline.image_model_skills import selected_image_model_prompt_skill
from app.replica_pipeline.schemas import AssetImagePromptAuthoringResult, ReplicaLocalizedStoryboardContent
from app.skills.professional import get_professional_skill


def _storyboard() -> ReplicaLocalizedStoryboardContent:
    return ReplicaLocalizedStoryboardContent.model_validate({
        "source_snapshot_artifact_id": "snapshot-1",
        "target_language": "en-US",
        "target_region": "US",
        "characters": [{
            "source_character_id": "source-char-1",
            "target_character_id": "target-char-1",
            "source_name": "周杰",
            "display_name": "Jake Zhou",
            "identity_description_zh": "20多岁华裔男性，Rachel 的丈夫，性格谨慎。",
            "appearance_description_zh": "短黑发、棕色眼睛、浅肤色，穿浅灰色连帽卫衣和蓝色牛仔裤。",
        }],
        "scenes": [],
        "props": [],
        "dialogue": [],
        "shots": [{
            "storyboard_shot_id": "localized:ep1:shot1",
            "episode_id": "ep1",
            "episode_order": 1,
            "source_shot_anchor_id": "shot1",
            "shot_number": 1,
            "start_us": 0,
            "end_us": 2_000_000,
            "duration_us": 2_000_000,
            "output_ratio": "16:9",
            "camera_language": {
                "shot_size": "中景",
                "composition": "人物居中",
                "angle_or_type": "平视",
                "movement": "固定",
                "focal_length_dof": "自然景深",
            },
            "source_visual_description": "A man looks at his phone.",
            "localized_visual_description_zh": "Jake 独自在客厅里低头看手机，穿浅灰色连帽卫衣和蓝色牛仔裤。",
            "camera_description_zh": "固定中景平视镜头。",
            "target_character_ids": ["target-char-1"],
            "target_scene_ids": [],
            "target_prop_ids": [],
            "dialogue": [],
            "sound_effects": [],
            "ambience": [],
        }],
    })


def _character_context() -> dict:
    return _entity_specs(_storyboard(), "写实电影感")[0]["prompt_context"]


def test_asset_orchestration_skill_requires_model_prompt_compilation() -> None:
    skill = get_professional_skill("asset-image-generation")
    assert skill.version == "1.1.0"
    assert [step.id for step in skill.steps] == [
        "extract_entities",
        "compile_model_prompt",
        "render_reference_images",
    ]

    binding, prompt_skill = selected_image_model_prompt_skill()
    assert binding.model_id == "Z-Image-Turbo"
    assert binding.prompt_contract == "z-image-turbo-replica-assets-v1"
    assert prompt_skill.id == "z-image-turbo-asset-prompting"
    assert prompt_skill.version == "1.0.0"


def test_character_asset_extraction_preserves_storyboard_evidence_without_direct_prompt() -> None:
    spec = _entity_specs(_storyboard(), "写实电影感")[0]

    assert spec["asset_type"].value == "CHARACTER"
    assert spec["width"] == CHARACTER_WIDTH
    assert spec["height"] == CHARACTER_HEIGHT
    assert "prompt" not in spec
    assert spec["prompt_context"]["target_entity_id"] == "target-char-1"
    assert "Rachel 的丈夫" in spec["prompt_context"]["identity_description_zh"]
    assert spec["prompt_context"]["storyboard_evidence"] == [{
        "storyboard_shot_id": "localized:ep1:shot1",
        "shot_number": 1,
        "localized_visual_description_zh": "Jake 独自在客厅里低头看手机，穿浅灰色连帽卫衣和蓝色牛仔裤。",
    }]


def test_character_prompt_contract_requires_three_views_plus_face_closeup() -> None:
    context = _character_context()
    valid = AssetImagePromptAuthoringResult.model_validate({
        "assets": [{
            "target_entity_id": "target-char-1",
            "image_prompt": (
                "A clean production reference sheet of the same character. "
                "Show exactly a front full-body view, side full-body view, back full-body view, "
                "and a large face close-up on a white background. Do not add another person."
            ),
            "negative_prompt": "extra people, couple, text, watermark",
            "review_prompt_zh": "同一人物的正面全身、侧面全身、背面全身和面部特写参考板。",
        }],
    })
    authored = validate_authored_asset_batch([context], valid)
    assert authored["target-char-1"].image_prompt.startswith("A clean production reference sheet")

    invalid = AssetImagePromptAuthoringResult.model_validate({
        "assets": [{
            "target_entity_id": "target-char-1",
            "image_prompt": "A single half-body portrait of Jake looking at a phone.",
            "negative_prompt": "extra people",
            "review_prompt_zh": "单张人物半身肖像。",
        }],
    })
    with pytest.raises(AppError) as exc_info:
        validate_authored_asset_batch([context], invalid)
    assert exc_info.value.code == "ASSET_IMAGE_CHARACTER_LAYOUT_INVALID"


def test_z_image_runtime_matches_verified_local_comfyui_workflow() -> None:
    runtime = ComfyUIZImageTurboRuntime()
    payload = runtime._workflow(
        "front full-body view, side full-body view, back full-body view, face close-up, same character",
        "extra people, text",
        prefix="test/z-image",
        seed=123,
        width=1280,
        height=736,
    )
    graph = payload["prompt"]

    assert graph["1"] == {"class_type": "UNETLoader", "inputs": {"unet_name": "z_image_turbo_bf16.safetensors", "weight_dtype": "default"}}
    assert graph["2"]["inputs"] == {"clip_name": "qwen_3_4b.safetensors", "type": "lumina2", "device": "default"}
    assert graph["3"]["inputs"]["vae_name"] == "ae.safetensors"
    assert graph["6"]["inputs"] == {"width": 1280, "height": 736, "batch_size": 1}
    assert graph["7"] == {"class_type": "ModelSamplingAuraFlow", "inputs": {"shift": 3.0, "model": ["1", 0]}}
    assert graph["8"]["inputs"]["steps"] == 8
    assert graph["8"]["inputs"]["sampler_name"] == "res_multistep"
    assert graph["8"]["inputs"]["scheduler"] == "simple"
    assert "Hard exclusions" in graph["4"]["inputs"]["text"]
