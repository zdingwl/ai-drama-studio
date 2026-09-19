"""SCRIPT_TO_DRAMA production runtime.

This module is intentionally isolated from Replica persistence/API contracts. It only reuses
model adapters/runtimes whose input/output contracts are generic (image runtime, image/video
Prompt Skills, H3 provider, ffprobe and the shared Task/ProviderJob infrastructure).
"""

import hashlib
import json
import math
import subprocess
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactEdge, ArtifactNode
from app.artifacts.service import _invalidate_project_plan, _mark_stale_with_downstream
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.time import utc_now
from app.p15.schemas import GenerationAudioMode, GenerationSegment, H3ReferenceCondition
from app.p16.media import duration_tolerance_us, probe_video, sha256_file
from app.p16.provider import build_h3_generation_provider
from app.projects.enums import ProjectType
from app.projects.service import get_project
from app.replica_pipeline.asset_images import (
    CHARACTER_PANEL_HEIGHT,
    CHARACTER_PANEL_WIDTH,
    SCENE_HEIGHT,
    SCENE_WIDTH,
    PROP_HEIGHT,
    PROP_WIDTH,
    asset_image_runtime,
)
from app.replica_pipeline.image_model_skills import selected_image_model_prompt_skill
from app.replica_pipeline.video_model_skills import selected_video_model_prompt_skill
from app.script_localization.providers import ScriptLocalizationProvider
from app.script_to_drama.models import ScriptToDramaRevision
from app.script_to_drama.schemas import (
    AssetMedia,
    AssetPromptBatch,
    GeneratedAsset,
    GeneratedClip,
    H3PromptBatch,
    SelectionCommand,
)
from app.skills.models import ArtifactType, Capability
from app.skills.professional import get_professional_skill
from app.workflow.models import Task, TaskStatus
from app.workflow.provider_service import ProviderDispatchResult, dispatch_provider_call
from app.workflow.schemas import TaskCommandCreate, TaskWorkerRead
from app.workflow.task_service import (
    TaskCancelled,
    create_task_from_command,
    mark_task_failed,
    mark_task_succeeded,
    resume_task,
    retry_task,
)
from app.workflow.worker import TaskExecutionContext

TASK_TYPE = "SCRIPT_TO_DRAMA_PRODUCTION"
STAGES = {"asset_images", "prompts", "generate", "post"}
MAX_PROMPT_BATCH = 10
OUTPUT_RATIO = "9:16"
MAX_SEGMENT_US = 15_000_000
MIN_SEGMENT_US = 4_000_000


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_project(db: Session, project_id: str):
    project = get_project(db, project_id)
    if project.project_type != ProjectType.SCRIPT_TO_DRAMA:
        raise AppError("SCRIPT_TO_DRAMA_NOT_ALLOWED", "当前操作仅适用于剧本生成短剧", status_code=422)
    return project


def _current(db: Session, project_id: str, kind: ArtifactType) -> ArtifactNode | None:
    rows = list(db.scalars(select(ArtifactNode).where(
        ArtifactNode.project_id == project_id,
        ArtifactNode.artifact_type == kind.value,
        ArtifactNode.validity == ArtifactValidity.CURRENT,
        ArtifactNode.is_current.is_(True),
    )).all())
    if len(rows) > 1:
        raise AppError("SCRIPT_TO_DRAMA_CURRENT_AMBIGUOUS", f"{kind.value} 当前版本不唯一", status_code=409)
    return rows[0] if rows else None


def _require(db: Session, project_id: str, kind: ArtifactType) -> ArtifactNode:
    artifact = _current(db, project_id, kind)
    if artifact is None:
        raise AppError("SCRIPT_TO_DRAMA_INPUT_REQUIRED", f"请先完成 {kind.value}", status_code=409)
    return artifact


def _content(db: Session, artifact: ArtifactNode) -> dict:
    row = db.scalar(select(ScriptToDramaRevision).where(
        ScriptToDramaRevision.project_id == artifact.project_id,
        ScriptToDramaRevision.artifact_id == artifact.id,
    ))
    if row is None:
        raise AppError("SCRIPT_TO_DRAMA_REVISION_MISSING", "剧本生成短剧版本记录缺失", status_code=500)
    return row.content_json


def _publish_one(
    db: Session,
    *,
    project_id: str,
    kind: ArtifactType,
    namespace: ArtifactNamespace,
    label: str,
    content: dict,
    sources: list[ArtifactNode],
    skill_id: str,
    skill_version: str,
    task_id: str | None,
    provider_job_ids: list[str] | None = None,
) -> ArtifactNode:
    previous = _current(db, project_id, kind)
    if previous is not None:
        _mark_stale_with_downstream(db, [previous])
    revision = int(db.scalar(select(func.max(ArtifactNode.revision)).where(
        ArtifactNode.project_id == project_id,
        ArtifactNode.artifact_type == kind.value,
    )) or 0) + 1
    node = ArtifactNode(
        project_id=project_id,
        artifact_type=kind.value,
        namespace=namespace,
        label=label,
        revision=revision,
        input_fingerprint=_hash({"sources": [item.id for item in sources], "content": content}),
        skill_id=skill_id,
        skill_version=skill_version,
        validity=ArtifactValidity.CURRENT,
        is_current=True,
        metadata_json={
            "script_to_drama": True,
            "schema_version": "1.0",
            "source_ids": [item.id for item in sources],
        },
    )
    db.add(node)
    db.flush()
    db.add(ScriptToDramaRevision(
        project_id=project_id,
        artifact_id=node.id,
        content_json=content,
        provenance_json={
            "task_id": task_id,
            "provider_job_ids": provider_job_ids or [],
            "source_ids": [item.id for item in sources],
            "skill_id": skill_id,
            "skill_version": skill_version,
        },
    ))
    for parent in sources:
        db.add(ArtifactEdge(
            project_id=project_id,
            source_node_id=parent.id,
            target_node_id=node.id,
            relation_type=ArtifactRelationType.DERIVED_FROM,
        ))
    if previous is not None:
        db.add(ArtifactEdge(
            project_id=project_id,
            source_node_id=node.id,
            target_node_id=previous.id,
            relation_type=ArtifactRelationType.SUPERSEDES,
        ))
    return node


