from types import SimpleNamespace

import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace, ArtifactValidity
from app.artifacts.models import ArtifactNode

from app.core.errors import AppError
from app.projects.enums import AudioPolicy, ProjectType, SceneStrategy
from app.projects.models import Project
from app.replica_pipeline import asset_images as asset_images_module
from app.replica_pipeline.asset_images import (
    CHARACTER_HEIGHT,
    CHARACTER_PANEL_HEIGHT,
    CHARACTER_PANEL_WIDTH,
    CHARACTER_WIDTH,
    QWEN_CHARACTER_EDIT_CFG,
    QWEN_CHARACTER_EDIT_CLIP,
    QWEN_CHARACTER_EDIT_STEPS,
    QWEN_CHARACTER_EDIT_UNET,
    QWEN_CHARACTER_EDIT_VAE,
    ComfyUIZImageTurboRuntime,
    GeneratedImage,
    _character_identity_reference_media,
    _entity_specs,
    _promote_asset_image_candidate,
    create_asset_images_task,
)
from app.replica_pipeline.asset_prompting import validate_authored_asset_batch
from app.replica_pipeline.models import ReplicaAssetImageCandidate, ReplicaAssetImageRevision
from app.replica_pipeline.schemas import ASSET_IMAGES_SCHEMA_VERSION, CandidateStatus
from app.replica_pipeline.image_model_skills import selected_character_edit_prompt_skill, selected_image_model_prompt_skill
from app.replica_pipeline.schemas import AssetImagePromptAuthoringResult, ReplicaLocalizedStoryboardContent
from app.skills.professional import get_professional_skill
from app.skills.models import ArtifactType


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
    assert skill.version == "1.4.0"
    assert [step.id for step in skill.steps] == [
        "extract_entities",
        "compile_model_prompt",
        "render_reference_images",
    ]

    binding, prompt_skill = selected_image_model_prompt_skill()
    assert binding.model_id == "Z-Image-Turbo"
    assert binding.prompt_contract == "replica-assets-zimage-clean-positive-v5"
    assert prompt_skill.id == "z-image-turbo-asset-prompting"
    assert prompt_skill.version == "1.5.0"

    edit_binding, edit_skill = selected_character_edit_prompt_skill()
    assert edit_binding.model_id == "Qwen-Image-Edit-2511"
    assert edit_binding.prompt_contract == "qwen-image-edit-2511-character-orientation-v1"
    assert edit_skill.id == "qwen-image-edit-character-asset-prompting"
    assert edit_skill.version == "1.0.0"


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
                "One young Chinese man in his twenties with an angular oval face, defined jaw, straight nose, brown almond-shaped eyes, "
                "thick level brows, fair warm skin, short neatly tapered black hair, lean medium-height frame and squared shoulders. "
                "He wears a light gray cotton hoodie with a relaxed silhouette and blue straight-leg denim jeans. "
                "Neutral attentive expression, empty hands, centered solitary subject, clean seamless studio styling, typography-free image."
            ),
            "negative_prompt": "extra people, couple, phone, text, watermark",
            "review_prompt_zh": "稳定单人物视觉身份，版式由运行时生成。",
        }],
    })
    authored = validate_authored_asset_batch([context], valid)
    assert "short neatly tapered black hair" in authored["target-char-1"].image_prompt

    mixed_positive_negative = AssetImagePromptAuthoringResult.model_validate({
        "assets": [{
            "target_entity_id": "target-char-1",
            "image_prompt": (
                "Single young Chinese man in his twenties, short black hair, brown eyes, fair skin, average build, "
                "light gray hoodie and blue jeans, neutral expression, stable realistic character identity. "
                "Do not create a reference sheet, contact sheet, multi-panel layout, front full-body view, "
                "side full-body view, back full-body view or face close-up."
            ),
            "negative_prompt": "extra people, couple, phone, text, watermark",
            "review_prompt_zh": "稳定单人物身份，并明确排除由模型自由排版多视图。",
        }],
    })
    with pytest.raises(AppError) as mixed_exc:
        validate_authored_asset_batch([context], mixed_positive_negative)
    assert mixed_exc.value.code == "ASSET_IMAGE_POSITIVE_NEGATIVE_MIXED"

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
    assert "Hard exclusions" not in graph["4"]["inputs"]["text"]
    assert "people, text" not in graph["4"]["inputs"]["text"]


