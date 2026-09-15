import hashlib
import json
import math
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from PIL import Image
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
    MAX_ASSET_PROMPT_BATCH_SIZE,
    AssetPromptAuthorInput,
    AssetPromptAuthorResult,
    asset_prompt_author_provider,
    validate_authored_asset_batch,
)
from app.replica_pipeline.image_model_skills import selected_image_model_prompt_skill
from app.replica_pipeline.models import ReplicaAssetImageCandidate, ReplicaAssetImageRevision, ReplicaLocalizedStoryboardRevision
from app.replica_pipeline.schemas import (
    ASSET_IMAGES_SCHEMA_VERSION,
    AssetImageCandidateRead,
    AssetImageEntity,
    AssetImageProvenance,
    AssetImagesRead,
    CandidateStatus,
    PipelineReviewCommand,
    ReplicaAssetImagesContent,
    ReplicaLocalizedStoryboardContent,
    ResultStatus,
)
from app.skills.models import ArtifactType, Capability
from app.skills.professional import get_professional_skill
from app.target_assets.schemas import ReferenceMediaRole, TargetAssetType, TargetReferenceMedia
from app.workflow.models import ProviderJob, ProviderJobStatus, Task, TaskStatus
from app.workflow.provider_service import ProviderDispatchResult, dispatch_provider_call, provider_payload_fingerprint
from app.workflow.schemas import TaskCommandCreate, TaskWorkerRead
from app.workflow.task_service import TaskCancelled, create_task_from_command, mark_task_failed, mark_task_succeeded
from app.workflow.worker import TaskExecutionContext


TASK_TYPE = "replica.asset-images"
SKILL_ID = "asset-image-generation"
DEFAULT_UNET = "z_image_turbo_bf16.safetensors"
DEFAULT_CLIP = "qwen_3_4b.safetensors"
DEFAULT_VAE = "ae.safetensors"
CHARACTER_WIDTH = 1280
CHARACTER_HEIGHT = 736
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