def _stage_inputs(db: Session, project_id: str, stage: str) -> tuple[object, list[ArtifactNode], list[dict]]:
    if stage not in STAGES:
        raise AppError("SCRIPT_TO_DRAMA_STAGE_INVALID", "未知生产阶段", status_code=422)
    project = _require_project(db, project_id)
    if stage == "asset_images":
        artifacts = [_require(db, project_id, ArtifactType.TARGET_ASSETS)]
    elif stage == "prompts":
        artifacts = [
            _require(db, project_id, ArtifactType.TARGET_STORYBOARD),
            _require(db, project_id, ArtifactType.TARGET_ASSETS),
            _require(db, project_id, ArtifactType.TARGET_ASSET_IMAGES),
        ]
    elif stage == "generate":
        artifacts = [
            _require(db, project_id, ArtifactType.GENERATION_SEGMENTS),
            _require(db, project_id, ArtifactType.TARGET_ASSET_IMAGES),
        ]
    else:
        artifacts = [_require(db, project_id, ArtifactType.GENERATION_SELECTION)]
    return project, artifacts, [_content(db, item) for item in artifacts]


def _profile_for_stage(project, stage: str) -> dict:
    settings = get_settings()
    if stage == "asset_images":
        runtime = asset_image_runtime()
        binding, skill = selected_image_model_prompt_skill(settings)
        text_provider = ScriptLocalizationProvider(settings, project.source_understanding_provider)
        return {
            "runtime": runtime.profile(),
            "prompt_model": binding.model_id,
            "prompt_skill": [skill.id, skill.version, binding.prompt_contract],
            "text_provider": text_provider.profile(),
        }
    if stage == "prompts":
        binding, skill = selected_video_model_prompt_skill(settings)
        text_provider = ScriptLocalizationProvider(settings, project.source_understanding_provider)
        return {
            "video_model": binding.model_id,
            "prompt_skill": [skill.id, skill.version, binding.prompt_contract],
            "text_provider": text_provider.profile(),
        }
    if stage == "generate":
        provider = build_h3_generation_provider(settings)
        return provider.profile()
    return {"runtime": "ffmpeg-concat-v1", "ffmpeg": settings.ffmpeg_binary}


def _fingerprint(project, artifacts: list[ArtifactNode], stage: str) -> str:
    return _hash({
        "task": TASK_TYPE,
        "stage": stage,
        "workflow_revision": project.workflow_revision,
        "inputs": [(item.id, item.revision, item.input_fingerprint) for item in artifacts],
        "profile": _profile_for_stage(project, stage),
    })


def start_stage(db: Session, project_id: str, stage: str, idempotency_key: str) -> Task:
    project, artifacts, _ = _stage_inputs(db, project_id, stage)
    task = create_task_from_command(
        db,
        project_id=project_id,
        idempotency_key=idempotency_key,
        payload=TaskCommandCreate(
            task_type=TASK_TYPE,
            task_name={
                "asset_images": "生成人物/场景/道具资产图",
                "prompts": "编译 MiniMax H3 模型专属提示词",
                "generate": "生成音画镜头",
                "post": "合成正式短剧",
            }[stage],
            input_fingerprint=_fingerprint(project, artifacts, stage),
            input_artifact_ids=[item.id for item in artifacts],
            initial_checkpoint_json={"stage": stage, "completed": 0, "results": [], "provider_job_ids": []},
            max_attempts=3,
        ),
    )
    key = idempotency_key.strip()
    if task.status == TaskStatus.FAILED and task.attempt < task.max_attempts and task.idempotency_key != key:
        return retry_task(db, project_id, task.id)
    if task.status == TaskStatus.INTERRUPTED and task.attempt < task.max_attempts and task.idempotency_key != key:
        return resume_task(db, project_id, task.id)
    return task


def _assert_fresh(db: Session, task: TaskWorkerRead, stage: str):
    project, artifacts, contents = _stage_inputs(db, task.project_id, stage)
    if task.input_artifact_ids_json != [item.id for item in artifacts] or             task.input_fingerprint != _fingerprint(project, artifacts, stage):
        raise AppError("STALE_ARTIFACT_INPUT", "生产期间上游版本或模型 Runtime 已变化，请重新发起任务", status_code=409)
    return project, artifacts, contents


def _entity_specs(asset_definitions: dict) -> list[dict]:
    specs: list[dict] = []
    for field, asset_type, width, height in (
        ("characters", "CHARACTER", CHARACTER_PANEL_WIDTH * 4, CHARACTER_PANEL_HEIGHT),
        ("locations", "SCENE", SCENE_WIDTH, SCENE_HEIGHT),
        ("props", "PROP", PROP_WIDTH, PROP_HEIGHT),
    ):
        for item in asset_definitions.get(field, []) or []:
            entity_id = str(item.get("id") or "").strip()
            name = str(item.get("name") or "").strip()
            description = str(item.get("visual_description") or "").strip()
            if not entity_id or not name or not description:
                raise AppError("SCRIPT_TO_DRAMA_ASSET_DEFINITION_INVALID", "资产定义缺少稳定 ID、名称或视觉描述", status_code=422)
            specs.append({
                "target_entity_id": entity_id,
                "asset_type": asset_type,
                "display_name": name,
                "visual_description": description,
                "width": width,
                "height": height,
            })
    if not specs:
        raise AppError("SCRIPT_TO_DRAMA_ASSET_DEFINITION_EMPTY", "没有可生成的视觉资产", status_code=409)
    return specs


