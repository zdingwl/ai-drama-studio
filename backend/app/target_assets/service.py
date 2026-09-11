from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import func, inspect, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactEdge, ArtifactNode
from app.artifacts.service import _invalidate_project_plan, _mark_stale_with_downstream
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.time import utc_now
from app.projects.enums import ProjectType
from app.projects.service import get_project
from app.skills.capabilities import CAPABILITY_BY_ID
from app.skills.models import ArtifactType, Capability, CapabilityAvailability
from app.skills.professional import get_professional_skill
from app.target_assets.models import ReplicaTargetAssetsCandidate, ReplicaTargetAssetsRevision
from app.target_assets.providers import (
    TargetAssetImageProvider,
    TargetAssetImageProviderResult,
    TargetAssetImageRequest,
    TargetAssetsSpecProvider,
    TargetAssetsSpecProviderResult,
    build_target_asset_image_provider,
    build_target_assets_spec_provider,
)
from app.target_assets.schemas import (
    P13_PROMPT_VERSION,
    P13_SCHEMA_VERSION,
    P13_SKILL_ID,
    P13_TARGET_CONTRACT,
    ReplicaTargetAssetsContent,
    ReplicaTargetAssetsRead,
    ReplicaTargetAssetsRevisionSummary,
    ReplicaTargetCharacterAsset,
    ReplicaTargetPropAsset,
    ReplicaTargetSceneAsset,
    TargetAssetCandidateStatus,
    TargetAssetKind,
    TargetAssetResultStatus,
    TargetAssetsCandidateRead,
    TargetAssetsGenerateCommand,
    TargetAssetsProvenance,
    TargetAssetsProviderInput,
    TargetAssetsProviderJobProvenance,
    TargetAssetsSemantic,
)
from app.target_assets.storage import store_reference_image, verify_reference_image
from app.target_bible.models import ReplicaTargetRevision
from app.target_bible.schemas import ReplicaTargetBibleContent, TargetBibleArtifactKind
from app.workflow.models import Task, TaskStatus
from app.workflow.provider_service import ProviderDispatchResult, dispatch_provider_call
from app.workflow.schemas import TaskCommandCreate, TaskWorkerRead
from app.workflow.task_service import TaskCancelled, create_task_from_command, mark_task_failed, mark_task_succeeded
from app.workflow.worker import TaskExecutionContext


P13_TASK_TYPE = "P13_TARGET_ASSETS"
# P12 has passed real manual acceptance, so P13 may be engineered and validated.
# TARGET_ASSETS intentionally remains PLANNED until the user explicitly accepts P13.
P13_FORMALLY_ADMITTED = True


@dataclass(frozen=True)
class P13Inputs:
    project: Any
    target_bible_artifact: ArtifactNode
    target_bible_revision: ReplicaTargetRevision
    target_bible: ReplicaTargetBibleContent


@dataclass(frozen=True)
class AssetBinding:
    target_asset_id: str
    asset_kind: TargetAssetKind
    target_entity_id: str
    entity: Any


@dataclass(frozen=True)
class P13Providers:
    spec: TargetAssetsSpecProvider
    image: TargetAssetImageProvider


@dataclass(frozen=True)
class ReferenceLookup:
    path: Path
    media_type: str


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
    missing = [
        name
        for name in (
            ReplicaTargetAssetsCandidate.__tablename__,
            ReplicaTargetAssetsRevision.__tablename__,
        )
        if not inspector.has_table(name)
    ]
    if missing:
        raise AppError(
            "P13_DATABASE_MIGRATION_REQUIRED",
            "P13 数据库迁移尚未应用，请先执行 alembic upgrade head",
            status_code=503,
            details={"missing_tables": missing},
        )


def _assert_p13_admitted() -> None:
    if not P13_FORMALLY_ADMITTED:
        raise AppError("P13_NOT_ADMITTED", "P13 尚未正式准入", status_code=409)
    blockers = [
        capability.value
        for capability in (Capability.TARGET_BIBLE, Capability.TARGET_SCRIPT)
        if CAPABILITY_BY_ID[capability].availability != CapabilityAvailability.AVAILABLE
    ]
    if blockers:
        raise AppError(
            "P13_NOT_ADMITTED",
            "P12 验收能力状态不完整，当前不能执行目标资产生成",
            status_code=409,
            details={"required_capabilities": blockers},
        )


def _assert_replica(project: Any) -> None:
    if project.project_type != ProjectType.REPLICA:
        raise AppError(
            "REPLICA_TARGET_ASSETS_NOT_ALLOWED",
            "当前 P13 Target Assets 仅用于复刻短剧",
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
        .where(ArtifactNode.project_id == project_id, ArtifactNode.artifact_type == artifact_type.value)
        .order_by(ArtifactNode.revision.desc(), ArtifactNode.created_at.desc())
        .limit(1)
    )


def _load_inputs(db: Session, project_id: str) -> P13Inputs:
    project = get_project(db, project_id)
    _assert_replica(project)
    bible_artifact = _current_artifact(db, project_id, ArtifactType.TARGET_BIBLE)
    if bible_artifact is None:
        latest = _latest_artifact(db, project_id, ArtifactType.TARGET_BIBLE)
        if latest is not None:
            raise AppError("P13_TARGET_BIBLE_STALE", "TARGET_BIBLE 已过期，不能生成目标资产", status_code=409)
        raise AppError("P13_TARGET_BIBLE_REQUIRED", "P13 需要 CURRENT TARGET_BIBLE", status_code=409)
    bible_row = db.scalar(select(ReplicaTargetRevision).where(ReplicaTargetRevision.artifact_id == bible_artifact.id))
    if bible_row is None or bible_row.artifact_kind != TargetBibleArtifactKind.TARGET_BIBLE.value:
        raise AppError("P13_TARGET_BIBLE_CONTENT_MISSING", "CURRENT TARGET_BIBLE 缺少 P11 typed revision", status_code=500)
    bible = ReplicaTargetBibleContent.model_validate(bible_row.content_json)
    if bible.target_language != project.target_language or bible.target_region != project.target_region:
        raise AppError(
            "P13_TARGET_CONFIG_MISMATCH",
            "CURRENT TARGET_BIBLE 与项目目标语言或地区不一致",
            status_code=409,
        )
    return P13Inputs(
        project=project,
        target_bible_artifact=bible_artifact,
        target_bible_revision=bible_row,
        target_bible=bible,
    )


