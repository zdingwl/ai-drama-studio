import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy import func, inspect, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactEdge, ArtifactNode
from app.artifacts.service import _invalidate_project_plan, _mark_stale_with_downstream
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.time import utc_now
from app.projects.enums import ProjectType
from app.projects.service import get_project
from app.skills.capabilities import CAPABILITY_BY_ID
from app.skills.models import ArtifactType, Capability, CapabilityAvailability
from app.skills.professional import get_professional_skill
from app.target_assets.models import ReplicaTargetAssetsCandidate, ReplicaTargetAssetsRevision
from app.target_assets.providers import (
    TargetAssetsProvider,
    TargetAssetsProviderInput,
    TargetAssetsProviderResult,
    build_target_assets_provider,
)
from app.target_assets.schemas import (
    CandidateReviewStatus,
    P13_ENTITY_BINDING_CONTRACT,
    P13_PROMPT_VERSION,
    P13_REVIEW_CONTRACT,
    P13_SCHEMA_VERSION,
    P13_SKILL_ID,
    P13_TARGET_ASSET_CONTRACT,
    ReplicaTargetAssetsContent,
    ReplicaTargetAssetsRead,
    ReplicaTargetAssetsRevisionSummary,
    TargetAssetType,
    TargetAssetsCandidateProvenance,
    TargetAssetsCandidateRead,
    TargetAssetsProvenance,
    TargetAssetsProviderJobProvenance,
    TargetAssetsResultStatus,
    TargetAssetsReviewCommand,
    TargetAssetsSemantic,
    TargetCharacterAsset,
    TargetPropAsset,
    TargetSceneAsset,
)
from app.target_bible.models import ReplicaTargetRevision
from app.target_bible.schemas import ReplicaTargetBibleContent, TargetBibleArtifactKind
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


P13_TASK_TYPE = "P13_REPLICA_TARGET_ASSETS"
P13_FORMALLY_ADMITTED = True


@dataclass(frozen=True)
class P13Inputs:
    project: Any
    target_bible_artifact: ArtifactNode
    target_bible_revision: ReplicaTargetRevision
    target_bible: ReplicaTargetBibleContent
    base_target_assets_artifact: ArtifactNode | None
    base_target_assets: ReplicaTargetAssetsContent | None


@dataclass(frozen=True)
class P13ExecutionResult:
    content: ReplicaTargetAssetsContent
    provider_job: TargetAssetsProviderJobProvenance
    provider_profile: dict
    generation_sequence: int
    generation_base_fingerprint: str
    base_target_assets_artifact_id: str | None


def _sha(payload: object) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _stable_id(prefix: str, payload: object) -> str:
    return f"{prefix}_{_sha(payload)[:20]}"


def _assert_storage_ready(db: Session) -> None:
    inspector = inspect(db.get_bind())
    if not inspector.has_table(ReplicaTargetAssetsCandidate.__tablename__) or not inspector.has_table(
        ReplicaTargetAssetsRevision.__tablename__
    ):
        raise AppError(
            "P13_DATABASE_MIGRATION_REQUIRED",
            "P13 数据库迁移尚未应用，请先执行 alembic upgrade head",
            status_code=503,
        )


def _assert_p13_admitted() -> None:
    if not P13_FORMALLY_ADMITTED:
        raise AppError("P13_NOT_ADMITTED", "P13 尚未正式准入", status_code=409)
    if CAPABILITY_BY_ID[Capability.TARGET_BIBLE].availability != CapabilityAvailability.AVAILABLE:
        raise AppError(
            "P13_NOT_ADMITTED",
            "P11 Target Bible 能力尚未完成正式验收，当前不能执行 P13",
            status_code=409,
        )


def _assert_replica(project: Any) -> None:
    if project.project_type != ProjectType.REPLICA:
        raise AppError(
            "REPLICA_TARGET_ASSETS_NOT_ALLOWED",
            "当前 P13 目标资产仅用于复刻短剧",
            status_code=422,
        )


def _current_artifact(db: Session, project_id: str, artifact_type: ArtifactType) -> ArtifactNode | None:
    rows = list(
        db.scalars(
            select(ArtifactNode).where(
                ArtifactNode.project_id == project_id,
                ArtifactNode.artifact_type == artifact_type.value,
                ArtifactNode.validity == ArtifactValidity.CURRENT,
                ArtifactNode.is_current.is_(True),
            )
        ).all()
    )
    if len(rows) > 1:
        raise AppError(
            "P13_CURRENT_ARTIFACT_AMBIGUOUS",
            f"{artifact_type.value} 存在多个 CURRENT Artifact",
            status_code=409,
        )
    return rows[0] if rows else None


def _latest_artifact(db: Session, project_id: str, artifact_type: ArtifactType) -> ArtifactNode | None:
    return db.scalar(
        select(ArtifactNode)
        .where(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == artifact_type.value,
        )
        .order_by(ArtifactNode.revision.desc(), ArtifactNode.created_at.desc())
        .limit(1)
    )


def _load_assets_content(db: Session, artifact: ArtifactNode | None) -> ReplicaTargetAssetsContent | None:
    if artifact is None:
        return None
    row = db.scalar(
        select(ReplicaTargetAssetsRevision).where(ReplicaTargetAssetsRevision.artifact_id == artifact.id)
    )
    if row is None:
        raise AppError("P13_TARGET_ASSETS_CONTENT_MISSING", "TARGET_ASSETS 缺少 P13 typed revision", status_code=500)
    return ReplicaTargetAssetsContent.model_validate(row.content_json)


