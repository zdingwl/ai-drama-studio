"""P9 lifecycle adapter for retry semantics, safe diagnostics and staged Speaker evidence.

The P9 base service owns CURRENT-input validation, ProviderJob-before-remote persistence,
Artifact publication and the core four-skill composition rules. This adapter mirrors the accepted
P8 retry behaviour and owns the product background runner.

Speaker attribution is the only P9 skill that receives the staged SOURCE_CHARACTERS result from
the same automatic P9 run. The Provider contract explicitly allows ``evidence_refs[].ref_id`` to
reference one of those staged P9 ``character_id`` values. Those ids are not Source input ids and
therefore are intentionally absent from the base Source-only ``_known_ref_ids()`` set. Validate
that extra namespace only inside Speaker composition, while keeping all Episode/Shot/Utterance
context checks fail-closed. This prevents valid staged Character evidence from being rejected as
``P9_EVIDENCE_REF_INVALID`` without weakening Character/Scene/Prop Source evidence validation.
"""

from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import AppError
from app.source_resolution import service as _base
from app.source_resolution.schemas import (
    CharacterResolutionSemantic,
    EntityGroupSemantic,
    EvidenceRef,
    PropResolutionSemantic,
    ResolutionStatus,
    SceneResolutionSemantic,
    SourceResolutionKind,
    SpeakerAttribution,
    SpeakerEntity,
    SpeakerResolutionContent,
    SpeakerResolutionSemantic,
)
from app.workflow.models import TaskStatus
from app.workflow.schemas import TaskWorkerRead
from app.workflow.task_service import TaskCancelled, mark_task_succeeded, retry_task
from app.workflow.worker import TaskExecutionContext


P9_TASK_TYPE = _base.P9_TASK_TYPE


def create_source_resolution_task(db: Session, *, project_id: str, idempotency_key: str):
    task = _base.create_source_resolution_task(
        db,
        project_id=project_id,
        idempotency_key=idempotency_key,
    )
    if task.status == TaskStatus.FAILED and task.idempotency_key != idempotency_key.strip():
        return retry_task(db, project_id, task.id)
    return task


def _p9_task_error_message(exc: AppError) -> str:
    """Expose only the authored safe AppError code/message, never raw provider output."""

    return f"P9 最终归一失败（{exc.code}）：{exc.message}"


def _validate_speaker_evidence_refs(
    refs: list[EvidenceRef],
    inputs: _base.P9Inputs,
    *,
    staged_character_ids: set[str],
) -> None:
    """Validate Source refs plus only the staged P9 Character ids visible to Speaker."""

    source_refs = [ref for ref in refs if ref.ref_id not in staged_character_ids]
    _base._validate_evidence_refs(source_refs, inputs)

    episode_ids = {item.episode.id for item in inputs.contexts}
    shot_ids = set(_base._shot_fact_map(inputs))
    utterance_ids = set(_base._utterance_map(inputs))
    for ref in refs:
        if ref.ref_id not in staged_character_ids:
            continue
        if ref.episode_id is not None and ref.episode_id not in episode_ids:
            raise AppError("P9_EVIDENCE_REF_INVALID", "P9 evidence episode_id 无效", status_code=422)
        if ref.shot_anchor_id is not None and ref.shot_anchor_id not in shot_ids:
            raise AppError("P9_EVIDENCE_REF_INVALID", "P9 evidence shot_anchor_id 无效", status_code=422)
        if ref.utterance_id is not None and ref.utterance_id not in utterance_ids:
            raise AppError("P9_EVIDENCE_REF_INVALID", "P9 evidence utterance_id 无效", status_code=422)


def _speaker_groups(
    groups: list[EntityGroupSemantic],
    inputs: _base.P9Inputs,
    *,
    staged_character_ids: set[str],
) -> dict[str, EntityGroupSemantic]:
    by_key = {item.group_key: item for item in groups}
    if len(by_key) != len(groups):
        raise AppError("P9_GROUP_KEY_DUPLICATED", "P9 Provider group_key 重复", status_code=422)
    for group in groups:
        if group.resolution_status != ResolutionStatus.RESOLVED:
            raise AppError(
                "P9_GROUP_STATUS_INVALID",
                "Provider stable group 必须是 RESOLVED；未决结果不得伪造 stable identity",
                status_code=422,
            )
        if not group.evidence_refs:
            raise AppError("P9_GROUP_EVIDENCE_REQUIRED", "Provider stable group 必须提供可追溯 evidence_refs", status_code=422)
        _validate_speaker_evidence_refs(
            group.evidence_refs,
            inputs,
            staged_character_ids=staged_character_ids,
        )
    return by_key