def _asset_id(kind: TargetAssetKind, target_entity_id: str) -> str:
    prefix = {
        TargetAssetKind.CHARACTER: "tasset_chr",
        TargetAssetKind.SCENE: "tasset_scn",
        TargetAssetKind.PROP: "tasset_prop",
    }[kind]
    return _stable_id(prefix, {"asset_kind": kind.value, "target_entity_id": target_entity_id})


def _bindings(bible: ReplicaTargetBibleContent) -> list[AssetBinding]:
    result: list[AssetBinding] = []
    for entity in bible.characters:
        result.append(
            AssetBinding(
                target_asset_id=_asset_id(TargetAssetKind.CHARACTER, entity.target_character_id),
                asset_kind=TargetAssetKind.CHARACTER,
                target_entity_id=entity.target_character_id,
                entity=entity,
            )
        )
    for entity in bible.scenes:
        result.append(
            AssetBinding(
                target_asset_id=_asset_id(TargetAssetKind.SCENE, entity.target_scene_id),
                asset_kind=TargetAssetKind.SCENE,
                target_entity_id=entity.target_scene_id,
                entity=entity,
            )
        )
    for entity in bible.props:
        result.append(
            AssetBinding(
                target_asset_id=_asset_id(TargetAssetKind.PROP, entity.target_prop_id),
                asset_kind=TargetAssetKind.PROP,
                target_entity_id=entity.target_prop_id,
                entity=entity,
            )
        )
    ids = [item.target_asset_id for item in result]
    if len(ids) != len(set(ids)):
        raise AppError("P13_TARGET_ASSET_ID_COLLISION", "Target Asset stable id 发生冲突", status_code=500)
    return result


def _current_assets_content(db: Session, inputs: P13Inputs) -> tuple[ArtifactNode | None, ReplicaTargetAssetsContent | None]:
    artifact = _current_artifact(db, inputs.project.id, ArtifactType.TARGET_ASSETS)
    if artifact is None:
        return None, None
    row = db.scalar(select(ReplicaTargetAssetsRevision).where(ReplicaTargetAssetsRevision.artifact_id == artifact.id))
    if row is None:
        raise AppError("P13_TARGET_ASSETS_CONTENT_MISSING", "CURRENT TARGET_ASSETS 缺少 typed revision", status_code=500)
    content = ReplicaTargetAssetsContent.model_validate(row.content_json)
    return artifact, content


def _validate_content_bindings(content: ReplicaTargetAssetsContent, inputs: P13Inputs) -> None:
    expected_characters = [item.target_character_id for item in inputs.target_bible.characters]
    expected_scenes = [item.target_scene_id for item in inputs.target_bible.scenes]
    expected_props = [item.target_prop_id for item in inputs.target_bible.props]
    actual_characters = [item.target_character_id for item in content.character_assets]
    actual_scenes = [item.target_scene_id for item in content.scene_assets]
    actual_props = [item.target_prop_id for item in content.prop_assets]
    if actual_characters != expected_characters or len(actual_characters) != len(set(actual_characters)):
        raise AppError("P13_CHARACTER_COVERAGE_INVALID", "Target Character Assets 必须按 Target Bible 一一完整覆盖", status_code=422)
    if actual_scenes != expected_scenes or len(actual_scenes) != len(set(actual_scenes)):
        raise AppError("P13_SCENE_COVERAGE_INVALID", "Target Scene Assets 必须按 Target Bible 一一完整覆盖", status_code=422)
    if actual_props != expected_props or len(actual_props) != len(set(actual_props)):
        raise AppError("P13_PROP_COVERAGE_INVALID", "Target Prop Assets 必须按 Target Bible 一一完整覆盖", status_code=422)
    expected_assets = [item.target_asset_id for item in _bindings(inputs.target_bible)]
    actual_assets = [
        *(item.target_asset_id for item in content.character_assets),
        *(item.target_asset_id for item in content.scene_assets),
        *(item.target_asset_id for item in content.prop_assets),
    ]
    if actual_assets != expected_assets:
        raise AppError("P13_ASSET_BINDING_INVALID", "target_asset_id 与 Target Bible entity 的稳定绑定不一致", status_code=422)
    if content.target_bible_artifact_id != inputs.target_bible_artifact.id or content.target_bible_revision != inputs.target_bible_artifact.revision:
        raise AppError("P13_TARGET_BIBLE_LINEAGE_MISMATCH", "TARGET_ASSETS 与 CURRENT TARGET_BIBLE lineage 不一致", status_code=409)


def _providers(inputs: P13Inputs, settings: Settings | None = None) -> P13Providers:
    runtime = settings or get_settings()
    return P13Providers(
        spec=build_target_assets_spec_provider(runtime, inputs.project.source_understanding_provider),
        image=build_target_asset_image_provider(runtime),
    )


def _validate_scope(
    command: TargetAssetsGenerateCommand,
    bindings: list[AssetBinding],
    current_artifact: ArtifactNode | None,
    current_content: ReplicaTargetAssetsContent | None,
    inputs: P13Inputs,
) -> list[str]:
    all_ids = [item.target_asset_id for item in bindings]
    if not command.target_asset_ids:
        return all_ids
    if current_artifact is None or current_content is None:
        raise AppError(
            "P13_TARGETED_REGEN_REQUIRES_CURRENT_ASSETS",
            "首次 P13 生成必须全量覆盖，不能只生成部分 Target Asset",
            status_code=409,
        )
    _validate_content_bindings(current_content, inputs)
    requested = list(command.target_asset_ids)
    unknown = [item for item in requested if item not in set(all_ids)]
    if unknown:
        raise AppError(
            "P13_TARGET_ASSET_SCOPE_INVALID",
            "定向重新生成包含未知 target_asset_id",
            status_code=422,
            details={"target_asset_ids": unknown},
        )
    return requested


