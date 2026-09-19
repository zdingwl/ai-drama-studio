import hashlib
import base64
import json
import math
import secrets
import time
from io import BytesIO
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from arkruntime import Ark
from arkruntime._exceptions import ArkBadRequestError
from PIL import Image, ImageOps
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactEdge, ArtifactNode
from app.artifacts.service import _invalidate_project_plan, _mark_stale_with_downstream
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.time import utc_now
from app.projects.enums import ProjectType
from app.projects.service import get_project
from app.replica_pipeline.asset_prompting import (
    CHARACTER_RUNTIME_LAYOUT_TOKENS,
    MAX_ASSET_PROMPT_BATCH_SIZE,
    AssetPromptAuthorInput,
    AssetPromptAuthorResult,
    asset_prompt_author_provider,
    validate_authored_asset_batch,
)
from app.replica_pipeline.character_visual_design import (
    MAX_CHARACTER_VISUAL_BATCH_SIZE,
    CharacterVisualDesignInput,
    CharacterVisualDesignResult,
    character_visual_design_provider,
    character_visual_design_skill,
    validate_character_visual_design_batch,
)
from app.replica_pipeline.character_consistency import validate_character_asset_identity, validate_character_reference_set
from app.replica_pipeline.image_model_skills import selected_character_edit_prompt_skill, selected_image_model_prompt_skill
from app.replica_pipeline.models import ReplicaAssetImageCandidate, ReplicaAssetImageRevision, ReplicaAssetWorkspace, ReplicaLocalizedStoryboardRevision
from app.replica_pipeline.schemas import (
    ASSET_IMAGES_SCHEMA_VERSION,
    AssetImageCandidateRead,
    AssetImageEntity,
    AssetImageProvenance,
    AssetImagePromptAuthoredEntity,
    AssetWorkspaceContent,
    AssetWorkspaceEntity,
    AssetWorkspaceGeneration,
    AssetWorkspaceRead,
    AssetImagesRead,
    CandidateStatus,
    CharacterVisualDesignPacket,
    PipelineReviewCommand,
    ReplicaAssetImagesContent,
    ReplicaLocalizedStoryboardContent,
    ResultStatus,
)
from app.skills.models import ArtifactType, Capability
from app.skills.professional import get_professional_skill
from app.target_assets.schemas import ReferenceMediaRole, TargetAssetType, TargetReferenceMedia
from app.target_bible.models import ReplicaTargetRevision
from app.target_bible.schemas import ReplicaTargetBibleContent, TargetBibleArtifactKind
from app.workflow.models import ProviderJob, ProviderJobStatus, Task, TaskStatus
from app.workflow.provider_service import ProviderDispatchResult, dispatch_provider_call, provider_payload_fingerprint
from app.workflow.schemas import TaskCommandCreate, TaskWorkerRead
from app.workflow.task_service import TaskCancelled, create_task_from_command, mark_task_failed, mark_task_succeeded
from app.workflow.worker import TaskExecutionContext


TASK_TYPE = "replica.asset-images"
ASSET_PROMPT_TASK_TYPE = "replica.asset-prompts"
SKILL_ID = "asset-image-generation"
DEFAULT_UNET = "z_image_turbo_bf16.safetensors"
DEFAULT_CLIP = "qwen_3_4b.safetensors"
DEFAULT_VAE = "ae.safetensors"
QWEN_CHARACTER_EDIT_UNET = "qwen_image_edit_2511_fp8mixed.safetensors"
QWEN_CHARACTER_EDIT_CLIP = "qwen_2.5_vl_7b_fp8_scaled.safetensors"
QWEN_CHARACTER_EDIT_VAE = "qwen_image_vae.safetensors"
QWEN_CHARACTER_EDIT_STEPS = 20
QWEN_CHARACTER_EDIT_CFG = 4.0
QWEN_CHARACTER_EDIT_SHIFT = 3.1
CHARACTER_PANEL_WIDTH = 384
CHARACTER_PANEL_HEIGHT = 768
CHARACTER_RENDER_WIDTH = 512
CHARACTER_RENDER_HEIGHT = 1024
CHARACTER_WIDTH = CHARACTER_PANEL_WIDTH * 4
CHARACTER_HEIGHT = CHARACTER_PANEL_HEIGHT
SCENE_WIDTH = 1280
SCENE_HEIGHT = 736
PROP_WIDTH = 1024
PROP_HEIGHT = 1024