def _load_inputs(db: Session, project_id: str) -> P13Inputs:
    project = get_project(db, project_id)
    _assert_replica(project)
    _assert_p13_admitted()
    bible_artifact = _current_artifact(db, project_id, ArtifactType.TARGET_BIBLE)
    if bible_artifact is None:
        latest = _latest_artifact(db, project_id, ArtifactType.TARGET_BIBLE)
        if latest is None:
            raise AppError("P13_TARGET_BIBLE_REQUIRED", "P13 需要 CURRENT TARGET_BIBLE", status_code=409)
        raise AppError("P13_TARGET_BIBLE_STALE", "TARGET_BIBLE 已 STALE，请先重新生成目标设定", status_code=409)
    bible_row = db.scalar(
        select(ReplicaTargetRevision).where(ReplicaTargetRevision.artifact_id == bible_artifact.id)
    )
    if bible_row is None or bible_row.artifact_kind != TargetBibleArtifactKind.TARGET_BIBLE.value:
        raise AppError("P13_TARGET_BIBLE_CONTENT_MISSING", "CURRENT TARGET_BIBLE 缺少 P11 typed revision", status_code=500)
    bible = ReplicaTargetBibleContent.model_validate(bible_row.content_json)
    if bible.target_language != project.target_language or bible.target_region != project.target_region:
        raise AppError(
            "P13_TARGET_CONFIG_MISMATCH",
            "CURRENT TARGET_BIBLE 与项目目标语言或地区不一致",
            status_code=409,
        )
    for values, label in (
        ([item.target_character_id for item in bible.characters], "Character"),
        ([item.target_scene_id for item in bible.scenes], "Scene"),
        ([item.target_prop_id for item in bible.props], "Prop"),
    ):
        if len(values) != len(set(values)):
            raise AppError("P13_TARGET_ENTITY_SET_INVALID", f"Target {label} id 必须唯一", status_code=409)

    base_artifact = _latest_artifact(db, project_id, ArtifactType.TARGET_ASSETS)
    base_content = _load_assets_content(db, base_artifact)
    return P13Inputs(
        project=project,
        target_bible_artifact=bible_artifact,
        target_bible_revision=bible_row,
        target_bible=bible,
        base_target_assets_artifact=base_artifact,
        base_target_assets=base_content,
    )


def _entity_manifest(inputs: P13Inputs) -> dict[str, list[dict[str, str]]]:
    return {
        "characters": [
            {"target_character_id": item.target_character_id, "display_name": item.display_name}
            for item in inputs.target_bible.characters
        ],
        "scenes": [
            {"target_scene_id": item.target_scene_id, "display_name": item.display_name}
            for item in inputs.target_bible.scenes
        ],
        "props": [
            {"target_prop_id": item.target_prop_id, "display_name": item.display_name}
            for item in inputs.target_bible.props
        ],
    }


def _provider_for_project(project: Any) -> TargetAssetsProvider:
    return build_target_assets_provider(get_settings(), project.source_understanding_provider)


def _generation_base_fingerprint(inputs: P13Inputs, provider: TargetAssetsProvider) -> str:
    skill = get_professional_skill(P13_SKILL_ID)
    base = inputs.base_target_assets_artifact
    return _sha(
        {
            "task": P13_TASK_TYPE,
            "target_bible": [
                inputs.target_bible_artifact.id,
                inputs.target_bible_artifact.revision,
                inputs.target_bible_artifact.input_fingerprint,
            ],
            "base_target_assets": (
                [base.id, base.revision, base.input_fingerprint] if base is not None else None
            ),
            "target_language": inputs.project.target_language,
            "target_region": inputs.project.target_region,
            "skill": [skill.id, skill.version],
            "provider_profile": provider.profile(),
            "prompt_version": P13_PROMPT_VERSION,
            "schema_version": P13_SCHEMA_VERSION,
            "target_asset_contract": P13_TARGET_ASSET_CONTRACT,
            "entity_binding_contract": P13_ENTITY_BINDING_CONTRACT,
            "review_contract": P13_REVIEW_CONTRACT,
            "entity_manifest": _entity_manifest(inputs),
        }
    )


def _fingerprint_inputs(base_fingerprint: str, generation_sequence: int) -> str:
    return _sha(
        {
            "generation_base_fingerprint": base_fingerprint,
            "generation_sequence": generation_sequence,
        }
    )


def _latest_candidate(db: Session, project_id: str, target_bible_artifact_id: str) -> ReplicaTargetAssetsCandidate | None:
    return db.scalar(
        select(ReplicaTargetAssetsCandidate)
        .where(
            ReplicaTargetAssetsCandidate.project_id == project_id,
            ReplicaTargetAssetsCandidate.target_bible_artifact_id == target_bible_artifact_id,
        )
        .order_by(
            ReplicaTargetAssetsCandidate.generation_sequence.desc(),
            ReplicaTargetAssetsCandidate.created_at.desc(),
        )
        .limit(1)
    )