def _fingerprint_inputs(
    *,
    inputs: P13Inputs,
    current_artifact: ArtifactNode | None,
    selected_ids: list[str],
    providers: P13Providers,
    idempotency_key: str,
) -> str:
    skill = get_professional_skill(P13_SKILL_ID)
    return _sha(
        {
            "task": P13_TASK_TYPE,
            "target_bible": [
                inputs.target_bible_artifact.id,
                inputs.target_bible_artifact.revision,
                inputs.target_bible_artifact.input_fingerprint,
            ],
            "current_target_assets": (
                [current_artifact.id, current_artifact.revision, current_artifact.input_fingerprint]
                if current_artifact is not None
                else None
            ),
            "selected_target_asset_ids": selected_ids,
            "professional_skill": [skill.id, skill.version],
            "spec_provider_profile": providers.spec.profile(),
            "image_provider_profile": providers.image.profile(),
            "schema_version": P13_SCHEMA_VERSION,
            "prompt_version": P13_PROMPT_VERSION,
            "asset_contract": P13_TARGET_CONTRACT,
            # Image generation is stochastic. A new explicit idempotency key means a new generation
            # request, while retrying the same key still resolves to exactly one Task.
            "generation_request_key": idempotency_key.strip(),
        }
    )


def create_target_assets_task(
    db: Session,
    *,
    project_id: str,
    command: TargetAssetsGenerateCommand,
    idempotency_key: str,
) -> Task:
    _assert_storage_ready(db)
    _assert_p13_admitted()
    inputs = _load_inputs(db, project_id)
    providers = _providers(inputs)
    current_artifact, current_content = _current_assets_content(db, inputs)
    bindings = _bindings(inputs.target_bible)
    selected_ids = _validate_scope(command, bindings, current_artifact, current_content, inputs)
    fingerprint = _fingerprint_inputs(
        inputs=inputs,
        current_artifact=current_artifact,
        selected_ids=selected_ids,
        providers=providers,
        idempotency_key=idempotency_key,
    )
    return create_task_from_command(
        db,
        project_id=project_id,
        idempotency_key=idempotency_key,
        payload=TaskCommandCreate(
            task_type=P13_TASK_TYPE,
            task_name="生成目标视觉资产候选",
            input_fingerprint=fingerprint,
            input_artifact_ids=[inputs.target_bible_artifact.id],
            max_attempts=3,
        ),
    )


def _selected_from_task(task: TaskWorkerRead, inputs: P13Inputs, providers: P13Providers) -> tuple[list[str], ArtifactNode | None, ReplicaTargetAssetsContent | None]:
    if list(task.input_artifact_ids_json) != [inputs.target_bible_artifact.id]:
        raise AppError("STALE_ARTIFACT_INPUT", "P13 TARGET_BIBLE 硬输入已变化，请重新创建任务", status_code=409)
    current_artifact, current_content = _current_assets_content_for_task(inputs, task)
    all_ids = [item.target_asset_id for item in _bindings(inputs.target_bible)]
    # Fingerprint is intentionally opaque. Recover scope by matching the finite possibilities used
    # by the command: full scope, or any explicit subset recorded in task checkpoint at claim time.
    scope = list((task.checkpoint_json or {}).get("requested_target_asset_ids") or [])
    if not scope:
        scope = all_ids
    if any(item not in set(all_ids) for item in scope) or len(scope) != len(set(scope)):
        raise AppError("P13_TARGET_ASSET_SCOPE_INVALID", "P13 Task scope 无效", status_code=409)
    return scope, current_artifact, current_content


def _current_assets_content_for_task(inputs: P13Inputs, task: TaskWorkerRead) -> tuple[ArtifactNode | None, ReplicaTargetAssetsContent | None]:
    # This helper exists so execution can re-read CURRENT state in its own session. It is replaced
    # by the session-aware call in _execute; keeping Task input_artifact_ids restricted to Target Bible
    # preserves the formal hard-input contract.
    return None, None


def _provider_input(inputs: P13Inputs, selected: list[AssetBinding]) -> TargetAssetsProviderInput:
    return TargetAssetsProviderInput(
        target_language=inputs.project.target_language,
        target_region=inputs.project.target_region,
        target_world=inputs.target_bible.target_world.model_dump(mode="json"),
        visual_style=inputs.target_bible.visual_style,
        global_continuity_rules=list(inputs.target_bible.continuity_rules),
        characters=[item.entity.model_dump(mode="json") for item in selected if item.asset_kind == TargetAssetKind.CHARACTER],
        scenes=[item.entity.model_dump(mode="json") for item in selected if item.asset_kind == TargetAssetKind.SCENE],
        props=[item.entity.model_dump(mode="json") for item in selected if item.asset_kind == TargetAssetKind.PROP],
    )


def _validate_semantic(selected: list[AssetBinding], semantic: TargetAssetsSemantic) -> None:
    expected_characters = [item.target_entity_id for item in selected if item.asset_kind == TargetAssetKind.CHARACTER]
    expected_scenes = [item.target_entity_id for item in selected if item.asset_kind == TargetAssetKind.SCENE]
    expected_props = [item.target_entity_id for item in selected if item.asset_kind == TargetAssetKind.PROP]
    actual_characters = [item.target_character_id for item in semantic.characters]
    actual_scenes = [item.target_scene_id for item in semantic.scenes]
    actual_props = [item.target_prop_id for item in semantic.props]
    for expected, actual, code, label in (
        (expected_characters, actual_characters, "P13_CHARACTER_PROVIDER_COVERAGE_INVALID", "Character"),
        (expected_scenes, actual_scenes, "P13_SCENE_PROVIDER_COVERAGE_INVALID", "Scene"),
        (expected_props, actual_props, "P13_PROP_PROVIDER_COVERAGE_INVALID", "Prop"),
    ):
        if set(actual) != set(expected) or len(actual) != len(set(actual)):
            raise AppError(code, f"P13 Provider {label} identity 必须与请求 scope 一一完整匹配", status_code=422)