def _sha(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _asset_id(project_id: str, entity_id: str) -> str:
    return f"asset:{hashlib.sha256(f'{project_id}|{entity_id}'.encode()).hexdigest()[:24]}"


@dataclass(frozen=True)
class GeneratedImage:
    storage_relpath: str
    sha256: str
    width: int
    height: int
    mime_type: str
    remote_url: str
    remote_job_id: str | None


def _character_identity_reference_media(
    *,
    project_id: str,
    asset_id: str,
    generated: GeneratedImage,
    provider_job_id: str,
) -> list[TargetReferenceMedia]:
    """Persist H3-ready identity crops from the deterministic four-panel character board.

    The board remains the human review surface, while Ref2VA receives dedicated FACE and
    front FULL_BODY images.  Feeding the entire four-panel board to H3 encourages the model
    to treat four depictions as separate identities, especially in close-ups.
    """
    root = get_settings().artifact_root.resolve()
    source = (root / generated.storage_relpath).resolve()
    if root not in source.parents or not source.is_file():
        raise AppError("ASSET_IMAGE_CHARACTER_BOARD_MISSING", "人物资产参考板不存在，无法派生 H3 身份参考图", status_code=500)
    if _file_sha(source) != generated.sha256:
        raise AppError("ASSET_IMAGE_CHARACTER_BOARD_HASH_MISMATCH", "人物资产参考板 hash 已变化，禁止派生 H3 身份参考图", status_code=409)

    with Image.open(source) as board:
        board = board.convert("RGB")
        if board.size != (CHARACTER_WIDTH, CHARACTER_HEIGHT):
            raise AppError(
                "ASSET_IMAGE_CHARACTER_BOARD_SIZE_INVALID",
                "人物资产参考板尺寸不符合固定四栏合同",
                status_code=500,
                details={"actual": list(board.size), "expected": [CHARACTER_WIDTH, CHARACTER_HEIGHT]},
            )
        crops = (
            (ReferenceMediaRole.FULL_BODY_FRONT, "front", (0, 0, CHARACTER_PANEL_WIDTH, CHARACTER_PANEL_HEIGHT)),
            (ReferenceMediaRole.FULL_BODY_SIDE, "side", (CHARACTER_PANEL_WIDTH, 0, 2 * CHARACTER_PANEL_WIDTH, CHARACTER_PANEL_HEIGHT)),
            (ReferenceMediaRole.FULL_BODY_BACK, "back", (2 * CHARACTER_PANEL_WIDTH, 0, 3 * CHARACTER_PANEL_WIDTH, CHARACTER_PANEL_HEIGHT)),
            (
                ReferenceMediaRole.FACE,
                "face",
                (3 * CHARACTER_PANEL_WIDTH, 0, 4 * CHARACTER_PANEL_WIDTH, CHARACTER_PANEL_HEIGHT),
            ),
        )
        result: list[TargetReferenceMedia] = []
        source_rel = PurePosixPath(generated.storage_relpath)
        for role, suffix, box in crops:
            relpath = str(source_rel.with_name(f"{source_rel.stem}.{suffix}.png"))
            output = (root / relpath).resolve()
            if root not in output.parents:
                raise AppError("ASSET_IMAGE_STORAGE_INVALID", "人物身份参考图存储路径越界", status_code=500)
            output.parent.mkdir(parents=True, exist_ok=True)
            board.crop(box).save(output, format="PNG")
            digest = _file_sha(output)
            reference_id = f"ref:{hashlib.sha256(f'{asset_id}|{role.value}|{digest}'.encode()).hexdigest()[:24]}"
            result.append(TargetReferenceMedia(
                reference_id=reference_id,
                role=role,
                uri=f"/api/v3/projects/{project_id}/asset-images/media/{reference_id}",
                mime_type="image/png",
                sha256=digest,
                width=CHARACTER_PANEL_WIDTH,
                height=CHARACTER_PANEL_HEIGHT,
                provider_job_id=provider_job_id,
                storage_relpath=relpath,
            ))
    return result


class ComfyUIZImageTurboRuntime:
    provider_name = "local-comfyui"
    _base_required_nodes = {
        "UNETLoader",
        "CLIPLoader",
        "VAELoader",
        "CLIPTextEncode",
        "ConditioningZeroOut",
        "EmptySD3LatentImage",
        "ModelSamplingAuraFlow",
        "KSampler",
        "VAEDecode",
        "SaveImage",
    }
    _character_edit_required_nodes = {
        "LoadImage",
        "FluxKontextImageScale",
        "TextEncodeQwenImageEditPlus",
        "FluxKontextMultiReferenceLatentMethod",
        "CFGNorm",
        "VAEEncode",
    }

    def __init__(self):
        settings = get_settings()
        self.settings = settings
        self.base_url = settings.p16_h3_comfyui_base_url.rstrip("/")
        self.model_name = DEFAULT_UNET
        self.clip_name = DEFAULT_CLIP
        self.vae_name = DEFAULT_VAE
        self.character_edit_model_name = QWEN_CHARACTER_EDIT_UNET
        self.character_edit_clip_name = QWEN_CHARACTER_EDIT_CLIP
        self.character_edit_vae_name = QWEN_CHARACTER_EDIT_VAE
        self.timeout_seconds = 1800.0
        self.poll_interval = 1.0

    def profile(self) -> dict:
        character_edit_binding, character_edit_skill = selected_character_edit_prompt_skill()
        return {
            "provider": self.provider_name,
            "base_url": self.base_url,
            "model": self.model_name,
            "clip": self.clip_name,
            "vae": self.vae_name,
            "workflow": "replica-assets-hybrid-v4",
            "character_sheet": "zimage-front-master-qwen-edit-side-back-plus-front-face-crop-v4",
            "character_render_size": [CHARACTER_RENDER_WIDTH, CHARACTER_RENDER_HEIGHT],
            "character_front_model": self.model_name,
            "character_edit_model_id": character_edit_binding.model_id,
            "character_edit_model": self.character_edit_model_name,
            "character_edit_clip": self.character_edit_clip_name,
            "character_edit_vae": self.character_edit_vae_name,
            "character_edit_prompt_skill_id": character_edit_skill.id,
            "character_edit_prompt_skill_version": character_edit_skill.version,
            "character_edit_prompt_contract": character_edit_binding.prompt_contract,
            "character_edit_steps": QWEN_CHARACTER_EDIT_STEPS,
            "character_edit_cfg": QWEN_CHARACTER_EDIT_CFG,
            "character_edit_sampling_shift": QWEN_CHARACTER_EDIT_SHIFT,
            "character_edit_sampler": "euler",
            "character_edit_scheduler": "simple",
            "steps": 8,
            "sampler": "res_multistep",
            "scheduler": "simple",
            "model_sampling": "ModelSamplingAuraFlow:shift=3.0",
            "negative_conditioning": "zeroed-with-inline-hard-exclusions",
        }

    @property
    def character_pipeline_model_name(self) -> str:
        return f"{self.model_name}+{self.character_edit_model_name}"

    @property
    def pipeline_model_name(self) -> str:
        return f"{self.model_name}; character-edit={self.character_edit_model_name}"

    @staticmethod
    def _safe_preview(response: httpx.Response) -> str:
        try: text = " ".join(response.text.split())
        except Exception: return "<unreadable body>"
        return text[:400] if text else "<empty body>"

    def assert_ready(self, *, require_character_edit: bool = False) -> None:
        try:
            with httpx.Client(timeout=5.0, trust_env=False) as client:
                stats = client.get(f"{self.base_url}/system_stats")
                if stats.status_code != 200:
                    raise AppError("ASSET_IMAGE_RUNTIME_NOT_READY", f"ComfyUI /system_stats 返回 HTTP {stats.status_code}", status_code=503)
                info = client.get(f"{self.base_url}/object_info")
                if info.status_code != 200:
                    raise AppError("ASSET_IMAGE_RUNTIME_INCOMPATIBLE", "ComfyUI 未提供 /object_info", status_code=502)
                nodes = info.json()
                if not isinstance(nodes, dict):
                    raise AppError("ASSET_IMAGE_RUNTIME_INCOMPATIBLE", "ComfyUI /object_info 返回格式无效", status_code=502)
                required_nodes = set(self._base_required_nodes)
                if require_character_edit:
                    required_nodes.update(self._character_edit_required_nodes)
                missing_nodes = sorted(required_nodes - set(nodes))
                if missing_nodes:
                    raise AppError("ASSET_IMAGE_RUNTIME_INCOMPATIBLE", "ComfyUI 缺少 Z-Image Turbo 所需节点：" + "、".join(missing_nodes), status_code=502)

                def _options(node_name: str, field: str) -> list[str]:
                    required = ((nodes.get(node_name, {}).get("input") or {}).get("required") or {}).get(field) or []
                    return required[0] if isinstance(required, list) and required and isinstance(required[0], list) else []

                required_models = [
                    ("UNETLoader", "unet_name", self.model_name),
                    ("CLIPLoader", "clip_name", self.clip_name),
                    ("VAELoader", "vae_name", self.vae_name),
                ]
                if require_character_edit:
                    required_models.extend([
                        ("UNETLoader", "unet_name", self.character_edit_model_name),
                        ("CLIPLoader", "clip_name", self.character_edit_clip_name),
                        ("VAELoader", "vae_name", self.character_edit_vae_name),
                    ])
                missing_models = [
                    filename
                    for node_name, field, filename in required_models
                    if filename not in _options(node_name, field)
                ]
                if missing_models:
                    raise AppError("ASSET_IMAGE_MODEL_MISSING", "ComfyUI 缺少资产图模型文件：" + "、".join(missing_models), status_code=502)
        except AppError: raise
        except (httpx.HTTPError, OSError, ValueError) as exc:
            raise AppError("ASSET_IMAGE_RUNTIME_NOT_READY", f"无法连接本地 ComfyUI：{self.base_url}", status_code=503) from exc

    def _workflow(self, prompt: str, negative_prompt: str, *, prefix: str, seed: int, width: int, height: int) -> dict:
        execution_prompt = prompt.strip()
        graph = {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": self.model_name, "weight_dtype": "default"}},
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": self.clip_name, "type": "lumina2", "device": "default"}},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": self.vae_name}},
            "4": {"class_type": "CLIPTextEncode", "inputs": {"text": execution_prompt, "clip": ["2", 0]}},
            "5": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["4", 0]}},
            "6": {"class_type": "EmptySD3LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
            "7": {"class_type": "ModelSamplingAuraFlow", "inputs": {"shift": 3.0, "model": ["1", 0]}},
            "8": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": 8, "cfg": 1.0, "sampler_name": "res_multistep", "scheduler": "simple", "denoise": 1.0, "model": ["7", 0], "positive": ["4", 0], "negative": ["5", 0], "latent_image": ["6", 0]}},
            "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
            "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": prefix}},
        }
        return {"prompt": graph, "client_id": f"ai-drama-assets-{uuid4()}"}

    @staticmethod
    def _contains_character_layout_language(value: str) -> bool:
        lowered = value.lower()
        return any(token in lowered for token in CHARACTER_RUNTIME_LAYOUT_TOKENS)

    @classmethod
    def _character_identity_for_runtime(cls, identity_prompt: str) -> str:
        """Remove only Runtime-owned layout language from legacy character prompts.

        Prompt Skill v1.2 no longer emits these phrases, but existing/older authored
        prompts can contain negated phrases such as ``do not create a reference sheet``.
        Z-Image Turbo can still react to those words and produce miniature turnarounds,
        so the Runtime strips only those layout clauses while preserving visual identity.
        """
        chunks = [chunk.strip() for chunk in identity_prompt.replace("\n", " ").split(".") if chunk.strip()]
        kept: list[str] = []
        for chunk in chunks:
            lowered_chunk = chunk.lower()
            if "do not" in lowered_chunk or lowered_chunk.startswith("avoid ") or "hard exclusions" in lowered_chunk:
                continue
            if cls._contains_character_layout_language(chunk):
                comma_parts = [part.strip() for part in chunk.split(",") if part.strip()]
                clean_parts = [part for part in comma_parts if not cls._contains_character_layout_language(part)]
                if clean_parts:
                    kept.append(", ".join(clean_parts))
                continue
            kept.append(chunk)
        cleaned = ". ".join(kept).strip()
        if not cleaned:
            raise AppError(
                "ASSET_IMAGE_CHARACTER_IDENTITY_PROMPT_EMPTY",
                "人物 Prompt 去除 Runtime 版式词后没有剩余稳定视觉身份内容",
                status_code=502,
            )
        return cleaned

    @classmethod
    def _character_negative_for_runtime(cls, negative_prompt: str) -> str:
        parts = [part.strip() for part in negative_prompt.replace("\n", ",").split(",") if part.strip()]
        return ", ".join(part for part in parts if not cls._contains_character_layout_language(part))

    @classmethod
    def _character_front_prompt(cls, identity_prompt: str) -> str:
        identity = cls._character_identity_for_runtime(identity_prompt)
        return (
            "A full-length studio photograph of ONE person only. This image is the canonical MASTER identity image. "
            "The person stands alone in the center, body and face square to the camera, neutral standing pose, arms relaxed, head and both shoes fully visible. "
            "The image contains exactly one human figure total, one pose only, with no miniature repetitions or secondary figures anywhere in the frame. "
            "The subject should occupy most of the image height with empty space on both sides. "
            "Clean seamless very light neutral studio background, soft even lighting, no props, no environment, no text. "
            f"Stable appearance: {identity}"
        )

    @classmethod
    def _qwen_character_edit_prompt(cls, negative_prompt: str, view: str) -> str:
        orientation = {
            "side": (
                "Rotate only the person/camera orientation into a strict 90-degree left-facing full-body profile. "
                "The nose points left and the shoulders are perpendicular to the camera."
            ),
            "back": (
                "Rotate only the person/camera orientation into an exact rear full-body view. "
                "Show the back of the head and body; the face must not be visible."
            ),
        }[view]
        prompt = (
            "Image 1 is the authoritative canonical identity and wardrobe reference. It is immutable. Edit the image; do not redesign the person. "
            f"{orientation} Preserve exactly the same person identity, facial structure, skull shape, apparent age, hairstyle silhouette, hair length, hair color, skin tone, body proportions, "
            "and every wardrobe detail visible in Image 1. Preserve garment topology exactly: same upper garment, same sleeve length, same lower-garment type and length, "
            "same colors, same patterns, same fabric appearance, and the same footwear presence, type and color. Do not substitute trousers, shorts, skirts or dresses for one another. "
            "Do not remove footwear and do not change footwear type. Only orientation may change. Keep a neutral standing pose, exactly one person, head and both feet fully visible, "
            "clean seamless very light neutral studio background, soft even lighting, no added props, no text, no extra people."
        )
        runtime_negative = cls._character_negative_for_runtime(negative_prompt)
        if runtime_negative:
            prompt += f" Do not introduce any excluded content: {runtime_negative}."
        return prompt

    def _character_front_workflow(self, identity_prompt: str, negative_prompt: str, *, prefix: str, seed: int) -> dict:
        graph: dict[str, dict] = {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": self.model_name, "weight_dtype": "default"}},
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": self.clip_name, "type": "lumina2", "device": "default"}},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": self.vae_name}},
            "4": {"class_type": "ModelSamplingAuraFlow", "inputs": {"shift": 3.0, "model": ["1", 0]}},
        }
        front_prompt = self._character_front_prompt(identity_prompt)
        graph["10"] = {"class_type": "CLIPTextEncode", "inputs": {"text": front_prompt, "clip": ["2", 0]}}
        graph["11"] = {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["10", 0]}}
        graph["12"] = {"class_type": "EmptySD3LatentImage", "inputs": {"width": CHARACTER_RENDER_WIDTH, "height": CHARACTER_RENDER_HEIGHT, "batch_size": 1}}
        graph["13"] = {"class_type": "KSampler", "inputs": {"seed": seed, "steps": 8, "cfg": 1.0, "sampler_name": "res_multistep", "scheduler": "simple", "denoise": 1.0, "model": ["4", 0], "positive": ["10", 0], "negative": ["11", 0], "latent_image": ["12", 0]}}
        graph["14"] = {"class_type": "VAEDecode", "inputs": {"samples": ["13", 0], "vae": ["3", 0]}}
        graph["15"] = {"class_type": "SaveImage", "inputs": {"images": ["14", 0], "filename_prefix": f"{prefix}/front"}}
        return {"prompt": graph, "client_id": f"ai-drama-character-front-{uuid4()}"}

    def _character_edit_workflow(self, reference_image_name: str, negative_prompt: str, *, prefix: str, seed: int) -> dict:
        graph: dict[str, dict] = {
            "101": {"class_type": "UNETLoader", "inputs": {"unet_name": self.character_edit_model_name, "weight_dtype": "default"}},
            "102": {"class_type": "CLIPLoader", "inputs": {"clip_name": self.character_edit_clip_name, "type": "qwen_image", "device": "default"}},
            "103": {"class_type": "VAELoader", "inputs": {"vae_name": self.character_edit_vae_name}},
            "104": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["101", 0], "shift": QWEN_CHARACTER_EDIT_SHIFT}},
            "105": {"class_type": "CFGNorm", "inputs": {"model": ["104", 0], "strength": 1.0}},
            "106": {"class_type": "LoadImage", "inputs": {"image": reference_image_name}},
            "107": {"class_type": "FluxKontextImageScale", "inputs": {"image": ["106", 0]}},
            "108": {"class_type": "VAEEncode", "inputs": {"pixels": ["107", 0], "vae": ["103", 0]}},
        }
        for base, view in ((120, "side"), (130, "back")):
            prompt = self._qwen_character_edit_prompt(negative_prompt, view)
            graph[str(base)] = {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {"clip": ["102", 0], "prompt": prompt, "vae": ["103", 0], "image1": ["107", 0]}}
            graph[str(base + 1)] = {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {"clip": ["102", 0], "prompt": "", "vae": ["103", 0], "image1": ["107", 0]}}
            graph[str(base + 2)] = {"class_type": "FluxKontextMultiReferenceLatentMethod", "inputs": {"conditioning": [str(base), 0], "reference_latents_method": "index_timestep_zero"}}
            graph[str(base + 3)] = {"class_type": "FluxKontextMultiReferenceLatentMethod", "inputs": {"conditioning": [str(base + 1), 0], "reference_latents_method": "index_timestep_zero"}}
            branch_seed = (seed + (0 if view == "side" else 1)) % ((1 << 63) - 1)
            graph[str(base + 4)] = {"class_type": "KSampler", "inputs": {"seed": branch_seed, "steps": QWEN_CHARACTER_EDIT_STEPS, "cfg": QWEN_CHARACTER_EDIT_CFG, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0, "model": ["105", 0], "positive": [str(base + 2), 0], "negative": [str(base + 3), 0], "latent_image": ["108", 0]}}
            graph[str(base + 5)] = {"class_type": "VAEDecode", "inputs": {"samples": [str(base + 4), 0], "vae": ["103", 0]}}
            graph[str(base + 6)] = {"class_type": "SaveImage", "inputs": {"images": [str(base + 5), 0], "filename_prefix": f"{prefix}/{view}"}}
        return {"prompt": graph, "client_id": f"ai-drama-character-qwen-edit-{uuid4()}"}

    def _submit_prompt(self, client: httpx.Client, payload: dict, *, label: str) -> str:
        response = client.post(f"{self.base_url}/prompt", json=payload)
        try:
            body = response.json()
        except Exception as exc:
            raise AppError("ASSET_IMAGE_CREATE_FAILED", f"ComfyUI {label} /prompt 返回非 JSON：HTTP {response.status_code}；{self._safe_preview(response)}", status_code=502) from exc
        if response.status_code >= 400:
            raise AppError("ASSET_IMAGE_CREATE_FAILED", f"ComfyUI {label} 工作流拒绝：{str(body)[:600]}", status_code=502)
        prompt_id = str(body.get("prompt_id") or "").strip()
        if not prompt_id:
            raise AppError("ASSET_IMAGE_CREATE_FAILED", f"ComfyUI {label} /prompt 缺少 prompt_id", status_code=502)
        return prompt_id

    def _wait_saved_images(self, client: httpx.Client, prompt_id: str, node_ids: tuple[str, ...], *, label: str) -> list[dict]:
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            history = client.get(f"{self.base_url}/history/{prompt_id}")
            if history.status_code != 200:
                raise AppError("ASSET_IMAGE_QUERY_FAILED", f"ComfyUI {label} history 返回 HTTP {history.status_code}", status_code=502)
            entry = self._history_entry(history.json(), prompt_id)
            if entry:
                status = entry.get("status") if isinstance(entry.get("status"), dict) else {}
                if str(status.get("status_str") or "").lower() in {"error", "failed"}:
                    raise AppError("ASSET_IMAGE_GENERATION_FAILED", f"ComfyUI {label} 生成失败：{str(status.get('messages'))[:800]}", status_code=502)
                images = [self._find_saved_image(entry, node_id) for node_id in node_ids]
                if all(image is not None for image in images):
                    return [image for image in images if image is not None]
                if status.get("completed") is True:
                    raise AppError("ASSET_IMAGE_MEDIA_MISSING", f"ComfyUI 完成 {label} 任务但缺少预期输出", status_code=502)
            time.sleep(self.poll_interval)
        raise AppError("ASSET_IMAGE_TIMEOUT", f"ComfyUI {label} 生成超时", status_code=504)

    def _upload_character_master(self, client: httpx.Client, front: Image.Image, *, project_id: str, task_id: str, asset_id: str) -> str:
        buffer = BytesIO()
        front.save(buffer, format="PNG")
        buffer.seek(0)
        subfolder = f"ai_drama_studio/character_refs/{project_id}/{task_id}/{asset_id.replace(':', '_')}"
        try:
            response = client.post(
                f"{self.base_url}/upload/image",
                data={"type": "input", "overwrite": "true", "subfolder": subfolder},
                files={"image": ("front-master.png", buffer, "image/png")},
                timeout=httpx.Timeout(300.0),
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise AppError("ASSET_IMAGE_REFERENCE_UPLOAD_FAILED", "上传人物正面主身份图到 ComfyUI 失败", status_code=503) from exc
        try:
            body = response.json()
        except Exception as exc:
            raise AppError("ASSET_IMAGE_REFERENCE_UPLOAD_FAILED", f"ComfyUI 人物主身份图上传返回非 JSON：HTTP {response.status_code}；{self._safe_preview(response)}", status_code=502) from exc
        if response.status_code >= 400:
            raise AppError("ASSET_IMAGE_REFERENCE_UPLOAD_FAILED", f"ComfyUI 人物主身份图上传失败：{str(body)[:600]}", status_code=502)
        name = str(body.get("name") or "").strip()
        actual_subfolder = str(body.get("subfolder") or subfolder).strip("/\\")
        if not name:
            raise AppError("ASSET_IMAGE_REFERENCE_UPLOAD_FAILED", "ComfyUI 人物主身份图上传响应缺少 name", status_code=502)
        return f"{actual_subfolder}/{name}" if actual_subfolder else name

    @staticmethod
    def _find_saved_image(entry: dict, node_id: str) -> dict | None:
        outputs = entry.get("outputs")
        if not isinstance(outputs, dict):
            return None
        save = outputs.get(node_id)
        if not isinstance(save, dict):
            return None
        images = save.get("images")
        if not isinstance(images, list) or not images:
            return None
        return images[0] if isinstance(images[0], dict) else None

    @staticmethod
    def _download_pil(client: httpx.Client, base_url: str, image: dict) -> Image.Image:
        params = {"filename": image.get("filename", ""), "subfolder": image.get("subfolder", ""), "type": image.get("type", "output")}
        response = client.get(f"{base_url}/view", params=params, timeout=httpx.Timeout(300.0))
        response.raise_for_status()
        with Image.open(BytesIO(response.content)) as source:
            return source.convert("RGB").copy()

    @staticmethod
    def _compose_character_sheet(front: Image.Image, side: Image.Image, back: Image.Image) -> Image.Image:
        panel_size = (CHARACTER_PANEL_WIDTH, CHARACTER_PANEL_HEIGHT)
        normalized = [ImageOps.fit(image.convert("RGB"), panel_size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5)) for image in (front, side, back)]
        front_image = normalized[0]
        crop_box = (
            int(front_image.width * 0.24),
            0,
            int(front_image.width * 0.76),
            int(front_image.height * 0.42),
        )
        face_source = front_image.crop(crop_box)
        face_panel = ImageOps.fit(face_source, panel_size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.16))
        sheet = Image.new("RGB", (CHARACTER_WIDTH, CHARACTER_HEIGHT), "white")
        for index, panel in enumerate((*normalized, face_panel)):
            sheet.paste(panel, (index * CHARACTER_PANEL_WIDTH, 0))
        return sheet

    def generate_character_sheet(self, *, project_id: str, task_id: str, asset_id: str, prompt: str, negative_prompt: str) -> GeneratedImage:
        self.assert_ready(require_character_edit=True)
        prefix = f"ai_drama_studio/assets/{project_id}/{task_id}/{asset_id.replace(':', '_')}/character_views"
        front_seed = secrets.randbelow((1 << 63) - 1)
        edit_seed = secrets.randbelow((1 << 63) - 2)
        front_payload = self._character_front_workflow(prompt, negative_prompt, prefix=prefix, seed=front_seed)
        with httpx.Client(timeout=httpx.Timeout(120.0), trust_env=False) as client:
            front_prompt_id = self._submit_prompt(client, front_payload, label="Z-Image 人物正面主身份")
            [front_image] = self._wait_saved_images(client, front_prompt_id, ("15",), label="Z-Image 人物正面主身份")
            front = self._download_pil(client, self.base_url, front_image)
            reference_image_name = self._upload_character_master(client, front, project_id=project_id, task_id=task_id, asset_id=asset_id)
            edit_payload = self._character_edit_workflow(reference_image_name, negative_prompt, prefix=prefix, seed=edit_seed)
            edit_prompt_id = self._submit_prompt(client, edit_payload, label="Qwen Image Edit 人物朝向")
            side_image, back_image = self._wait_saved_images(client, edit_prompt_id, ("126", "136"), label="Qwen Image Edit 人物侧面/背面")
            side = self._download_pil(client, self.base_url, side_image)
            back = self._download_pil(client, self.base_url, back_image)

        storage_relpath = f"target_asset_images/{project_id}/{task_id}/{asset_id.replace(':', '_')}.png"
        output = (self.settings.artifact_root / storage_relpath).resolve()
        root = self.settings.artifact_root.resolve()
        if root not in output.parents:
            raise AppError("ASSET_IMAGE_STORAGE_INVALID", "人物资产图存储路径越界", status_code=500)
        output.parent.mkdir(parents=True, exist_ok=True)
        sheet = self._compose_character_sheet(front, side, back)
        sheet.save(output, format="PNG")
        remote_job_id = f"front:{front_prompt_id};qwen-edit:{edit_prompt_id}"
        return GeneratedImage(storage_relpath=storage_relpath, sha256=_file_sha(output), width=CHARACTER_WIDTH, height=CHARACTER_HEIGHT, mime_type="image/png", remote_url="", remote_job_id=remote_job_id)

    @staticmethod
    def _history_entry(body: dict, prompt_id: str) -> dict | None:
        value = body.get(prompt_id)
        return value if isinstance(value, dict) else None

    @staticmethod
    def _find_image(entry: dict) -> dict | None:
        outputs = entry.get("outputs")
        if not isinstance(outputs, dict): return None
        save = outputs.get("10")
        if not isinstance(save, dict): return None
        images = save.get("images")
        if not isinstance(images, list) or not images: return None
        return images[0] if isinstance(images[0], dict) else None

    def generate(self, *, project_id: str, task_id: str, asset_id: str, prompt: str, negative_prompt: str, width: int, height: int) -> GeneratedImage:
        self.assert_ready()
        prefix = f"ai_drama_studio/assets/{project_id}/{task_id}/{asset_id.replace(':', '_')}"
        payload = self._workflow(prompt, negative_prompt, prefix=prefix, seed=secrets.randbelow((1 << 63) - 1), width=width, height=height)
        with httpx.Client(timeout=httpx.Timeout(120.0), trust_env=False) as client:
            response = client.post(f"{self.base_url}/prompt", json=payload)
            try: body = response.json()
            except Exception as exc: raise AppError("ASSET_IMAGE_CREATE_FAILED", f"ComfyUI /prompt 返回非 JSON：HTTP {response.status_code}；{self._safe_preview(response)}", status_code=502) from exc
            if response.status_code >= 400: raise AppError("ASSET_IMAGE_CREATE_FAILED", f"ComfyUI 资产图工作流拒绝：{str(body)[:600]}", status_code=502)
            prompt_id = str(body.get("prompt_id") or "").strip()
            if not prompt_id: raise AppError("ASSET_IMAGE_CREATE_FAILED", "ComfyUI /prompt 缺少 prompt_id", status_code=502)
            deadline = time.monotonic() + self.timeout_seconds
            image = None
            while time.monotonic() < deadline:
                history = client.get(f"{self.base_url}/history/{prompt_id}")
                if history.status_code != 200: raise AppError("ASSET_IMAGE_QUERY_FAILED", f"ComfyUI history 返回 HTTP {history.status_code}", status_code=502)
                entry = self._history_entry(history.json(), prompt_id)
                if entry:
                    status = entry.get("status") if isinstance(entry.get("status"), dict) else {}
                    if str(status.get("status_str") or "").lower() in {"error", "failed"}: raise AppError("ASSET_IMAGE_GENERATION_FAILED", f"ComfyUI Z-Image Turbo 生成失败：{str(status.get('messages'))[:800]}", status_code=502)
                    image = self._find_image(entry)
                    if image: break
                    if status.get("completed") is True: raise AppError("ASSET_IMAGE_MEDIA_MISSING", "ComfyUI 完成但没有 SaveImage 输出", status_code=502)
                time.sleep(self.poll_interval)
            if not image: raise AppError("ASSET_IMAGE_TIMEOUT", "ComfyUI 资产图生成超时", status_code=504)
            params = {"filename": image.get("filename", ""), "subfolder": image.get("subfolder", ""), "type": image.get("type", "output")}
            remote_url = f"{self.base_url}/view?{urlencode(params)}"
            storage_relpath = f"target_asset_images/{project_id}/{task_id}/{asset_id.replace(':', '_')}.png"
            output = (self.settings.artifact_root / storage_relpath).resolve()
            root = self.settings.artifact_root.resolve()
            if root not in output.parents: raise AppError("ASSET_IMAGE_STORAGE_INVALID", "资产图存储路径越界", status_code=500)
            output.parent.mkdir(parents=True, exist_ok=True)
            with client.stream("GET", f"{self.base_url}/view", params=params, timeout=httpx.Timeout(300.0)) as download:
                download.raise_for_status()
                with output.open("wb") as handle:
                    for chunk in download.iter_bytes(): handle.write(chunk)
        with Image.open(output) as im:
            width, height = im.size
            im.verify()
        return GeneratedImage(storage_relpath=storage_relpath, sha256=_file_sha(output), width=width, height=height, mime_type="image/png", remote_url=remote_url, remote_job_id=prompt_id)