def test_character_runtime_uses_zimage_front_master_and_qwen_reference_edit_identity_lock() -> None:
    runtime = ComfyUIZImageTurboRuntime()
    front_payload = runtime._character_front_workflow(
        "Single young Chinese man, short black hair, light gray hoodie and blue jeans.",
        "extra people, text",
        prefix="test/character",
        seed=777,
    )
    front = front_payload["prompt"]
    assert front["4"] == {"class_type": "ModelSamplingAuraFlow", "inputs": {"shift": 3.0, "model": ["1", 0]}}
    assert front["12"]["inputs"] == {"width": 512, "height": 1024, "batch_size": 1}
    assert front["13"]["inputs"]["seed"] == 777
    assert "body and face square to the camera" in front["10"]["inputs"]["text"]
    assert "canonical MASTER identity image" in front["10"]["inputs"]["text"]
    assert "Hard exclusions" not in front["10"]["inputs"]["text"]
    assert "extra people, text" not in front["10"]["inputs"]["text"]
    assert front["15"]["inputs"]["filename_prefix"].endswith("/front")

    edit_payload = runtime._character_edit_workflow(
        "refs/front-master.png",
        "extra people, text",
        prefix="test/character",
        seed=888,
    )
    edit = edit_payload["prompt"]
    assert edit["101"]["inputs"]["unet_name"] == QWEN_CHARACTER_EDIT_UNET
    assert edit["102"]["inputs"] == {"clip_name": QWEN_CHARACTER_EDIT_CLIP, "type": "qwen_image", "device": "default"}
    assert edit["103"]["inputs"]["vae_name"] == QWEN_CHARACTER_EDIT_VAE
    assert edit["106"] == {"class_type": "LoadImage", "inputs": {"image": "refs/front-master.png"}}
    assert edit["108"] == {"class_type": "VAEEncode", "inputs": {"pixels": ["107", 0], "vae": ["103", 0]}}
    assert edit["120"]["inputs"]["image1"] == ["107", 0]
    assert edit["130"]["inputs"]["image1"] == ["107", 0]
    assert edit["124"]["inputs"]["steps"] == QWEN_CHARACTER_EDIT_STEPS
    assert edit["124"]["inputs"]["cfg"] == QWEN_CHARACTER_EDIT_CFG
    assert edit["124"]["inputs"]["seed"] == 888
    assert edit["134"]["inputs"]["seed"] == 889
    assert edit["124"]["inputs"]["latent_image"] == ["108", 0]
    assert edit["134"]["inputs"]["latent_image"] == ["108", 0]
    side_prompt = edit["120"]["inputs"]["prompt"]
    back_prompt = edit["130"]["inputs"]["prompt"]
    assert "authoritative canonical identity and wardrobe reference" in side_prompt
    assert "90-degree left-facing" in side_prompt
    assert "Never" not in side_prompt
    assert "Do not substitute trousers, shorts, skirts or dresses" in side_prompt
    assert "Do not remove footwear" in side_prompt
    assert "exact rear full-body view" in back_prompt
    assert "face must not be visible" in back_prompt
    assert edit["126"]["inputs"]["filename_prefix"].endswith("/side")
    assert edit["136"]["inputs"]["filename_prefix"].endswith("/back")


def test_character_runtime_strips_legacy_layout_language_before_z_image_execution() -> None:
    runtime = ComfyUIZImageTurboRuntime()
    legacy_prompt = (
        "Senior East Asian woman in her late 60s, short gray hair, gray striped knit sweater. "
        "Do not include other people, do not create multi-panel, turnaround or reference sheet layouts, "
        "do not add text or watermarks."
    )
    legacy_negative = "other people, multi-panel layouts, reference sheets, turnaround, text, watermarks"

    payload = runtime._character_front_workflow(legacy_prompt, legacy_negative, prefix="test/senior", seed=123)
    text = payload["prompt"]["10"]["inputs"]["text"].lower()
    assert "senior east asian woman" in text
    assert "gray striped knit sweater" in text
    assert "other people" not in text
    assert "watermarks" not in text
    assert "multi-panel" not in text
    assert "reference sheet" not in text
    assert "turnaround" not in text

    qwen_text = runtime._qwen_character_edit_prompt(legacy_negative, "side").lower()
    assert "other people" in qwen_text
    assert "text" in qwen_text
    assert "watermarks" in qwen_text
    assert "multi-panel" not in qwen_text
    assert "reference sheet" not in qwen_text
    assert "turnaround" not in qwen_text


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