def _provider_job(job: Any) -> TargetAssetsProviderJobProvenance:
    return TargetAssetsProviderJobProvenance(
        provider_job_id=job.id,
        provider=job.provider,
        model=job.model,
        capability=job.capability,
        payload_fingerprint=job.payload_fingerprint,
        remote_job_id=job.remote_job_id,
    )


def _dispatch_spec(provider: TargetAssetsSpecProvider, payload: TargetAssetsProviderInput) -> ProviderDispatchResult:
    result: TargetAssetsSpecProviderResult = provider.design(payload)
    return ProviderDispatchResult(value=result.semantic, remote_job_id=result.remote_job_id, completed=True)


def _dispatch_image(provider: TargetAssetImageProvider, payload: TargetAssetImageRequest) -> ProviderDispatchResult:
    result: TargetAssetImageProviderResult = provider.generate(payload)
    return ProviderDispatchResult(value=result, remote_job_id=result.remote_job_id, completed=True)


def _merge_constraints(*groups: list[str]) -> list[str]:
    result: list[str] = []
    for group in groups:
        for item in group:
            value = item.strip()
            if value and value not in result:
                result.append(value)
    if not result:
        raise AppError("P13_CONTINUITY_CONSTRAINTS_EMPTY", "P13 continuity constraints 不能为空", status_code=422)
    return result


def _image_prompt(inputs: P13Inputs, asset_payload: dict) -> str:
    return (
        "Create one clean professional visual reference sheet for a reusable drama production asset. "
        "This is NOT a storyboard frame and NOT a narrative scene. Show multiple useful reference views "
        "inside one coherent sheet when appropriate. Preserve identity exactly across views. "
        f"Target world: {json.dumps(inputs.target_bible.target_world.model_dump(mode='json'), ensure_ascii=False)}\n"
        f"Global visual style: {inputs.target_bible.visual_style}\n"
        f"Asset specification: {json.dumps(asset_payload, ensure_ascii=False, separators=(',', ':'))}\n"
        "Do not add shot numbers, subtitles, dialogue, timing, video-generation instructions, watermarks or logos."
    )


def _previous_asset_map(content: ReplicaTargetAssetsContent | None) -> dict[str, Any]:
    if content is None:
        return {}
    return {
        item.target_asset_id: item
        for collection in (content.character_assets, content.scene_assets, content.prop_assets)
        for item in collection
    }


def _reference_id(candidate_id: str, target_asset_id: str, asset_revision: int) -> str:
    return _stable_id(
        "tref",
        {"candidate_id": candidate_id, "target_asset_id": target_asset_id, "asset_revision": asset_revision},
    )


def _spec_asset_payload(inputs: P13Inputs, binding: AssetBinding, semantic: Any, asset_revision: int) -> dict:
    entity = binding.entity
    if binding.asset_kind == TargetAssetKind.CHARACTER:
        return ReplicaTargetCharacterAsset(
            target_asset_id=binding.target_asset_id,
            asset_revision=asset_revision,
            target_character_id=entity.target_character_id,
            display_name=entity.display_name,
            localized_identity=entity.localized_identity,
            appearance_direction=entity.appearance_direction,
            face_identity=semantic.face_identity,
            hair_identity=semantic.hair_identity,
            body_silhouette=semantic.body_silhouette,
            wardrobe_baseline=semantic.wardrobe_baseline,
            signature_features=list(semantic.signature_features),
            palette_materials=list(semantic.palette_materials),
            continuity_constraints=_merge_constraints(list(entity.continuity_rules), list(semantic.continuity_constraints)),
            generation_guidance=list(semantic.generation_guidance),
            negative_constraints=list(semantic.negative_constraints),
            reference_assets=[],
        ).model_dump(mode="json")
    if binding.asset_kind == TargetAssetKind.SCENE:
        return ReplicaTargetSceneAsset(
            target_asset_id=binding.target_asset_id,
            asset_revision=asset_revision,
            target_scene_id=entity.target_scene_id,
            display_name=entity.display_name,
            localized_setting=entity.localized_setting,
            visual_direction=entity.visual_direction,
            spatial_identity=semantic.spatial_identity,
            layout=semantic.layout,
            architecture_style=semantic.architecture_style,
            materials_palette=list(semantic.materials_palette),
            fixed_landmarks=list(semantic.fixed_landmarks),
            lighting_baseline=semantic.lighting_baseline,
            time_of_day_baseline=semantic.time_of_day_baseline,
            continuity_constraints=_merge_constraints(list(entity.continuity_rules), list(semantic.continuity_constraints)),
            generation_guidance=list(semantic.generation_guidance),
            negative_constraints=list(semantic.negative_constraints),
            reference_assets=[],
        ).model_dump(mode="json")
    return ReplicaTargetPropAsset(
        target_asset_id=binding.target_asset_id,
        asset_revision=asset_revision,
        target_prop_id=entity.target_prop_id,
        display_name=entity.display_name,
        localized_form=entity.localized_form,
        visual_form=semantic.visual_form,
        materials=list(semantic.materials),
        color_palette=list(semantic.color_palette),
        scale=semantic.scale,
        functional_identity=semantic.functional_identity,
        signature_details=list(semantic.signature_details),
        continuity_constraints=_merge_constraints(list(entity.continuity_rules), list(semantic.continuity_constraints)),
        generation_guidance=list(semantic.generation_guidance),
        negative_constraints=list(semantic.negative_constraints),
        reference_assets=[],
    ).model_dump(mode="json")