def _generation_sequence(
    db: Session,
    *,
    inputs: P13Inputs,
    base_fingerprint: str,
    regenerate: bool,
) -> int:
    latest = _latest_candidate(db, inputs.project.id, inputs.target_bible_artifact.id)
    if latest is None:
        return 1
    if not regenerate:
        try:
            provenance = TargetAssetsCandidateProvenance.model_validate(latest.provenance_json)
        except Exception:
            provenance = None
        if provenance is not None and provenance.generation_base_fingerprint == base_fingerprint:
            return latest.generation_sequence
    return latest.generation_sequence + 1


def create_target_assets_task(
    db: Session,
    *,
    project_id: str,
    idempotency_key: str,
    regenerate: bool = False,
) -> Task:
    _assert_storage_ready(db)
    inputs = _load_inputs(db, project_id)
    provider = _provider_for_project(inputs.project)
    base_fingerprint = _generation_base_fingerprint(inputs, provider)
    generation_sequence = _generation_sequence(
        db,
        inputs=inputs,
        base_fingerprint=base_fingerprint,
        regenerate=regenerate,
    )
    fingerprint = _fingerprint_inputs(base_fingerprint, generation_sequence)
    task = create_task_from_command(
        db,
        project_id=project_id,
        idempotency_key=idempotency_key,
        payload=TaskCommandCreate(
            task_type=P13_TASK_TYPE,
            task_name="重新生成目标资产候选" if regenerate else "生成目标资产候选",
            input_fingerprint=fingerprint,
            input_artifact_ids=[inputs.target_bible_artifact.id],
            max_attempts=3,
        ),
    )
    if not task.checkpoint_json:
        task.checkpoint_json = {
            "generation_sequence": generation_sequence,
            "generation_base_fingerprint": base_fingerprint,
        }
        db.add(task)
        db.commit()
        db.refresh(task)
    normalized_key = idempotency_key.strip()
    if task.status == TaskStatus.FAILED and task.attempt < task.max_attempts and task.idempotency_key != normalized_key:
        return retry_task(db, project_id, task.id)
    if task.status == TaskStatus.INTERRUPTED and task.attempt < task.max_attempts and task.idempotency_key != normalized_key:
        return resume_task(db, project_id, task.id)
    return task


def _task_generation(task: TaskWorkerRead | Task) -> tuple[int, str]:
    checkpoint = dict(task.checkpoint_json or {})
    sequence = checkpoint.get("generation_sequence")
    base_fingerprint = checkpoint.get("generation_base_fingerprint")
    if not isinstance(sequence, int) or sequence < 1 or not isinstance(base_fingerprint, str) or len(base_fingerprint) != 64:
        raise AppError("P13_TASK_GENERATION_CONTEXT_MISSING", "P13 Task 缺少生成序列上下文", status_code=500)
    return sequence, base_fingerprint


def _checkpoint(
    context: TaskExecutionContext,
    *,
    stage: str,
    progress_percent: int,
    generation_sequence: int,
    generation_base_fingerprint: str,
) -> None:
    context.checkpoint(
        {
            "stage": stage,
            "generation_sequence": generation_sequence,
            "generation_base_fingerprint": generation_base_fingerprint,
        },
        progress_percent=progress_percent,
    )


def _assert_task_inputs(
    task: TaskWorkerRead | Task,
    inputs: P13Inputs,
    provider: TargetAssetsProvider,
    generation_sequence: int,
    generation_base_fingerprint: str,
) -> None:
    if list(task.input_artifact_ids_json) != [inputs.target_bible_artifact.id]:
        raise AppError("STALE_ARTIFACT_INPUT", "P13 TARGET_BIBLE 输入已变化，请重新创建任务", status_code=409)
    current_base = _generation_base_fingerprint(inputs, provider)
    if current_base != generation_base_fingerprint:
        raise AppError("STALE_ARTIFACT_INPUT", "P13 Target Bible、Provider profile 或正式资产基线已变化", status_code=409)
    if task.input_fingerprint != _fingerprint_inputs(current_base, generation_sequence):
        raise AppError("STALE_ARTIFACT_INPUT", "P13 生成序列或输入 fingerprint 已变化", status_code=409)


def _validate_semantic(inputs: P13Inputs, semantic: TargetAssetsSemantic) -> None:
    expected_characters = [item.target_character_id for item in inputs.target_bible.characters]
    expected_scenes = [item.target_scene_id for item in inputs.target_bible.scenes]
    expected_props = [item.target_prop_id for item in inputs.target_bible.props]
    actual_characters = [item.target_character_id for item in semantic.characters]
    actual_scenes = [item.target_scene_id for item in semantic.scenes]
    actual_props = [item.target_prop_id for item in semantic.props]
    if actual_characters != expected_characters or len(actual_characters) != len(set(actual_characters)):
        raise AppError(
            "P13_CHARACTER_COVERAGE_INVALID",
            "Target Character Asset 必须按 CURRENT Target Bible 顺序一一完整覆盖",
            status_code=422,
        )
    if actual_scenes != expected_scenes or len(actual_scenes) != len(set(actual_scenes)):
        raise AppError(
            "P13_SCENE_COVERAGE_INVALID",
            "Target Scene Asset 必须按 CURRENT Target Bible 顺序一一完整覆盖",
            status_code=422,
        )
    if actual_props != expected_props or len(actual_props) != len(set(actual_props)):
        raise AppError(
            "P13_PROP_COVERAGE_INVALID",
            "Target Prop Asset 必须按 CURRENT Target Bible 顺序一一完整覆盖",
            status_code=422,
        )