# Compatibility import for code/tests written before the Step 3 runtime switched from Flux
# to Z-Image Turbo. The implementation and runtime profile are intentionally Z-Image now.
ComfyUIFluxRuntime = ComfyUIZImageTurboRuntime


class ArkSeedreamRuntime:
    provider_name = "volcengine-ark-seedream"

    def __init__(self):
        self.settings = get_settings()
        self.model_name = self.settings.asset_seedream_lite_model
        self.character_pipeline_model_name = self.settings.asset_seedream_pro_model
        self.pipeline_model_name = (
            f"character={self.character_pipeline_model_name};"
            f"scene-prop={self.model_name}"
        )

    def assert_ready(self, *, require_character_edit: bool = False) -> None:
        if self.settings.p7_doubao_api_key is None or not self.settings.p7_doubao_api_key.get_secret_value().strip():
            raise AppError("ASSET_IMAGE_SEEDREAM_NOT_CONFIGURED", "Seedream 图片 Provider 尚未配置火山方舟 API Key", status_code=409)

    def profile(self) -> dict:
        return {
            "provider": self.provider_name,
            "character_model": self.character_pipeline_model_name,
            "scene_prop_model": self.model_name,
            "workflow": "seedream5-pro-reference-identity-lite-assets-v1",
            "watermark": False,
        }

    def _client(self) -> Ark:
        self.assert_ready()
        assert self.settings.p7_doubao_api_key is not None
        return Ark(
            api_key=self.settings.p7_doubao_api_key.get_secret_value(),
            base_url=self.settings.p7_doubao_base_url,
            timeout=self.settings.asset_seedream_timeout_seconds,
            max_retries=2,
        )

    @staticmethod
    def _data_uri(image: Image.Image) -> str:
        buffer = BytesIO()
        image.convert("RGB").save(buffer, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")

    @staticmethod
    def _response_image(response) -> tuple[Image.Image, str]:
        data = list(getattr(response, "data", None) or [])
        if not data:
            raise AppError("ASSET_IMAGE_SEEDREAM_EMPTY", "Seedream 未返回图片", status_code=502)
        item = data[0]
        encoded = getattr(item, "b64_json", None)
        if encoded:
            raw = base64.b64decode(encoded)
        else:
            url = str(getattr(item, "url", "") or "")
            if not url:
                raise AppError("ASSET_IMAGE_SEEDREAM_EMPTY", "Seedream 返回结果缺少图片内容", status_code=502)
            response_image = httpx.get(url, timeout=300.0, follow_redirects=True)
            response_image.raise_for_status()
            raw = response_image.content
        with Image.open(BytesIO(raw)) as source:
            image = source.convert("RGB").copy()
        return image, str(getattr(response, "id", "") or "")

    @staticmethod
    def _request_size(width: int, height: int) -> str:
        # Seedream 5.0 accepts its documented quality tiers.  The old ComfyUI
        # card sizes (for example 512x1024) are UI/output sizes, not valid Ark
        # render sizes.  We resize/crop the returned image only after generation.
        return "2K"

    def _generate(self, *, model: str, prompt: str, width: int, height: int, reference: Image.Image | None = None) -> tuple[Image.Image, str]:
        try:
            response = self._client().images.generate(
                model=model,
                prompt=prompt,
                image=[self._data_uri(reference)] if reference is not None else None,
                response_format="url",
                size=self._request_size(width, height),
                watermark=False,
            )
        except ArkBadRequestError as exc:
            # The SDK's public message/body contains Ark's parameter or model
            # diagnosis, but never request credentials. Keep it bounded before
            # it enters the ProviderJob/UI error path.
            detail = str(getattr(exc, "body", None) or str(exc)).replace("\n", " ").strip()
            raise AppError(
                "ASSET_IMAGE_SEEDREAM_REQUEST_INVALID",
                f"Seedream 请求参数无效：{detail[:480] or '请检查模型配置'}",
                status_code=502,
            ) from exc
        return self._response_image(response)

    def generate_character_sheet(self, *, project_id: str, task_id: str, asset_id: str, prompt: str, negative_prompt: str) -> GeneratedImage:
        front_prompt = ComfyUIZImageTurboRuntime._character_front_prompt(prompt)
        runtime_negative = ComfyUIZImageTurboRuntime._character_negative_for_runtime(negative_prompt)
        if runtime_negative:
            front_prompt += f" Exclude these visual defects or additions: {runtime_negative}."
        front, front_id = self._generate(model=self.character_pipeline_model_name, prompt=front_prompt, width=CHARACTER_RENDER_WIDTH, height=CHARACTER_RENDER_HEIGHT)
        side, side_id = self._generate(model=self.character_pipeline_model_name, prompt=ComfyUIZImageTurboRuntime._qwen_character_edit_prompt(negative_prompt, "side"), width=CHARACTER_RENDER_WIDTH, height=CHARACTER_RENDER_HEIGHT, reference=front)
        back, back_id = self._generate(model=self.character_pipeline_model_name, prompt=ComfyUIZImageTurboRuntime._qwen_character_edit_prompt(negative_prompt, "back"), width=CHARACTER_RENDER_WIDTH, height=CHARACTER_RENDER_HEIGHT, reference=front)
        sheet = ComfyUIZImageTurboRuntime._compose_character_sheet(front, side, back)
        return self._persist(project_id, task_id, asset_id, sheet, ";".join(filter(None, (front_id, side_id, back_id))))

    def generate(self, *, project_id: str, task_id: str, asset_id: str, prompt: str, negative_prompt: str, width: int, height: int) -> GeneratedImage:
        execution_prompt = prompt
        if negative_prompt.strip():
            execution_prompt += f" Exclude these visual defects or additions: {negative_prompt.strip()}."
        image, remote_id = self._generate(model=self.model_name, prompt=execution_prompt, width=width, height=height)
        image = ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS)
        return self._persist(project_id, task_id, asset_id, image, remote_id)

    def _persist(self, project_id: str, task_id: str, asset_id: str, image: Image.Image, remote_id: str) -> GeneratedImage:
        storage_relpath = f"target_asset_images/{project_id}/{task_id}/{asset_id.replace(':', '_')}.png"
        output = (self.settings.artifact_root / storage_relpath).resolve()
        root = self.settings.artifact_root.resolve()
        if root not in output.parents:
            raise AppError("ASSET_IMAGE_STORAGE_INVALID", "资产图存储路径越界", status_code=500)
        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output, format="PNG")
        width, height = image.size
        return GeneratedImage(storage_relpath, _file_sha(output), width, height, "image/png", "", remote_id or None)