def _compose_speakers_with_staged_character_refs(
    inputs: _base.P9Inputs,
    characters,
    semantic: SpeakerResolutionSemantic,
) -> SpeakerResolutionContent:
    """Compose Speaker truth while accepting only this run's staged P9 Character refs."""

    utterance_map = _base._utterance_map(inputs)
    actual_ids = [item.utterance_id for item in semantic.attributions]
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != set(utterance_map):
        raise AppError(
            "P9_SPEAKER_UTTERANCE_SET_INVALID",
            "Speaker attribution 必须与 CURRENT P6 canonical utterance 一一对应",
            status_code=422,
        )

    valid_character_ids = {item.character_id for item in characters.entities}
    group_map = _speaker_groups(
        list(semantic.groups),
        inputs,
        staged_character_ids=valid_character_ids,
    )
    p7_character_ids = {
        item.character_id for context in inputs.contexts for item in context.source_bible_episode.characters
    }
    for group in semantic.groups:
        if group.character_id is not None and group.character_id not in valid_character_ids:
            raise AppError(
                "P9_SPEAKER_CHARACTER_LINK_INVALID",
                "Speaker 引用了不存在的 P9 Character identity",
                status_code=422,
            )
        if set(group.source_candidate_character_ids) - p7_character_ids:
            raise AppError(
                "P9_SPEAKER_CANDIDATE_INVALID",
                "Speaker 引用了不存在的 P7 Character candidate",
                status_code=422,
            )

    members: dict[str, list[str]] = {key: [] for key in group_map}
    attributions: list[SpeakerAttribution] = []
    for item in semantic.attributions:
        group = _base._binding(item.group_key, item.resolution_status, group_map)
        episode_id, utterance = utterance_map[item.utterance_id]
        if group is not None:
            members[group.group_key].append(item.utterance_id)
        attributions.append(
            SpeakerAttribution(
                episode_id=episode_id,
                utterance_id=utterance.id,
                utterance_number=utterance.utterance_number,
                start_us=utterance.start_us,
                end_us=utterance.end_us,
                text=utterance.text,
                speaker_id=None,
                resolution_status=item.resolution_status,
                reason=item.reason,
            )
        )

    entity_by_group: dict[str, SpeakerEntity] = {}
    shot_map = _base._shot_fact_map(inputs)
    for key, group in group_map.items():
        utterance_ids = sorted(set(members[key]))
        if not utterance_ids:
            raise AppError("P9_UNREFERENCED_GROUP", "Speaker stable group 没有 canonical utterance", status_code=422)
        speaker_id = _base._stable_id("spk", utterance_ids)
        episode_ids = sorted({utterance_map[value][0] for value in utterance_ids})
        utterance_id_set = set(utterance_ids)
        shot_ids = sorted(
            {
                shot_id
                for shot_id, (_episode_id, shot) in shot_map.items()
                if any(binding.utterance_id in utterance_id_set for binding in shot.dialogue)
            }
        )
        entity_by_group[key] = SpeakerEntity(
            entity_id=speaker_id,
            speaker_id=speaker_id,
            display_name=group.display_name,
            aliases=group.aliases,
            source_candidate_ids=sorted(set(group.source_candidate_character_ids)),
            source_candidate_character_ids=sorted(set(group.source_candidate_character_ids)),
            episode_ids=episode_ids,
            shot_anchor_ids=shot_ids,
            utterance_ids=utterance_ids,
            evidence_refs=group.evidence_refs,
            confidence=group.confidence,
            resolution_status=ResolutionStatus.RESOLVED,
            notes=group.notes,
            character_id=group.character_id,
        )
    for index, item in enumerate(semantic.attributions):
        if item.group_key is not None:
            attributions[index] = attributions[index].model_copy(
                update={"speaker_id": entity_by_group[item.group_key].speaker_id}
            )
    return SpeakerResolutionContent(entities=list(entity_by_group.values()), attributions=attributions)