class ComfyUIZImageTurboRuntime:
    provider_name = "local-comfyui"
    _required_nodes = {
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

    def __init__(self):
        settings = get_settings()
        self.settings = settings
        self.base_url = settings.p16_h3_comfyui_base_url.rstrip("/")
        self.model_name = DEFAULT_UNET
        self.clip_name = DEFAULT_CLIP
        self.vae_name = DEFAULT_VAE
        self.timeout_seconds = 1800.0
        self.poll_interval = 1.0

    def profile(self) -> dict:
        return {
            "provider": self.provider_name,
            "base_url": self.base_url,
            "model": self.model_name,
            "clip": self.clip_name,
            "vae": self.vae_name,
            "workflow": "z-image-turbo-t2i-v1",
            "steps": 8,
            "sampler": "res_multistep",
            "scheduler": "simple",
            "model_sampling": "ModelSamplingAuraFlow:shift=3.0",
            "negative_conditioning": "zeroed-with-inline-hard-exclusions",
        }

    @staticmethod
    def _safe_preview(response: httpx.Response) -> str:
        try: text = " ".join(response.text.split())
        except Exception: return "<unreadable body>"
        return text[:400] if text else "<empty body>"

    def assert_ready(self) -> None:
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
                missing_nodes = sorted(self._required_nodes - set(nodes))
                if missing_nodes:
                    raise AppError("ASSET_IMAGE_RUNTIME_INCOMPATIBLE", "ComfyUI 缺少 Z-Image Turbo 所需节点：" + "、".join(missing_nodes), status_code=502)

                def _options(node_name: str, field: str) -> list[str]:
                    required = ((nodes.get(node_name, {}).get("input") or {}).get("required") or {}).get(field) or []
                    return required[0] if isinstance(required, list) and required and isinstance(required[0], list) else []

                missing_models = [
                    filename
                    for node_name, field, filename in (
                        ("UNETLoader", "unet_name", self.model_name),
                        ("CLIPLoader", "clip_name", self.clip_name),
                        ("VAELoader", "vae_name", self.vae_name),
                    )
                    if filename not in _options(node_name, field)
                ]
                if missing_models:
                    raise AppError("ASSET_IMAGE_MODEL_MISSING", "ComfyUI 缺少 Z-Image Turbo 资产图模型文件：" + "、".join(missing_models), status_code=502)
        except AppError: raise
        except (httpx.HTTPError, OSError, ValueError) as exc:
            raise AppError("ASSET_IMAGE_RUNTIME_NOT_READY", f"无法连接本地 ComfyUI：{self.base_url}", status_code=503) from exc

    def _workflow(self, prompt: str, negative_prompt: str, *, prefix: str, seed: int, width: int, height: int) -> dict:
        execution_prompt = prompt.strip()
        if negative_prompt.strip():
            execution_prompt += f"\n\nHard exclusions — do not include any of the following: {negative_prompt.strip()}"
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


def _entity_specs(content: ReplicaLocalizedStoryboardContent, visual_style: str) -> list[dict]:
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
            "prompt_context": {
                "target_entity_id": item.target_character_id,
                "asset_type": TargetAssetType.CHARACTER.value,
                "display_name": item.display_name,
                "review_definition_zh": review_zh,
                "identity_description_zh": item.identity_description_zh,
                "appearance_description_zh": item.appearance_description_zh,
                "visual_style": visual_style,
                "storyboard_evidence": _evidence(item.target_character_id, TargetAssetType.CHARACTER),
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


def create_asset_images_task(db: Session, *, project_id: str, idempotency_key: str) -> Task:
    project = get_project(db, project_id)
    if project.project_type != ProjectType.REPLICA: raise AppError("ASSET_IMAGES_PROJECT_UNSUPPORTED", "当前五步主生产链只正式支持 REPLICA", status_code=422)
    storyboard_artifact, content = _load_storyboard(db, project_id)
    runtime = ComfyUIZImageTurboRuntime(); runtime.assert_ready()
    binding, prompt_skill = selected_image_model_prompt_skill()
    prompt_provider = asset_prompt_author_provider()
    fingerprint = _sha({
        "storyboard": storyboard_artifact.input_fingerprint,
        "visual_style": project.visual_style,
        "runtime": runtime.profile(),
        "orchestration_skill": get_professional_skill(SKILL_ID).version,
        "prompt_skill": [prompt_skill.id, prompt_skill.version, binding.prompt_contract],
        "prompt_provider": prompt_provider.profile(),
    })
    return create_task_from_command(db, project_id=project_id, idempotency_key=idempotency_key, payload=TaskCommandCreate(task_type=TASK_TYPE, task_name="提取资产、Skill 生成提示词并生成资产图", input_fingerprint=fingerprint, input_artifact_ids=[storyboard_artifact.id], max_attempts=3))


def _generation_sequence(db: Session, project_id: str, storyboard_artifact_id: str) -> int:
    latest = db.scalar(select(func.max(ReplicaAssetImageCandidate.generation_sequence)).where(ReplicaAssetImageCandidate.project_id == project_id, ReplicaAssetImageCandidate.target_storyboard_artifact_id == storyboard_artifact_id))
    return int(latest or 0) + 1


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
    runtime = ComfyUIZImageTurboRuntime()
    with context.session_factory() as db:
        project = get_project(db, task.project_id)
        storyboard_artifact, storyboard = _load_storyboard(db, task.project_id)
        sequence = _generation_sequence(db, task.project_id, storyboard_artifact.id)
    specs = _entity_specs(storyboard, project.visual_style or "写实电影感")
    if not specs: raise AppError("ASSET_IMAGES_EMPTY", "本土化分镜没有可提取的人物、场景或道具", status_code=409)
    binding, prompt_skill = selected_image_model_prompt_skill()
    prompt_provider = asset_prompt_author_provider()
    authored_by_id = {}
    prompt_provider_job_ids: list[str] = []
    prompt_batches = [specs[index:index + MAX_ASSET_PROMPT_BATCH_SIZE] for index in range(0, len(specs), MAX_ASSET_PROMPT_BATCH_SIZE)]
    for batch_index, batch in enumerate(prompt_batches, 1):
        prompt_input = AssetPromptAuthorInput(
            binding=binding,
            skill=prompt_skill,
            assets=tuple(spec["prompt_context"] for spec in batch),
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
        authored_by_id.update(validate_authored_asset_batch([spec["prompt_context"] for spec in batch], prompt_result.content))
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
            progress_percent=min(28, 5 + math.floor(batch_index / len(prompt_batches) * 23)),
        )
    assets: list[AssetImageEntity] = []
    provider_job_ids: list[str] = []
    for index, spec in enumerate(specs, 1):
        asset_id = _asset_id(task.project_id, spec["entity_id"])
        authored = authored_by_id[spec["entity_id"]]
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
                job, dispatched = dispatch_provider_call(db, task_id=task.id, provider=runtime.provider_name, model=runtime.model_name, capability=Capability.ASSET_IMAGE_GENERATION, payload=job_payload, artifact_id=storyboard_artifact.id, remote_call=_remote)
                generated = dispatched.value
        provider_job_ids.append(job.id)
        reference_id = f"ref:{hashlib.sha256(f'{asset_id}|{generated.sha256}'.encode()).hexdigest()[:24]}"
        uri = f"/api/v3/projects/{task.project_id}/asset-images/media/{reference_id}"
        role = ReferenceMediaRole.FULL_BODY if spec["asset_type"] == TargetAssetType.CHARACTER else ReferenceMediaRole.LAYOUT if spec["asset_type"] == TargetAssetType.SCENE else ReferenceMediaRole.DETAIL
        media = TargetReferenceMedia(reference_id=reference_id, role=role, uri=uri, mime_type=generated.mime_type, sha256=generated.sha256, width=generated.width, height=generated.height, provider_job_id=job.id, storage_relpath=generated.storage_relpath)
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
            reference_media=[media],
        ))
        context.checkpoint({"stage": "image-runtime", "generation_sequence": sequence, "generated_assets": index, "total_assets": len(specs), "prompt_provider_job_ids": prompt_provider_job_ids, "provider_job_ids": provider_job_ids}, progress_percent=min(95, 30 + math.floor(index / len(specs) * 65)))
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
        provider_job_ids=provider_job_ids,
        image_runtime=runtime.provider_name,
        image_model=runtime.model_name,
        generated_by_task_id=task.id,
    )
    return content, provenance