def asset_image_runtime() -> ArkSeedreamRuntime | ComfyUIZImageTurboRuntime:
    settings = get_settings()
    if settings.asset_image_runtime == "ARK_SEEDREAM":
        return ArkSeedreamRuntime()
    return ComfyUIZImageTurboRuntime()


def _current_artifact(db: Session, project_id: str, artifact_type: ArtifactType) -> ArtifactNode | None:
    return db.scalar(select(ArtifactNode).where(ArtifactNode.project_id == project_id, ArtifactNode.artifact_type == artifact_type.value, ArtifactNode.is_current.is_(True), ArtifactNode.validity == ArtifactValidity.CURRENT))


def _latest_artifact(db: Session, project_id: str, artifact_type: ArtifactType) -> ArtifactNode | None:
    return db.scalar(select(ArtifactNode).where(ArtifactNode.project_id == project_id, ArtifactNode.artifact_type == artifact_type.value).order_by(ArtifactNode.revision.desc()).limit(1))


def _load_storyboard(db: Session, project_id: str) -> tuple[ArtifactNode, ReplicaLocalizedStoryboardContent]:
    artifact = _current_artifact(db, project_id, ArtifactType.TARGET_STORYBOARD)
    if artifact is None: raise AppError("ASSET_IMAGES_STORYBOARD_NOT_READY", "请先完成并确认第 2 步本土化分镜", status_code=409)
    row = db.scalar(select(ReplicaLocalizedStoryboardRevision).where(ReplicaLocalizedStoryboardRevision.artifact_id == artifact.id))
    if row is None: raise AppError("ASSET_IMAGES_REQUIRES_V2_STORYBOARD", "当前 TARGET_STORYBOARD 是旧合同结果，请先生成新的本土化分镜", status_code=409)
    return artifact, ReplicaLocalizedStoryboardContent.model_validate(row.content_json)


def _optional_target_bible_characters(db: Session, project_id: str) -> dict[str, dict]:
    """Return optional stable character identity evidence without making legacy P11 a Step 3 gate."""
    artifact = _current_artifact(db, project_id, ArtifactType.TARGET_BIBLE)
    if artifact is None:
        return {}
    row = db.scalar(select(ReplicaTargetRevision).where(ReplicaTargetRevision.artifact_id == artifact.id))
    if row is None or row.artifact_kind != TargetBibleArtifactKind.TARGET_BIBLE.value:
        raise AppError("ASSET_IMAGES_TARGET_BIBLE_CONTENT_INVALID", "CURRENT TARGET_BIBLE 缺少有效 typed revision", status_code=500)
    content = ReplicaTargetBibleContent.model_validate(row.content_json)
    return {
        item.target_character_id: {
            "target_bible_artifact_id": artifact.id,
            "display_name": item.display_name,
            "localized_identity": item.localized_identity,
            "appearance_direction": item.appearance_direction,
            "continuity_rules": list(item.continuity_rules),
        }
        for item in content.characters
    }


def _entity_specs(
    content: ReplicaLocalizedStoryboardContent,
    visual_style: str,
    target_bible_characters: dict[str, dict] | None = None,
) -> list[dict]:
    target_bible_characters = target_bible_characters or {}
    referenced_characters = {
        entity_id
        for shot in content.shots
        for entity_id in [
            *shot.target_character_ids,
            *(line.target_character_id for line in shot.dialogue if line.target_character_id),
        ]
    }
    referenced_scenes = {entity_id for shot in content.shots for entity_id in shot.target_scene_ids}
    referenced_props = {entity_id for shot in content.shots for entity_id in shot.target_prop_ids}

    characters = {item.target_character_id: item for item in content.characters}
    scenes = {item.target_scene_id: item for item in content.scenes}
    props = {item.target_prop_id: item for item in content.props}
    missing = {
        "characters": sorted(referenced_characters - set(characters)),
        "scenes": sorted(referenced_scenes - set(scenes)),
        "props": sorted(referenced_props - set(props)),
    }
    if any(missing.values()):
        raise AppError(
            "ASSET_IMAGES_STORYBOARD_ENTITY_MISSING",
            "本土化分镜引用了没有正式实体定义的人物、场景或道具，禁止生成不完整资产集",
            status_code=409,
            details=missing,
        )

    def _evidence(entity_id: str, asset_type: TargetAssetType) -> list[dict]:
        rows: list[dict] = []
        seen: set[str] = set()
        for shot in content.shots:
            referenced = False
            if asset_type == TargetAssetType.CHARACTER:
                referenced = entity_id in shot.target_character_ids or any(
                    line.target_character_id == entity_id for line in shot.dialogue
                )
            elif asset_type == TargetAssetType.SCENE:
                referenced = entity_id in shot.target_scene_ids
            elif asset_type == TargetAssetType.PROP:
                referenced = entity_id in shot.target_prop_ids
            if not referenced:
                continue
            description = shot.localized_visual_description_zh.strip()
            if description in seen:
                continue
            seen.add(description)
            rows.append({
                "storyboard_shot_id": shot.storyboard_shot_id,
                "shot_number": shot.shot_number,
                "localized_visual_description_zh": description,
            })
            if len(rows) >= 24:
                break
        return rows

    specs: list[dict] = []
    for item in content.characters:
        if item.target_character_id not in referenced_characters:
            continue
        review_zh = f"{item.identity_description_zh}；{item.appearance_description_zh}"
        specs.append({
            "asset_type": TargetAssetType.CHARACTER,
            "entity_id": item.target_character_id,
            "display_name": item.display_name,
            "review_zh": review_zh,
            "width": CHARACTER_WIDTH,
            "height": CHARACTER_HEIGHT,
            "character_design_context": {
                "character_id": item.target_character_id,
                "display_name": item.display_name,
                "localized_storyboard_identity": item.identity_description_zh,
                "localized_storyboard_appearance": item.appearance_description_zh,
                "visual_style": visual_style,
                "storyboard_evidence": _evidence(item.target_character_id, TargetAssetType.CHARACTER),
                "optional_target_bible": target_bible_characters.get(item.target_character_id),
            },
        })
    for item in content.scenes:
        if item.target_scene_id not in referenced_scenes:
            continue
        review_zh = f"{item.setting_description_zh}；{item.visual_description_zh}"
        specs.append({
            "asset_type": TargetAssetType.SCENE,
            "entity_id": item.target_scene_id,
            "display_name": item.display_name,
            "review_zh": review_zh,
            "width": SCENE_WIDTH,
            "height": SCENE_HEIGHT,
            "prompt_context": {
                "target_entity_id": item.target_scene_id,
                "asset_type": TargetAssetType.SCENE.value,
                "display_name": item.display_name,
                "review_definition_zh": review_zh,
                "setting_description_zh": item.setting_description_zh,
                "visual_description_zh": item.visual_description_zh,
                "visual_style": visual_style,
                "storyboard_evidence": _evidence(item.target_scene_id, TargetAssetType.SCENE),
            },
        })
    for item in content.props:
        if item.target_prop_id not in referenced_props:
            continue
        review_zh = f"{item.function_description_zh}；{item.visual_description_zh}"
        specs.append({
            "asset_type": TargetAssetType.PROP,
            "entity_id": item.target_prop_id,
            "display_name": item.display_name,
            "review_zh": review_zh,
            "width": PROP_WIDTH,
            "height": PROP_HEIGHT,
            "prompt_context": {
                "target_entity_id": item.target_prop_id,
                "asset_type": TargetAssetType.PROP.value,
                "display_name": item.display_name,
                "review_definition_zh": review_zh,
                "function_description_zh": item.function_description_zh,
                "visual_description_zh": item.visual_description_zh,
                "visual_style": visual_style,
                "storyboard_evidence": _evidence(item.target_prop_id, TargetAssetType.PROP),
            },
        })
    return specs


def _model_prompt_context(spec: dict, character_visual_design: CharacterVisualDesignPacket | None = None) -> dict:
    if spec["asset_type"] != TargetAssetType.CHARACTER:
        return dict(spec["prompt_context"])
    if character_visual_design is None:
        raise AppError(
            "ASSET_IMAGE_CHARACTER_VISUAL_DESIGN_REQUIRED",
            "人物资产必须先完成 Character Visual Design，再编译图片模型 Prompt",
            status_code=409,
            details={"target_entity_id": spec["entity_id"]},
        )
    return {
        "target_entity_id": spec["entity_id"],
        "asset_type": TargetAssetType.CHARACTER.value,
        "display_name": spec["display_name"],
        "visual_style": spec["character_design_context"]["visual_style"],
        "character_visual_design": character_visual_design.model_dump(mode="json"),
    }


def get_asset_workspace(db: Session, project_id: str) -> AssetWorkspaceRead:
    get_project(db, project_id)
    storyboard = _current_artifact(db, project_id, ArtifactType.TARGET_STORYBOARD)
    row = db.scalar(select(ReplicaAssetWorkspace).where(ReplicaAssetWorkspace.project_id == project_id))
    if row is None or storyboard is None or row.target_storyboard_artifact_id != storyboard.id:
        return AssetWorkspaceRead(project_id=project_id, status="EMPTY")
    content = AssetWorkspaceContent.model_validate(row.content_json)
    return AssetWorkspaceRead(project_id=project_id, status="READY", revision=row.revision, content=content)


def extract_asset_workspace(db: Session, project_id: str) -> AssetWorkspaceRead:
    project = get_project(db, project_id)
    if project.project_type != ProjectType.REPLICA:
        raise AppError("ASSET_IMAGES_PROJECT_UNSUPPORTED", "当前五步主生产链只正式支持 REPLICA", status_code=422)
    storyboard_artifact, storyboard = _load_storyboard(db, project_id)
    visual_style = project.visual_style or "写实电影感"
    specs = _entity_specs(storyboard, visual_style, _optional_target_bible_characters(db, project_id))
    if not specs:
        raise AppError("ASSET_IMAGES_EMPTY", "本土化分镜没有可提取的人物、场景或道具", status_code=409)
    existing = db.scalar(select(ReplicaAssetWorkspace).where(ReplicaAssetWorkspace.project_id == project_id))
    if existing is not None and existing.target_storyboard_artifact_id == storyboard_artifact.id:
        return AssetWorkspaceRead(project_id=project_id, status="READY", revision=existing.revision, content=AssetWorkspaceContent.model_validate(existing.content_json))
    content = AssetWorkspaceContent(
        target_storyboard_artifact_id=storyboard_artifact.id,
        target_language=storyboard.target_language,
        target_region=storyboard.target_region,
        visual_style=visual_style,
        assets=[AssetWorkspaceEntity(
            target_asset_id=_asset_id(project_id, spec["entity_id"]),
            asset_type=spec["asset_type"],
            target_entity_id=spec["entity_id"],
            display_name=spec["display_name"],
            review_description_zh=spec["review_zh"],
            width=spec["width"],
            height=spec["height"],
        ) for spec in specs],
    )
    now = utc_now()
    if existing is None:
        existing = ReplicaAssetWorkspace(project_id=project_id, target_storyboard_artifact_id=storyboard_artifact.id, revision=1, content_json=content.model_dump(mode="json"), created_at=now, updated_at=now)
    else:
        existing.target_storyboard_artifact_id = storyboard_artifact.id
        existing.revision += 1
        existing.content_json = content.model_dump(mode="json")
        existing.updated_at = now
    db.add(existing); db.commit(); db.refresh(existing)
    return AssetWorkspaceRead(project_id=project_id, status="READY", revision=existing.revision, content=content)


def create_asset_workspace_task(db: Session, *, project_id: str, idempotency_key: str, operation: str, target_asset_ids: list[str]) -> Task:
    project = get_project(db, project_id)
    if project.project_type != ProjectType.REPLICA:
        raise AppError("ASSET_IMAGES_PROJECT_UNSUPPORTED", "当前五步主生产链只正式支持 REPLICA", status_code=422)
    storyboard_artifact, _ = _load_storyboard(db, project_id)
    workspace = db.scalar(select(ReplicaAssetWorkspace).where(ReplicaAssetWorkspace.project_id == project_id))
    if workspace is None or workspace.target_storyboard_artifact_id != storyboard_artifact.id:
        raise AppError("ASSET_WORKSPACE_NOT_EXTRACTED", "请先提取人物、场景和道具", status_code=409)
    content = AssetWorkspaceContent.model_validate(workspace.content_json)
    by_id = {asset.target_asset_id: asset for asset in content.assets}
    if any(asset_id not in by_id for asset_id in target_asset_ids):
        raise AppError("ASSET_WORKSPACE_SELECTION_INVALID", "所选资产不存在或已经失效", status_code=422)
    if operation == "images":
        asset_image_runtime().assert_ready()
        if any(not by_id[asset_id].image_prompt for asset_id in target_asset_ids):
            raise AppError("ASSET_WORKSPACE_PROMPT_MISSING", "请先为所选资产生成提示词", status_code=409)
        visual_skill = character_visual_design_skill()
        stale_characters = [
            asset_id for asset_id in target_asset_ids
            if by_id[asset_id].asset_type == TargetAssetType.CHARACTER and (
                by_id[asset_id].character_visual_design is None
                or by_id[asset_id].character_visual_skill_id != visual_skill.id
                or by_id[asset_id].character_visual_skill_version != visual_skill.version
            )
        ]
        if stale_characters:
            raise AppError(
                "ASSET_WORKSPACE_CHARACTER_VISUAL_DESIGN_MISSING",
                "人物资产缺少当前版本角色视觉设计，请先重新生成所选人物提示词",
                status_code=409,
                details={"asset_ids": stale_characters},
            )
    task_type = ASSET_PROMPT_TASK_TYPE if operation == "prompts" else TASK_TYPE
    visual_skill = character_visual_design_skill()
    fingerprint = _sha({"storyboard": storyboard_artifact.input_fingerprint, "workspace_revision": workspace.revision, "operation": operation, "asset_ids": target_asset_ids, "character_visual_skill": [visual_skill.id, visual_skill.version], "request": idempotency_key})
    task = create_task_from_command(db, project_id=project_id, idempotency_key=idempotency_key, payload=TaskCommandCreate(task_type=task_type, task_name="生成资产提示词" if operation == "prompts" else "顺序生成资产图片", input_fingerprint=fingerprint, input_artifact_ids=[storyboard_artifact.id], max_attempts=3, initial_checkpoint_json={"operation": operation, "target_asset_ids": target_asset_ids, "workspace_revision": workspace.revision}))
    if task.status == TaskStatus.QUEUED:
        for asset in content.assets:
            if asset.target_asset_id in target_asset_ids:
                if operation == "prompts": asset.prompt_status = "QUEUED"
                else: asset.image_status = "QUEUED"
                asset.last_error = None
        workspace.revision += 1; workspace.content_json = content.model_dump(mode="json"); workspace.updated_at = utc_now()
        db.add(workspace); db.add(task); db.commit(); db.refresh(task)
    return task