def test_character_board_persists_dedicated_h3_front_and_face_identity_media() -> None:
    root = asset_images_module.get_settings().artifact_root
    relpath = "target_asset_images/project-1/task-1/character.png"
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    board = Image.new("RGB", (CHARACTER_WIDTH, CHARACTER_HEIGHT), "white")
    board.paste(Image.new("RGB", (CHARACTER_PANEL_WIDTH, CHARACTER_PANEL_HEIGHT), "red"), (0, 0))
    board.paste(Image.new("RGB", (CHARACTER_PANEL_WIDTH, CHARACTER_PANEL_HEIGHT), "yellow"), (3 * CHARACTER_PANEL_WIDTH, 0))
    board.save(path, format="PNG")
    generated = GeneratedImage(
        storage_relpath=relpath,
        sha256=asset_images_module._file_sha(path),
        width=CHARACTER_WIDTH,
        height=CHARACTER_HEIGHT,
        mime_type="image/png",
        remote_url="",
        remote_job_id="remote-1",
    )

    media = _character_identity_reference_media(
        project_id="project-1",
        asset_id="asset:character-1",
        generated=generated,
        provider_job_id="provider-job-1",
    )

    assert [item.role.value for item in media] == ["FULL_BODY", "FACE"]
    assert all(item.provider_job_id == "provider-job-1" for item in media)
    assert all(item.storage_relpath and (root / item.storage_relpath).is_file() for item in media)
    with Image.open(root / media[0].storage_relpath) as front:
        assert front.size == (CHARACTER_PANEL_WIDTH, CHARACTER_PANEL_HEIGHT)
        assert front.getpixel((100, 700)) == (255, 0, 0)
    with Image.open(root / media[1].storage_relpath) as face:
        assert face.size == (CHARACTER_PANEL_WIDTH, CHARACTER_PANEL_HEIGHT)
        assert face.getpixel((100, 400)) == (255, 255, 0)


def test_explicit_asset_regeneration_gets_a_new_business_fingerprint(monkeypatch) -> None:
    captured = []
    project = SimpleNamespace(project_type=ProjectType.REPLICA, visual_style="写实电影感")
    storyboard = SimpleNamespace(id="storyboard-1", input_fingerprint="storyboard-fingerprint")
    binding = SimpleNamespace(model_id="Z-Image-Turbo", prompt_contract="z-image-v1")
    prompt_skill = SimpleNamespace(id="z-image-prompting", version="1.0.0")
    prompt_provider = SimpleNamespace(profile=lambda: {"provider": "test"})

    monkeypatch.setattr(asset_images_module, "get_project", lambda *_: project)
    monkeypatch.setattr(asset_images_module, "_load_storyboard", lambda *_: (storyboard, SimpleNamespace()))
    monkeypatch.setattr(asset_images_module.ComfyUIZImageTurboRuntime, "assert_ready", lambda *_: None)
    monkeypatch.setattr(asset_images_module.ComfyUIZImageTurboRuntime, "profile", lambda *_: {"runtime": "test"})
    monkeypatch.setattr(asset_images_module, "selected_image_model_prompt_skill", lambda: (binding, prompt_skill))
    monkeypatch.setattr(asset_images_module, "asset_prompt_author_provider", lambda: prompt_provider)
    monkeypatch.setattr(asset_images_module, "get_professional_skill", lambda *_: SimpleNamespace(version="1.1.0"))

    def capture_task(*_, payload, idempotency_key, **__):
        captured.append((payload, idempotency_key))
        return SimpleNamespace(id=f"task-{len(captured)}")

    monkeypatch.setattr(asset_images_module, "create_task_from_command", capture_task)

    create_asset_images_task(SimpleNamespace(), project_id="project-1", idempotency_key="regen-1", regenerate=True)
    create_asset_images_task(SimpleNamespace(), project_id="project-1", idempotency_key="regen-2", regenerate=True)

    assert captured[0][0].input_fingerprint != captured[1][0].input_fingerprint
    assert captured[0][0].task_name == "重新提取并生成资产图"
    assert captured[0][1] == "regen-1"