def _compose_candidate(
    *,
    inputs: P13Inputs,
    selected_bindings: list[AssetBinding],
    semantic: TargetAssetsSemantic,
    current_content: ReplicaTargetAssetsContent | None,
    generated_assets: dict[str, Any],
) -> ReplicaTargetAssetsContent:
    previous = _previous_asset_map(current_content)
    selected_ids = {item.target_asset_id for item in selected_bindings}
    characters: list[ReplicaTargetCharacterAsset] = []
    scenes: list[ReplicaTargetSceneAsset] = []
    props: list[ReplicaTargetPropAsset] = []
    for binding in _bindings(inputs.target_bible):
        if binding.target_asset_id in selected_ids:
            item = generated_assets[binding.target_asset_id]
        else:
            item = previous.get(binding.target_asset_id)
            if item is None:
                raise AppError("P13_CARRY_FORWARD_MISSING", "定向重新生成缺少可 carry forward 的正式资产", status_code=409)
        if binding.asset_kind == TargetAssetKind.CHARACTER:
            characters.append(ReplicaTargetCharacterAsset.model_validate(item))
        elif binding.asset_kind == TargetAssetKind.SCENE:
            scenes.append(ReplicaTargetSceneAsset.model_validate(item))
        else:
            props.append(ReplicaTargetPropAsset.model_validate(item))
    content = ReplicaTargetAssetsContent(
        target_bible_artifact_id=inputs.target_bible_artifact.id,
        target_bible_revision=inputs.target_bible_artifact.revision,
        target_language=inputs.project.target_language,
        target_region=inputs.project.target_region,
        visual_style=inputs.target_bible.visual_style,
        global_continuity_constraints=list(inputs.target_bible.continuity_rules),
        character_assets=characters,
        scene_assets=scenes,
        prop_assets=props,
    )
    _validate_content_bindings(content, inputs)
    return content


def _scope_from_checkpoint(task: TaskWorkerRead, all_ids: list[str]) -> list[str]:
    requested = list((task.checkpoint_json or {}).get("requested_target_asset_ids") or [])
    return requested or all_ids