def create_asset_images_task(db: Session, *, project_id: str, idempotency_key: str, regenerate: bool = False) -> Task:
    project = get_project(db, project_id)
    if project.project_type != ProjectType.REPLICA: raise AppError("ASSET_IMAGES_PROJECT_UNSUPPORTED", "当前五步主生产链只正式支持 REPLICA", status_code=422)
    storyboard_artifact, content = _load_storyboard(db, project_id)
    runtime = asset_image_runtime(); runtime.assert_ready()
    binding, prompt_skill = selected_image_model_prompt_skill()
    prompt_provider = asset_prompt_author_provider()
    visual_skill = character_visual_design_skill()
    visual_provider = character_visual_design_provider()
    fingerprint_payload = {
        "storyboard": storyboard_artifact.input_fingerprint,
        "visual_style": project.visual_style,
        "runtime": runtime.profile(),
        "orchestration_skill": get_professional_skill(SKILL_ID).version,
        "character_visual_skill": [visual_skill.id, visual_skill.version],
        "character_visual_provider": visual_provider.profile(),
        "prompt_skill": [prompt_skill.id, prompt_skill.version, binding.prompt_contract],
        "prompt_provider": prompt_provider.profile(),
    }
    if regenerate:
        fingerprint_payload["regeneration_request"] = idempotency_key.strip()
    fingerprint = _sha(fingerprint_payload)
    task_name = "重新提取并生成资产图" if regenerate else "提取资产、Skill 生成提示词并生成资产图"
    return create_task_from_command(db, project_id=project_id, idempotency_key=idempotency_key, payload=TaskCommandCreate(task_type=TASK_TYPE, task_name=task_name, input_fingerprint=fingerprint, input_artifact_ids=[storyboard_artifact.id], max_attempts=3))


def _generation_sequence(db: Session, project_id: str, storyboard_artifact_id: str) -> int:
    latest = db.scalar(select(func.max(ReplicaAssetImageCandidate.generation_sequence)).where(ReplicaAssetImageCandidate.project_id == project_id, ReplicaAssetImageCandidate.target_storyboard_artifact_id == storyboard_artifact_id))
    return int(latest or 0) + 1


def _author_character_visual_designs(
    context: TaskExecutionContext,
    task: TaskWorkerRead,
    storyboard_artifact: ArtifactNode,
    specs: list[dict],
    *,
    progress_start: int = 4,
    progress_end: int = 24,
) -> tuple[dict[str, tuple[CharacterVisualDesignPacket, str]], list[str]]:
    character_specs = [spec for spec in specs if spec["asset_type"] == TargetAssetType.CHARACTER]
    if not character_specs:
        return {}, []
    skill = character_visual_design_skill()
    provider = character_visual_design_provider()
    authored: dict[str, tuple[CharacterVisualDesignPacket, str]] = {}
    provider_job_ids: list[str] = []
    batches = [
        character_specs[index:index + MAX_CHARACTER_VISUAL_BATCH_SIZE]
        for index in range(0, len(character_specs), MAX_CHARACTER_VISUAL_BATCH_SIZE)
    ]
    for batch_index, batch in enumerate(batches, 1):
        payload = CharacterVisualDesignInput(
            skill=skill,
            characters=tuple(spec["character_design_context"] for spec in batch),
        )
        provider_payload = {
            "target_storyboard_artifact_id": storyboard_artifact.id,
            "character_visual_skill": [skill.id, skill.version],
            "batch_index": batch_index,
            "batch_count": len(batches),
            "character_ids": [spec["entity_id"] for spec in batch],
            "semantic_payload_fingerprint": _sha(payload.characters),
            "provider_profile": provider.profile(),
        }

        def _remote(_, current_payload=payload):
            result = provider.design(current_payload)
            return ProviderDispatchResult(value=result, remote_job_id=result.remote_job_id)

        with context.session_factory() as db:
            job, dispatched = dispatch_provider_call(
                db,
                task_id=task.id,
                provider=provider.provider_name,
                model=provider.model_name,
                capability=Capability.MODEL_PROMPTING,
                payload=provider_payload,
                artifact_id=storyboard_artifact.id,
                remote_call=_remote,
            )
        result: CharacterVisualDesignResult = dispatched.value
        batch_authored = validate_character_visual_design_batch(
            [spec["character_design_context"] for spec in batch],
            result.content,
        )
        for character_id, packet in batch_authored.items():
            authored[character_id] = (packet, job.id)
        provider_job_ids.append(job.id)
        progress = progress_start + math.floor(batch_index / len(batches) * max(1, progress_end - progress_start))
        context.checkpoint(
            {
                **(task.checkpoint_json or {}),
                "stage": "character-visual-design",
                "character_visual_skill": f"{skill.id}@{skill.version}",
                "character_visual_provider_job_ids": provider_job_ids,
                "completed_character_visual_batches": batch_index,
                "character_visual_batch_count": len(batches),
            },
            progress_percent=min(progress_end, progress),
        )
    return authored, provider_job_ids


def _reusable_generated_image(
    db: Session,
    *,
    task: TaskWorkerRead,
    asset_id: str,
    job_payload: dict,
) -> tuple[ProviderJob, GeneratedImage] | None:
    job = db.scalar(select(ProviderJob).where(
        ProviderJob.task_id == task.id,
        ProviderJob.payload_fingerprint == provider_payload_fingerprint(job_payload),
        ProviderJob.status == ProviderJobStatus.SUCCEEDED,
    ).order_by(ProviderJob.created_at.desc()).limit(1))
    if job is None:
        return None
    storage_relpath = f"target_asset_images/{task.project_id}/{task.id}/{asset_id.replace(':', '_')}.png"
    output = (get_settings().artifact_root / storage_relpath).resolve()
    root = get_settings().artifact_root.resolve()
    if root not in output.parents or not output.is_file():
        return None
    try:
        with Image.open(output) as image:
            width, height = image.size
            image.verify()
    except (OSError, ValueError):
        return None
    return job, GeneratedImage(
        storage_relpath=storage_relpath,
        sha256=_file_sha(output),
        width=width,
        height=height,
        mime_type="image/png",
        remote_url="",
        remote_job_id=job.remote_job_id,
    )


def _execute(context: TaskExecutionContext, task: TaskWorkerRead) -> tuple[ReplicaAssetImagesContent, AssetImageProvenance]:
    runtime = asset_image_runtime()
    with context.session_factory() as db:
        project = get_project(db, task.project_id)
        storyboard_artifact, storyboard = _load_storyboard(db, task.project_id)
        sequence = _generation_sequence(db, task.project_id, storyboard_artifact.id)
        target_bible_characters = _optional_target_bible_characters(db, task.project_id)
    specs = _entity_specs(storyboard, project.visual_style or "写实电影感", target_bible_characters)
    if not specs: raise AppError("ASSET_IMAGES_EMPTY", "本土化分镜没有可提取的人物、场景或道具", status_code=409)
    visual_skill = character_visual_design_skill()
    visual_designs, character_visual_provider_job_ids = _author_character_visual_designs(
        context,
        task,
        storyboard_artifact,
        specs,
    )
    model_prompt_contexts = {
        spec["entity_id"]: _model_prompt_context(
            spec,
            visual_designs.get(spec["entity_id"], (None, ""))[0],
        )
        for spec in specs
    }
    binding, prompt_skill = selected_image_model_prompt_skill()
    prompt_provider = asset_prompt_author_provider()
    authored_by_id = {}
    prompt_provider_job_ids: list[str] = []
    prompt_batches = [specs[index:index + MAX_ASSET_PROMPT_BATCH_SIZE] for index in range(0, len(specs), MAX_ASSET_PROMPT_BATCH_SIZE)]
    for batch_index, batch in enumerate(prompt_batches, 1):
        prompt_input = AssetPromptAuthorInput(
            binding=binding,
            skill=prompt_skill,
            assets=tuple(model_prompt_contexts[spec["entity_id"]] for spec in batch),
        )
        prompt_job_payload = {
            "target_storyboard_artifact_id": storyboard_artifact.id,
            "image_model": binding.model_id,
            "prompt_skill": [prompt_skill.id, prompt_skill.version],
            "prompt_contract": binding.prompt_contract,
            "batch_index": batch_index,
            "batch_count": len(prompt_batches),
            "target_entity_ids": [spec["entity_id"] for spec in batch],
            "semantic_payload_fingerprint": _sha(prompt_input.assets),
            "provider_profile": prompt_provider.profile(),
        }

        def _prompt_remote(_, current_input=prompt_input):
            result = prompt_provider.author(current_input)
            return ProviderDispatchResult(value=result, remote_job_id=result.remote_job_id)

        with context.session_factory() as db:
            prompt_job, prompt_dispatched = dispatch_provider_call(
                db,
                task_id=task.id,
                provider=prompt_provider.provider_name,
                model=prompt_provider.model_name,
                capability=Capability.ASSET_IMAGE_GENERATION,
                payload=prompt_job_payload,
                artifact_id=storyboard_artifact.id,
                remote_call=_prompt_remote,
            )
        prompt_result: AssetPromptAuthorResult = prompt_dispatched.value
        authored_by_id.update(validate_authored_asset_batch([model_prompt_contexts[spec["entity_id"]] for spec in batch], prompt_result.content))
        prompt_provider_job_ids.append(prompt_job.id)
        context.checkpoint(
            {
                "stage": "asset-prompt-skill",
                "prompt_skill": f"{prompt_skill.id}@{prompt_skill.version}",
                "prompt_provider_job_ids": prompt_provider_job_ids,
                "completed_prompt_batches": batch_index,
                "prompt_batch_count": len(prompt_batches),
                "total_assets": len(specs),
            },
            progress_percent=min(44, 24 + math.floor(batch_index / len(prompt_batches) * 20)),
        )
    assets: list[AssetImageEntity] = []
    provider_job_ids: list[str] = []
    for index, spec in enumerate(specs, 1):
        asset_id = _asset_id(task.project_id, spec["entity_id"])
        authored = authored_by_id[spec["entity_id"]]
        visual_design, visual_provider_job_id = visual_designs.get(spec["entity_id"], (None, None))
        with context.session_factory() as db:
            job_payload = {
                "target_storyboard_artifact_id": storyboard_artifact.id,
                "asset_id": asset_id,
                "target_entity_id": spec["entity_id"],
                "asset_type": spec["asset_type"].value,
                "prompt_skill": [prompt_skill.id, prompt_skill.version, binding.prompt_contract],
                "prompt_sha256": _sha(authored.image_prompt),
                "negative_prompt_sha256": _sha(authored.negative_prompt),
                "width": spec["width"],
                "height": spec["height"],
                "runtime": runtime.profile(),
            }
            reused = _reusable_generated_image(db, task=task, asset_id=asset_id, job_payload=job_payload)
            if reused is not None:
                job, generated = reused
            else:
                def _remote(job):
                    if spec["asset_type"] == TargetAssetType.CHARACTER:
                        generated = runtime.generate_character_sheet(
                            project_id=task.project_id,
                            task_id=task.id,
                            asset_id=asset_id,
                            prompt=authored.image_prompt,
                            negative_prompt=authored.negative_prompt,
                        )
                    else:
                        generated = runtime.generate(
                            project_id=task.project_id,
                            task_id=task.id,
                            asset_id=asset_id,
                            prompt=authored.image_prompt,
                            negative_prompt=authored.negative_prompt,
                            width=spec["width"],
                            height=spec["height"],
                        )
                    return ProviderDispatchResult(value=generated, remote_job_id=generated.remote_job_id)
                runtime_model = runtime.character_pipeline_model_name if spec["asset_type"] == TargetAssetType.CHARACTER else runtime.model_name
                job, dispatched = dispatch_provider_call(db, task_id=task.id, provider=runtime.provider_name, model=runtime_model, capability=Capability.ASSET_IMAGE_GENERATION, payload=job_payload, artifact_id=storyboard_artifact.id, remote_call=_remote)
                generated = dispatched.value
        provider_job_ids.append(job.id)
        if spec["asset_type"] == TargetAssetType.CHARACTER:
            consistency = validate_character_asset_identity(
                str(get_settings().artifact_root / generated.storage_relpath)
            )
            # 保留失败候选，由 consistency_status 和发布门禁决定是否采用。

        reference_id = f"ref:{hashlib.sha256(f'{asset_id}|{generated.sha256}'.encode()).hexdigest()[:24]}"
        uri = f"/api/v3/projects/{task.project_id}/asset-images/media/{reference_id}"
        role = ReferenceMediaRole.OTHER if spec["asset_type"] == TargetAssetType.CHARACTER else ReferenceMediaRole.LAYOUT if spec["asset_type"] == TargetAssetType.SCENE else ReferenceMediaRole.DETAIL
        media = TargetReferenceMedia(reference_id=reference_id, role=role, uri=uri, mime_type=generated.mime_type, sha256=generated.sha256, width=generated.width, height=generated.height, provider_job_id=job.id, storage_relpath=generated.storage_relpath)
        reference_media = [media]
        if spec["asset_type"] == TargetAssetType.CHARACTER:
            reference_media.extend(_character_identity_reference_media(
                project_id=task.project_id,
                asset_id=asset_id,
                generated=generated,
                provider_job_id=job.id,
            ))
        assets.append(AssetImageEntity(
            target_asset_id=asset_id,
            target_asset_revision=1,
            asset_type=spec["asset_type"],
            target_entity_id=spec["entity_id"],
            display_name=spec["display_name"],
            review_description_zh=spec["review_zh"],
            image_prompt=authored.image_prompt,
            negative_prompt=authored.negative_prompt,
            prompt_review_zh=authored.review_prompt_zh,
            image_model_id=binding.model_id,
            prompt_skill_id=prompt_skill.id,
            prompt_skill_version=prompt_skill.version,
            prompt_contract=binding.prompt_contract,
            character_visual_design=visual_design,
            character_visual_skill_id=visual_skill.id if visual_design is not None else None,
            character_visual_skill_version=visual_skill.version if visual_design is not None else None,
            character_visual_provider_job_id=visual_provider_job_id,
            reference_media=reference_media,
        ))
        context.checkpoint({"stage": "image-runtime", "generation_sequence": sequence, "generated_assets": index, "total_assets": len(specs), "character_visual_provider_job_ids": character_visual_provider_job_ids, "prompt_provider_job_ids": prompt_provider_job_ids, "provider_job_ids": provider_job_ids}, progress_percent=min(95, 44 + math.floor(index / len(specs) * 51)))
    content = ReplicaAssetImagesContent(target_storyboard_artifact_id=storyboard_artifact.id, target_language=storyboard.target_language, target_region=storyboard.target_region, visual_style=project.visual_style or "写实电影感", assets=assets)
    skill = get_professional_skill(SKILL_ID)
    provenance = AssetImageProvenance(
        target_storyboard_artifact_id=storyboard_artifact.id,
        target_storyboard_revision=storyboard_artifact.revision,
        target_storyboard_fingerprint=storyboard_artifact.input_fingerprint,
        generation_sequence=sequence,
        professional_skill_version=skill.version,
        image_model_id=binding.model_id,
        prompt_skill_id=prompt_skill.id,
        prompt_skill_version=prompt_skill.version,
        prompt_contract=binding.prompt_contract,
        prompt_provider=prompt_provider.provider_name,
        prompt_model=prompt_provider.model_name,
        prompt_provider_job_ids=prompt_provider_job_ids,
        character_visual_skill_id=visual_skill.id,
        character_visual_skill_version=visual_skill.version,
        character_visual_provider_job_ids=character_visual_provider_job_ids,
        provider_job_ids=provider_job_ids,
        image_runtime=runtime.provider_name,
        image_model=runtime.pipeline_model_name,
        generated_by_task_id=task.id,
    )
    return content, provenance