def _claim(db: Session, task_id: str, worker_id: str) -> Task | None:
    task = db.get(Task, task_id)
    if task is None or task.task_type != TASK_TYPE or task.status != TaskStatus.QUEUED or task.attempt >= task.max_attempts: return None
    now = utc_now(); result = db.execute(update(Task).where(Task.id == task_id, Task.task_type == TASK_TYPE, Task.status == TaskStatus.QUEUED, Task.attempt < Task.max_attempts).values(status=TaskStatus.RUNNING, attempt=task.attempt + 1, worker_id=worker_id, heartbeat_at=now, started_at=func.coalesce(Task.started_at, now), finished_at=None, updated_at=now))
    if result.rowcount != 1: db.rollback(); return None
    db.commit(); return db.get(Task, task_id)


def run_asset_images_task(session_factory: sessionmaker[Session], task_id: str) -> None:
    worker_id = f"asset-images-{uuid4()}"
    with session_factory() as db:
        claimed = _claim(db, task_id, worker_id)
        if claimed is None: return
        snapshot = TaskWorkerRead.model_validate(claimed)
    context = TaskExecutionContext(session_factory=session_factory, task_id=snapshot.id, worker_id=worker_id)
    try: content, provenance = _execute(context, snapshot)
    except TaskCancelled: return
    except AppError as exc:
        with session_factory() as db: mark_task_failed(db, snapshot.id, safe_error=f"资产图生成失败（{exc.code}）：{exc.message}", worker_id=worker_id)
        return
    except Exception as exc:
        with session_factory() as db: mark_task_failed(db, snapshot.id, safe_error=f"资产图生成失败（{type(exc).__name__}）", worker_id=worker_id)
        return
    with session_factory() as db:
        finished = mark_task_succeeded(db, snapshot.id, worker_id=worker_id)
        if finished.status == TaskStatus.CANCELLED: return
        existing = db.scalar(select(ReplicaAssetImageCandidate).where(ReplicaAssetImageCandidate.generated_by_task_id == snapshot.id))
        if existing is None:
            db.add(ReplicaAssetImageCandidate(project_id=snapshot.project_id, target_storyboard_artifact_id=content.target_storyboard_artifact_id, generated_by_task_id=snapshot.id, generation_sequence=provenance.generation_sequence, input_fingerprint=snapshot.input_fingerprint, schema_version=ASSET_IMAGES_SCHEMA_VERSION, content_json=content.model_dump(mode="json"), provenance_json=provenance.model_dump(mode="json"), review_status=CandidateStatus.NEEDS_REVIEW.value)); db.commit()