def _execute(context: TaskExecutionContext, task: TaskWorkerRead) -> str:
    _assert_p13_admitted()
    settings = get_settings()
    with context.session_factory() as db:
        existing = db.scalar(
            select(ReplicaTargetAssetsCandidate).where(ReplicaTargetAssetsCandidate.generated_by_task_id == task.id)
        )
        if existing is not None:
            return existing.id
        inputs = _load_inputs(db, task.project_id)
        providers = _providers(inputs, settings)
        bindings = _bindings(inputs.target_bible)
        all_ids = [item.target_asset_id for item in bindings]
        selected_ids = _scope_from_checkpoint(task, all_ids)
        if any(item not in set(all_ids) for item in selected_ids) or len(selected_ids) != len(set(selected_ids)):
            raise AppError("P13_TARGET_ASSET_SCOPE_INVALID", "P13 Task scope 无效", status_code=409)
        current_artifact, current_content = _current_assets_content(db, inputs)
        if selected_ids != all_ids:
            if current_artifact is None or current_content is None:
                raise AppError("P13_TARGETED_REGEN_REQUIRES_CURRENT_ASSETS", "定向重新生成需要 CURRENT TARGET_ASSETS", status_code=409)
            _validate_content_bindings(current_content, inputs)
        expected_fingerprint = _fingerprint_inputs(
            inputs=inputs,
            current_artifact=current_artifact,
            selected_ids=selected_ids,
            providers=providers,
            idempotency_key=task.idempotency_key,
        )
        if task.input_fingerprint != expected_fingerprint or list(task.input_artifact_ids_json) != [inputs.target_bible_artifact.id]:
            raise AppError("STALE_ARTIFACT_INPUT", "P13 Target Bible、资产基线或 Provider profile 已变化", status_code=409)
        selected_bindings = [item for item in bindings if item.target_asset_id in set(selected_ids)]

    context.checkpoint(
        {"stage": "visual_spec", "requested_target_asset_ids": selected_ids},
        progress_percent=10,
    )
    provider_input = _provider_input(inputs, selected_bindings)
    with context.session_factory() as db:
        spec_job, dispatched = dispatch_provider_call(
            db,
            task_id=task.id,
            provider=providers.spec.provider_name,
            model=providers.spec.model_name,
            capability=Capability.TARGET_ASSETS,
            artifact_id=inputs.target_bible_artifact.id,
            payload={
                "profile": P13_PROMPT_VERSION,
                "schema_version": P13_SCHEMA_VERSION,
                "asset_contract": P13_TARGET_CONTRACT,
                "professional_skill_id": P13_SKILL_ID,
                "target_bible_artifact_id": inputs.target_bible_artifact.id,
                "target_asset_ids": selected_ids,
                "provider_profile": providers.spec.profile(),
            },
            remote_call=lambda _job: _dispatch_spec(providers.spec, provider_input),
        )
    semantic_raw = dispatched.value
    semantic = semantic_raw if isinstance(semantic_raw, TargetAssetsSemantic) else TargetAssetsSemantic.model_validate(semantic_raw)
    _validate_semantic(selected_bindings, semantic)

    semantic_maps = {
        TargetAssetKind.CHARACTER: {item.target_character_id: item for item in semantic.characters},
        TargetAssetKind.SCENE: {item.target_scene_id: item for item in semantic.scenes},
        TargetAssetKind.PROP: {item.target_prop_id: item for item in semantic.props},
    }
    previous = _previous_asset_map(current_content)
    candidate_id = str(uuid4())
    generated_assets: dict[str, Any] = {}
    image_jobs: list[TargetAssetsProviderJobProvenance] = []
    total = max(len(selected_bindings), 1)
    for index, binding in enumerate(selected_bindings, start=1):
        old = previous.get(binding.target_asset_id)
        asset_revision = int(old.asset_revision if old is not None else 0) + 1
        semantic_item = semantic_maps[binding.asset_kind][binding.target_entity_id]
        asset_payload = _spec_asset_payload(inputs, binding, semantic_item, asset_revision)
        image_request = TargetAssetImageRequest(
            target_asset_id=binding.target_asset_id,
            asset_kind=binding.asset_kind.value,
            prompt=_image_prompt(inputs, asset_payload),
        )
        context.checkpoint(
            {
                "stage": "reference_media",
                "requested_target_asset_ids": selected_ids,
                "target_asset_id": binding.target_asset_id,
                "asset_index": index,
                "asset_total": total,
            },
            progress_percent=min(85, 20 + int(index * 60 / total)),
        )
        with context.session_factory() as db:
            image_job, image_dispatched = dispatch_provider_call(
                db,
                task_id=task.id,
                provider=providers.image.provider_name,
                model=providers.image.model_name,
                capability=Capability.TARGET_ASSETS,
                artifact_id=inputs.target_bible_artifact.id,
                payload={
                    "profile": P13_PROMPT_VERSION,
                    "schema_version": P13_SCHEMA_VERSION,
                    "target_bible_artifact_id": inputs.target_bible_artifact.id,
                    "target_asset_id": binding.target_asset_id,
                    "asset_kind": binding.asset_kind.value,
                    "asset_revision": asset_revision,
                    "provider_profile": providers.image.profile(),
                },
                remote_call=lambda _job, request=image_request: _dispatch_image(providers.image, request),
            )
        image_result = image_dispatched.value
        if not isinstance(image_result, TargetAssetImageProviderResult):
            raise AppError("P13_IMAGE_PROVIDER_RESPONSE_INVALID", "P13 图片 Provider 返回类型无效", status_code=502)
        reference_id = _reference_id(candidate_id, binding.target_asset_id, asset_revision)
        reference = store_reference_image(
            settings=settings,
            project_id=task.project_id,
            candidate_id=candidate_id,
            target_asset_id=binding.target_asset_id,
            reference_asset_id=reference_id,
            image_bytes=image_result.image_bytes,
            media_type=image_result.media_type,
            provider_job_id=image_job.id,
            provider=image_job.provider,
            model=image_job.model,
        )
        asset_payload["reference_assets"] = [reference.model_dump(mode="json")]
        generated_assets[binding.target_asset_id] = asset_payload
        image_jobs.append(_provider_job(image_job))

    candidate_content = _compose_candidate(
        inputs=inputs,
        selected_bindings=selected_bindings,
        semantic=semantic,
        current_content=current_content,
        generated_assets=generated_assets,
    )
    context.checkpoint(
        {"stage": "candidate_validation", "requested_target_asset_ids": selected_ids},
        progress_percent=92,
    )
    skill = get_professional_skill(P13_SKILL_ID)
    provenance = TargetAssetsProvenance(
        target_bible_artifact_id=inputs.target_bible_artifact.id,
        target_bible_revision=inputs.target_bible_artifact.revision,
        target_bible_fingerprint=inputs.target_bible_artifact.input_fingerprint,
        professional_skill_id=skill.id,
        professional_skill_version=skill.version,
        candidate_id=candidate_id,
        generated_by_task_id=task.id,
        visual_spec_provider_profile=providers.spec.profile(),
        visual_spec_provider_job=_provider_job(spec_job),
        image_provider_profile=providers.image.profile(),
        image_provider_jobs=image_jobs,
    )
    with context.session_factory() as db:
        latest_inputs = _load_inputs(db, task.project_id)
        if latest_inputs.target_bible_artifact.id != inputs.target_bible_artifact.id:
            raise AppError("STALE_ARTIFACT_INPUT", "P13 生成期间 TARGET_BIBLE 已变化，候选不会发布", status_code=409)
        candidate = ReplicaTargetAssetsCandidate(
            id=candidate_id,
            project_id=task.project_id,
            target_bible_artifact_id=inputs.target_bible_artifact.id,
            target_bible_revision=inputs.target_bible_artifact.revision,
            target_bible_fingerprint=inputs.target_bible_artifact.input_fingerprint,
            input_fingerprint=task.input_fingerprint,
            status=TargetAssetCandidateStatus.READY_FOR_REVIEW.value,
            scope_json=selected_ids,
            content_json=candidate_content.model_dump(mode="json"),
            provenance_json=provenance.model_dump(mode="json"),
            generated_by_task_id=task.id,
        )
        db.add(candidate)
        db.commit()
    return candidate_id


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
            Task.attempt < task.max_attempts,
        )
        .values(
            status=TaskStatus.RUNNING,
            attempt=task.attempt + 1,
            worker_id=worker_id,
            heartbeat_at=now,
            started_at=func.coalesce(Task.started_at, now),
            finished_at=None,
            updated_at=now,
            checkpoint_json={"stage": "claimed", "requested_target_asset_ids": list((task.checkpoint_json or {}).get("requested_target_asset_ids") or [])},
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


def _safe_task_error(exc: Exception) -> str:
    if isinstance(exc, AppError):
        return f"任务执行失败（{exc.code}）：{exc.message}"[:1000]
    return f"任务执行失败（{type(exc).__name__}）"


def run_target_assets_task(session_factory: sessionmaker[Session], task_id: str) -> None:
    worker_id = f"p13-target-assets-{uuid4()}"
    with session_factory() as db:
        claimed = _claim(db, task_id, worker_id)
        if claimed is None:
            return
        snapshot = TaskWorkerRead.model_validate(claimed)
    context = TaskExecutionContext(session_factory=session_factory, task_id=snapshot.id, worker_id=worker_id)
    try:
        _execute(context, snapshot)
    except TaskCancelled:
        return
    except Exception as exc:
        with session_factory() as db:
            task = db.get(Task, task_id)
            if task is not None and task.status == TaskStatus.RUNNING and task.worker_id == worker_id:
                mark_task_failed(db, task_id, safe_error=_safe_task_error(exc), worker_id=worker_id)
        return
    with session_factory() as db:
        task = db.get(Task, task_id)
        if task is not None and task.status == TaskStatus.RUNNING and task.worker_id == worker_id:
            mark_task_succeeded(db, task_id, worker_id=worker_id)


def _candidate_read(
    candidate: ReplicaTargetAssetsCandidate,
    *,
    current_bible_id: str | None,
) -> TargetAssetsCandidateRead:
    status = TargetAssetCandidateStatus(candidate.status)
    if status == TargetAssetCandidateStatus.READY_FOR_REVIEW and current_bible_id != candidate.target_bible_artifact_id:
        status = TargetAssetCandidateStatus.STALE
    return TargetAssetsCandidateRead(
        candidate_id=candidate.id,
        status=status,
        target_bible_artifact_id=candidate.target_bible_artifact_id,
        target_bible_revision=candidate.target_bible_revision,
        input_fingerprint=candidate.input_fingerprint,
        scope_target_asset_ids=list(candidate.scope_json or []),
        content=ReplicaTargetAssetsContent.model_validate(candidate.content_json),
        provenance=TargetAssetsProvenance.model_validate(candidate.provenance_json),
        published_artifact_id=candidate.published_artifact_id,
        created_at=candidate.created_at,
        approved_at=candidate.approved_at,
    )


def _latest_candidate(db: Session, project_id: str) -> ReplicaTargetAssetsCandidate | None:
    return db.scalar(
        select(ReplicaTargetAssetsCandidate)
        .where(ReplicaTargetAssetsCandidate.project_id == project_id)
        .order_by(ReplicaTargetAssetsCandidate.created_at.desc(), ReplicaTargetAssetsCandidate.id.desc())
        .limit(1)
    )


def get_target_assets(db: Session, project_id: str) -> ReplicaTargetAssetsRead:
    _assert_storage_ready(db)
    project = get_project(db, project_id)
    _assert_replica(project)
    current_bible = _current_artifact(db, project_id, ArtifactType.TARGET_BIBLE)
    current = _current_artifact(db, project_id, ArtifactType.TARGET_ASSETS)
    artifact = current or _latest_artifact(db, project_id, ArtifactType.TARGET_ASSETS)
    candidate = _latest_candidate(db, project_id)
    candidate_read = _candidate_read(candidate, current_bible_id=current_bible.id if current_bible else None) if candidate else None
    if artifact is None:
        return ReplicaTargetAssetsRead(
            project_id=project_id,
            status=TargetAssetResultStatus.NOT_BUILT,
            latest_candidate=candidate_read,
        )
    row = db.scalar(select(ReplicaTargetAssetsRevision).where(ReplicaTargetAssetsRevision.artifact_id == artifact.id))
    if row is None:
        raise AppError("P13_TARGET_ASSETS_CONTENT_MISSING", "TARGET_ASSETS 缺少 typed revision", status_code=500)
    return ReplicaTargetAssetsRead(
        project_id=project_id,
        status=(
            TargetAssetResultStatus.CURRENT
            if artifact.validity == ArtifactValidity.CURRENT and artifact.is_current
            else TargetAssetResultStatus.STALE
        ),
        artifact_id=artifact.id,
        revision=artifact.revision,
        input_fingerprint=artifact.input_fingerprint,
        content=ReplicaTargetAssetsContent.model_validate(row.content_json),
        provenance=TargetAssetsProvenance.model_validate(row.provenance_json),
        latest_candidate=candidate_read,
    )


def list_target_assets_revisions(db: Session, project_id: str) -> list[ReplicaTargetAssetsRevisionSummary]:
    _assert_storage_ready(db)
    project = get_project(db, project_id)
    _assert_replica(project)
    artifacts = list(
        db.scalars(
            select(ArtifactNode)
            .where(ArtifactNode.project_id == project_id, ArtifactNode.artifact_type == ArtifactType.TARGET_ASSETS.value)
            .order_by(ArtifactNode.revision.desc(), ArtifactNode.created_at.desc())
        ).all()
    )
    if not artifacts:
        return []
    rows = list(
        db.scalars(
            select(ReplicaTargetAssetsRevision).where(
                ReplicaTargetAssetsRevision.artifact_id.in_([item.id for item in artifacts])
            )
        ).all()
    )
    by_artifact = {row.artifact_id: row for row in rows}
    return [
        ReplicaTargetAssetsRevisionSummary(
            artifact_id=artifact.id,
            revision=artifact.revision,
            validity=artifact.validity,
            input_fingerprint=artifact.input_fingerprint,
            target_bible_artifact_id=by_artifact[artifact.id].target_bible_artifact_id,
            target_bible_revision=by_artifact[artifact.id].target_bible_revision,
            created_at=artifact.created_at,
        )
        for artifact in artifacts
        if artifact.id in by_artifact
    ]


def _next_revision(db: Session, project_id: str) -> int:
    latest = db.scalar(
        select(func.max(ArtifactNode.revision)).where(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == ArtifactType.TARGET_ASSETS.value,
        )
    )
    return int(latest or 0) + 1


def approve_target_assets_candidate(
    db: Session,
    *,
    project_id: str,
    candidate_id: str,
    idempotency_key: str,
) -> ReplicaTargetAssetsRead:
    _assert_storage_ready(db)
    _assert_p13_admitted()
    normalized_key = idempotency_key.strip()
    if not normalized_key or len(normalized_key) > 128:
        raise AppError("INVALID_IDEMPOTENCY_KEY", "Idempotency-Key 无效", status_code=422)
    project = get_project(db, project_id)
    _assert_replica(project)
    candidate = db.get(ReplicaTargetAssetsCandidate, candidate_id)
    if candidate is None or candidate.project_id != project_id:
        raise AppError("P13_CANDIDATE_NOT_FOUND", "P13 Target Assets candidate 不存在", status_code=404)
    if candidate.status == TargetAssetCandidateStatus.PUBLISHED.value:
        if candidate.published_artifact_id is None:
            raise AppError("P13_CANDIDATE_PUBLICATION_CORRUPT", "P13 candidate 已发布但 Artifact 引用缺失", status_code=500)
        return get_target_assets(db, project_id)
    if candidate.status != TargetAssetCandidateStatus.READY_FOR_REVIEW.value:
        raise AppError("P13_CANDIDATE_NOT_APPROVABLE", "当前 P13 candidate 不能批准", status_code=409)

    inputs = _load_inputs(db, project_id)
    if (
        candidate.target_bible_artifact_id != inputs.target_bible_artifact.id
        or candidate.target_bible_revision != inputs.target_bible_artifact.revision
        or candidate.target_bible_fingerprint != inputs.target_bible_artifact.input_fingerprint
    ):
        raise AppError("P13_CANDIDATE_STALE", "P13 candidate 的 Target Bible 已不是 CURRENT，拒绝批准", status_code=409)
    content = ReplicaTargetAssetsContent.model_validate(candidate.content_json)
    _validate_content_bindings(content, inputs)
    settings = get_settings()
    for collection in (content.character_assets, content.scene_assets, content.prop_assets):
        for item in collection:
            for reference in item.reference_assets:
                verify_reference_image(settings, reference)

    previous = _current_artifact(db, project_id, ArtifactType.TARGET_ASSETS)
    if previous is not None:
        _mark_stale_with_downstream(db, [previous])
    now = utc_now()
    provenance = TargetAssetsProvenance.model_validate(candidate.provenance_json).model_copy(
        update={
            "approved_at": now,
            "approval_method": "EXPLICIT_USER_COMMAND",
            "supersedes_artifact_id": previous.id if previous is not None else None,
        }
    )
    skill = get_professional_skill(P13_SKILL_ID)
    artifact_fingerprint = _sha(
        {
            "candidate_input_fingerprint": candidate.input_fingerprint,
            "artifact_type": ArtifactType.TARGET_ASSETS.value,
            "schema_version": P13_SCHEMA_VERSION,
            "content": content.model_dump(mode="json"),
        }
    )
    artifact = ArtifactNode(
        project_id=project_id,
        artifact_type=ArtifactType.TARGET_ASSETS.value,
        namespace=ArtifactNamespace.TARGET,
        label="目标视觉资产",
        revision=_next_revision(db, project_id),
        input_fingerprint=artifact_fingerprint,
        skill_id=skill.id,
        skill_version=skill.version,
        validity=ArtifactValidity.CURRENT,
        is_current=True,
        metadata_json={
            "schema_version": P13_SCHEMA_VERSION,
            "target_bible_artifact_id": inputs.target_bible_artifact.id,
            "target_bible_revision": inputs.target_bible_artifact.revision,
            "character_asset_count": len(content.character_assets),
            "scene_asset_count": len(content.scene_assets),
            "prop_asset_count": len(content.prop_assets),
            "candidate_id": candidate.id,
            "document_title": "目标视觉资产",
        },
    )
    try:
        db.add(artifact)
        db.flush()
        spec_job = provenance.visual_spec_provider_job
        db.add(
            ReplicaTargetAssetsRevision(
                project_id=project_id,
                artifact_id=artifact.id,
                target_bible_artifact_id=inputs.target_bible_artifact.id,
                target_bible_revision=inputs.target_bible_artifact.revision,
                target_bible_fingerprint=inputs.target_bible_artifact.input_fingerprint,
                generated_by_task_id=candidate.generated_by_task_id,
                approved_from_candidate_id=candidate.id,
                schema_version=P13_SCHEMA_VERSION,
                prompt_version=P13_PROMPT_VERSION,
                provider=spec_job.provider,
                model_id=spec_job.model,
                input_fingerprint=artifact_fingerprint,
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
        if previous is not None:
            db.add(
                ArtifactEdge(
                    project_id=project_id,
                    source_node_id=artifact.id,
                    target_node_id=previous.id,
                    relation_type=ArtifactRelationType.SUPERSEDES,
                )
            )
        candidate.status = TargetAssetCandidateStatus.PUBLISHED.value
        candidate.published_artifact_id = artifact.id
        candidate.approval_idempotency_key = normalized_key
        candidate.approved_at = now
        candidate.updated_at = now
        db.add(candidate)
        _invalidate_project_plan(db, project)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return get_target_assets(db, project_id)


def find_reference_asset(db: Session, *, project_id: str, reference_asset_id: str) -> ReferenceLookup:
    _assert_storage_ready(db)
    project = get_project(db, project_id)
    _assert_replica(project)
    settings = get_settings()
    candidates = list(
        db.scalars(
            select(ReplicaTargetAssetsCandidate)
            .where(ReplicaTargetAssetsCandidate.project_id == project_id)
            .order_by(ReplicaTargetAssetsCandidate.created_at.desc())
        ).all()
    )
    revisions = list(
        db.scalars(
            select(ReplicaTargetAssetsRevision)
            .where(ReplicaTargetAssetsRevision.project_id == project_id)
            .order_by(ReplicaTargetAssetsRevision.created_at.desc())
        ).all()
    )
    for payload in [*(item.content_json for item in candidates), *(item.content_json for item in revisions)]:
        content = ReplicaTargetAssetsContent.model_validate(payload)
        for collection in (content.character_assets, content.scene_assets, content.prop_assets):
            for asset in collection:
                for reference in asset.reference_assets:
                    if reference.reference_asset_id == reference_asset_id:
                        path = verify_reference_image(settings, reference)
                        return ReferenceLookup(path=path, media_type=reference.media_type)
    raise AppError("P13_REFERENCE_ASSET_NOT_FOUND", "P13 reference asset 不存在", status_code=404)