def _claim(db: Session, task_id: str, worker_id: str) -> Task | None:
    task = db.get(Task, task_id)
    if task is None or task.task_type not in {TASK_TYPE, ASSET_PROMPT_TASK_TYPE} or task.status != TaskStatus.QUEUED or task.attempt >= task.max_attempts: return None
    now = utc_now(); result = db.execute(update(Task).where(Task.id == task_id, Task.task_type == task.task_type, Task.status == TaskStatus.QUEUED, Task.attempt < Task.max_attempts).values(status=TaskStatus.RUNNING, attempt=task.attempt + 1, worker_id=worker_id, heartbeat_at=now, started_at=func.coalesce(Task.started_at, now), finished_at=None, updated_at=now))
    if result.rowcount != 1: db.rollback(); return None
    db.commit(); return db.get(Task, task_id)


def _workspace_inputs(db: Session, task: TaskWorkerRead) -> tuple[ReplicaAssetWorkspace, AssetWorkspaceContent, ArtifactNode, ReplicaLocalizedStoryboardContent, list[dict]]:
    workspace = db.scalar(select(ReplicaAssetWorkspace).where(ReplicaAssetWorkspace.project_id == task.project_id))
    storyboard_artifact, storyboard = _load_storyboard(db, task.project_id)
    if workspace is None or workspace.target_storyboard_artifact_id != storyboard_artifact.id:
        raise AppError("ASSET_WORKSPACE_STALE", "资产工作台已经失效，请重新提取", status_code=409)
    content = AssetWorkspaceContent.model_validate(workspace.content_json)
    selected_ids = list(task.checkpoint_json.get("target_asset_ids") or [])
    assets = {asset.target_asset_id: asset for asset in content.assets}
    if not selected_ids or any(asset_id not in assets for asset_id in selected_ids):
        raise AppError("ASSET_WORKSPACE_SELECTION_INVALID", "资产任务选择已经失效", status_code=409)
    all_specs = _entity_specs(storyboard, content.visual_style, _optional_target_bible_characters(db, task.project_id))
    spec_by_asset_id = {_asset_id(task.project_id, spec["entity_id"]): spec for spec in all_specs}
    return workspace, content, storyboard_artifact, storyboard, [spec_by_asset_id[asset_id] for asset_id in selected_ids]


def _run_workspace_prompts(context: TaskExecutionContext, task: TaskWorkerRead) -> None:
    with context.session_factory() as db:
        _, _, storyboard_artifact, _, specs = _workspace_inputs(db, task)
    visual_skill = character_visual_design_skill()
    binding, prompt_skill = selected_image_model_prompt_skill()
    provider = asset_prompt_author_provider()
    for index, spec in enumerate(specs, 1):
        asset_id = _asset_id(task.project_id, spec["entity_id"])
        with context.session_factory() as db:
            workspace, latest, _, _, _ = _workspace_inputs(db, task)
            for asset in latest.assets:
                if asset.target_asset_id == asset_id:
                    asset.prompt_status = "GENERATING"
                    asset.last_error = None
            workspace.content_json = latest.model_dump(mode="json"); workspace.updated_at = utc_now(); db.add(workspace); db.commit()
        visual_design: CharacterVisualDesignPacket | None = None
        if spec["asset_type"] == TargetAssetType.CHARACTER:
            # Persist each character's visual packet before compiling its prompt.
            progress_base = max(4, math.floor((index - 1) / len(specs) * 95))
            visual_designs, _ = _author_character_visual_designs(
                context,
                task,
                storyboard_artifact,
                [spec],
                progress_start=progress_base,
                progress_end=min(94, progress_base + 4),
            )
            visual_design, visual_provider_job_id = visual_designs[spec["entity_id"]]
            with context.session_factory() as db:
                workspace, latest, _, _, _ = _workspace_inputs(db, task)
                current_asset = next(item for item in latest.assets if item.target_asset_id == asset_id)
                current_asset.character_visual_design = visual_design
                current_asset.character_visual_skill_id = visual_skill.id
                current_asset.character_visual_skill_version = visual_skill.version
                current_asset.character_visual_provider_job_id = visual_provider_job_id
                workspace.revision += 1; workspace.content_json = latest.model_dump(mode="json"); workspace.updated_at = utc_now(); db.add(workspace); db.commit()
        # Prompt authoring is deliberately serial.  Each completed asset is
        # committed immediately so the workspace remains useful after an
        # interrupted task, just like sequential image generation.
        dispatch_progress = min(90, max(30, math.floor((index - 1) / len(specs) * 60) + 30))
        context.checkpoint(
            {
                **task.checkpoint_json,
                "active_prompt_asset": asset_id,
                "prompt_asset_count": len(specs),
            },
            progress_percent=dispatch_progress,
        )
        model_prompt_context = _model_prompt_context(spec, visual_design)
        prompt_input = AssetPromptAuthorInput(binding=binding, skill=prompt_skill, assets=(model_prompt_context,))
        payload = {"target_storyboard_artifact_id": storyboard_artifact.id, "asset_id": asset_id, "image_model": binding.model_id, "prompt_skill": [prompt_skill.id, prompt_skill.version], "prompt_contract": binding.prompt_contract, "queue_position": index, "queue_size": len(specs), "target_entity_ids": [spec["entity_id"]], "semantic_payload_fingerprint": _sha(prompt_input.assets), "provider_profile": provider.profile()}
        def _remote(_, current_input=prompt_input):
            result = provider.author(current_input)
            return ProviderDispatchResult(value=result, remote_job_id=result.remote_job_id)
        with context.session_factory() as db:
            _, dispatched = dispatch_provider_call(db, task_id=task.id, provider=provider.provider_name, model=provider.model_name, capability=Capability.ASSET_IMAGE_GENERATION, payload=payload, artifact_id=storyboard_artifact.id, remote_call=_remote)
        result: AssetPromptAuthorResult = dispatched.value
        authored = validate_authored_asset_batch([model_prompt_context], result.content)[spec["entity_id"]]
        with context.session_factory() as db:
            workspace, latest, _, _, _ = _workspace_inputs(db, task)
            prompt_changed = False
            for asset in latest.assets:
                if asset.target_asset_id != asset_id:
                    continue
                if asset.image_prompt and (asset.image_prompt != authored.image_prompt or asset.negative_prompt != authored.negative_prompt): asset.active_generation_id = None; prompt_changed = True
                asset.image_prompt = authored.image_prompt; asset.negative_prompt = authored.negative_prompt; asset.prompt_review_zh = authored.review_prompt_zh
                asset.image_model_id = binding.model_id; asset.prompt_skill_id = prompt_skill.id; asset.prompt_skill_version = prompt_skill.version; asset.prompt_contract = binding.prompt_contract
                asset.prompt_status = "READY"; asset.last_error = None
            if prompt_changed:
                current_assets = _current_artifact(db, task.project_id, ArtifactType.TARGET_ASSETS)
                if current_assets is not None: _mark_stale_with_downstream(db, [current_assets])
            workspace.revision += 1; workspace.content_json = latest.model_dump(mode="json"); workspace.updated_at = utc_now(); db.add(workspace); db.commit()
        context.checkpoint({**task.checkpoint_json, "completed_prompt_assets": index, "prompt_asset_count": len(specs)}, progress_percent=28 + math.floor(index / len(specs) * 67))


def _active_media(asset: AssetWorkspaceEntity) -> list[TargetReferenceMedia]:
    generation = next((item for item in asset.generations if item.generation_id == asset.active_generation_id), None)
    return generation.reference_media if generation is not None else []


def _publish_workspace_if_complete(db: Session, *, task: TaskWorkerRead, workspace: ReplicaAssetWorkspace, content: AssetWorkspaceContent, provider_job_ids: list[str], runtime: ArkSeedreamRuntime | ComfyUIZImageTurboRuntime) -> None:
    if any(not _active_media(asset) for asset in content.assets):
        return
    binding, prompt_skill = selected_image_model_prompt_skill()
    visual_skill = character_visual_design_skill()
    prompt_provider = asset_prompt_author_provider()
    # H3 consumes the adopted reference media, not the historical image-prompt
    # implementation that produced it.  A model/Prompt Skill upgrade must not
    # invalidate a real, intact asset set or force users to pay for a full redraw.
    # Character consistency remains review metadata; hard runtime checks still
    # require the FACE + front FULL_BODY pair for every visible character.
    storyboard = db.get(ArtifactNode, content.target_storyboard_artifact_id)
    if storyboard is None:
        raise AppError("ASSET_WORKSPACE_STALE", "本土化分镜已经失效", status_code=409)
    assets = [
        AssetImageEntity(
            target_asset_id=asset.target_asset_id,
            target_asset_revision=max(1, len(asset.generations)),
            asset_type=asset.asset_type,
            target_entity_id=asset.target_entity_id,
            display_name=asset.display_name,
            review_description_zh=asset.review_description_zh,
            image_prompt=asset.image_prompt or "",
            negative_prompt=asset.negative_prompt,
            prompt_review_zh=asset.prompt_review_zh,
            image_model_id=asset.image_model_id,
            prompt_skill_id=asset.prompt_skill_id,
            prompt_skill_version=asset.prompt_skill_version,
            prompt_contract=asset.prompt_contract,
            character_visual_design=asset.character_visual_design,
            character_visual_skill_id=asset.character_visual_skill_id,
            character_visual_skill_version=asset.character_visual_skill_version,
            character_visual_provider_job_id=asset.character_visual_provider_job_id,
            reference_media=_active_media(asset),
        )
        for asset in content.assets
    ]
    formal = ReplicaAssetImagesContent(target_storyboard_artifact_id=storyboard.id, target_language=content.target_language, target_region=content.target_region, visual_style=content.visual_style, assets=assets)
    sequence = _generation_sequence(db, task.project_id, storyboard.id)
    character_visual_provider_job_ids = list(dict.fromkeys(
        asset.character_visual_provider_job_id
        for asset in content.assets
        if asset.character_visual_provider_job_id
    ))
    active_image_provider_job_ids = list(dict.fromkeys(
        media.provider_job_id
        for asset in content.assets
        for media in _active_media(asset)
        if media.provider_job_id
    ))
    provenance = AssetImageProvenance(
        target_storyboard_artifact_id=storyboard.id,
        target_storyboard_revision=storyboard.revision,
        target_storyboard_fingerprint=storyboard.input_fingerprint,
        generation_sequence=sequence,
        professional_skill_version=get_professional_skill(SKILL_ID).version,
        image_model_id=binding.model_id,
        prompt_skill_id=prompt_skill.id,
        prompt_skill_version=prompt_skill.version,
        prompt_contract=binding.prompt_contract,
        prompt_provider=prompt_provider.provider_name,
        prompt_model=prompt_provider.model_name,
        character_visual_skill_id=visual_skill.id,
        character_visual_skill_version=visual_skill.version,
        character_visual_provider_job_ids=character_visual_provider_job_ids,
        provider_job_ids=active_image_provider_job_ids or provider_job_ids,
        image_runtime=runtime.provider_name,
        image_model=runtime.pipeline_model_name,
        generated_by_task_id=task.id,
    )
    has_consistency_failure = any(asset.consistency_status == "FAIL" for asset in formal.assets)
    candidate_status = CandidateStatus.FAILED_CONSISTENCY.value if has_consistency_failure else CandidateStatus.NEEDS_REVIEW.value
    candidate = ReplicaAssetImageCandidate(project_id=task.project_id, target_storyboard_artifact_id=storyboard.id, generated_by_task_id=task.id, generation_sequence=sequence, input_fingerprint=_sha({"workspace": workspace.id, "revision": workspace.revision, "content": formal.model_dump(mode="json")}), schema_version=ASSET_IMAGES_SCHEMA_VERSION, content_json=formal.model_dump(mode="json"), provenance_json=provenance.model_dump(mode="json"), review_status=candidate_status)
    if has_consistency_failure:
        candidate.review_reason = "人物一致性检测失败，保留候选结果，等待重新生成该资产。"
    db.add(candidate); db.flush()
    if not has_consistency_failure:
        _promote_asset_image_candidate(db, project_id=task.project_id, candidate=candidate, reviewed_by="SYSTEM_AUTO_PUBLISH", review_reason="所选图片生成完成后自动采用；全部资产齐备后发布完整资产集。")


