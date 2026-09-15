import pytest
from PIL import Image

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
    assert skill.version == "1.2.0"
    assert [step.id for step in skill.steps] == [
        "extract_entities",
        "compile_model_prompt",
        "render_reference_images",
    ]

    binding, prompt_skill = selected_image_model_prompt_skill()
    assert binding.model_id == "Z-Image-Turbo"
    assert binding.prompt_contract == "z-image-turbo-replica-assets-v2"
    assert prompt_skill.id == "z-image-turbo-asset-prompting"
    assert prompt_skill.version == "1.1.0"


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


def test_character_prompt_contract_keeps_layout_out_of_model_authored_identity_prompt() -> None:
    context = _character_context()
    valid = AssetImagePromptAuthoringResult.model_validate({
        "assets": [{
            "target_entity_id": "target-char-1",
            "image_prompt": (
                "Single young Chinese man in his twenties, short black hair, brown eyes, fair skin, average build, "
                "light gray hoodie, blue jeans, neutral expression, stable realistic character identity, clean studio styling. "
                "Do not add another person, romantic partner, phone, text or watermark."
            ),
            "negative_prompt": "extra people, couple, phone, text, watermark",
            "review_prompt_zh": "稳定单人物视觉身份，版式由运行时生成。",
        }],
    })
    authored = validate_authored_asset_batch([context], valid)
    assert "short black hair" in authored["target-char-1"].image_prompt

    invalid = AssetImagePromptAuthoringResult.model_validate({
        "assets": [{
            "target_entity_id": "target-char-1",
            "image_prompt": (
                "A production reference sheet with front full-body view, side full-body view, "
                "back full-body view and face close-up of Jake."
            ),
            "negative_prompt": "extra people, text, watermark",
            "review_prompt_zh": "错误地把多面板排版交给模型。",
        }],
    })
    with pytest.raises(AppError) as exc_info:
        validate_authored_asset_batch([context], invalid)
    assert exc_info.value.code == "ASSET_IMAGE_CHARACTER_PROMPT_SCOPE_INVALID"


def test_z_image_runtime_matches_verified_local_comfyui_workflow() -> None:
    runtime = ComfyUIZImageTurboRuntime()
    payload = runtime._workflow(
        "Empty apartment kitchen, pale oak cabinets, matte stone counters, clean architectural reference.",
        "people, text",
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


def test_character_runtime_renders_three_single_view_branches_with_one_identity_seed() -> None:
    runtime = ComfyUIZImageTurboRuntime()
    payload = runtime._character_workflow(
        "Single young Chinese man, short black hair, light gray hoodie and blue jeans.",
        "extra people, text",
        prefix="test/character",
        seed=777,
    )
    graph = payload["prompt"]

    assert graph["4"] == {"class_type": "ModelSamplingAuraFlow", "inputs": {"shift": 3.0, "model": ["1", 0]}}
    assert graph["12"]["inputs"] == {"width": 384, "height": 768, "batch_size": 1}
    assert graph["22"]["inputs"] == {"width": 384, "height": 768, "batch_size": 1}
    assert graph["32"]["inputs"] == {"width": 384, "height": 768, "batch_size": 1}
    assert {graph[node]["inputs"]["seed"] for node in ("13", "23", "33")} == {777}
    assert "FRONT view" in graph["10"]["inputs"]["text"]
    assert "SIDE PROFILE view" in graph["20"]["inputs"]["text"]
    assert "BACK view" in graph["30"]["inputs"]["text"]
    for node in ("10", "20", "30"):
        assert "Do not create a collage" in graph[node]["inputs"]["text"]
        assert "Hard exclusions" in graph[node]["inputs"]["text"]
    assert graph["15"]["inputs"]["filename_prefix"].endswith("/front")
    assert graph["25"]["inputs"]["filename_prefix"].endswith("/side")
    assert graph["35"]["inputs"]["filename_prefix"].endswith("/back")


def test_character_sheet_composition_has_fixed_three_views_plus_front_derived_face() -> None:
    front = Image.new("RGB", (384, 768), "red")
    side = Image.new("RGB", (384, 768), "green")
    back = Image.new("RGB", (384, 768), "blue")

    sheet = ComfyUIZImageTurboRuntime._compose_character_sheet(front, side, back)

    assert sheet.size == (CHARACTER_WIDTH, CHARACTER_HEIGHT) == (1536, 768)
    assert sheet.getpixel((100, 700)) == (255, 0, 0)
    assert sheet.getpixel((500, 700)) == (0, 128, 0)
    assert sheet.getpixel((900, 700)) == (0, 0, 255)
    assert sheet.getpixel((1400, 400)) == (255, 0, 0)