def _candidate_read(row: ReplicaAssetImageCandidate) -> AssetImageCandidateRead:
    return AssetImageCandidateRead(id=row.id, project_id=row.project_id, generation_sequence=row.generation_sequence, review_status=CandidateStatus(row.review_status), review_reason=row.review_reason, reviewed_at=row.reviewed_at, created_at=row.created_at, content=ReplicaAssetImagesContent.model_validate(row.content_json), provenance=AssetImageProvenance.model_validate(row.provenance_json))


def list_asset_image_candidates(db: Session, project_id: str) -> list[AssetImageCandidateRead]:
    get_project(db, project_id)
    return [_candidate_read(row) for row in db.scalars(select(ReplicaAssetImageCandidate).where(ReplicaAssetImageCandidate.project_id == project_id).order_by(ReplicaAssetImageCandidate.created_at.desc())).all()]


def get_asset_images(db: Session, project_id: str) -> AssetImagesRead:
    get_project(db, project_id); current = _current_artifact(db, project_id, ArtifactType.TARGET_ASSETS); latest = current or _latest_artifact(db, project_id, ArtifactType.TARGET_ASSETS)
    if latest is None: return AssetImagesRead(project_id=project_id, status=ResultStatus.NOT_BUILT)
    row = db.scalar(select(ReplicaAssetImageRevision).where(ReplicaAssetImageRevision.artifact_id == latest.id))
    if row is None: return AssetImagesRead(project_id=project_id, status=ResultStatus.NOT_BUILT)
    return AssetImagesRead(project_id=project_id, status=ResultStatus.CURRENT if current else ResultStatus.STALE, artifact_id=latest.id, revision=latest.revision, input_fingerprint=latest.input_fingerprint, content=ReplicaAssetImagesContent.model_validate(row.content_json), provenance=row.provenance_json)


def _find_reference(db: Session, project_id: str, reference_id: str) -> TargetReferenceMedia:
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