def _run_workspace_images(context: TaskExecutionContext, task: TaskWorkerRead) -> None:
    runtime = asset_image_runtime()
    provider_job_ids: list[str] = []
    with context.session_factory() as db:
        _, content, storyboard_artifact, _, specs = _workspace_inputs(db, task)
        selected_ids = list(task.checkpoint_json.get("target_asset_ids") or [])
        assets = {asset.target_asset_id: asset for asset in content.assets}
    binding, prompt_skill = selected_image_model_prompt_skill()
    visual_skill = character_visual_design_skill()
    for index, (asset_id, spec) in enumerate(zip(selected_ids, specs, strict=True), 1):
        asset = assets[asset_id]
        if asset.asset_type == TargetAssetType.CHARACTER and (
            asset.character_visual_design is None
            or asset.character_visual_skill_id != visual_skill.id
            or asset.character_visual_skill_version != visual_skill.version
        ):
            raise AppError(
                "ASSET_IMAGE_CHARACTER_VISUAL_DESIGN_REQUIRED",
                "人物图片生成必须使用当前版本 Character Visual Design，请先重新生成提示词",
                status_code=409,
                details={"target_asset_id": asset_id},
            )
        with context.session_factory() as db:
            workspace, latest, _, _, _ = _workspace_inputs(db, task)
            current_asset = next(item for item in latest.assets if item.target_asset_id == asset_id)
            current_asset.image_status = "GENERATING"; current_asset.last_error = None
            workspace.content_json = latest.model_dump(mode="json"); workspace.updated_at = utc_now(); db.add(workspace); db.commit()
        payload = {"target_storyboard_artifact_id": storyboard_artifact.id, "asset_id": asset_id, "target_entity_id": asset.target_entity_id, "asset_type": asset.asset_type.value, "prompt_skill": [prompt_skill.id, prompt_skill.version, binding.prompt_contract], "prompt_sha256": _sha(asset.image_prompt), "negative_prompt_sha256": _sha(asset.negative_prompt), "width": asset.width, "height": asset.height, "runtime": runtime.profile(), "queue_position": index, "queue_size": len(selected_ids)}
        with context.session_factory() as db:
            model = runtime.character_pipeline_model_name if asset.asset_type == TargetAssetType.CHARACTER else runtime.model_name
            reused = _reusable_generated_image(db, task=task, asset_id=asset_id, job_payload=payload)
            if reused is not None:
                job, generated = reused
            else:
                def _remote(job):
                    if asset.asset_type == TargetAssetType.CHARACTER:
                        generated = runtime.generate_character_sheet(project_id=task.project_id, task_id=task.id, asset_id=asset_id, prompt=asset.image_prompt or "", negative_prompt=asset.negative_prompt)
                    else:
                        generated = runtime.generate(project_id=task.project_id, task_id=task.id, asset_id=asset_id, prompt=asset.image_prompt or "", negative_prompt=asset.negative_prompt, width=asset.width, height=asset.height)
                    return ProviderDispatchResult(value=generated, remote_job_id=generated.remote_job_id)
                job, dispatched = dispatch_provider_call(db, task_id=task.id, provider=runtime.provider_name, model=model, capability=Capability.ASSET_IMAGE_GENERATION, payload=payload, artifact_id=storyboard_artifact.id, remote_call=_remote)
                generated = dispatched.value
        consistency_report: dict[str, object] = {}
        consistency_status: str | None = None
        if asset.asset_type == TargetAssetType.CHARACTER:
            consistency = validate_character_asset_identity(
                str(get_settings().artifact_root / generated.storage_relpath)
            )
            consistency_report = dict(consistency.checks)
            consistency_report["reason"] = consistency.reason
            consistency_status = "PASS" if consistency.passed else "FAIL"
            # 一致性失败保留候选结果，不中断整个资产任务。
            # 后续由 consistency_status 与发布门禁阻止进入正式资产。
        provider_job_ids.append(job.id)
        reference_id = f"ref:{hashlib.sha256(f'{asset_id}|{generated.sha256}'.encode()).hexdigest()[:24]}"
        role = ReferenceMediaRole.OTHER if asset.asset_type == TargetAssetType.CHARACTER else ReferenceMediaRole.LAYOUT if asset.asset_type == TargetAssetType.SCENE else ReferenceMediaRole.DETAIL
        media = TargetReferenceMedia(reference_id=reference_id, role=role, uri=f"/api/v3/projects/{task.project_id}/asset-images/media/{reference_id}", mime_type=generated.mime_type, sha256=generated.sha256, width=generated.width, height=generated.height, provider_job_id=job.id, storage_relpath=generated.storage_relpath)
        references = [media]
        if asset.asset_type == TargetAssetType.CHARACTER:
            references.extend(_character_identity_reference_media(project_id=task.project_id, asset_id=asset_id, generated=generated, provider_job_id=job.id))
            reference_paths = {
                media.role.value: media.storage_relpath
                for media in references
                if media.storage_relpath
            }
            consistency = validate_character_reference_set(reference_paths)
            consistency_report.update(consistency.checks)
            consistency_report["reason"] = consistency.reason
            consistency_status = "PASS" if consistency.passed else "FAIL"
            # 参考集合失败时继续保存 workspace candidate，
            # 由 consistency_status=FAIL 标记，禁止 promote。
        generation = AssetWorkspaceGeneration(generation_id=f"gen:{uuid4()}", task_id=task.id, created_at=utc_now(), reference_media=references)
        with context.session_factory() as db:
            workspace, latest, _, _, _ = _workspace_inputs(db, task)
            latest_asset = next(item for item in latest.assets if item.target_asset_id == asset_id)
            latest_asset.generations.append(generation); latest_asset.active_generation_id = generation.generation_id; latest_asset.image_status = "READY"; latest_asset.last_error = None
            latest_asset.consistency_status = consistency_status
            latest_asset.consistency_report = consistency_report
            workspace.revision += 1; workspace.content_json = latest.model_dump(mode="json"); workspace.updated_at = utc_now(); db.add(workspace); db.commit()
        context.checkpoint({**task.checkpoint_json, "completed_assets": index, "total_assets": len(selected_ids), "provider_job_ids": provider_job_ids}, progress_percent=math.floor(index / len(selected_ids) * 95))
    with context.session_factory() as db:
        workspace, latest, _, _, _ = _workspace_inputs(db, task)
        _publish_workspace_if_complete(db, task=task, workspace=workspace, content=latest, provider_job_ids=provider_job_ids, runtime=runtime)
        db.commit()


def run_asset_images_task(session_factory: sessionmaker[Session], task_id: str) -> None:
    worker_id = f"asset-images-{uuid4()}"
    with session_factory() as db:
        claimed = _claim(db, task_id, worker_id)
        if claimed is None: return
        snapshot = TaskWorkerRead.model_validate(claimed)
    context = TaskExecutionContext(session_factory=session_factory, task_id=snapshot.id, worker_id=worker_id)
    operation = str((snapshot.checkpoint_json or {}).get("operation") or "")
    if operation in {"prompts", "images"}:
        try:
            if operation == "prompts": _run_workspace_prompts(context, snapshot)
            else: _run_workspace_images(context, snapshot)
            with session_factory() as db: mark_task_succeeded(db, snapshot.id, worker_id=worker_id)
        except TaskCancelled:
            with session_factory() as db:
                task = db.get(Task, snapshot.id)
                if task is not None:
                    reconcile_asset_workspace_task_state(db, task)
                    db.commit()
        except AppError as exc:
            with session_factory() as db:
                failed = mark_task_failed(db, snapshot.id, safe_error=f"视觉资产任务失败（{exc.code}）：{exc.message}", worker_id=worker_id)
                reconcile_asset_workspace_task_state(db, failed)
                db.commit()
        except Exception as exc:
            with session_factory() as db:
                failed = mark_task_failed(db, snapshot.id, safe_error=f"视觉资产任务失败（{type(exc).__name__}）", worker_id=worker_id)
                reconcile_asset_workspace_task_state(db, failed)
                db.commit()
        return
    try: content, provenance = _execute(context, snapshot)
    except TaskCancelled: return
    except AppError as exc:
        with session_factory() as db: mark_task_failed(db, snapshot.id, safe_error=f"资产图生成失败（{exc.code}）：{exc.message}", worker_id=worker_id)
        return
    except Exception as exc:
        with session_factory() as db: mark_task_failed(db, snapshot.id, safe_error=f"资产图生成失败（{type(exc).__name__}）", worker_id=worker_id)
        return
    try:
        with session_factory() as db:
            task = db.get(Task, snapshot.id)
            if task is None or task.status != TaskStatus.RUNNING or task.worker_id != worker_id:
                return
            if task.cancel_requested:
                mark_task_succeeded(db, snapshot.id, worker_id=worker_id)
                return
            candidate = db.scalar(select(ReplicaAssetImageCandidate).where(ReplicaAssetImageCandidate.generated_by_task_id == snapshot.id))
            if candidate is None:
                candidate = ReplicaAssetImageCandidate(
                    project_id=snapshot.project_id,
                    target_storyboard_artifact_id=content.target_storyboard_artifact_id,
                    generated_by_task_id=snapshot.id,
                    generation_sequence=provenance.generation_sequence,
                    input_fingerprint=snapshot.input_fingerprint,
                    schema_version=ASSET_IMAGES_SCHEMA_VERSION,
                    content_json=content.model_dump(mode="json"),
                    provenance_json=provenance.model_dump(mode="json"),
                    review_status=CandidateStatus.NEEDS_REVIEW.value,
                )
                db.add(candidate)
                db.flush()
            if candidate.review_status == CandidateStatus.NEEDS_REVIEW.value:
                _promote_asset_image_candidate(
                    db,
                    project_id=snapshot.project_id,
                    candidate=candidate,
                    reviewed_by="SYSTEM_AUTO_PUBLISH",
                    review_reason="资产图生成完成并通过正式 reference_media 与上游一致性校验后自动采用。",
                )
            mark_task_succeeded(db, snapshot.id, worker_id=worker_id)
    except AppError as exc:
        with session_factory() as db:
            task = db.get(Task, snapshot.id)
            if task is not None and task.status == TaskStatus.RUNNING and task.worker_id == worker_id:
                mark_task_failed(db, snapshot.id, safe_error=f"资产图发布失败（{exc.code}）：{exc.message}", worker_id=worker_id)
    except Exception as exc:
        with session_factory() as db:
            task = db.get(Task, snapshot.id)
            if task is not None and task.status == TaskStatus.RUNNING and task.worker_id == worker_id:
                mark_task_failed(db, snapshot.id, safe_error=f"资产图发布失败（{type(exc).__name__}）", worker_id=worker_id)