def _derive_character_media(project_id: str, generated) -> list[AssetMedia]:
    root = get_settings().artifact_root.resolve()
    source = (root / generated.storage_relpath).resolve()
    if root not in source.parents or not source.is_file():
        raise AppError("SCRIPT_TO_DRAMA_ASSET_MEDIA_MISSING", "人物参考板不存在", status_code=500)
    with Image.open(source) as image:
        board = image.convert("RGB")
        expected = (CHARACTER_PANEL_WIDTH * 4, CHARACTER_PANEL_HEIGHT)
        if board.size != expected:
            raise AppError("SCRIPT_TO_DRAMA_CHARACTER_BOARD_INVALID", "人物参考板尺寸不符合运行时合同", status_code=500)
        crops = [
            ("FULL_BODY_FRONT", "front", (0, 0, CHARACTER_PANEL_WIDTH, CHARACTER_PANEL_HEIGHT)),
            ("FACE", "face", (3 * CHARACTER_PANEL_WIDTH, 0, 4 * CHARACTER_PANEL_WIDTH, CHARACTER_PANEL_HEIGHT)),
        ]
        result = [
            AssetMedia(
                reference_id=f"ref:{_hash([generated.sha256, 'BOARD'])[:24]}",
                role="BOARD",
                storage_relpath=generated.storage_relpath,
                sha256=generated.sha256,
                width=generated.width,
                height=generated.height,
            )
        ]
        source_path = Path(generated.storage_relpath)
        for role, suffix, box in crops:
            relpath = str(source_path.with_name(f"{source_path.stem}.{suffix}.png")).replace("\\", "/")
            output = (root / relpath).resolve()
            if root not in output.parents:
                raise AppError("SCRIPT_TO_DRAMA_ASSET_STORAGE_INVALID", "人物参考图存储路径越界", status_code=500)
            output.parent.mkdir(parents=True, exist_ok=True)
            crop = ImageOps.fit(board.crop(box), (CHARACTER_PANEL_WIDTH, CHARACTER_PANEL_HEIGHT))
            crop.save(output, format="PNG")
            result.append(AssetMedia(
                reference_id=f"ref:{_hash([generated.sha256, role, _file_sha(output)])[:24]}",
                role=role,
                storage_relpath=relpath,
                sha256=_file_sha(output),
                width=CHARACTER_PANEL_WIDTH,
                height=CHARACTER_PANEL_HEIGHT,
            ))
    return result


def _simple_media(generated, role: str) -> list[AssetMedia]:
    return [AssetMedia(
        reference_id=f"ref:{_hash([generated.sha256, role])[:24]}",
        role=role,
        storage_relpath=generated.storage_relpath,
        sha256=generated.sha256,
        width=generated.width,
        height=generated.height,
    )]


