import hashlib
import json
import math
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactEdge, ArtifactNode
from app.artifacts.service import _invalidate_project_plan, _mark_stale_with_downstream
from app.core.errors import AppError
from app.core.time import utc_now
from app.p15.schemas import (
    GenerationAudioMode,
    GenerationSegment,
    H3ReferenceCondition,
    ReplicaGenerationSegmentsContent,
    StoryboardDialogueRef,
)
from app.projects.enums import ProjectType
from app.projects.service import get_project
from app.replica_pipeline.models import ReplicaAssetImageRevision, ReplicaH3PromptRevision, ReplicaLocalizedStoryboardRevision
from app.replica_pipeline.schemas import (
    H3_PROMPT_SCHEMA_VERSION,
    H3PromptProvenance,
    H3PromptsRead,
    ReplicaAssetImagesContent,
    ReplicaLocalizedStoryboardContent,
    ResultStatus,
)
from app.skills.models import ArtifactType
from app.skills.professional import get_professional_skill
from app.target_assets.schemas import TargetAssetRef, TargetAssetType
from app.workflow.models import Task, TaskStatus
from app.workflow.schemas import TaskCommandCreate, TaskWorkerRead
from app.workflow.task_service import TaskCancelled, create_task_from_command, mark_task_failed, mark_task_succeeded
from app.workflow.worker import TaskExecutionContext


TASK_TYPE = "replica.h3-prompts"
SKILL_ID = "minimax-h3-prompting"
MODEL_ID = "MiniMaxAI/MiniMax-H3"
PROMPT_CONTRACT = "minimax-h3-multi-reference-av-v1"
MAX_SEGMENT_DURATION_US = 15_000_000


