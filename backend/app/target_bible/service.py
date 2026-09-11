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
from app.skills.models import ArtifactType, Capability
from app.skills.professional import get_professional_skill
from app.source_snapshot.models import SourceVideoSnapshotRevision
from app.source_snapshot.schemas import SourceVideoSnapshotContent
from app.target_bible.models import ReplicaTargetRevision
from app.target_bible.providers import (
    ReplicaTargetBibleProvider,
    ReplicaTargetBibleProviderInput,
    ReplicaTargetBibleProviderResult,
    build_replica_target_bible_provider,
)
from app.target_bible.schemas import (
    P11_PRESERVATION_CONTRACT,
    P11_PROMPT_VERSION,
    P11_SCHEMA_VERSION,
    P11_SKILL_ID,
    P11_TARGET_CONTRACT,
    LocalizationCategory,
    LocalizationDecision,
    PreservationCategory,
    PreservationLock,
    ReplicaAdaptationPlanContent,
    ReplicaTargetArtifactRead,
    ReplicaTargetBibleContent,
    ReplicaTargetBibleRead,
    ReplicaTargetBibleRevisionSummary,
    ReplicaTargetBibleSemantic,
    ReplicaTargetCharacter,
    ReplicaTargetProp,
    ReplicaTargetProvenance,
    ReplicaTargetScene,
    ReplicaTargetWorld,
    TargetBibleArtifactKind,
    TargetBibleProviderJobProvenance,
    TargetBibleResultStatus,
)
from app.workflow.models import ProviderJob, Task, TaskStatus
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


P11_TASK_TYPE = "P11_REPLICA_TARGET_BIBLE"
_ARTIFACT_TYPES = {
    TargetBibleArtifactKind.ADAPTATION_PLAN: ArtifactType.ADAPTATION_PLAN,
    TargetBibleArtifactKind.TARGET_BIBLE: ArtifactType.TARGET_BIBLE,
}
_ARTIFACT_LABELS = {
    TargetBibleArtifactKind.ADAPTATION_PLAN: "复刻本土化方案",
    TargetBibleArtifactKind.TARGET_BIBLE: "复刻目标设定",
}
_BEAT_CATEGORY = {
    "HOOK": PreservationCategory.HOOK,
    "CONFLICT": PreservationCategory.CONFLICT,
    "REVEAL": PreservationCategory.INFORMATION_REVEAL,
    "REVERSAL": PreservationCategory.REVERSAL,
    "EMOTIONAL_PEAK": PreservationCategory.EMOTIONAL_PEAK,
    "PAYOFF": PreservationCategory.PAYOFF,
    "CLIFFHANGER": PreservationCategory.CLIFFHANGER,
}


@dataclass(frozen=True)
class P11Inputs:
    project: Any
    snapshot_artifact: ArtifactNode
    snapshot_revision: SourceVideoSnapshotRevision
    snapshot_content: SourceVideoSnapshotContent
    preservation_locks: tuple[PreservationLock, ...]


@dataclass(frozen=True)
class P11ExecutionResult:
    adaptation_plan: ReplicaAdaptationPlanContent
    target_bible: ReplicaTargetBibleContent
    provider_job: TargetBibleProviderJobProvenance
    provider_profile: dict


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
    if not inspect(db.get_bind()).has_table(ReplicaTargetRevision.__tablename__):
        raise AppError(
            "P11_DATABASE_MIGRATION_REQUIRED",
            "P11 数据库迁移尚未应用，请先执行 alembic upgrade head",
            status_code=503,
        )