def _run_asset_images(context: TaskExecutionContext, task: TaskWorkerRead) -> tuple[dict, list[str]]:
    with context.session_factory() as db:
        project, artifacts, contents = _assert_fresh(db, task, "asset_images")
        definitions = contents[0]
        specs = _entity_specs(definitions)
        text_provider = ScriptLocalizationProvider(get_settings(), project.source_understanding_provider)
        binding, prompt_skill = selected_image_model_prompt_skill()
        runtime = asset_image_runtime()
        runtime.assert_ready()

    authored: dict[str, object] = {}
    provider_job_ids: list[str] = list(task.checkpoint_json.get("provider_job_ids") or [])
    resumable_results = list(task.checkpoint_json.get("results") or [])
    for start in range(0, len(specs), MAX_PROMPT_BATCH):
        batch = specs[start:start + MAX_PROMPT_BATCH]
        prompt = (
            f"请为图片模型 {binding.model_id} 编译资产生成 Prompt。必须精确返回这些 target_entity_id，不能增加或遗漏。"
            "CHARACTER 只描述一个人的稳定身份和服装；SCENE 不出现人物；PROP 不出现人物。"
            "正向 Prompt 以英文为主，review_prompt_zh 用中文。输入："
            + json.dumps(batch, ensure_ascii=False)
        )

        def remote(_job, current_prompt=prompt):
            value, remote_id = text_provider.generate(
                skill_id=prompt_skill.id,
                prompt=current_prompt,
                output_model=AssetPromptBatch,
                max_output_tokens=8192,
            )
            return ProviderDispatchResult(value=value.model_dump(mode="json"), remote_job_id=remote_id)

        with context.session_factory() as db:
            _, fresh_artifacts, _ = _assert_fresh(db, task, "asset_images")
            job, dispatched = dispatch_provider_call(
                db,
                task_id=task.id,
                provider=text_provider.provider_name,
                model=text_provider.model_name,
                capability=Capability.MODEL_PROMPTING,
                payload={
                    "task": TASK_TYPE,
                    "stage": "asset_prompt",
                    "target_entity_ids": [item["target_entity_id"] for item in batch],
                    "prompt_skill": [prompt_skill.id, prompt_skill.version, binding.prompt_contract],
                },
                artifact_id=fresh_artifacts[-1].id,
                remote_call=remote,
            )
        result = AssetPromptBatch.model_validate(dispatched.value)
        expected = {item["target_entity_id"] for item in batch}
        actual = {item.target_entity_id for item in result.assets}
        if expected != actual or len(actual) != len(result.assets):
            raise AppError("SCRIPT_TO_DRAMA_ASSET_PROMPT_COVERAGE_INVALID", "图片 Prompt 没有精确覆盖本批资产", status_code=502)
        authored.update({item.target_entity_id: item for item in result.assets})
        provider_job_ids.append(job.id)
        context.checkpoint(
            {"stage": "asset_images", "phase": "prompting", "completed": min(len(specs), start + len(batch)),
             "results": resumable_results, "provider_job_ids": provider_job_ids},
            progress_percent=10 + int(min(len(specs), start + len(batch)) / len(specs) * 20),
        )

    generated_assets: list[dict] = []
    completed = list(resumable_results)
    if completed:
        # A retry may resume image generation only when every stored file still exists and hashes match.
        root = get_settings().artifact_root.resolve()
        for row in completed:
            asset = GeneratedAsset.model_validate(row)
            if any(not (root / media.storage_relpath).is_file() or _file_sha(root / media.storage_relpath) != media.sha256 for media in asset.media):
                completed = []
                break
    completed_ids = {row["target_entity_id"] for row in completed}
    generated_assets.extend(completed)

    for index, spec in enumerate(specs, 1):
        if spec["target_entity_id"] in completed_ids:
            continue
        item = authored.get(spec["target_entity_id"])
        if item is None:
            raise AppError("SCRIPT_TO_DRAMA_ASSET_PROMPT_MISSING", "资产图片 Prompt 缺失", status_code=500)
        asset_id = f"asset:{_hash([task.project_id, spec['target_entity_id']])[:24]}"
        job_payload = {
            "task": TASK_TYPE,
            "stage": "asset_image_runtime",
            "target_entity_id": spec["target_entity_id"],
            "asset_type": spec["asset_type"],
            "prompt_sha256": _hash(item.image_prompt),
            "runtime": runtime.profile(),
        }

        def image_remote(_job):
            if spec["asset_type"] == "CHARACTER":
                generated = runtime.generate_character_sheet(
                    project_id=task.project_id,
                    task_id=task.id,
                    asset_id=asset_id,
                    prompt=item.image_prompt,
                    negative_prompt=item.negative_prompt,
                )
            else:
                generated = runtime.generate(
                    project_id=task.project_id,
                    task_id=task.id,
                    asset_id=asset_id,
                    prompt=item.image_prompt,
                    negative_prompt=item.negative_prompt,
                    width=spec["width"],
                    height=spec["height"],
                )
            return ProviderDispatchResult(value=generated, remote_job_id=generated.remote_job_id)

        with context.session_factory() as db:
            _, fresh_artifacts, _ = _assert_fresh(db, task, "asset_images")
            runtime_model = runtime.character_pipeline_model_name if spec["asset_type"] == "CHARACTER" else runtime.model_name
            job, dispatched = dispatch_provider_call(
                db,
                task_id=task.id,
                provider=runtime.provider_name,
                model=runtime_model,
                capability=Capability.ASSET_IMAGE_GENERATION,
                payload=job_payload,
                artifact_id=fresh_artifacts[-1].id,
                remote_call=image_remote,
            )
        generated = dispatched.value
        media = _derive_character_media(task.project_id, generated) if spec["asset_type"] == "CHARACTER" else             _simple_media(generated, "LAYOUT" if spec["asset_type"] == "SCENE" else "DETAIL")
        row = GeneratedAsset(
            target_asset_id=asset_id,
            target_entity_id=spec["target_entity_id"],
            asset_type=spec["asset_type"],
            display_name=spec["display_name"],
            image_prompt=item.image_prompt,
            negative_prompt=item.negative_prompt,
            review_prompt_zh=item.review_prompt_zh,
            media=media,
        ).model_dump(mode="json")
        generated_assets.append(row)
        provider_job_ids.append(job.id)
        context.checkpoint(
            {"stage": "asset_images", "phase": "runtime", "completed": len(generated_assets),
             "results": generated_assets, "provider_job_ids": provider_job_ids},
            progress_percent=min(95, 30 + int(len(generated_assets) / len(specs) * 65)),
        )
    if len(generated_assets) != len(specs):
        raise AppError("SCRIPT_TO_DRAMA_ASSET_IMAGES_INCOMPLETE", "资产图没有完整覆盖全部资产定义", status_code=422)
    return {
        "target_assets_definition_artifact_id": artifacts[0].id,
        "image_model_id": binding.model_id,
        "prompt_skill_id": prompt_skill.id,
        "prompt_skill_version": prompt_skill.version,
        "prompt_contract": binding.prompt_contract,
        "assets": generated_assets,
    }, provider_job_ids


def _asset_by_entity(content: dict) -> dict[str, GeneratedAsset]:
    rows = [GeneratedAsset.model_validate(item) for item in content.get("assets", [])]
    result = {item.target_entity_id: item for item in rows}
    if len(result) != len(rows):
        raise AppError("SCRIPT_TO_DRAMA_ASSET_IMAGES_DUPLICATE", "正式资产图存在重复实体", status_code=409)
    return result


def _reference_conditions(shot: dict, assets: dict[str, GeneratedAsset]) -> list[H3ReferenceCondition]:
    conditions: list[H3ReferenceCondition] = []

    def add(entity_id: str, roles: tuple[str, ...]):
        asset = assets.get(entity_id)
        if asset is None:
            raise AppError("SCRIPT_TO_DRAMA_REFERENCE_MISSING", "镜头引用实体缺少正式资产图", status_code=409,
                           details={"target_entity_id": entity_id})
        selected = [media for role in roles for media in asset.media if media.role == role]
        if not selected:
            selected = [asset.media[0]]
        for media in selected:
            if len(conditions) >= 9:
                raise AppError("SCRIPT_TO_DRAMA_REFERENCE_CAPACITY_EXCEEDED", "单镜头超过 H3 的 9 张参考图上限，请拆分镜头", status_code=409)
            conditions.append(H3ReferenceCondition(
                picture_index=len(conditions) + 1,
                target_asset_id=asset.target_asset_id,
                target_entity_id=asset.target_entity_id,
                asset_type=asset.asset_type,
                reference_id=media.reference_id,
                reference_role=media.role,
                reference_uri=f"/api/v3/projects/{shot['project_id']}/script-to-drama/media/{media.reference_id}",
                reference_sha256=media.sha256,
                storage_relpath=media.storage_relpath,
            ))

    for entity_id in shot.get("character_ids", []) or []:
        add(entity_id, ("FACE", "FULL_BODY_FRONT"))
    add(str(shot.get("scene_id")), ("LAYOUT",))
    for entity_id in shot.get("prop_ids", []) or []:
        add(entity_id, ("DETAIL",))
    return conditions