def _sha(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _current(db: Session, project_id: str, artifact_type: ArtifactType) -> ArtifactNode:
    rows = list(db.scalars(select(ArtifactNode).where(
        ArtifactNode.project_id == project_id,
        ArtifactNode.artifact_type == artifact_type.value,
        ArtifactNode.validity == ArtifactValidity.CURRENT,
        ArtifactNode.is_current.is_(True),
    )).all())
    if not rows:
        raise AppError("H3_PROMPT_INPUT_REQUIRED", f"第 4 步需要 CURRENT {artifact_type.value}", status_code=409)
    if len(rows) != 1:
        raise AppError("H3_PROMPT_INPUT_AMBIGUOUS", f"{artifact_type.value} 存在多个 CURRENT Artifact", status_code=409)
    return rows[0]


def _latest(db: Session, project_id: str, artifact_type: ArtifactType) -> ArtifactNode | None:
    return db.scalar(select(ArtifactNode).where(
        ArtifactNode.project_id == project_id,
        ArtifactNode.artifact_type == artifact_type.value,
    ).order_by(ArtifactNode.revision.desc()).limit(1))


def _load_inputs(db: Session, project_id: str) -> tuple[ArtifactNode, ReplicaLocalizedStoryboardContent, ArtifactNode, ReplicaAssetImagesContent]:
    storyboard_artifact = _current(db, project_id, ArtifactType.TARGET_STORYBOARD)
    assets_artifact = _current(db, project_id, ArtifactType.TARGET_ASSETS)
    storyboard_row = db.scalar(select(ReplicaLocalizedStoryboardRevision).where(ReplicaLocalizedStoryboardRevision.artifact_id == storyboard_artifact.id))
    assets_row = db.scalar(select(ReplicaAssetImageRevision).where(ReplicaAssetImageRevision.artifact_id == assets_artifact.id))
    if storyboard_row is None:
        raise AppError("H3_PROMPT_REQUIRES_V2_STORYBOARD", "当前分镜不是第 2 步本土化分镜，请先按五步主链重新生成", status_code=409)
    if assets_row is None:
        raise AppError("H3_PROMPT_REQUIRES_ASSET_IMAGES", "当前资产不是第 3 步真实资产图，请先生成并确认资产图", status_code=409)
    storyboard = ReplicaLocalizedStoryboardContent.model_validate(storyboard_row.content_json)
    assets = ReplicaAssetImagesContent.model_validate(assets_row.content_json)
    if assets.target_storyboard_artifact_id != storyboard_artifact.id:
        raise AppError("H3_PROMPT_LINEAGE_MISMATCH", "资产图不属于当前本土化分镜", status_code=409)
    return storyboard_artifact, storyboard, assets_artifact, assets


def _asset_lookup(assets: ReplicaAssetImagesContent) -> dict[str, object]:
    lookup = {item.target_entity_id: item for item in assets.assets}
    for entity_id, asset in lookup.items():
        if not asset.reference_media:
            raise AppError("H3_PROMPT_REFERENCE_MISSING", "H3 Prompt 需要每个目标资产都有已确认参考图", status_code=409, details={"target_entity_id": entity_id})
        if any(not media.storage_relpath for media in asset.reference_media):
            raise AppError("H3_PROMPT_REFERENCE_PATH_MISSING", "H3 Prompt 参考图缺少受管存储路径", status_code=409, details={"target_entity_id": entity_id})
    return lookup


def _ordered_entity_ids(shot, overlapping_dialogue: list) -> list[str]:
    ordered: list[str] = []
    ordered.extend(shot.target_scene_ids)
    ordered.extend(item.target_character_id for item in overlapping_dialogue if item.target_character_id)
    ordered.extend(shot.target_character_ids)
    ordered.extend(shot.target_prop_ids)
    return list(dict.fromkeys(value for value in ordered if value))


def _references(shot, overlapping_dialogue: list, assets_artifact_id: str, asset_by_entity: dict[str, object]) -> tuple[list[H3ReferenceCondition], list[TargetAssetRef]]:
    required_ids = list(dict.fromkeys([*shot.target_scene_ids, *shot.target_character_ids, *shot.target_prop_ids]))
    missing = [entity_id for entity_id in required_ids if entity_id not in asset_by_entity]
    if missing:
        raise AppError("H3_PROMPT_ASSET_MISSING", "本镜头引用的目标实体缺少已确认资产图", status_code=409, details={"target_entity_ids": missing})

    ordered_ids = _ordered_entity_ids(shot, overlapping_dialogue)
    conditions: list[H3ReferenceCondition] = []
    refs: list[TargetAssetRef] = []
    for entity_id in ordered_ids:
        asset = asset_by_entity[entity_id]
        refs.append(TargetAssetRef(
            target_assets_artifact_id=assets_artifact_id,
            target_asset_id=asset.target_asset_id,
            target_asset_revision=asset.target_asset_revision,
            asset_type=asset.asset_type,
            target_entity_id=asset.target_entity_id,
        ))
        if len(conditions) >= 9:
            continue
        media = asset.reference_media[0]
        assert media.storage_relpath is not None
        conditions.append(H3ReferenceCondition(
            picture_index=len(conditions) + 1,
            target_asset_id=asset.target_asset_id,
            target_entity_id=asset.target_entity_id,
            asset_type=asset.asset_type.value,
            reference_id=media.reference_id,
            reference_role=media.role.value,
            reference_uri=media.uri,
            reference_sha256=media.sha256,
            storage_relpath=media.storage_relpath,
        ))
    return conditions, refs


def _dialogue_refs(shot, start_us: int, end_us: int) -> list[StoryboardDialogueRef]:
    refs: list[StoryboardDialogueRef] = []
    for item in shot.dialogue:
        if item.overlap_start_us >= end_us or item.overlap_end_us <= start_us:
            continue
        refs.append(StoryboardDialogueRef(
            utterance_id=item.utterance_id,
            utterance_number=item.utterance_number,
            delivery=item.delivery,
            target_character_id=item.target_character_id,
            final_target_dialogue=item.target_dialogue,
            target_dialogue_zh=item.target_dialogue_zh,
            planned_speech_start_us=max(start_us, item.overlap_start_us),
            planned_speech_end_us=min(end_us, item.overlap_end_us),
        ))
    return refs


def _prompt_for_segment(*, shot, conditions: list[H3ReferenceCondition], dialogue_refs: list[StoryboardDialogueRef], character_names: dict[str, str], target_language: str, continuation_index: int, continuation_count: int) -> tuple[str, str]:
    skill = get_professional_skill(SKILL_ID)
    asset_lines: list[str] = []
    for ref in conditions:
        role = "scene" if ref.asset_type == TargetAssetType.SCENE.value else "character" if ref.asset_type == TargetAssetType.CHARACTER.value else "prop"
        asset_lines.append(f"<Picture {ref.picture_index}> is the strict {role} identity reference for this shot. Preserve its identity, design, colors and distinguishing details.")

    dialogue_lines: list[str] = []
    review_lines: list[str] = []
    for ref in dialogue_refs:
        speaker = character_names.get(ref.target_character_id or "", "Actor")
        dialogue_lines.append(f'{speaker} ({ref.delivery.value}) says exactly once in {target_language}: "{ref.final_target_dialogue}"')
        review_lines.append(f"{speaker}：{ref.final_target_dialogue} ｜ 中文理解：{ref.target_dialogue_zh or '—'}")

    camera = shot.camera_language
    prompt_parts = [
        *asset_lines,
        f"Generate localized replica shot {shot.shot_number}, continuation {continuation_index}/{continuation_count}.",
        f"Visual/action intent: {shot.localized_visual_description_zh}",
        f"Camera must preserve the source shot language: shot size {camera.shot_size}; composition {camera.composition}; angle/type {camera.angle_or_type}; movement {camera.movement}; lens/depth-of-field {camera.focal_length_dof}.",
        "Keep character and environment identity consistent with the referenced pictures. Do not redesign approved assets.",
    ]
    if dialogue_lines:
        prompt_parts.append("Spoken dialogue contract: " + " ".join(dialogue_lines))
        prompt_parts.append("Actors must speak only those target-language lines verbatim, completely, once, with natural performance and matching lip movement. Never speak the Chinese review translation.")
    else:
        prompt_parts.append("No spoken dialogue in this segment unless explicitly listed above.")
    prompt_parts.extend([
        f"Generate native synchronized picture and stereo audio. Ambience: {'; '.join(shot.ambience) or 'natural scene ambience'}. Sound effects: {'; '.join(shot.sound_effects) or 'only naturally motivated effects'}.",
        "No burned-in subtitles, no watermark, no source-language speech, no extra dialogue, no duplicate people, no identity drift.",
        f"Prompt contract: {PROMPT_CONTRACT}; skill: {skill.id}@{skill.version}.",
    ])
    review_prompt_zh = "\n".join([
        f"镜头 {shot.shot_number}：{shot.localized_visual_description_zh}",
        f"镜头语言：{shot.camera_description_zh}",
        *(review_lines or ["无对白"]),
        "参考图：" + "、".join(f"Picture {x.picture_index}={x.target_entity_id}" for x in conditions),
    ])
    return "\n".join(prompt_parts), review_prompt_zh


def compile_h3_segments(storyboard_artifact: ArtifactNode, storyboard: ReplicaLocalizedStoryboardContent, assets_artifact: ArtifactNode, assets: ReplicaAssetImagesContent) -> ReplicaGenerationSegmentsContent:
    skill = get_professional_skill(SKILL_ID)
    asset_by_entity = _asset_lookup(assets)
    character_names = {item.target_character_id: item.display_name for item in storyboard.characters}
    segments: list[GenerationSegment] = []
    episode_counts: dict[str, int] = {}

    for shot in sorted(storyboard.shots, key=lambda item: (item.episode_order, item.shot_number)):
        part_count = max(1, math.ceil(shot.duration_us / MAX_SEGMENT_DURATION_US))
        for part_index in range(part_count):
            start_us = shot.start_us + part_index * MAX_SEGMENT_DURATION_US
            end_us = min(shot.end_us, start_us + MAX_SEGMENT_DURATION_US)
            dialogue_refs = _dialogue_refs(shot, start_us, end_us)
            conditions, asset_refs = _references(shot, dialogue_refs, assets_artifact.id, asset_by_entity)
            generation_prompt, review_prompt_zh = _prompt_for_segment(
                shot=shot,
                conditions=conditions,
                dialogue_refs=dialogue_refs,
                character_names=character_names,
                target_language=storyboard.target_language,
                continuation_index=part_index + 1,
                continuation_count=part_count,
            )
            episode_counts[shot.episode_id] = episode_counts.get(shot.episode_id, 0) + 1
            segment_number = episode_counts[shot.episode_id]
            segments.append(GenerationSegment(
                generation_segment_id=f"h3:{shot.episode_id}:{segment_number:04d}",
                episode_id=shot.episode_id,
                episode_order=shot.episode_order,
                segment_number=segment_number,
                storyboard_shot_ids=[shot.storyboard_shot_id],
                start_us=start_us,
                end_us=end_us,
                duration_us=end_us - start_us,
                output_ratio=shot.output_ratio,
                continuation_index=part_index + 1,
                continuation_count=part_count,
                generation_prompt=generation_prompt,
                negative_prompt="burned-in subtitles; watermark; source-language speech; extra dialogue; duplicate people; identity drift; malformed hands; extra limbs",
                prompt_skill_id=skill.id,
                prompt_skill_version=skill.version,
                prompt_contract=PROMPT_CONTRACT,
                model_id=MODEL_ID,
                review_prompt_zh=review_prompt_zh,
                reference_conditions=conditions,
                target_asset_refs=asset_refs,
                audio_generation_mode=GenerationAudioMode.NATIVE_AUDIO_VIDEO,
                dialogue_refs=dialogue_refs,
                sound_effects=list(shot.sound_effects),
                ambience=list(shot.ambience),
                requires_lip_sync=False,
            ))
    if not segments:
        raise AppError("H3_PROMPT_EMPTY", "本土化分镜没有可生成的视频段", status_code=409)
    return ReplicaGenerationSegmentsContent(
        schema_version=H3_PROMPT_SCHEMA_VERSION,
        title="MiniMax H3 多参考音画同步提示词",
        target_storyboard_artifact_id=storyboard_artifact.id,
        target_assets_artifact_id=assets_artifact.id,
        max_segment_duration_us=MAX_SEGMENT_DURATION_US,
        segments=segments,
    )


def create_h3_prompt_task(db: Session, *, project_id: str, idempotency_key: str) -> Task:
    project = get_project(db, project_id)
    if project.project_type != ProjectType.REPLICA:
        raise AppError("H3_PROMPT_PROJECT_UNSUPPORTED", "当前五步主生产链只正式支持 REPLICA", status_code=422)
    storyboard_artifact, _, assets_artifact, _ = _load_inputs(db, project_id)
    skill = get_professional_skill(SKILL_ID)
    fingerprint = _sha({
        "storyboard": [storyboard_artifact.id, storyboard_artifact.revision, storyboard_artifact.input_fingerprint],
        "assets": [assets_artifact.id, assets_artifact.revision, assets_artifact.input_fingerprint],
        "skill": [skill.id, skill.version],
        "model": MODEL_ID,
        "contract": PROMPT_CONTRACT,
    })
    return create_task_from_command(db, project_id=project_id, idempotency_key=idempotency_key, payload=TaskCommandCreate(
        task_type=TASK_TYPE,
        task_name="生成 MiniMax H3 多参考音画提示词",
        input_fingerprint=fingerprint,
        input_artifact_ids=[storyboard_artifact.id, assets_artifact.id],
        max_attempts=3,
    ))


def _claim(db: Session, task_id: str, worker_id: str) -> Task | None:
    task = db.get(Task, task_id)
    if task is None or task.task_type != TASK_TYPE or task.status != TaskStatus.QUEUED or task.attempt >= task.max_attempts:
        return None
    now = utc_now()
    result = db.execute(update(Task).where(
        Task.id == task_id,
        Task.task_type == TASK_TYPE,
        Task.status == TaskStatus.QUEUED,
        Task.attempt < Task.max_attempts,
    ).values(
        status=TaskStatus.RUNNING,
        attempt=task.attempt + 1,
        worker_id=worker_id,
        heartbeat_at=now,
        started_at=Task.started_at if task.started_at is not None else now,
        finished_at=None,
        updated_at=now,
    ))
    if result.rowcount != 1:
        db.rollback()
        return None
    db.commit()
    return db.get(Task, task_id)


def _publish(db: Session, task: TaskWorkerRead, content: ReplicaGenerationSegmentsContent) -> ArtifactNode:
    project = get_project(db, task.project_id)
    storyboard_artifact, _, assets_artifact, _ = _load_inputs(db, task.project_id)
    if content.target_storyboard_artifact_id != storyboard_artifact.id or content.target_assets_artifact_id != assets_artifact.id:
        raise AppError("H3_PROMPT_STALE_INPUT", "Prompt 编译期间上游分镜或资产已经变化", status_code=409)
    previous = db.scalar(select(ArtifactNode).where(
        ArtifactNode.project_id == task.project_id,
        ArtifactNode.artifact_type == ArtifactType.GENERATION_SEGMENTS.value,
        ArtifactNode.is_current.is_(True),
        ArtifactNode.validity == ArtifactValidity.CURRENT,
    ))
    latest = _latest(db, task.project_id, ArtifactType.GENERATION_SEGMENTS)
    if previous is not None:
        _mark_stale_with_downstream(db, [previous])
    skill = get_professional_skill(SKILL_ID)
    artifact = ArtifactNode(
        project_id=task.project_id,
        artifact_type=ArtifactType.GENERATION_SEGMENTS.value,
        namespace=ArtifactNamespace.PRODUCTION,
        label="MiniMax H3 多参考音画提示词",
        revision=(latest.revision if latest else 0) + 1,
        input_fingerprint=_sha({"task": task.input_fingerprint, "content": content.model_dump(mode="json")}),
        skill_id=skill.id,
        skill_version=skill.version,
        validity=ArtifactValidity.CURRENT,
        is_current=True,
        metadata_json={
            "schema_version": H3_PROMPT_SCHEMA_VERSION,
            "prompt_contract": PROMPT_CONTRACT,
            "model_id": MODEL_ID,
            "segment_count": len(content.segments),
            "reference_count": sum(len(item.reference_conditions) for item in content.segments),
        },
    )
    db.add(artifact)
    db.flush()
    provenance = H3PromptProvenance(
        target_storyboard_artifact_id=storyboard_artifact.id,
        target_storyboard_revision=storyboard_artifact.revision,
        target_storyboard_fingerprint=storyboard_artifact.input_fingerprint,
        target_assets_artifact_id=assets_artifact.id,
        target_assets_revision=assets_artifact.revision,
        target_assets_fingerprint=assets_artifact.input_fingerprint,
        professional_skill_version=skill.version,
        generated_by_task_id=task.id,
    )
    db.add(ReplicaH3PromptRevision(
        project_id=task.project_id,
        artifact_id=artifact.id,
        target_storyboard_artifact_id=storyboard_artifact.id,
        target_assets_artifact_id=assets_artifact.id,
        generated_by_task_id=task.id,
        schema_version=H3_PROMPT_SCHEMA_VERSION,
        content_json=content.model_dump(mode="json"),
        provenance_json=provenance.model_dump(mode="json"),
    ))
    db.add(ArtifactEdge(project_id=task.project_id, source_node_id=storyboard_artifact.id, target_node_id=artifact.id, relation_type=ArtifactRelationType.DERIVED_FROM))
    db.add(ArtifactEdge(project_id=task.project_id, source_node_id=assets_artifact.id, target_node_id=artifact.id, relation_type=ArtifactRelationType.USES))
    if latest is not None:
        db.add(ArtifactEdge(project_id=task.project_id, source_node_id=artifact.id, target_node_id=latest.id, relation_type=ArtifactRelationType.SUPERSEDES))
    _invalidate_project_plan(db, project)
    db.commit()
    db.refresh(artifact)
    return artifact


def run_h3_prompt_task(session_factory: sessionmaker[Session], task_id: str) -> None:
    worker_id = f"h3-prompt-{uuid4()}"
    with session_factory() as db:
        claimed = _claim(db, task_id, worker_id)
        if claimed is None:
            return
        task = TaskWorkerRead.model_validate(claimed)
    context = TaskExecutionContext(session_factory=session_factory, task_id=task.id, worker_id=worker_id)
    try:
        with session_factory() as db:
            storyboard_artifact, storyboard, assets_artifact, assets = _load_inputs(db, task.project_id)
        context.checkpoint({"stage": "compile", "skill": SKILL_ID}, progress_percent=20)
        content = compile_h3_segments(storyboard_artifact, storyboard, assets_artifact, assets)
        context.checkpoint({"stage": "publish", "segment_count": len(content.segments)}, progress_percent=90)
        with session_factory() as db:
            _publish(db, task, content)
            mark_task_succeeded(db, task.id, worker_id=worker_id)
    except TaskCancelled:
        return
    except AppError as exc:
        with session_factory() as db:
            mark_task_failed(db, task.id, safe_error=f"H3 提示词生成失败（{exc.code}）：{exc.message}", worker_id=worker_id)
    except Exception as exc:
        with session_factory() as db:
            mark_task_failed(db, task.id, safe_error=f"H3 提示词生成失败（{type(exc).__name__}）", worker_id=worker_id)


def get_h3_prompts(db: Session, project_id: str) -> H3PromptsRead:
    get_project(db, project_id)
    current = db.scalar(select(ArtifactNode).where(
        ArtifactNode.project_id == project_id,
        ArtifactNode.artifact_type == ArtifactType.GENERATION_SEGMENTS.value,
        ArtifactNode.is_current.is_(True),
        ArtifactNode.validity == ArtifactValidity.CURRENT,
    ))
    latest = current or _latest(db, project_id, ArtifactType.GENERATION_SEGMENTS)
    if latest is None:
        return H3PromptsRead(project_id=project_id, status=ResultStatus.NOT_BUILT)
    row = db.scalar(select(ReplicaH3PromptRevision).where(ReplicaH3PromptRevision.artifact_id == latest.id))
    if row is None:
        return H3PromptsRead(project_id=project_id, status=ResultStatus.NOT_BUILT)
    return H3PromptsRead(
        project_id=project_id,
        status=ResultStatus.CURRENT if current is not None else ResultStatus.STALE,
        artifact_id=latest.id,
        revision=latest.revision,
        input_fingerprint=latest.input_fingerprint,
        content=ReplicaGenerationSegmentsContent.model_validate(row.content_json).model_dump(mode="json"),
        provenance=H3PromptProvenance.model_validate(row.provenance_json),
    )