def reconcile_asset_workspace_task_state(db: Session, task: Task) -> None:
    """Keep Task terminal/requeue state and per-asset workspace state consistent."""
    if task.task_type not in {ASSET_PROMPT_TASK_TYPE, TASK_TYPE}:
        return
    operation = str((task.checkpoint_json or {}).get("operation") or "")
    if operation not in {"prompts", "images"}:
        # Compatibility recovery for workspace tasks created before their
        # operation checkpoint was made atomic. They can only be terminal here;
        # clear unfinished card states without touching any READY backfill.
        if task.status not in {TaskStatus.CANCELLED, TaskStatus.INTERRUPTED}:
            return
        workspace = db.scalar(select(ReplicaAssetWorkspace).where(ReplicaAssetWorkspace.project_id == task.project_id))
        if workspace is None:
            return
        content = AssetWorkspaceContent.model_validate(workspace.content_json)
        status_field = "prompt_status" if task.task_type == ASSET_PROMPT_TASK_TYPE else "image_status"
        changed = False
        for asset in content.assets:
            if getattr(asset, status_field) not in {"QUEUED", "GENERATING"}:
                continue
            # A legacy all-in-one task may have queued regeneration for an asset that already
            # owns a valid prompt/image.  Cancelling or interrupting that task must reveal the
            # last committed result instead of falsely downgrading it to NOT_STARTED.
            if status_field == "prompt_status" and asset.image_prompt:
                asset.prompt_status = "READY"
            elif status_field == "image_status" and _active_media(asset):
                asset.image_status = "READY"
            else:
                setattr(asset, status_field, "NOT_STARTED")
            asset.last_error = "旧任务已中断，请重新发起"
            changed = True
        if changed:
            workspace.revision += 1
            workspace.content_json = content.model_dump(mode="json")
            workspace.updated_at = utc_now()
            db.add(workspace)
        return
    selected_ids = set((task.checkpoint_json or {}).get("target_asset_ids") or [])
    if not selected_ids:
        return
    workspace = db.scalar(select(ReplicaAssetWorkspace).where(ReplicaAssetWorkspace.project_id == task.project_id))
    if workspace is None:
        return
    content = AssetWorkspaceContent.model_validate(workspace.content_json)
    if task.status == TaskStatus.FAILED:
        error = task.last_error or "视觉资产任务失败，请重新生成"
        mutable_statuses = {"QUEUED", "GENERATING", "FAILED"}
    elif task.status in {TaskStatus.CANCELLED, TaskStatus.INTERRUPTED}:
        next_status = "NOT_STARTED"
        error = "已停止生成，请重新发起" if task.status == TaskStatus.CANCELLED else "后端工作进程中断，请重新生成"
        mutable_statuses = {"QUEUED", "GENERATING"}
    elif task.status == TaskStatus.QUEUED:
        next_status = "QUEUED"
        error = None
        mutable_statuses = {"FAILED", "NOT_STARTED", "QUEUED"}
    else:
        return
    changed = False
    for asset in content.assets:
        if asset.target_asset_id not in selected_ids:
            continue
        current_status = asset.prompt_status if operation == "prompts" else asset.image_status
        if current_status not in mutable_statuses:
            continue
        if task.status == TaskStatus.FAILED:
            active_key = "active_prompt_asset" if operation == "prompts" else "active_image_asset"
            active_asset_id = str((task.checkpoint_json or {}).get(active_key) or "")
            is_failed_asset = asset.target_asset_id == active_asset_id or (not active_asset_id and current_status == "GENERATING")
            if operation == "prompts":
                asset.prompt_status = "FAILED" if is_failed_asset else ("READY" if asset.image_prompt else "NOT_STARTED")
            else:
                asset.image_status = "FAILED" if is_failed_asset else ("READY" if _active_media(asset) else "NOT_STARTED")
            asset.last_error = error if is_failed_asset else None
        elif operation == "prompts":
            asset.prompt_status = "READY" if next_status == "NOT_STARTED" and asset.image_prompt else next_status
            asset.last_error = error
        else:
            asset.image_status = "READY" if next_status == "NOT_STARTED" and _active_media(asset) else next_status
            asset.last_error = error
        changed = True
    if changed:
        workspace.revision += 1
        workspace.content_json = content.model_dump(mode="json")
        workspace.updated_at = utc_now()
        db.add(workspace)


def reconcile_interrupted_asset_workspace_tasks(db: Session, tasks: list[Task]) -> None:
    """Reconcile persisted asset flags for tasks interrupted during backend restart."""
    for task in tasks:
        reconcile_asset_workspace_task_state(db, task)
    db.commit()


def _candidate_read(row: ReplicaAssetImageCandidate) -> AssetImageCandidateRead:
    return AssetImageCandidateRead(id=row.id, project_id=row.project_id, generation_sequence=row.generation_sequence, review_status=CandidateStatus(row.review_status), review_reason=row.review_reason, reviewed_at=row.reviewed_at, created_at=row.created_at, content=ReplicaAssetImagesContent.model_validate(row.content_json), provenance=AssetImageProvenance.model_validate(row.provenance_json))


def list_asset_image_candidates(db: Session, project_id: str) -> list[AssetImageCandidateRead]:
    get_project(db, project_id)
    return [_candidate_read(row) for row in db.scalars(select(ReplicaAssetImageCandidate).where(ReplicaAssetImageCandidate.project_id == project_id).order_by(ReplicaAssetImageCandidate.created_at.desc())).all()]


def _content_matches_current_asset_contract(content: ReplicaAssetImagesContent) -> bool:
    """Return whether adopted media can safely be consumed by the H3 Ref2VA chain.

    Image model and Prompt Skill versions describe provenance, not the validity of
    already-generated media.  They must stay visible for audit but are not a
    redraw gate.  H3 does require a managed reference file for every asset and
    dedicated FACE + front FULL_BODY references for characters.
    """
    if not content.assets:
        return False
    for asset in content.assets:
        if not asset.reference_media or any(
            not media.storage_relpath or not media.sha256
            for media in asset.reference_media
        ):
            return False
        if asset.asset_type == TargetAssetType.CHARACTER:
            roles = {media.role for media in asset.reference_media}
            if ReferenceMediaRole.FACE not in roles or not {
                ReferenceMediaRole.FULL_BODY,
                ReferenceMediaRole.FULL_BODY_FRONT,
            }.intersection(roles):
                return False
    return True


def get_asset_images(db: Session, project_id: str) -> AssetImagesRead:
    get_project(db, project_id); current = _current_artifact(db, project_id, ArtifactType.TARGET_ASSETS); latest = current or _latest_artifact(db, project_id, ArtifactType.TARGET_ASSETS)
    if latest is None: return AssetImagesRead(project_id=project_id, status=ResultStatus.NOT_BUILT)
    row = db.scalar(select(ReplicaAssetImageRevision).where(ReplicaAssetImageRevision.artifact_id == latest.id))
    if row is None: return AssetImagesRead(project_id=project_id, status=ResultStatus.NOT_BUILT)
    content = ReplicaAssetImagesContent.model_validate(row.content_json)
    contract_current = current is not None and _content_matches_current_asset_contract(content)
    return AssetImagesRead(project_id=project_id, status=ResultStatus.CURRENT if contract_current else ResultStatus.STALE, artifact_id=latest.id, revision=latest.revision, input_fingerprint=latest.input_fingerprint, content=content, provenance=row.provenance_json)


def _find_reference(db: Session, project_id: str, reference_id: str) -> TargetReferenceMedia:
    workspace = db.scalar(select(ReplicaAssetWorkspace).where(ReplicaAssetWorkspace.project_id == project_id))
    if workspace is not None:
        content = AssetWorkspaceContent.model_validate(workspace.content_json)
        for asset in content.assets:
            for generation in asset.generations:
                for media in generation.reference_media:
                    if media.reference_id == reference_id: return media
    rows = db.scalars(select(ReplicaAssetImageCandidate).where(ReplicaAssetImageCandidate.project_id == project_id).order_by(ReplicaAssetImageCandidate.created_at.desc())).all()
    for row in rows:
        content = ReplicaAssetImagesContent.model_validate(row.content_json)
        for asset in content.assets:
            for media in asset.reference_media:
                if media.reference_id == reference_id: return media
    raise AppError("ASSET_IMAGE_MEDIA_NOT_FOUND", "资产图媒体不存在", status_code=404)


def asset_image_media_path(db: Session, project_id: str, reference_id: str) -> Path:
    media = _find_reference(db, project_id, reference_id)
    if not media.storage_relpath: raise AppError("ASSET_IMAGE_MEDIA_PATH_MISSING", "资产图缺少受管存储路径", status_code=500)
    root = get_settings().artifact_root.resolve(); path = (root / media.storage_relpath).resolve()
    if root not in path.parents or not path.is_file(): raise AppError("ASSET_IMAGE_MEDIA_NOT_FOUND", "资产图文件不存在", status_code=404)
    if _file_sha(path) != media.sha256: raise AppError("ASSET_IMAGE_MEDIA_HASH_MISMATCH", "资产图文件 hash 与正式记录不一致", status_code=409)
    return path


def _promote_asset_image_candidate(
    db: Session,
    *,
    project_id: str,
    candidate: ReplicaAssetImageCandidate,
    reviewed_by: str,
    review_reason: str,
) -> tuple[ArtifactNode, ReplicaAssetImagesContent, dict]:
    project = get_project(db, project_id)
    if candidate is None or candidate.project_id != project_id: raise AppError("ASSET_IMAGE_CANDIDATE_NOT_FOUND", "资产图候选不存在", status_code=404)
    if candidate.review_status != CandidateStatus.NEEDS_REVIEW.value: raise AppError("ASSET_IMAGE_CANDIDATE_NOT_REVIEWABLE", "资产图候选当前不可审核", status_code=409)
    storyboard = _current_artifact(db, project_id, ArtifactType.TARGET_STORYBOARD)
    if storyboard is None or storyboard.id != candidate.target_storyboard_artifact_id: raise AppError("ASSET_IMAGE_REVIEW_STALE", "本土化分镜已经更新，请重新生成资产图", status_code=409)
    content = ReplicaAssetImagesContent.model_validate(candidate.content_json)
    if any(not asset.reference_media for asset in content.assets): raise AppError("ASSET_IMAGE_REFERENCE_MISSING", "正式资产图禁止存在无 reference_media 的资产", status_code=409)
    previous = _current_artifact(db, project_id, ArtifactType.TARGET_ASSETS); latest = _latest_artifact(db, project_id, ArtifactType.TARGET_ASSETS)
    if previous: _mark_stale_with_downstream(db, [previous])
    skill = get_professional_skill(SKILL_ID)
    artifact = ArtifactNode(project_id=project_id, artifact_type=ArtifactType.TARGET_ASSETS.value, namespace=ArtifactNamespace.TARGET, label="目标资产图", revision=(latest.revision if latest else 0)+1, input_fingerprint=_sha({"candidate": candidate.input_fingerprint, "content": content.model_dump(mode="json")}), skill_id=skill.id, skill_version=skill.version, validity=ArtifactValidity.CURRENT, is_current=True, metadata_json={"schema_version": ASSET_IMAGES_SCHEMA_VERSION, "target_storyboard_artifact_id": storyboard.id, "asset_count": len(content.assets), "reference_media_count": sum(len(x.reference_media) for x in content.assets)})
    reviewed_at = utc_now(); provenance = dict(candidate.provenance_json); provenance.update({"candidate_id": candidate.id, "reviewed_by": reviewed_by, "reviewed_at": reviewed_at.isoformat(), "review_reason": review_reason, "supersedes_artifact_id": latest.id if latest else None})
    db.add(artifact); db.flush(); db.add(ReplicaAssetImageRevision(project_id=project_id, artifact_id=artifact.id, target_storyboard_artifact_id=storyboard.id, candidate_id=candidate.id, generated_by_task_id=candidate.generated_by_task_id, schema_version=ASSET_IMAGES_SCHEMA_VERSION, content_json=content.model_dump(mode="json"), provenance_json=provenance)); db.add(ArtifactEdge(project_id=project_id, source_node_id=storyboard.id, target_node_id=artifact.id, relation_type=ArtifactRelationType.DERIVED_FROM))
    if latest: db.add(ArtifactEdge(project_id=project_id, source_node_id=artifact.id, target_node_id=latest.id, relation_type=ArtifactRelationType.SUPERSEDES))
    for other in db.scalars(select(ReplicaAssetImageCandidate).where(ReplicaAssetImageCandidate.project_id == project_id, ReplicaAssetImageCandidate.review_status == CandidateStatus.NEEDS_REVIEW.value, ReplicaAssetImageCandidate.id != candidate.id)).all(): other.review_status=CandidateStatus.SUPERSEDED.value; other.review_reason="A newer asset image candidate was accepted."; other.reviewed_at=reviewed_at; db.add(other)
    candidate.review_status=CandidateStatus.ACCEPTED.value; candidate.review_reason=review_reason; candidate.reviewed_at=reviewed_at; db.add(candidate); _invalidate_project_plan(db, project)
    return artifact, content, provenance


def accept_asset_image_candidate(db: Session, *, project_id: str, candidate_id: str, command: PipelineReviewCommand) -> AssetImagesRead:
    candidate = db.get(ReplicaAssetImageCandidate, candidate_id)
    if candidate is None or candidate.project_id != project_id: raise AppError("ASSET_IMAGE_CANDIDATE_NOT_FOUND", "资产图候选不存在", status_code=404)
    if candidate.target_storyboard_artifact_id != command.expected_upstream_artifact_id or candidate.generation_sequence != command.expected_generation_sequence: raise AppError("ASSET_IMAGE_REVIEW_STALE", "资产图审核输入已经变化", status_code=409)
    artifact, content, provenance = _promote_asset_image_candidate(db, project_id=project_id, candidate=candidate, reviewed_by="USER_EXPLICIT_ACTION", review_reason=command.reason)
    db.commit(); db.refresh(artifact)
    return AssetImagesRead(project_id=project_id, status=ResultStatus.CURRENT, artifact_id=artifact.id, revision=artifact.revision, input_fingerprint=artifact.input_fingerprint, content=content, provenance=provenance)


def reject_asset_image_candidate(db: Session, *, project_id: str, candidate_id: str, command: PipelineReviewCommand) -> AssetImageCandidateRead:
    get_project(db, project_id); candidate=db.get(ReplicaAssetImageCandidate,candidate_id)
    if candidate is None or candidate.project_id != project_id: raise AppError("ASSET_IMAGE_CANDIDATE_NOT_FOUND", "资产图候选不存在", status_code=404)
    if candidate.review_status != CandidateStatus.NEEDS_REVIEW.value: raise AppError("ASSET_IMAGE_CANDIDATE_NOT_REVIEWABLE", "资产图候选当前不可审核", status_code=409)
    candidate.review_status=CandidateStatus.REJECTED.value; candidate.review_reason=command.reason; candidate.reviewed_at=utc_now(); db.add(candidate); db.commit(); db.refresh(candidate); return _candidate_read(candidate)