def _segment_drafts(project_id: str, storyboard: dict, image_content: dict) -> list[dict]:
    assets = _asset_by_entity(image_content)
    segments: list[dict] = []
    cursor = 0
    for shot in storyboard.get("shots", []) or []:
        seconds = max(4.0, float(shot.get("estimated_seconds") or 4.0))
        count = max(1, int(math.ceil(seconds / 15.0)))
        per_us = max(MIN_SEGMENT_US, min(MAX_SEGMENT_US, int(round(seconds * 1_000_000 / count))))
        for continuation in range(1, count + 1):
            segment_id = f"SEG_{len(segments) + 1:05}"
            shot_view = {**shot, "project_id": project_id}
            references = _reference_conditions(shot_view, assets)
            segments.append({
                "generation_segment_id": segment_id,
                "episode_id": f"script-to-drama:{project_id}",
                "episode_order": 1,
                "segment_number": len(segments) + 1,
                "storyboard_shot_ids": [shot["shot_id"]],
                "start_us": cursor,
                "end_us": cursor + per_us,
                "duration_us": per_us,
                "output_ratio": OUTPUT_RATIO,
                "continuation_index": continuation,
                "continuation_count": count,
                "shot": shot,
                "reference_conditions": [item.model_dump(mode="json") for item in references],
                "picture_legend": [
                    {
                        "picture": f"<Picture {item.picture_index}>",
                        "target_entity_id": item.target_entity_id,
                        "asset_type": item.asset_type,
                        "role": item.reference_role,
                    }
                    for item in references
                ],
            })
            cursor += per_us
    if not segments:
        raise AppError("SCRIPT_TO_DRAMA_STORYBOARD_EMPTY", "导演分镜为空，无法编译视频提示词", status_code=409)
    return segments


def _run_prompts(context: TaskExecutionContext, task: TaskWorkerRead) -> tuple[dict, list[str]]:
    with context.session_factory() as db:
        project, artifacts, contents = _assert_fresh(db, task, "prompts")
        storyboard, definitions, image_content = contents
        if image_content.get("target_storyboard_artifact_id") != artifacts[0].id or                 image_content.get("target_assets_definition_artifact_id") != artifacts[1].id:
            raise AppError("SCRIPT_TO_DRAMA_ASSET_IMAGES_STALE", "资产图不属于当前导演分镜/资产定义", status_code=409)
        drafts = _segment_drafts(task.project_id, storyboard, image_content)
        provider = ScriptLocalizationProvider(get_settings(), project.source_understanding_provider)
        binding, skill = selected_video_model_prompt_skill()

    authored: dict[str, object] = {}
    job_ids: list[str] = []
    for start in range(0, len(drafts), MAX_PROMPT_BATCH):
        batch = drafts[start:start + MAX_PROMPT_BATCH]
        prompt = (
            f"为 MiniMax H3 编译可直接执行的音画视频 Prompt。目标模型 {binding.model_id}。"
            "每个 segment 必须严格复用给出的 generation_segment_id；<Picture N> 标签必须与 picture_legend 一致。"
            "保持导演分镜的动作、镜头语言、对白/旁白和人物身份，不增加剧情。"
            "execution_prompt 以模型可执行的英文视觉/动作/镜头描述为主；对白可以保留目标剧本语言；review_prompt_zh 用中文审阅。"
            "输入：" + json.dumps(batch, ensure_ascii=False)
        )

        def remote(_job, current_prompt=prompt):
            value, remote_id = provider.generate(
                skill_id=skill.id,
                prompt=current_prompt,
                output_model=H3PromptBatch,
                max_output_tokens=12288,
            )
            return ProviderDispatchResult(value=value.model_dump(mode="json"), remote_job_id=remote_id)

        with context.session_factory() as db:
            _, fresh_artifacts, _ = _assert_fresh(db, task, "prompts")
            job, dispatched = dispatch_provider_call(
                db,
                task_id=task.id,
                provider=provider.provider_name,
                model=provider.model_name,
                capability=Capability.MODEL_PROMPTING,
                payload={
                    "task": TASK_TYPE,
                    "stage": "h3_prompt",
                    "segment_ids": [item["generation_segment_id"] for item in batch],
                    "skill": [skill.id, skill.version, binding.prompt_contract],
                },
                artifact_id=fresh_artifacts[-1].id,
                remote_call=remote,
            )
        result = H3PromptBatch.model_validate(dispatched.value)
        expected = {item["generation_segment_id"] for item in batch}
        actual = {item.generation_segment_id for item in result.segments}
        if expected != actual or len(actual) != len(result.segments):
            raise AppError("SCRIPT_TO_DRAMA_H3_PROMPT_COVERAGE_INVALID", "H3 Prompt Skill 没有精确覆盖全部分段", status_code=502)
        authored.update({item.generation_segment_id: item for item in result.segments})
        job_ids.append(job.id)
        context.checkpoint(
            {"stage": "prompts", "completed": min(len(drafts), start + len(batch)),
             "results": [], "provider_job_ids": job_ids},
            progress_percent=10 + int(min(len(drafts), start + len(batch)) / len(drafts) * 80),
        )

    segments = []
    for draft in drafts:
        item = authored[draft["generation_segment_id"]]
        segment = GenerationSegment(
            generation_segment_id=draft["generation_segment_id"],
            episode_id=draft["episode_id"],
            episode_order=1,
            segment_number=draft["segment_number"],
            storyboard_shot_ids=draft["storyboard_shot_ids"],
            start_us=draft["start_us"],
            end_us=draft["end_us"],
            duration_us=draft["duration_us"],
            output_ratio=draft["output_ratio"],
            continuation_index=draft["continuation_index"],
            continuation_count=draft["continuation_count"],
            generation_prompt=item.execution_prompt,
            negative_prompt=item.negative_prompt,
            prompt_skill_id=skill.id,
            prompt_skill_version=skill.version,
            prompt_contract=binding.prompt_contract,
            model_id=binding.model_id,
            review_prompt_zh=item.review_prompt_zh,
            reference_conditions=[H3ReferenceCondition.model_validate(row) for row in draft["reference_conditions"]],
            audio_generation_mode=GenerationAudioMode.NATIVE_AUDIO_VIDEO,
        )
        segments.append(segment.model_dump(mode="json"))
    return {
        "target_storyboard_artifact_id": artifacts[0].id,
        "target_asset_images_artifact_id": artifacts[2].id,
        "model_id": binding.model_id,
        "prompt_skill_id": skill.id,
        "prompt_skill_version": skill.version,
        "prompt_contract": binding.prompt_contract,
        "segments": segments,
    }, job_ids