def _execute(context: TaskExecutionContext, task: TaskWorkerRead) -> _base.P9ExecutionResult:
    """Run P9 with the Speaker-only staged Character evidence namespace."""

    with context.session_factory() as db:
        inputs = _base._load_inputs(db, task.project_id)
        project = _base.get_project(db, task.project_id)
        provider = _base._provider_for_project(project)
        _base._assert_task_snapshot(db, task, inputs, provider)

    jobs = {}
    profiles = {}

    context.checkpoint({"stage": "character_resolution", "scope": "ALL_FULL_EPISODES"}, progress_percent=8)
    raw, job, profile = _base._run_provider_skill(
        context,
        task,
        inputs,
        provider,
        kind=SourceResolutionKind.CHARACTER,
        payload=_base._provider_input(inputs),
    )
    semantic = raw if isinstance(raw, CharacterResolutionSemantic) else CharacterResolutionSemantic.model_validate(raw)
    characters = _base._compose_characters(inputs, semantic)
    jobs[SourceResolutionKind.CHARACTER] = (job,)
    profiles[SourceResolutionKind.CHARACTER] = profile

    context.checkpoint({"stage": "speaker_attribution", "scope": "ALL_FULL_EPISODES"}, progress_percent=32)
    staged_character_fingerprint = _base._sha(characters.model_dump(mode="json"))
    raw, job, profile = _base._run_provider_skill(
        context,
        task,
        inputs,
        provider,
        kind=SourceResolutionKind.SPEAKER,
        payload=_base._provider_input(inputs, source_characters=characters),
        staged_character_fingerprint=staged_character_fingerprint,
    )
    semantic = raw if isinstance(raw, SpeakerResolutionSemantic) else SpeakerResolutionSemantic.model_validate(raw)
    speakers = _compose_speakers_with_staged_character_refs(inputs, characters, semantic)
    jobs[SourceResolutionKind.SPEAKER] = (job,)
    profiles[SourceResolutionKind.SPEAKER] = profile

    context.checkpoint({"stage": "scene_resolution", "scope": "ALL_FULL_EPISODES"}, progress_percent=54)
    raw, job, profile = _base._run_provider_skill(
        context,
        task,
        inputs,
        provider,
        kind=SourceResolutionKind.SCENE,
        payload=_base._provider_input(inputs),
    )
    semantic = raw if isinstance(raw, SceneResolutionSemantic) else SceneResolutionSemantic.model_validate(raw)
    scenes = _base._compose_scenes(inputs, semantic)
    jobs[SourceResolutionKind.SCENE] = (job,)
    profiles[SourceResolutionKind.SCENE] = profile

    context.checkpoint({"stage": "prop_resolution", "scope": "ALL_FULL_EPISODES"}, progress_percent=76)
    raw, job, profile = _base._run_provider_skill(
        context,
        task,
        inputs,
        provider,
        kind=SourceResolutionKind.PROP,
        payload=_base._provider_input(inputs),
    )
    semantic = raw if isinstance(raw, PropResolutionSemantic) else PropResolutionSemantic.model_validate(raw)
    props = _base._compose_props(inputs, semantic)
    jobs[SourceResolutionKind.PROP] = (job,)
    profiles[SourceResolutionKind.PROP] = profile

    context.checkpoint({"stage": "validate_p9_resolution_set"}, progress_percent=94)
    return _base.P9ExecutionResult(
        characters=characters,
        speakers=speakers,
        scenes=scenes,
        props=props,
        provider_jobs=jobs,
        provider_profiles=profiles,
    )


def run_p9_source_resolution_task(session_factory: sessionmaker[Session], task_id: str) -> None:
    """Run the P9 task while preserving safe stage-specific validation diagnostics."""

    worker_id = f"p9-source-resolution-{uuid4()}"
    with session_factory() as db:
        claimed = _base._claim(db, task_id, worker_id)
        if claimed is None:
            return
        snapshot = TaskWorkerRead.model_validate(claimed)
    context = TaskExecutionContext(session_factory=session_factory, task_id=snapshot.id, worker_id=worker_id)
    try:
        result = _execute(context, snapshot)
    except TaskCancelled:
        return
    except AppError as exc:
        _base._fail_if_running(session_factory, snapshot.id, worker_id, _p9_task_error_message(exc))
        return
    except Exception as exc:
        _base._fail_if_running(
            session_factory,
            snapshot.id,
            worker_id,
            f"P9 最终归一失败（{type(exc).__name__}）",
        )
        return

    with session_factory() as db:
        finished = mark_task_succeeded(db, snapshot.id, worker_id=worker_id)
    if finished.status == TaskStatus.CANCELLED:
        return
    try:
        with session_factory() as db:
            _base._publish_all(db, task_id=snapshot.id, result=result)
    except AppError as exc:
        _base._mark_publish_failed(
            session_factory,
            snapshot.id,
            f"P9 正式 Artifact 发布失败（{exc.code}）：{exc.message}",
        )
    except Exception as exc:
        _base._mark_publish_failed(
            session_factory,
            snapshot.id,
            f"P9 正式 Artifact 发布失败（{type(exc).__name__}）",
        )


get_source_resolution = _base.get_source_resolution
list_source_resolution_revisions = _base.list_source_resolution_revisions