def _assert_replica(project: Any) -> None:
    if project.project_type != ProjectType.REPLICA:
        raise AppError(
            "REPLICA_TARGET_BIBLE_NOT_ALLOWED",
            "当前 P11 目标设定仅用于复刻短剧",
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
            "P11_CURRENT_ARTIFACT_AMBIGUOUS",
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


def _source_snapshot(db: Session, project_id: str) -> tuple[ArtifactNode, SourceVideoSnapshotRevision, SourceVideoSnapshotContent]:
    snapshot = _current_artifact(db, project_id, ArtifactType.SOURCE_VIDEO_SNAPSHOT)
    if snapshot is None:
        latest = _latest_artifact(db, project_id, ArtifactType.SOURCE_VIDEO_SNAPSHOT)
        if latest is None:
            raise AppError("SOURCE_SNAPSHOT_REQUIRED", "P11 需要 CURRENT 原片分析定稿", status_code=409)
        raise AppError("SOURCE_SNAPSHOT_STALE", "原片分析定稿已有更新，请先重新解析原片", status_code=409)
    row = db.scalar(
        select(SourceVideoSnapshotRevision).where(SourceVideoSnapshotRevision.artifact_id == snapshot.id)
    )
    if row is None:
        raise AppError("SOURCE_SNAPSHOT_CONTENT_MISSING", "CURRENT Source Snapshot 缺少正式 typed revision", status_code=500)
    content = SourceVideoSnapshotContent.model_validate(row.content_json)
    return snapshot, row, content


def _time_ref(episode_id: str, start_us: int, end_us: int) -> str:
    return f"{episode_id}@{start_us}-{end_us}"


def _lock(
    category: PreservationCategory,
    source_summary: str,
    source_refs: list[str],
    constraint: str,
) -> PreservationLock:
    return PreservationLock(
        lock_id=_stable_id("lock", [category.value, source_summary, source_refs]),
        category=category,
        source_summary=source_summary,
        source_refs=source_refs,
        constraint=constraint,
    )


def _build_preservation_locks(content: SourceVideoSnapshotContent) -> tuple[PreservationLock, ...]:
    locks: list[PreservationLock] = []
    for episode in content.source_bible.episodes:
        episode_id = episode.material_baseline.episode_id
        story = episode.story_skeleton
        locks.append(
            _lock(
                PreservationCategory.STORY_MAINLINE,
                f"{story.premise}｜核心冲突：{story.central_conflict}",
                [episode_id],
                "保持本集故事主线、人物故事功能和核心冲突，不得因本土化改写因果链。",
            )
        )
        for beat_index, beat in enumerate(story.beats, 1):
            ref = _time_ref(episode_id, beat.time_range.start_us, beat.time_range.end_us)
            category = _BEAT_CATEGORY.get(beat.beat_type.value)
            if category is not None:
                locks.append(
                    _lock(
                        category,
                        beat.summary,
                        [ref],
                        f"保持 {beat.beat_type.value} 的叙事功能、相对顺序和信息量，不得删除或重排。",
                    )
                )
            locks.append(
                _lock(
                    PreservationCategory.STORY_BEAT_TIMING,
                    f"Beat #{beat_index} {beat.beat_type.value}: {beat.summary}",
                    [ref],
                    "保持 Story Beat 的时间位置基线；后续只能在正式 Timing 阶段做最小必要适配。",
                )
            )
        rhythm = episode.rhythm_skeleton
        locks.append(
            _lock(
                PreservationCategory.SHOT_RHYTHM,
                rhythm.overall_pace,
                [episode_id],
                "保持原片整体节奏与镜头反应基线，不在 Target Bible 阶段重做节奏。",
            )
        )
        for phase_index, phase in enumerate(rhythm.phases, 1):
            ref = _time_ref(episode_id, phase.time_range.start_us, phase.time_range.end_us)
            locks.append(
                _lock(
                    PreservationCategory.ACTION_RHYTHM,
                    f"Phase #{phase_index} {phase.pace}: {phase.dialogue_reaction_rhythm}",
                    [ref],
                    f"保持动作/对白反应节奏与 cut timing；允许偏差基线 {phase.allowable_deviation_ms}ms。",
                )
            )

    assignments = sorted(
        content.source_scenes.assignments,
        key=lambda item: (item.episode_id, item.shot_number, item.start_us),
    )
    scene_sequence = [f"{item.episode_id}#S{item.shot_number}:{item.scene_id or item.resolution_status.value}" for item in assignments]
    if scene_sequence:
        locks.append(
            _lock(
                PreservationCategory.SCENE_ORDER,
                " → ".join(scene_sequence),
                [item.shot_anchor_id for item in assignments],
                "保持 Source Scene Assignment 的连续顺序，不因目标地区替换而重排场次。",
            )
        )

    shot_ids: list[str] = []
    for episode in content.source_shot_facts.episodes:
        shot_ids.extend(item.shot_anchor_id for item in episode.shots)
    if shot_ids:
        locks.append(
            _lock(
                PreservationCategory.SHOT_LOGIC,
                f"保持 {len(shot_ids)} 个 Source Shot 的顺序、镜头功能与反应链。",
                shot_ids,
                "Target Bible 不创建、删除、合并或重排 Source Shot；正式 Target Storyboard 属于后续阶段。",
            )
        )
    return tuple(locks)


def _load_inputs(db: Session, project_id: str) -> P11Inputs:
    project = get_project(db, project_id)
    _assert_replica(project)
    snapshot, row, content = _source_snapshot(db, project_id)
    return P11Inputs(
        project=project,
        snapshot_artifact=snapshot,
        snapshot_revision=row,
        snapshot_content=content,
        preservation_locks=_build_preservation_locks(content),
    )


def _provider_for_project(project: Any) -> ReplicaTargetBibleProvider:
    return build_replica_target_bible_provider(get_settings(), project.source_understanding_provider)


def _fingerprint_inputs(inputs: P11Inputs, provider: ReplicaTargetBibleProvider) -> str:
    skill = get_professional_skill(P11_SKILL_ID)
    return _sha(
        {
            "task": P11_TASK_TYPE,
            "source_snapshot": [
                inputs.snapshot_artifact.id,
                inputs.snapshot_artifact.revision,
                inputs.snapshot_artifact.input_fingerprint,
            ],
            "target_language": inputs.project.target_language,
            "target_region": inputs.project.target_region,
            "scene_strategy": inputs.project.scene_strategy.value,
            "visual_style": inputs.project.visual_style,
            "skill": [skill.id, skill.version],
            "provider_profile": provider.profile(),
            "prompt_version": P11_PROMPT_VERSION,
            "schema_version": P11_SCHEMA_VERSION,
            "target_contract": P11_TARGET_CONTRACT,
            "preservation_contract": P11_PRESERVATION_CONTRACT,
            "locks": [item.model_dump(mode="json") for item in inputs.preservation_locks],
        }
    )


def create_replica_target_bible_task(db: Session, *, project_id: str, idempotency_key: str) -> Task:
    _assert_storage_ready(db)
    inputs = _load_inputs(db, project_id)
    provider = _provider_for_project(inputs.project)
    fingerprint = _fingerprint_inputs(inputs, provider)
    task = create_task_from_command(
        db,
        project_id=project_id,
        idempotency_key=idempotency_key,
        payload=TaskCommandCreate(
            task_type=P11_TASK_TYPE,
            task_name="生成复刻目标设定",
            input_fingerprint=fingerprint,
            input_artifact_ids=[inputs.snapshot_artifact.id],
            max_attempts=3,
        ),
    )
    normalized_key = idempotency_key.strip()
    if task.status == TaskStatus.FAILED and task.attempt < task.max_attempts and task.idempotency_key != normalized_key:
        return retry_task(db, project_id, task.id)
    if task.status == TaskStatus.INTERRUPTED and task.attempt < task.max_attempts and task.idempotency_key != normalized_key:
        return resume_task(db, project_id, task.id)
    return task


def _assert_task_snapshot(db: Session, task: TaskWorkerRead | Task, inputs: P11Inputs, provider: ReplicaTargetBibleProvider) -> None:
    if list(task.input_artifact_ids_json) != [inputs.snapshot_artifact.id]:
        raise AppError("STALE_ARTIFACT_INPUT", "P11 Source Snapshot 输入已变化，请重新创建任务", status_code=409)
    if task.input_fingerprint != _fingerprint_inputs(inputs, provider):
        raise AppError("STALE_ARTIFACT_INPUT", "P11 目标配置、Provider profile 或 Source Snapshot 已变化", status_code=409)


def _source_identity_maps(content: SourceVideoSnapshotContent) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    characters = {item.character_id: item for item in content.source_characters.entities}
    scenes = {item.scene_id: item for item in content.source_scenes.entities}
    props = {item.prop_id: item for item in content.source_props.entities}
    if len(characters) != len(content.source_characters.entities):
        raise AppError("P11_SOURCE_CHARACTER_SET_INVALID", "Snapshot Source Character id 重复", status_code=409)
    if len(scenes) != len(content.source_scenes.entities):
        raise AppError("P11_SOURCE_SCENE_SET_INVALID", "Snapshot Source Scene id 重复", status_code=409)
    if len(props) != len(content.source_props.entities):
        raise AppError("P11_SOURCE_PROP_SET_INVALID", "Snapshot Source Prop id 重复", status_code=409)
    return characters, scenes, props


def _assert_exact_ids(actual: list[str], expected: set[str], code: str, message: str) -> None:
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise AppError(code, message, status_code=422)


def _validate_semantic(inputs: P11Inputs, semantic: ReplicaTargetBibleSemantic) -> None:
    characters, scenes, props = _source_identity_maps(inputs.snapshot_content)
    _assert_exact_ids(
        [item.source_character_id for item in semantic.characters],
        set(characters),
        "P11_CHARACTER_COVERAGE_INVALID",
        "Target Character 必须与 Snapshot Source Character 一一完整对应",
    )
    _assert_exact_ids(
        [item.source_scene_id for item in semantic.scenes],
        set(scenes),
        "P11_SCENE_COVERAGE_INVALID",
        "Target Scene 必须与 Snapshot Source Scene 一一完整对应",
    )
    _assert_exact_ids(
        [item.source_prop_id for item in semantic.props],
        set(props),
        "P11_PROP_COVERAGE_INVALID",
        "Target Prop 必须与 Snapshot Source Prop 一一完整对应",
    )
    known_refs = set(characters) | set(scenes) | set(props)
    invalid_refs = sorted(
        {
            item.source_ref
            for item in semantic.localization_decisions
            if item.source_ref is not None and item.source_ref not in known_refs
        }
    )
    if invalid_refs:
        raise AppError(
            "P11_LOCALIZATION_SOURCE_REF_INVALID",
            "P11 localization decision 引用了 Snapshot 中不存在的 Source identity",
            status_code=422,
            details={"source_refs": invalid_refs},
        )


def _target_id(prefix: str, inputs: P11Inputs, source_id: str) -> str:
    return _stable_id(
        prefix,
        {
            "source_id": source_id,
            "source_snapshot_artifact_id": inputs.snapshot_artifact.id,
            "source_snapshot_fingerprint": inputs.snapshot_artifact.input_fingerprint,
            "target_language": inputs.project.target_language,
            "target_region": inputs.project.target_region,
        },
    )


def _decision(
    inputs: P11Inputs,
    *,
    category: LocalizationCategory,
    source_ref: str | None,
    source_value: str,
    target_value: str,
    reason: str,
) -> LocalizationDecision:
    return LocalizationDecision(
        decision_id=_stable_id(
            "loc",
            [
                inputs.snapshot_artifact.id,
                category.value,
                source_ref,
                source_value,
                target_value,
            ],
        ),
        category=category,
        source_ref=source_ref,
        source_value=source_value,
        target_value=target_value,
        reason=reason,
    )


def _compose(inputs: P11Inputs, semantic: ReplicaTargetBibleSemantic) -> tuple[ReplicaAdaptationPlanContent, ReplicaTargetBibleContent]:
    _validate_semantic(inputs, semantic)
    source_characters, source_scenes, source_props = _source_identity_maps(inputs.snapshot_content)

    target_characters = [
        ReplicaTargetCharacter(
            target_character_id=_target_id("tchr", inputs, item.source_character_id),
            source_character_id=item.source_character_id,
            source_display_name=source_characters[item.source_character_id].display_name,
            display_name=item.display_name,
            localized_identity=item.localized_identity,
            appearance_direction=item.appearance_direction,
            personality_constraints=item.personality_constraints,
            continuity_rules=item.continuity_rules,
        )
        for item in semantic.characters
    ]
    target_scenes = [
        ReplicaTargetScene(
            target_scene_id=_target_id("tscn", inputs, item.source_scene_id),
            source_scene_id=item.source_scene_id,
            source_display_name=source_scenes[item.source_scene_id].display_name,
            display_name=item.display_name,
            localized_setting=item.localized_setting,
            visual_direction=item.visual_direction,
            continuity_rules=item.continuity_rules,
        )
        for item in semantic.scenes
    ]
    target_props = [
        ReplicaTargetProp(
            target_prop_id=_target_id("tprop", inputs, item.source_prop_id),
            source_prop_id=item.source_prop_id,
            source_display_name=source_props[item.source_prop_id].display_name,
            display_name=item.display_name,
            localized_form=item.localized_form,
            continuity_rules=item.continuity_rules,
        )
        for item in semantic.props
    ]

    decisions: list[LocalizationDecision] = []
    for item in semantic.characters:
        decisions.append(
            _decision(
                inputs,
                category=LocalizationCategory.CHARACTER,
                source_ref=item.source_character_id,
                source_value=source_characters[item.source_character_id].display_name,
                target_value=f"{item.display_name}｜{item.localized_identity}｜{item.appearance_direction}",
                reason=item.reason,
            )
        )
    for item in semantic.scenes:
        decisions.append(
            _decision(
                inputs,
                category=LocalizationCategory.SCENE,
                source_ref=item.source_scene_id,
                source_value=source_scenes[item.source_scene_id].display_name,
                target_value=f"{item.display_name}｜{item.localized_setting}",
                reason=item.reason,
            )
        )
    for item in semantic.props:
        decisions.append(
            _decision(
                inputs,
                category=LocalizationCategory.PROP,
                source_ref=item.source_prop_id,
                source_value=source_props[item.source_prop_id].display_name,
                target_value=f"{item.display_name}｜{item.localized_form}",
                reason=item.reason,
            )
        )
    for item in semantic.localization_decisions:
        decisions.append(
            _decision(
                inputs,
                category=item.category,
                source_ref=item.source_ref,
                source_value=item.source_value,
                target_value=item.target_value,
                reason=item.reason,
            )
        )

    visual_style = inputs.project.visual_style or semantic.visual_style
    plan = ReplicaAdaptationPlanContent(
        target_language=inputs.project.target_language,
        target_region=inputs.project.target_region,
        source_snapshot_artifact_id=inputs.snapshot_artifact.id,
        preservation_locks=list(inputs.preservation_locks),
        localization_decisions=decisions,
        dialogue_localization_strategy=list(semantic.dialogue_style_rules),
        scene_strategy=inputs.project.scene_strategy.value,
        visual_style=visual_style,
    )
    bible = ReplicaTargetBibleContent(
        target_language=inputs.project.target_language,
        target_region=inputs.project.target_region,
        source_snapshot_artifact_id=inputs.snapshot_artifact.id,
        target_world=ReplicaTargetWorld(
            setting_summary=semantic.target_world.setting_summary,
            cultural_context=semantic.target_world.cultural_context,
            social_context=semantic.target_world.social_context,
            localization_principles=semantic.target_world.localization_principles,
        ),
        characters=target_characters,
        scenes=target_scenes,
        props=target_props,
        visual_style=visual_style,
        continuity_rules=list(semantic.continuity_rules),
        dialogue_style_rules=list(semantic.dialogue_style_rules),
        adaptation_summary=semantic.adaptation_summary,
    )
    return plan, bible


def _provider_input(inputs: P11Inputs) -> ReplicaTargetBibleProviderInput:
    return ReplicaTargetBibleProviderInput(
        source_snapshot=inputs.snapshot_content.model_dump(mode="json"),
        target_language=inputs.project.target_language,
        target_region=inputs.project.target_region,
        scene_strategy=inputs.project.scene_strategy.value,
        visual_style=inputs.project.visual_style,
        preservation_locks=inputs.preservation_locks,
    )


def _dispatch(provider: ReplicaTargetBibleProvider, payload: ReplicaTargetBibleProviderInput) -> ProviderDispatchResult:
    result: ReplicaTargetBibleProviderResult = provider.design(payload)
    return ProviderDispatchResult(value=result.semantic, remote_job_id=result.remote_job_id, completed=True)


def _execute(context: TaskExecutionContext, task: TaskWorkerRead) -> P11ExecutionResult:
    with context.session_factory() as db:
        inputs = _load_inputs(db, task.project_id)
        provider = _provider_for_project(inputs.project)
        _assert_task_snapshot(db, task, inputs, provider)
        profile = provider.profile()

    context.checkpoint({"stage": "replica_preservation_locks"}, progress_percent=12)
    payload = _provider_input(inputs)
    context.checkpoint({"stage": "target_world_localization"}, progress_percent=24)
    job_payload = {
        "profile": P11_PROMPT_VERSION,
        "schema_version": P11_SCHEMA_VERSION,
        "target_contract": P11_TARGET_CONTRACT,
        "preservation_contract": P11_PRESERVATION_CONTRACT,
        "professional_skill_id": P11_SKILL_ID,
        "professional_skill_version": get_professional_skill(P11_SKILL_ID).version,
        "source_snapshot_artifact_id": inputs.snapshot_artifact.id,
        "source_snapshot_fingerprint": inputs.snapshot_artifact.input_fingerprint,
        "target_language": inputs.project.target_language,
        "target_region": inputs.project.target_region,
        "scene_strategy": inputs.project.scene_strategy.value,
        "visual_style": inputs.project.visual_style,
        "provider_profile": profile,
    }
    with context.session_factory() as db:
        job, dispatched = dispatch_provider_call(
            db,
            task_id=task.id,
            provider=provider.provider_name,
            model=provider.model_name,
            capability=Capability.TARGET_BIBLE,
            payload=job_payload,
            artifact_id=inputs.snapshot_artifact.id,
            remote_call=lambda _job: _dispatch(provider, payload),
        )
    context.checkpoint({"stage": "validate_target_lineage"}, progress_percent=78)
    raw = dispatched.value
    semantic = raw if isinstance(raw, ReplicaTargetBibleSemantic) else ReplicaTargetBibleSemantic.model_validate(raw)
    adaptation_plan, target_bible = _compose(inputs, semantic)
    context.checkpoint({"stage": "validate_target_bible"}, progress_percent=94)
    provenance = TargetBibleProviderJobProvenance(
        provider_job_id=job.id,
        provider=job.provider,
        model=job.model,
        capability=job.capability,
        professional_skill_id=P11_SKILL_ID,
        payload_fingerprint=job.payload_fingerprint,
        remote_job_id=job.remote_job_id,
    )
    return P11ExecutionResult(
        adaptation_plan=adaptation_plan,
        target_bible=target_bible,
        provider_job=provenance,
        provider_profile=profile,
    )


def _next_revision(db: Session, project_id: str, artifact_type: ArtifactType) -> int:
    latest = db.scalar(
        select(func.max(ArtifactNode.revision)).where(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == artifact_type.value,
        )
    )
    return int(latest or 0) + 1


def _artifact_fingerprint(task: Task, kind: TargetBibleArtifactKind, content: BaseException | Any) -> str:
    return _sha(
        {
            "task_input_fingerprint": task.input_fingerprint,
            "artifact_kind": kind.value,
            "schema_version": P11_SCHEMA_VERSION,
            "content": content.model_dump(mode="json"),
        }
    )


def _provenance(
    *,
    task: Task,
    inputs: P11Inputs,
    result: P11ExecutionResult,
    kind: TargetBibleArtifactKind,
    previous: ArtifactNode | None,
) -> ReplicaTargetProvenance:
    skill = get_professional_skill(P11_SKILL_ID)
    return ReplicaTargetProvenance(
        artifact_kind=kind,
        source_snapshot_artifact_id=inputs.snapshot_artifact.id,
        source_snapshot_revision=inputs.snapshot_artifact.revision,
        source_snapshot_fingerprint=inputs.snapshot_artifact.input_fingerprint,
        target_language=inputs.project.target_language,
        target_region=inputs.project.target_region,
        scene_strategy=inputs.project.scene_strategy.value,
        visual_style=inputs.project.visual_style,
        professional_skill_id=skill.id,
        professional_skill_version=skill.version,
        provider=result.provider_job.provider,
        model=result.provider_job.model,
        provider_job=result.provider_job,
        generated_by_task_id=task.id,
        supersedes_artifact_id=previous.id if previous is not None else None,
    )


def _publish(db: Session, *, task_id: str, result: P11ExecutionResult) -> tuple[ArtifactNode, ArtifactNode]:
    task = db.get(Task, task_id)
    if task is None:
        raise AppError("TASK_NOT_FOUND", "P11 任务不存在", status_code=404)
    if task.status != TaskStatus.SUCCEEDED:
        raise AppError("TASK_NOT_SUCCEEDED", "只有执行成功的 P11 Task 才能发布目标设定", status_code=409)
    inputs = _load_inputs(db, task.project_id)
    provider = _provider_for_project(inputs.project)
    _assert_task_snapshot(db, task, inputs, provider)

    previous_plan = _current_artifact(db, task.project_id, ArtifactType.ADAPTATION_PLAN)
    previous_bible = _current_artifact(db, task.project_id, ArtifactType.TARGET_BIBLE)
    old_roots = [item for item in (previous_plan, previous_bible) if item is not None]
    if old_roots:
        _mark_stale_with_downstream(db, old_roots)

    skill = get_professional_skill(P11_SKILL_ID)
    plan_fp = _artifact_fingerprint(task, TargetBibleArtifactKind.ADAPTATION_PLAN, result.adaptation_plan)
    bible_fp = _artifact_fingerprint(task, TargetBibleArtifactKind.TARGET_BIBLE, result.target_bible)

    plan = ArtifactNode(
        project_id=task.project_id,
        artifact_type=ArtifactType.ADAPTATION_PLAN.value,
        namespace=ArtifactNamespace.TARGET,
        label=_ARTIFACT_LABELS[TargetBibleArtifactKind.ADAPTATION_PLAN],
        revision=_next_revision(db, task.project_id, ArtifactType.ADAPTATION_PLAN),
        input_fingerprint=plan_fp,
        skill_id=skill.id,
        skill_version=skill.version,
        validity=ArtifactValidity.CURRENT,
        is_current=True,
        metadata_json={
            "schema_version": P11_SCHEMA_VERSION,
            "source_snapshot_artifact_id": inputs.snapshot_artifact.id,
            "target_language": inputs.project.target_language,
            "target_region": inputs.project.target_region,
            "preservation_lock_count": len(result.adaptation_plan.preservation_locks),
            "localization_decision_count": len(result.adaptation_plan.localization_decisions),
            "document_title": _ARTIFACT_LABELS[TargetBibleArtifactKind.ADAPTATION_PLAN],
        },
    )
    bible = ArtifactNode(
        project_id=task.project_id,
        artifact_type=ArtifactType.TARGET_BIBLE.value,
        namespace=ArtifactNamespace.TARGET,
        label=_ARTIFACT_LABELS[TargetBibleArtifactKind.TARGET_BIBLE],
        revision=_next_revision(db, task.project_id, ArtifactType.TARGET_BIBLE),
        input_fingerprint=bible_fp,
        skill_id=skill.id,
        skill_version=skill.version,
        validity=ArtifactValidity.CURRENT,
        is_current=True,
        metadata_json={
            "schema_version": P11_SCHEMA_VERSION,
            "source_snapshot_artifact_id": inputs.snapshot_artifact.id,
            "target_language": inputs.project.target_language,
            "target_region": inputs.project.target_region,
            "character_count": len(result.target_bible.characters),
            "scene_count": len(result.target_bible.scenes),
            "prop_count": len(result.target_bible.props),
            "document_title": _ARTIFACT_LABELS[TargetBibleArtifactKind.TARGET_BIBLE],
        },
    )
    try:
        db.add_all([plan, bible])
        db.flush()
        plan_provenance = _provenance(
            task=task,
            inputs=inputs,
            result=result,
            kind=TargetBibleArtifactKind.ADAPTATION_PLAN,
            previous=previous_plan,
        )
        bible_provenance = _provenance(
            task=task,
            inputs=inputs,
            result=result,
            kind=TargetBibleArtifactKind.TARGET_BIBLE,
            previous=previous_bible,
        )
        db.add_all(
            [
                ReplicaTargetRevision(
                    project_id=task.project_id,
                    artifact_id=plan.id,
                    artifact_kind=TargetBibleArtifactKind.ADAPTATION_PLAN.value,
                    source_snapshot_artifact_id=inputs.snapshot_artifact.id,
                    generated_by_task_id=task.id,
                    schema_version=P11_SCHEMA_VERSION,
                    content_json=result.adaptation_plan.model_dump(mode="json"),
                    provenance_json=plan_provenance.model_dump(mode="json"),
                ),
                ReplicaTargetRevision(
                    project_id=task.project_id,
                    artifact_id=bible.id,
                    artifact_kind=TargetBibleArtifactKind.TARGET_BIBLE.value,
                    source_snapshot_artifact_id=inputs.snapshot_artifact.id,
                    generated_by_task_id=task.id,
                    schema_version=P11_SCHEMA_VERSION,
                    content_json=result.target_bible.model_dump(mode="json"),
                    provenance_json=bible_provenance.model_dump(mode="json"),
                ),
                ArtifactEdge(
                    project_id=task.project_id,
                    source_node_id=inputs.snapshot_artifact.id,
                    target_node_id=plan.id,
                    relation_type=ArtifactRelationType.DERIVED_FROM,
                ),
                ArtifactEdge(
                    project_id=task.project_id,
                    source_node_id=inputs.snapshot_artifact.id,
                    target_node_id=bible.id,
                    relation_type=ArtifactRelationType.DERIVED_FROM,
                ),
                ArtifactEdge(
                    project_id=task.project_id,
                    source_node_id=plan.id,
                    target_node_id=bible.id,
                    relation_type=ArtifactRelationType.USES,
                ),
            ]
        )
        if previous_plan is not None:
            db.add(
                ArtifactEdge(
                    project_id=task.project_id,
                    source_node_id=plan.id,
                    target_node_id=previous_plan.id,
                    relation_type=ArtifactRelationType.SUPERSEDES,
                )
            )
        if previous_bible is not None:
            db.add(
                ArtifactEdge(
                    project_id=task.project_id,
                    source_node_id=bible.id,
                    target_node_id=previous_bible.id,
                    relation_type=ArtifactRelationType.SUPERSEDES,
                )
            )
        _invalidate_project_plan(db, inputs.project)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(plan)
    db.refresh(bible)
    return plan, bible


def _claim(db: Session, task_id: str, worker_id: str) -> Task | None:
    task = db.get(Task, task_id)
    if (
        task is None
        or task.task_type != P11_TASK_TYPE
        or task.status != TaskStatus.QUEUED
        or task.attempt >= task.max_attempts
    ):
        return None
    now = utc_now()
    result = db.execute(
        update(Task)
        .where(
            Task.id == task_id,
            Task.task_type == P11_TASK_TYPE,
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


def _mark_publish_failed(factory: sessionmaker[Session], task_id: str, message: str) -> None:
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


def run_replica_target_bible_task(session_factory: sessionmaker[Session], task_id: str) -> None:
    worker_id = f"p11-replica-target-bible-{uuid4()}"
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
            f"P11 目标设定失败（{exc.code}）：{exc.message}",
        )
        return
    except Exception as exc:
        _fail_if_running(
            session_factory,
            snapshot.id,
            worker_id,
            f"P11 目标设定失败（{type(exc).__name__}）",
        )
        return

    with session_factory() as db:
        finished = mark_task_succeeded(db, snapshot.id, worker_id=worker_id)
    if finished.status == TaskStatus.CANCELLED:
        return
    try:
        with session_factory() as db:
            _publish(db, task_id=snapshot.id, result=result)
    except AppError as exc:
        _mark_publish_failed(
            session_factory,
            snapshot.id,
            f"P11 Target Artifact 发布失败（{exc.code}）：{exc.message}",
        )
    except Exception as exc:
        _mark_publish_failed(
            session_factory,
            snapshot.id,
            f"P11 Target Artifact 发布失败（{type(exc).__name__}）",
        )


def _read_artifact(
    db: Session,
    project_id: str,
    kind: TargetBibleArtifactKind,
) -> ReplicaTargetArtifactRead:
    artifact_type = _ARTIFACT_TYPES[kind]
    current = _current_artifact(db, project_id, artifact_type)
    latest = current or _latest_artifact(db, project_id, artifact_type)
    if latest is None:
        return ReplicaTargetArtifactRead(status=TargetBibleResultStatus.NOT_BUILT)
    row = db.scalar(select(ReplicaTargetRevision).where(ReplicaTargetRevision.artifact_id == latest.id))
    if row is None:
        raise AppError("P11_TARGET_CONTENT_MISSING", "P11 Target Artifact 缺少正式 typed revision", status_code=500)
    provenance = ReplicaTargetProvenance.model_validate(row.provenance_json)
    if kind == TargetBibleArtifactKind.ADAPTATION_PLAN:
        content: ReplicaAdaptationPlanContent | ReplicaTargetBibleContent = ReplicaAdaptationPlanContent.model_validate(row.content_json)
    else:
        content = ReplicaTargetBibleContent.model_validate(row.content_json)
    return ReplicaTargetArtifactRead(
        status=TargetBibleResultStatus.CURRENT if current is not None else TargetBibleResultStatus.STALE,
        artifact_id=latest.id,
        revision=latest.revision,
        input_fingerprint=latest.input_fingerprint,
        content=content,
        provenance=provenance,
    )


def get_replica_target_bible(db: Session, project_id: str) -> ReplicaTargetBibleRead:
    project = get_project(db, project_id)
    _assert_replica(project)
    plan = _read_artifact(db, project_id, TargetBibleArtifactKind.ADAPTATION_PLAN)
    bible = _read_artifact(db, project_id, TargetBibleArtifactKind.TARGET_BIBLE)
    if plan.status == TargetBibleResultStatus.CURRENT and bible.status == TargetBibleResultStatus.CURRENT:
        status = TargetBibleResultStatus.CURRENT
    elif plan.status == TargetBibleResultStatus.NOT_BUILT and bible.status == TargetBibleResultStatus.NOT_BUILT:
        status = TargetBibleResultStatus.NOT_BUILT
    else:
        status = TargetBibleResultStatus.STALE
    snapshot_id = None
    snapshot_revision = None
    provenance = bible.provenance or plan.provenance
    if provenance is not None:
        snapshot_id = provenance.source_snapshot_artifact_id
        snapshot_revision = provenance.source_snapshot_revision
    return ReplicaTargetBibleRead(
        project_id=project_id,
        status=status,
        source_snapshot_artifact_id=snapshot_id,
        source_snapshot_revision=snapshot_revision,
        adaptation_plan=plan,
        target_bible=bible,
    )


def list_replica_target_bible_revisions(
    db: Session,
    project_id: str,
) -> list[ReplicaTargetBibleRevisionSummary]:
    project = get_project(db, project_id)
    _assert_replica(project)
    artifacts = list(
        db.scalars(
            select(ArtifactNode)
            .where(
                ArtifactNode.project_id == project_id,
                ArtifactNode.artifact_type.in_([
                    ArtifactType.ADAPTATION_PLAN.value,
                    ArtifactType.TARGET_BIBLE.value,
                ]),
            )
            .order_by(ArtifactNode.created_at.desc(), ArtifactNode.revision.desc())
        ).all()
    )
    result: list[ReplicaTargetBibleRevisionSummary] = []
    type_to_kind = {
        ArtifactType.ADAPTATION_PLAN.value: TargetBibleArtifactKind.ADAPTATION_PLAN,
        ArtifactType.TARGET_BIBLE.value: TargetBibleArtifactKind.TARGET_BIBLE,
    }
    for artifact in artifacts:
        row = db.scalar(select(ReplicaTargetRevision).where(ReplicaTargetRevision.artifact_id == artifact.id))
        if row is None:
            continue
        result.append(
            ReplicaTargetBibleRevisionSummary(
                artifact_kind=type_to_kind[artifact.artifact_type],
                artifact_id=artifact.id,
                revision=artifact.revision,
                validity=artifact.validity.value,
                input_fingerprint=artifact.input_fingerprint,
                source_snapshot_artifact_id=row.source_snapshot_artifact_id,
                created_at=artifact.created_at.isoformat(),
            )
        )
    return result