def _run_generate(context: TaskExecutionContext, task: TaskWorkerRead) -> tuple[dict, list[str]]:
    with context.session_factory() as db:
        project, artifacts, contents = _assert_fresh(db, task, "generate")
        prompt_content, image_content = contents
        if prompt_content.get("target_asset_images_artifact_id") != artifacts[1].id:
            raise AppError("SCRIPT_TO_DRAMA_GENERATION_INPUT_STALE", "视频 Prompt 不属于当前资产图", status_code=409)
        segments = [GenerationSegment.model_validate(item) for item in prompt_content.get("segments", [])]
        if not segments:
            raise AppError("SCRIPT_TO_DRAMA_GENERATION_SEGMENTS_EMPTY", "没有可执行的视频生成分段", status_code=409)
        provider = build_h3_generation_provider(get_settings())
        provider.assert_ready()

    prior = list(task.checkpoint_json.get("results") or [])
    job_ids = list(task.checkpoint_json.get("provider_job_ids") or [])
    completed_ids = {row.get("generation_segment_id") for row in prior}
    root = get_settings().artifact_root.resolve()
    valid_prior: list[dict] = []
    for row in prior:
        try:
            clip = GeneratedClip.model_validate(row)
            path = (root / clip.storage_relpath).resolve()
            if root in path.parents and path.is_file() and _file_sha(path) == clip.sha256:
                valid_prior.append(row)
        except Exception:
            pass
    if len(valid_prior) != len(prior):
        valid_prior = []
        completed_ids = set()
        job_ids = []
    results = list(valid_prior)

    for index, segment in enumerate(segments, 1):
        if segment.generation_segment_id in completed_ids:
            continue
        relpath = f"script_to_drama/video/{task.project_id}/{task.id}/{segment.generation_segment_id}.mp4"
        output = (root / relpath).resolve()
        if root not in output.parents:
            raise AppError("SCRIPT_TO_DRAMA_VIDEO_STORAGE_INVALID", "视频生成存储路径越界", status_code=500)
        output.parent.mkdir(parents=True, exist_ok=True)

        def remote(_job):
            result = provider.generate_to_file(segment, output)
            probe = probe_video(output)
            tolerance = duration_tolerance_us() + 1_000_000
            requested_us = provider.requested_duration(segment) * 1_000_000
            if abs(probe.duration_us - requested_us) > tolerance:
                output.unlink(missing_ok=True)
                raise AppError("SCRIPT_TO_DRAMA_VIDEO_DURATION_INVALID", "生成视频实际时长与 Provider 请求时长偏差过大", status_code=502)
            return ProviderDispatchResult(
                value={
                    "storage_relpath": relpath,
                    "sha256": sha256_file(output),
                    "duration_us": probe.duration_us,
                    "width": probe.width,
                    "height": probe.height,
                    "codec_name": probe.codec_name,
                    "remote_job_id": result.remote_job_id,
                },
                remote_job_id=result.remote_job_id,
            )

        with context.session_factory() as db:
            _, fresh_artifacts, _ = _assert_fresh(db, task, "generate")
            job, dispatched = dispatch_provider_call(
                db,
                task_id=task.id,
                provider=provider.provider_name,
                model=provider.model_name,
                capability=Capability.VIDEO_GENERATION,
                payload={
                    "task": TASK_TYPE,
                    "stage": "generate",
                    "generation_segment_id": segment.generation_segment_id,
                    "prompt_sha256": _hash(segment.generation_prompt),
                    "reference_sha256": [item.reference_sha256 for item in segment.reference_conditions],
                    "runtime": provider.profile(),
                },
                artifact_id=fresh_artifacts[0].id,
                remote_call=remote,
            )
        value = dispatched.value
        clip = GeneratedClip(
            generation_segment_id=segment.generation_segment_id,
            storage_relpath=value["storage_relpath"],
            sha256=value["sha256"],
            duration_us=value["duration_us"],
            width=value["width"],
            height=value["height"],
            codec_name=value["codec_name"],
            provider_job_id=job.id,
            remote_job_id=value.get("remote_job_id"),
        ).model_dump(mode="json")
        results.append(clip)
        job_ids.append(job.id)
        context.checkpoint(
            {"stage": "generate", "completed": len(results), "results": results, "provider_job_ids": job_ids},
            progress_percent=5 + int(len(results) / len(segments) * 90),
        )
    if {item.generation_segment_id for item in segments} != {row["generation_segment_id"] for row in results}:
        raise AppError("SCRIPT_TO_DRAMA_VIDEO_COVERAGE_INVALID", "生成视频未覆盖全部分段", status_code=422)
    return {
        "generation_segments_artifact_id": artifacts[0].id,
        "target_asset_images_artifact_id": artifacts[1].id,
        "review_status": "NEEDS_REVIEW",
        "clips": results,
    }, job_ids