def _merge_rules(*groups: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for raw in group:
            value = raw.strip()
            if value and value not in seen:
                seen.add(value)
                result.append(value)
    return result


def _asset_id(project_id: str, asset_type: TargetAssetType, target_entity_id: str) -> str:
    prefix = {
        TargetAssetType.CHARACTER: "tasset_chr",
        TargetAssetType.SCENE: "tasset_scn",
        TargetAssetType.PROP: "tasset_prop",
    }[asset_type]
    return _stable_id(
        prefix,
        [project_id, asset_type.value, target_entity_id, P13_ENTITY_BINDING_CONTRACT],
    )


def _previous_asset_map(content: ReplicaTargetAssetsContent | None) -> dict[str, Any]:
    if content is None:
        return {}
    values = [*content.characters, *content.scenes, *content.props]
    return {item.target_asset_id: item for item in values}


def _revision_for(previous: dict[str, Any], asset_id: str, fingerprint: str) -> int:
    old = previous.get(asset_id)
    if old is None:
        return 1
    if old.asset_fingerprint == fingerprint:
        return old.target_asset_revision
    return old.target_asset_revision + 1


def _compose(inputs: P13Inputs, semantic: TargetAssetsSemantic) -> ReplicaTargetAssetsContent:
    _validate_semantic(inputs, semantic)
    previous = _previous_asset_map(inputs.base_target_assets)

    characters: list[TargetCharacterAsset] = []
    for bible, generated in zip(inputs.target_bible.characters, semantic.characters, strict=True):
        asset_id = _asset_id(inputs.project.id, TargetAssetType.CHARACTER, bible.target_character_id)
        payload = {
            "asset_type": TargetAssetType.CHARACTER.value,
            "target_entity_id": bible.target_character_id,
            "target_character_id": bible.target_character_id,
            "display_name": bible.display_name,
            "identity_direction": bible.localized_identity,
            "demographic_direction": generated.demographic_direction,
            "face_direction": generated.face_direction,
            "hair_direction": generated.hair_direction,
            "body_direction": generated.body_direction,
            "wardrobe_baseline": generated.wardrobe_baseline,
            "signature_visual_features": generated.signature_visual_features,
            "continuity_constraints": _merge_rules(generated.continuity_constraints),
            "generation_guidance": generated.generation_guidance,
            "negative_constraints": generated.negative_constraints,
            "reference_media": [],
        }
        fingerprint = _sha(payload)
        characters.append(
            TargetCharacterAsset(
                target_asset_id=asset_id,
                target_asset_revision=_revision_for(previous, asset_id, fingerprint),
                asset_fingerprint=fingerprint,
                **payload,
            )
        )

    scenes: list[TargetSceneAsset] = []
    for bible, generated in zip(inputs.target_bible.scenes, semantic.scenes, strict=True):
        asset_id = _asset_id(inputs.project.id, TargetAssetType.SCENE, bible.target_scene_id)
        payload = {
            "asset_type": TargetAssetType.SCENE.value,
            "target_entity_id": bible.target_scene_id,
            "target_scene_id": bible.target_scene_id,
            "display_name": bible.display_name,
            "spatial_identity": bible.localized_setting,
            "layout": generated.layout,
            "architecture_style": generated.architecture_style,
            "interior_exterior_style": generated.interior_exterior_style,
            "materials_palette": generated.materials_palette,
            "fixed_landmarks": generated.fixed_landmarks,
            "lighting_baseline": generated.lighting_baseline,
            "time_of_day_baseline": generated.time_of_day_baseline,
            "continuity_constraints": _merge_rules(generated.continuity_constraints),
            "generation_guidance": generated.generation_guidance,
            "negative_constraints": generated.negative_constraints,
            "reference_media": [],
        }
        fingerprint = _sha(payload)
        scenes.append(
            TargetSceneAsset(
                target_asset_id=asset_id,
                target_asset_revision=_revision_for(previous, asset_id, fingerprint),
                asset_fingerprint=fingerprint,
                **payload,
            )
        )

    props: list[TargetPropAsset] = []
    for bible, generated in zip(inputs.target_bible.props, semantic.props, strict=True):
        asset_id = _asset_id(inputs.project.id, TargetAssetType.PROP, bible.target_prop_id)
        payload = {
            "asset_type": TargetAssetType.PROP.value,
            "target_entity_id": bible.target_prop_id,
            "target_prop_id": bible.target_prop_id,
            "display_name": bible.display_name,
            "functional_identity": bible.localized_form,
            "visual_form": generated.visual_form,
            "materials": generated.materials,
            "color_palette": generated.color_palette,
            "scale_reference": generated.scale_reference,
            "signature_visual_features": generated.signature_visual_features,
            "continuity_constraints": _merge_rules(generated.continuity_constraints),
            "generation_guidance": generated.generation_guidance,
            "negative_constraints": generated.negative_constraints,
            "reference_media": [],
        }
        fingerprint = _sha(payload)
        props.append(
            TargetPropAsset(
                target_asset_id=asset_id,
                target_asset_revision=_revision_for(previous, asset_id, fingerprint),
                asset_fingerprint=fingerprint,
                **payload,
            )
        )

    return ReplicaTargetAssetsContent(
        target_bible_artifact_id=inputs.target_bible_artifact.id,
        target_language=inputs.target_bible.target_language,
        target_region=inputs.target_bible.target_region,
        visual_style=inputs.target_bible.visual_style,
        characters=characters,
        scenes=scenes,
        props=props,
    )


def _provider_input(inputs: P13Inputs) -> TargetAssetsProviderInput:
    return TargetAssetsProviderInput(
        target_language=inputs.project.target_language,
        target_region=inputs.project.target_region,
        target_bible=inputs.target_bible.model_dump(mode="json"),
        entity_manifest=_entity_manifest(inputs),
    )


def _dispatch(provider: TargetAssetsProvider, payload: TargetAssetsProviderInput) -> ProviderDispatchResult:
    result: TargetAssetsProviderResult = provider.design(payload)
    return ProviderDispatchResult(value=result.semantic, remote_job_id=result.remote_job_id, completed=True)


def _execute(context: TaskExecutionContext, task: TaskWorkerRead) -> P13ExecutionResult:
    _assert_p13_admitted()
    generation_sequence, base_fingerprint = _task_generation(task)
    with context.session_factory() as db:
        inputs = _load_inputs(db, task.project_id)
        provider = _provider_for_project(inputs.project)
        _assert_task_inputs(task, inputs, provider, generation_sequence, base_fingerprint)
        profile = provider.profile()
        base_artifact_id = inputs.base_target_assets_artifact.id if inputs.base_target_assets_artifact else None

    _checkpoint(
        context,
        stage="target_asset_identity_manifest",
        progress_percent=15,
        generation_sequence=generation_sequence,
        generation_base_fingerprint=base_fingerprint,
    )
    payload = _provider_input(inputs)
    _checkpoint(
        context,
        stage="design_visual_identity_packets",
        progress_percent=25,
        generation_sequence=generation_sequence,
        generation_base_fingerprint=base_fingerprint,
    )
    job_payload = {
        "profile": P13_PROMPT_VERSION,
        "schema_version": P13_SCHEMA_VERSION,
        "target_asset_contract": P13_TARGET_ASSET_CONTRACT,
        "entity_binding_contract": P13_ENTITY_BINDING_CONTRACT,
        "review_contract": P13_REVIEW_CONTRACT,
        "professional_skill_id": P13_SKILL_ID,
        "professional_skill_version": get_professional_skill(P13_SKILL_ID).version,
        "target_bible_artifact_id": inputs.target_bible_artifact.id,
        "target_bible_fingerprint": inputs.target_bible_artifact.input_fingerprint,
        "generation_sequence": generation_sequence,
        "provider_profile": profile,
        "reference_media_generation": "NOT_CONFIGURED",
    }
    with context.session_factory() as db:
        job, dispatched = dispatch_provider_call(
            db,
            task_id=task.id,
            provider=provider.provider_name,
            model=provider.model_name,
            capability=Capability.TARGET_ASSETS,
            payload=job_payload,
            artifact_id=inputs.target_bible_artifact.id,
            remote_call=lambda _job: _dispatch(provider, payload),
        )
    _checkpoint(
        context,
        stage="validate_target_asset_lineage",
        progress_percent=82,
        generation_sequence=generation_sequence,
        generation_base_fingerprint=base_fingerprint,
    )
    raw = dispatched.value
    semantic = raw if isinstance(raw, TargetAssetsSemantic) else TargetAssetsSemantic.model_validate(raw)
    content = _compose(inputs, semantic)
    _checkpoint(
        context,
        stage="stage_for_human_review",
        progress_percent=94,
        generation_sequence=generation_sequence,
        generation_base_fingerprint=base_fingerprint,
    )
    provider_job = TargetAssetsProviderJobProvenance(
        provider_job_id=job.id,
        provider=job.provider,
        model=job.model,
        capability=job.capability,
        professional_skill_id=P13_SKILL_ID,
        payload_fingerprint=job.payload_fingerprint,
        remote_job_id=job.remote_job_id,
    )
    return P13ExecutionResult(
        content=content,
        provider_job=provider_job,
        provider_profile=profile,
        generation_sequence=generation_sequence,
        generation_base_fingerprint=base_fingerprint,
        base_target_assets_artifact_id=base_artifact_id,
    )


def _candidate_provenance(task: Task, inputs: P13Inputs, result: P13ExecutionResult) -> TargetAssetsCandidateProvenance:
    skill = get_professional_skill(P13_SKILL_ID)
    return TargetAssetsCandidateProvenance(
        target_bible_artifact_id=inputs.target_bible_artifact.id,
        target_bible_revision=inputs.target_bible_artifact.revision,
        target_bible_fingerprint=inputs.target_bible_artifact.input_fingerprint,
        base_target_assets_artifact_id=result.base_target_assets_artifact_id,
        target_language=inputs.project.target_language,
        target_region=inputs.project.target_region,
        generation_sequence=result.generation_sequence,
        generation_base_fingerprint=result.generation_base_fingerprint,
        professional_skill_version=skill.version,
        provider=result.provider_job.provider,
        model=result.provider_job.model,
        provider_job=result.provider_job,
        generated_by_task_id=task.id,
    )


def _stage_candidate(db: Session, *, task_id: str, result: P13ExecutionResult) -> ReplicaTargetAssetsCandidate:
    existing = db.scalar(
        select(ReplicaTargetAssetsCandidate).where(ReplicaTargetAssetsCandidate.generated_by_task_id == task_id)
    )
    if existing is not None:
        return existing
    task = db.get(Task, task_id)
    if task is None:
        raise AppError("TASK_NOT_FOUND", "P13 任务不存在", status_code=404)
    if task.status != TaskStatus.SUCCEEDED:
        raise AppError("TASK_NOT_SUCCEEDED", "只有执行成功的 P13 Task 才能生成待确认候选", status_code=409)
    inputs = _load_inputs(db, task.project_id)
    provider = _provider_for_project(inputs.project)
    _assert_task_inputs(
        task,
        inputs,
        provider,
        result.generation_sequence,
        result.generation_base_fingerprint,
    )
    current_base_id = inputs.base_target_assets_artifact.id if inputs.base_target_assets_artifact else None
    if current_base_id != result.base_target_assets_artifact_id:
        raise AppError("P13_BASE_ASSETS_CHANGED", "正式目标资产基线已变化，请重新生成候选", status_code=409)
    provenance = _candidate_provenance(task, inputs, result)
    candidate = ReplicaTargetAssetsCandidate(
        project_id=task.project_id,
        target_bible_artifact_id=inputs.target_bible_artifact.id,
        base_target_assets_artifact_id=result.base_target_assets_artifact_id,
        generated_by_task_id=task.id,
        generation_sequence=result.generation_sequence,
        input_fingerprint=task.input_fingerprint,
        schema_version=P13_SCHEMA_VERSION,
        content_json=result.content.model_dump(mode="json"),
        provenance_json=provenance.model_dump(mode="json"),
        review_status=CandidateReviewStatus.NEEDS_REVIEW.value,
    )
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return candidate


def _claim(db: Session, task_id: str, worker_id: str) -> Task | None:
    task = db.get(Task, task_id)
    if (
        task is None
        or task.task_type != P13_TASK_TYPE
        or task.status != TaskStatus.QUEUED
        or task.attempt >= task.max_attempts
    ):
        return None
    now = utc_now()
    result = db.execute(
        update(Task)
        .where(
            Task.id == task_id,
            Task.task_type == P13_TASK_TYPE,
            Task.status == TaskStatus.QUEUED,
            Task.attempt < Task.max_attempts,
        )
        .values(
            status=TaskStatus.RUNNING,
            attempt=task.attempt + 1,
            worker_id=worker_id,
            heartbeat_at=now,
            started_at=func.coalesce(Task.started_at, now),
            finished_at=None,
            updated_at=now,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        return None
    db.commit()
    claimed = db.get(Task, task_id)
    if claimed is not None:
        db.refresh(claimed)
    return claimed


def _fail_if_running(factory: sessionmaker[Session], task_id: str, worker_id: str, message: str) -> None:
    with factory() as db:
        task = db.get(Task, task_id)
        if task is not None and task.status == TaskStatus.RUNNING and task.worker_id == worker_id:
            mark_task_failed(db, task_id, safe_error=message, worker_id=worker_id)


def _mark_stage_failed(factory: sessionmaker[Session], task_id: str, message: str) -> None:
    with factory() as db:
        task = db.get(Task, task_id)
        if task is None or task.status != TaskStatus.SUCCEEDED:
            return
        now = utc_now()
        task.status = TaskStatus.FAILED
        task.progress_percent = min(task.progress_percent, 99)
        task.last_error = message[:1000]
        task.finished_at = now
        task.updated_at = now
        db.add(task)
        db.commit()


def run_target_assets_task(session_factory: sessionmaker[Session], task_id: str) -> None:
    worker_id = f"p13-target-assets-{uuid4()}"
    with session_factory() as db:
        claimed = _claim(db, task_id, worker_id)
        if claimed is None:
            return
        snapshot = TaskWorkerRead.model_validate(claimed)
    context = TaskExecutionContext(session_factory=session_factory, task_id=snapshot.id, worker_id=worker_id)
    try:
        result = _execute(context, snapshot)
    except TaskCancelled:
        return
    except AppError as exc:
        _fail_if_running(
            session_factory,
            snapshot.id,
            worker_id,
            f"P13 目标资产失败（{exc.code}）：{exc.message}",
        )
        return
    except Exception as exc:
        _fail_if_running(
            session_factory,
            snapshot.id,
            worker_id,
            f"P13 目标资产失败（{type(exc).__name__}）",
        )
        return

    with session_factory() as db:
        finished = mark_task_succeeded(db, snapshot.id, worker_id=worker_id)
    if finished.status == TaskStatus.CANCELLED:
        return
    try:
        with session_factory() as db:
            _stage_candidate(db, task_id=snapshot.id, result=result)
    except AppError as exc:
        _mark_stage_failed(
            session_factory,
            snapshot.id,
            f"P13 候选持久化失败（{exc.code}）：{exc.message}",
        )
    except Exception as exc:
        _mark_stage_failed(
            session_factory,
            snapshot.id,
            f"P13 候选持久化失败（{type(exc).__name__}）",
        )


def _candidate_read(row: ReplicaTargetAssetsCandidate) -> TargetAssetsCandidateRead:
    return TargetAssetsCandidateRead(
        id=row.id,
        project_id=row.project_id,
        target_bible_artifact_id=row.target_bible_artifact_id,
        base_target_assets_artifact_id=row.base_target_assets_artifact_id,
        generated_by_task_id=row.generated_by_task_id,
        generation_sequence=row.generation_sequence,
        input_fingerprint=row.input_fingerprint,
        schema_version=row.schema_version,
        review_status=CandidateReviewStatus(row.review_status),
        review_reason=row.review_reason,
        reviewed_at=row.reviewed_at,
        created_at=row.created_at,
        content=ReplicaTargetAssetsContent.model_validate(row.content_json),
        provenance=TargetAssetsCandidateProvenance.model_validate(row.provenance_json),
    )


def list_target_assets_candidates(db: Session, project_id: str) -> list[TargetAssetsCandidateRead]:
    _assert_storage_ready(db)
    project = get_project(db, project_id)
    _assert_replica(project)
    rows = list(
        db.scalars(
            select(ReplicaTargetAssetsCandidate)
            .where(ReplicaTargetAssetsCandidate.project_id == project_id)
            .order_by(
                ReplicaTargetAssetsCandidate.created_at.desc(),
                ReplicaTargetAssetsCandidate.generation_sequence.desc(),
            )
        ).all()
    )
    return [_candidate_read(row) for row in rows]


def get_target_assets(db: Session, project_id: str) -> ReplicaTargetAssetsRead:
    _assert_storage_ready(db)
    project = get_project(db, project_id)
    _assert_replica(project)
    current = _current_artifact(db, project_id, ArtifactType.TARGET_ASSETS)
    latest = current or _latest_artifact(db, project_id, ArtifactType.TARGET_ASSETS)
    if latest is None:
        return ReplicaTargetAssetsRead(project_id=project_id, status=TargetAssetsResultStatus.NOT_BUILT)
    row = db.scalar(
        select(ReplicaTargetAssetsRevision).where(ReplicaTargetAssetsRevision.artifact_id == latest.id)
    )
    if row is None:
        raise AppError("P13_TARGET_ASSETS_CONTENT_MISSING", "TARGET_ASSETS 缺少 P13 typed revision", status_code=500)
    return ReplicaTargetAssetsRead(
        project_id=project_id,
        status=TargetAssetsResultStatus.CURRENT if current is not None else TargetAssetsResultStatus.STALE,
        artifact_id=latest.id,
        revision=latest.revision,
        input_fingerprint=latest.input_fingerprint,
        content=ReplicaTargetAssetsContent.model_validate(row.content_json),
        provenance=TargetAssetsProvenance.model_validate(row.provenance_json),
    )


def list_target_assets_revisions(db: Session, project_id: str) -> list[ReplicaTargetAssetsRevisionSummary]:
    _assert_storage_ready(db)
    project = get_project(db, project_id)
    _assert_replica(project)
    artifacts = list(
        db.scalars(
            select(ArtifactNode)
            .where(
                ArtifactNode.project_id == project_id,
                ArtifactNode.artifact_type == ArtifactType.TARGET_ASSETS.value,
            )
            .order_by(ArtifactNode.created_at.desc(), ArtifactNode.revision.desc())
        ).all()
    )
    result: list[ReplicaTargetAssetsRevisionSummary] = []
    for artifact in artifacts:
        row = db.scalar(
            select(ReplicaTargetAssetsRevision).where(ReplicaTargetAssetsRevision.artifact_id == artifact.id)
        )
        if row is None:
            continue
        result.append(
            ReplicaTargetAssetsRevisionSummary(
                artifact_id=artifact.id,
                revision=artifact.revision,
                validity=artifact.validity.value,
                input_fingerprint=artifact.input_fingerprint,
                target_bible_artifact_id=row.target_bible_artifact_id,
                candidate_id=row.candidate_id,
                created_at=artifact.created_at.isoformat(),
            )
        )
    return result


def _review_candidate(
    db: Session,
    *,
    project_id: str,
    candidate_id: str,
    command: TargetAssetsReviewCommand,
) -> tuple[ReplicaTargetAssetsCandidate, P13Inputs]:
    inputs = _load_inputs(db, project_id)
    if command.expected_target_bible_artifact_id != inputs.target_bible_artifact.id:
        raise AppError("P13_REVIEW_TARGET_BIBLE_CHANGED", "Target Bible 已变化，请刷新后重新审核", status_code=409)
    candidate = db.get(ReplicaTargetAssetsCandidate, candidate_id)
    if candidate is None or candidate.project_id != project_id:
        raise AppError("P13_CANDIDATE_NOT_FOUND", "目标资产候选不存在", status_code=404)
    if candidate.review_status != CandidateReviewStatus.NEEDS_REVIEW.value:
        raise AppError("P13_CANDIDATE_NOT_REVIEWABLE", "目标资产候选当前状态不能再次审核", status_code=409)
    if candidate.target_bible_artifact_id != inputs.target_bible_artifact.id:
        raise AppError("P13_CANDIDATE_TARGET_BIBLE_STALE", "候选基于旧 Target Bible，不能发布", status_code=409)
    if candidate.generation_sequence != command.expected_generation_sequence:
        raise AppError("P13_CANDIDATE_REVISION_CHANGED", "候选生成序列已变化，请刷新后重试", status_code=409)
    latest_base = inputs.base_target_assets_artifact.id if inputs.base_target_assets_artifact else None
    if candidate.base_target_assets_artifact_id != latest_base:
        raise AppError("P13_CANDIDATE_BASE_CHANGED", "正式目标资产基线已变化，请重新生成候选", status_code=409)
    ReplicaTargetAssetsContent.model_validate(candidate.content_json)
    TargetAssetsCandidateProvenance.model_validate(candidate.provenance_json)
    return candidate, inputs


def reject_target_assets_candidate(
    db: Session,
    *,
    project_id: str,
    candidate_id: str,
    command: TargetAssetsReviewCommand,
) -> TargetAssetsCandidateRead:
    _assert_storage_ready(db)
    candidate, _inputs = _review_candidate(
        db,
        project_id=project_id,
        candidate_id=candidate_id,
        command=command,
    )
    candidate.review_status = CandidateReviewStatus.REJECTED.value
    candidate.review_reason = command.reason.strip()
    candidate.reviewed_at = utc_now()
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return _candidate_read(candidate)


def _next_revision(db: Session, project_id: str) -> int:
    latest = db.scalar(
        select(func.max(ArtifactNode.revision)).where(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == ArtifactType.TARGET_ASSETS.value,
        )
    )
    return int(latest or 0) + 1


def accept_target_assets_candidate(
    db: Session,
    *,
    project_id: str,
    candidate_id: str,
    command: TargetAssetsReviewCommand,
) -> ReplicaTargetAssetsRead:
    _assert_storage_ready(db)
    candidate, inputs = _review_candidate(
        db,
        project_id=project_id,
        candidate_id=candidate_id,
        command=command,
    )
    content = ReplicaTargetAssetsContent.model_validate(candidate.content_json)
    candidate_provenance = TargetAssetsCandidateProvenance.model_validate(candidate.provenance_json)
    previous_current = _current_artifact(db, project_id, ArtifactType.TARGET_ASSETS)
    previous_latest = _latest_artifact(db, project_id, ArtifactType.TARGET_ASSETS)
    if previous_current is not None:
        _mark_stale_with_downstream(db, [previous_current])

    fingerprint = _sha(
        {
            "candidate_id": candidate.id,
            "candidate_input_fingerprint": candidate.input_fingerprint,
            "schema_version": P13_SCHEMA_VERSION,
            "content": content.model_dump(mode="json"),
        }
    )
    skill = get_professional_skill(P13_SKILL_ID)
    artifact = ArtifactNode(
        project_id=project_id,
        artifact_type=ArtifactType.TARGET_ASSETS.value,
        namespace=ArtifactNamespace.TARGET,
        label="目标资产",
        revision=_next_revision(db, project_id),
        input_fingerprint=fingerprint,
        skill_id=skill.id,
        skill_version=skill.version,
        validity=ArtifactValidity.CURRENT,
        is_current=True,
        metadata_json={
            "schema_version": P13_SCHEMA_VERSION,
            "target_bible_artifact_id": inputs.target_bible_artifact.id,
            "candidate_id": candidate.id,
            "character_count": len(content.characters),
            "scene_count": len(content.scenes),
            "prop_count": len(content.props),
            "reference_media_count": sum(
                len(item.reference_media) for item in [*content.characters, *content.scenes, *content.props]
            ),
            "review_contract": P13_REVIEW_CONTRACT,
        },
    )
    reviewed_at = utc_now()
    provenance = TargetAssetsProvenance(
        **candidate_provenance.model_dump(),
        candidate_id=candidate.id,
        reviewed_at=reviewed_at,
        review_reason=command.reason.strip(),
        supersedes_artifact_id=previous_latest.id if previous_latest is not None else None,
    )
    try:
        db.add(artifact)
        db.flush()
        db.add(
            ReplicaTargetAssetsRevision(
                project_id=project_id,
                artifact_id=artifact.id,
                target_bible_artifact_id=inputs.target_bible_artifact.id,
                candidate_id=candidate.id,
                generated_by_task_id=candidate.generated_by_task_id,
                schema_version=P13_SCHEMA_VERSION,
                content_json=content.model_dump(mode="json"),
                provenance_json=provenance.model_dump(mode="json"),
            )
        )
        db.add(
            ArtifactEdge(
                project_id=project_id,
                source_node_id=inputs.target_bible_artifact.id,
                target_node_id=artifact.id,
                relation_type=ArtifactRelationType.DERIVED_FROM,
            )
        )
        if previous_latest is not None:
            db.add(
                ArtifactEdge(
                    project_id=project_id,
                    source_node_id=artifact.id,
                    target_node_id=previous_latest.id,
                    relation_type=ArtifactRelationType.SUPERSEDES,
                )
            )
        pending = list(
            db.scalars(
                select(ReplicaTargetAssetsCandidate).where(
                    ReplicaTargetAssetsCandidate.project_id == project_id,
                    ReplicaTargetAssetsCandidate.review_status == CandidateReviewStatus.NEEDS_REVIEW.value,
                    ReplicaTargetAssetsCandidate.id != candidate.id,
                )
            ).all()
        )
        for other in pending:
            other.review_status = CandidateReviewStatus.SUPERSEDED.value
            other.review_reason = "A newer candidate was explicitly accepted."
            other.reviewed_at = reviewed_at
            db.add(other)
        candidate.review_status = CandidateReviewStatus.ACCEPTED.value
        candidate.review_reason = command.reason.strip()
        candidate.reviewed_at = reviewed_at
        db.add(candidate)
        _invalidate_project_plan(db, inputs.project)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(artifact)
    return ReplicaTargetAssetsRead(
        project_id=project_id,
        status=TargetAssetsResultStatus.CURRENT,
        artifact_id=artifact.id,
        revision=artifact.revision,
        input_fingerprint=artifact.input_fingerprint,
        content=content,
        provenance=provenance,
    )