def test_generated_asset_candidate_can_be_auto_published_without_user_confirmation(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as db:
        project = Project(
            name="Asset auto publish",
            project_type=ProjectType.REPLICA,
            source_language="zh-CN",
            target_language="en-US",
            target_region="US",
            scene_strategy=SceneStrategy.LOCALIZE,
            audio_policy=AudioPolicy.REGENERATE_AUDIO,
            visual_style="写实电影感",
            root_skill_id="replica",
            root_skill_version="1.0.0",
        )
        db.add(project)
        db.flush()
        project_id = project.id
        storyboard = ArtifactNode(
            project_id=project_id,
            artifact_type=ArtifactType.TARGET_STORYBOARD.value,
            namespace=ArtifactNamespace.PRODUCTION,
            label="本土化分镜表",
            revision=1,
            input_fingerprint="a" * 64,
            skill_id="storyboard-localization",
            skill_version="1.0.0",
            validity=ArtifactValidity.CURRENT,
            is_current=True,
            metadata_json={},
        )
        db.add(storyboard)
        db.flush()
        candidate = ReplicaAssetImageCandidate(
            project_id=project_id,
            target_storyboard_artifact_id=storyboard.id,
            generated_by_task_id=None,
            generation_sequence=1,
            input_fingerprint="c" * 64,
            schema_version=ASSET_IMAGES_SCHEMA_VERSION,
            content_json={
                "schema_version": ASSET_IMAGES_SCHEMA_VERSION,
                "title": "目标资产图",
                "target_storyboard_artifact_id": storyboard.id,
                "target_language": "en-US",
                "target_region": "US",
                "visual_style": "写实电影感",
                "assets": [{
                    "target_asset_id": "asset:scene-1",
                    "target_asset_revision": 1,
                    "asset_type": "SCENE",
                    "target_entity_id": "scene-1",
                    "display_name": "客厅",
                    "review_description_zh": "现代客厅，无人物。",
                    "image_prompt": "modern living room",
                    "negative_prompt": "people, text",
                    "prompt_review_zh": "保持无人场景。",
                    "image_model_id": "Z-Image-Turbo",
                    "prompt_skill_id": "z-image-turbo-asset-prompting",
                    "prompt_skill_version": "1.5.0",
                    "prompt_contract": "replica-assets-zimage-clean-positive-v5",
                    "reference_media": [{
                        "reference_id": "ref:scene-1",
                        "role": "LAYOUT",
                        "uri": "/media/scene-1.png",
                        "mime_type": "image/png",
                        "sha256": "b" * 64,
                        "width": 1280,
                        "height": 736,
                        "provider_job_id": "provider-job-1",
                        "storage_relpath": "target_asset_images/test/scene-1.png",
                    }],
                }],
            },
            provenance_json={},
            review_status=CandidateStatus.NEEDS_REVIEW.value,
        )
        db.add(candidate)
        db.flush()

        artifact, _, provenance = _promote_asset_image_candidate(
            db,
            project_id=project_id,
            candidate=candidate,
            reviewed_by="SYSTEM_AUTO_PUBLISH",
            review_reason="自动采用",
        )
        db.commit()
        db.refresh(candidate)
        db.refresh(artifact)

        revision = db.scalar(select(ReplicaAssetImageRevision).where(ReplicaAssetImageRevision.artifact_id == artifact.id))
        assert artifact.artifact_type == ArtifactType.TARGET_ASSETS.value
        assert artifact.validity == ArtifactValidity.CURRENT
        assert artifact.is_current is True
        assert candidate.review_status == CandidateStatus.ACCEPTED.value
        assert candidate.reviewed_at is not None
        assert provenance["reviewed_by"] == "SYSTEM_AUTO_PUBLISH"
        assert revision is not None
        assert revision.candidate_id == candidate.id
        assert revision.provenance_json["reviewed_by"] == "SYSTEM_AUTO_PUBLISH"