def _run_post(context: TaskExecutionContext, task: TaskWorkerRead) -> tuple[dict, list[str]]:
    with context.session_factory() as db:
        _, artifacts, contents = _assert_fresh(db, task, "post")
        selection = contents[0]
    clips = [GeneratedClip.model_validate(item) for item in selection.get("clips", [])]
    if not clips:
        raise AppError("SCRIPT_TO_DRAMA_SELECTION_EMPTY", "正式选片为空，无法合成成片", status_code=409)
    root = get_settings().artifact_root.resolve()
    paths: list[Path] = []
    for clip in clips:
        path = (root / clip.storage_relpath).resolve()
        if root not in path.parents or not path.is_file() or _file_sha(path) != clip.sha256:
            raise AppError("SCRIPT_TO_DRAMA_SELECTED_MEDIA_STALE", "正式选片媒体缺失或 hash 已变化", status_code=409)
        paths.append(path)
    output_rel = f"script_to_drama/final/{task.project_id}/{task.id}/final.mp4"
    output = (root / output_rel).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    concat = output.with_suffix(".concat.txt")
    concat_lines: list[str] = []
    for media_path in paths:
        escaped_path = str(media_path).replace("'", "'\\''")
        concat_lines.append(f"file '{escaped_path}'\\n")
    concat.write_text("".join(concat_lines), encoding="utf-8")
    settings = get_settings()
    try:
        subprocess.run([
            settings.ffmpeg_binary, "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output),
        ], check=True, capture_output=True, text=True, timeout=3600)
    except Exception as exc:
        output.unlink(missing_ok=True)
        raise AppError("SCRIPT_TO_DRAMA_POST_FAILED", "FFmpeg 合成正式短剧失败", status_code=502) from exc
    finally:
        concat.unlink(missing_ok=True)
    probe = probe_video(output)
    context.checkpoint({"stage": "post", "completed": 1, "results": [output_rel], "provider_job_ids": []}, progress_percent=95)
    return {
        "generation_selection_artifact_id": artifacts[0].id,
        "storage_relpath": output_rel,
        "sha256": sha256_file(output),
        "mime_type": "video/mp4",
        "duration_us": probe.duration_us,
        "width": probe.width,
        "height": probe.height,
        "codec_name": probe.codec_name,
    }, []


def _publish(db: Session, task_id: str, stage: str, content: dict, job_ids: list[str]) -> None:
    task = db.get(Task, task_id)
    if task is None or task.status != TaskStatus.SUCCEEDED:
        raise AppError("SCRIPT_TO_DRAMA_TASK_INCOMPLETE", "生产任务尚未成功", status_code=409)
    project, artifacts, _ = _stage_inputs(db, task.project_id, stage)
    if task.input_artifact_ids_json != [item.id for item in artifacts] or             task.input_fingerprint != _fingerprint(project, artifacts, stage):
        raise AppError("STALE_ARTIFACT_INPUT", "生产完成时上游版本已经变化，拒绝发布旧结果", status_code=409)
    if stage == "asset_images":
        skill = get_professional_skill("asset-image-generation")
        _publish_one(db, project_id=task.project_id, kind=ArtifactType.TARGET_ASSET_IMAGES,
                     namespace=ArtifactNamespace.TARGET, label="剧本生成短剧·正式资产图",
                     content=content, sources=artifacts, skill_id=skill.id,
                     skill_version=skill.version, task_id=task.id, provider_job_ids=job_ids)
    elif stage == "prompts":
        skill = get_professional_skill("minimax-h3-prompting")
        _publish_one(db, project_id=task.project_id, kind=ArtifactType.GENERATION_SEGMENTS,
                     namespace=ArtifactNamespace.PRODUCTION, label="剧本生成短剧·H3 生成分段与模型 Prompt",
                     content=content, sources=artifacts, skill_id=skill.id,
                     skill_version=skill.version, task_id=task.id, provider_job_ids=job_ids)
    elif stage == "generate":
        skill = get_professional_skill("video-generation-qc")
        _publish_one(db, project_id=task.project_id, kind=ArtifactType.GENERATED_VIDEO,
                     namespace=ArtifactNamespace.PRODUCTION, label="剧本生成短剧·待人工确认生成镜头",
                     content=content, sources=artifacts, skill_id=skill.id,
                     skill_version=skill.version, task_id=task.id, provider_job_ids=job_ids)
    else:
        skill = get_professional_skill("post-production")
        _publish_one(db, project_id=task.project_id, kind=ArtifactType.FINAL_OUTPUT,
                     namespace=ArtifactNamespace.PRODUCTION, label="剧本生成短剧·正式成片",
                     content=content, sources=artifacts, skill_id=skill.id,
                     skill_version=skill.version, task_id=task.id, provider_job_ids=[])
    _invalidate_project_plan(db, project)
    db.commit()