def accept_asset_image_candidate(db: Session, *, project_id: str, candidate_id: str, command: PipelineReviewCommand) -> AssetImagesRead:
    project = get_project(db, project_id); candidate = db.get(ReplicaAssetImageCandidate, candidate_id)
    if candidate is None or candidate.project_id != project_id: raise AppError("ASSET_IMAGE_CANDIDATE_NOT_FOUND", "资产图候选不存在", status_code=404)
    if candidate.review_status != CandidateStatus.NEEDS_REVIEW.value: raise AppError("ASSET_IMAGE_CANDIDATE_NOT_REVIEWABLE", "资产图候选当前不可审核", status_code=409)
    if candidate.target_storyboard_artifact_id != command.expected_upstream_artifact_id or candidate.generation_sequence != command.expected_generation_sequence: raise AppError("ASSET_IMAGE_REVIEW_STALE", "资产图审核输入已经变化", status_code=409)
    storyboard = _current_artifact(db, project_id, ArtifactType.TARGET_STORYBOARD)
    if storyboard is None or storyboard.id != candidate.target_storyboard_artifact_id: raise AppError("ASSET_IMAGE_REVIEW_STALE", "本土化分镜已经更新，请重新生成资产图", status_code=409)
    content = ReplicaAssetImagesContent.model_validate(candidate.content_json)
    if any(not asset.reference_media for asset in content.assets): raise AppError("ASSET_IMAGE_REFERENCE_MISSING", "正式资产图禁止存在无 reference_media 的资产", status_code=409)
    previous = _current_artifact(db, project_id, ArtifactType.TARGET_ASSETS); latest = _latest_artifact(db, project_id, ArtifactType.TARGET_ASSETS)
    if previous: _mark_stale_with_downstream(db, [previous])
    skill = get_professional_skill(SKILL_ID)
    artifact = ArtifactNode(project_id=project_id, artifact_type=ArtifactType.TARGET_ASSETS.value, namespace=ArtifactNamespace.TARGET, label="目标资产图", revision=(latest.revision if latest else 0)+1, input_fingerprint=_sha({"candidate": candidate.input_fingerprint, "content": content.model_dump(mode="json")}), skill_id=skill.id, skill_version=skill.version, validity=ArtifactValidity.CURRENT, is_current=True, metadata_json={"schema_version": ASSET_IMAGES_SCHEMA_VERSION, "target_storyboard_artifact_id": storyboard.id, "asset_count": len(content.assets), "reference_media_count": sum(len(x.reference_media) for x in content.assets)})
    reviewed_at = utc_now(); provenance = dict(candidate.provenance_json); provenance.update({"candidate_id": candidate.id, "reviewed_by": "USER_EXPLICIT_ACTION", "reviewed_at": reviewed_at.isoformat(), "review_reason": command.reason, "supersedes_artifact_id": latest.id if latest else None})
    db.add(artifact); db.flush(); db.add(ReplicaAssetImageRevision(project_id=project_id, artifact_id=artifact.id, target_storyboard_artifact_id=storyboard.id, candidate_id=candidate.id, generated_by_task_id=candidate.generated_by_task_id, schema_version=ASSET_IMAGES_SCHEMA_VERSION, content_json=content.model_dump(mode="json"), provenance_json=provenance)); db.add(ArtifactEdge(project_id=project_id, source_node_id=storyboard.id, target_node_id=artifact.id, relation_type=ArtifactRelationType.DERIVED_FROM))
    if latest: db.add(ArtifactEdge(project_id=project_id, source_node_id=artifact.id, target_node_id=latest.id, relation_type=ArtifactRelationType.SUPERSEDES))
    for other in db.scalars(select(ReplicaAssetImageCandidate).where(ReplicaAssetImageCandidate.project_id == project_id, ReplicaAssetImageCandidate.review_status == CandidateStatus.NEEDS_REVIEW.value, ReplicaAssetImageCandidate.id != candidate.id)).all(): other.review_status=CandidateStatus.SUPERSEDED.value; other.review_reason="A newer asset image candidate was accepted."; other.reviewed_at=reviewed_at; db.add(other)
    candidate.review_status=CandidateStatus.ACCEPTED.value; candidate.review_reason=command.reason; candidate.reviewed_at=reviewed_at; db.add(candidate); _invalidate_project_plan(db, project); db.commit(); db.refresh(artifact)
    return AssetImagesRead(project_id=project_id, status=ResultStatus.CURRENT, artifact_id=artifact.id, revision=artifact.revision, input_fingerprint=artifact.input_fingerprint, content=content, provenance=provenance)


def reject_asset_image_candidate(db: Session, *, project_id: str, candidate_id: str, command: PipelineReviewCommand) -> AssetImageCandidateRead:
    get_project(db, project_id); candidate=db.get(ReplicaAssetImageCandidate,candidate_id)
    if candidate is None or candidate.project_id != project_id: raise AppError("ASSET_IMAGE_CANDIDATE_NOT_FOUND", "资产图候选不存在", status_code=404)
    if candidate.review_status != CandidateStatus.NEEDS_REVIEW.value: raise AppError("ASSET_IMAGE_CANDIDATE_NOT_REVIEWABLE", "资产图候选当前不可审核", status_code=409)
    candidate.review_status=CandidateStatus.REJECTED.value; candidate.review_reason=command.reason; candidate.reviewed_at=utc_now(); db.add(candidate); db.commit(); db.refresh(candidate); return _candidate_read(candidate)