def accept_generated_video(db: Session, project_id: str, command: SelectionCommand) -> ArtifactNode:
    project = _require_project(db, project_id)
    generated = _require(db, project_id, ArtifactType.GENERATED_VIDEO)
    if generated.id != command.expected_generated_video_artifact_id:
        raise AppError("SCRIPT_TO_DRAMA_SELECTION_CONFLICT", "生成镜头版本已经变化，请刷新后重新确认", status_code=409)
    content = _content(db, generated)
    clips = [GeneratedClip.model_validate(item) for item in content.get("clips", [])]
    expected = [item.generation_segment_id for item in clips]
    selected = list(dict.fromkeys(command.selected_segment_ids))
    if selected != expected:
        raise AppError(
            "SCRIPT_TO_DRAMA_SELECTION_COVERAGE_INVALID",
            "当前成片必须逐段确认全部生成镜头；如需重做镜头，请重新生成后再确认",
            status_code=422,
            details={"expected": expected, "selected": selected},
        )
    prior = _current(db, project_id, ArtifactType.GENERATION_SELECTION)
    skill = get_professional_skill("video-generation-qc")
    selection = _publish_one(
        db,
        project_id=project_id,
        kind=ArtifactType.GENERATION_SELECTION,
        namespace=ArtifactNamespace.PRODUCTION,
        label="剧本生成短剧·人工确认正式选片",
        content={
            "generated_video_artifact_id": generated.id,
            "review_status": "ACCEPTED",
            "review_reason": command.reason.strip(),
            "clips": [item.model_dump(mode="json") for item in clips],
        },
        sources=[generated],
        skill_id=skill.id,
        skill_version=skill.version,
        task_id=None,
    )
    _invalidate_project_plan(db, project)
    db.commit()
    return selection


def media_path(db: Session, project_id: str, reference_id: str) -> Path:
    _require_project(db, project_id)
    root = get_settings().artifact_root.resolve()
    # Search only CURRENT/STALE script-to-drama revision payloads; never arbitrary user paths.
    rows = list(db.scalars(select(ScriptToDramaRevision).where(
        ScriptToDramaRevision.project_id == project_id,
    )).all())
    wanted = reference_id.strip()
    relpath: str | None = None
    for row in rows:
        content = row.content_json
        for asset in content.get("assets", []) if isinstance(content, dict) else []:
            for media in asset.get("media", []) if isinstance(asset, dict) else []:
                if media.get("reference_id") == wanted:
                    relpath = str(media.get("storage_relpath") or "")
                    break
        for clip in content.get("clips", []) if isinstance(content, dict) else []:
            if clip.get("generation_segment_id") == wanted:
                relpath = str(clip.get("storage_relpath") or "")
        if content.get("storage_relpath") and wanted == "final":
            relpath = str(content["storage_relpath"])
        if relpath:
            break
    if not relpath:
        raise AppError("SCRIPT_TO_DRAMA_MEDIA_NOT_FOUND", "媒体不存在", status_code=404)
    path = (root / relpath).resolve()
    if root not in path.parents or not path.is_file():
        raise AppError("SCRIPT_TO_DRAMA_MEDIA_NOT_FOUND", "媒体文件不存在", status_code=404)
    return path


def _claim(db: Session, task_id: str, worker_id: str) -> Task | None:
    now = utc_now()
    changed = db.execute(update(Task).where(
        Task.id == task_id,
        Task.task_type == TASK_TYPE,
        Task.status == TaskStatus.QUEUED,
        Task.attempt < Task.max_attempts,
    ).values(
        status=TaskStatus.RUNNING,
        attempt=Task.attempt + 1,
        worker_id=worker_id,
        heartbeat_at=now,
        started_at=func.coalesce(Task.started_at, now),
        finished_at=None,
        updated_at=now,
    ))
    if changed.rowcount != 1:
        db.rollback()
        return None
    db.commit()
    return db.get(Task, task_id)


def _mark_publish_failed(db: Session, task_id: str, message: str) -> None:
    task = db.get(Task, task_id)
    if task is not None and task.status == TaskStatus.SUCCEEDED:
        task.status = TaskStatus.FAILED
        task.progress_percent = min(task.progress_percent, 99)
        task.last_error = message[:1000]
        task.finished_at = utc_now()
        db.add(task)
        db.commit()


def run_stage_task(factory: sessionmaker[Session], task_id: str) -> None:
    worker_id = f"script-to-drama-production-{uuid4()}"
    with factory() as db:
        claimed = _claim(db, task_id, worker_id)
        if claimed is None:
            return
        snapshot = TaskWorkerRead.model_validate(claimed)
    context = TaskExecutionContext(factory, snapshot.id, worker_id)
    stage = str(snapshot.checkpoint_json.get("stage") or "")
    try:
        if stage == "asset_images":
            content, jobs = _run_asset_images(context, snapshot)
        elif stage == "prompts":
            content, jobs = _run_prompts(context, snapshot)
        elif stage == "generate":
            content, jobs = _run_generate(context, snapshot)
        elif stage == "post":
            content, jobs = _run_post(context, snapshot)
        else:
            raise AppError("SCRIPT_TO_DRAMA_STAGE_INVALID", "未知生产阶段", status_code=422)
    except TaskCancelled:
        return
    except AppError as exc:
        with factory() as db:
            mark_task_failed(db, snapshot.id,
                             safe_error=f"剧本生成短剧生产失败（{exc.code}）：{exc.message}",
                             worker_id=worker_id)
        return
    except Exception as exc:
        with factory() as db:
            mark_task_failed(db, snapshot.id,
                             safe_error=f"剧本生成短剧生产异常（{type(exc).__name__}）",
                             worker_id=worker_id)
        return
    with factory() as db:
        done = mark_task_succeeded(db, snapshot.id, worker_id=worker_id)
    if done.status == TaskStatus.CANCELLED:
        return
    try:
        with factory() as db:
            _publish(db, snapshot.id, stage, content, jobs)
    except AppError as exc:
        with factory() as db:
            db.rollback()
            _mark_publish_failed(db, snapshot.id, f"生产发布失败（{exc.code}）：{exc.message}")
    except Exception as exc:
        with factory() as db:
            db.rollback()
            _mark_publish_failed(db, snapshot.id, f"生产发布异常（{type(exc).__name__}）")
