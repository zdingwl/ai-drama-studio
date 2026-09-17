import hashlib
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactValidity
from app.artifacts.models import ArtifactNode
from app.core.config import Settings
from app.core.errors import AppError
from app.core.time import utc_now
from app.p15.schemas import GenerationSegment
from app.p16.common import attempt_to_read, input_artifact_ids, load_inputs, sha, storage_dir
from app.p16.media import duration_tolerance_us, probe_video, sha256_file
from app.p16.models import ReplicaGeneratedVideoRevision, ReplicaGenerationAttempt, ReplicaGenerationSelectionCandidate
from app.p16.provider import H3GenerationProvider, build_h3_generation_provider
from app.p16.schemas import (
    H3RuntimeReadinessRead,
    H3RuntimeReadinessState,
    P16CandidateProvenance,
    P16SelectionCandidateContent,
    P16SelectionCandidateRead,
    P16_CONTRACT,
    P16_SCHEMA_VERSION,
    ReplicaGeneratedVideoContent,
    SelectedGenerationClip,
    SelectionReviewStatus,
    TechnicalQcStatus,
)
from app.projects.enums import ProjectType
from app.projects.service import get_project
from app.skills.models import ArtifactType, Capability
from app.skills.professional import get_professional_skill
from app.workflow.models import ProviderJob, Task, TaskStatus
from app.workflow.provider_service import ProviderDispatchResult, dispatch_provider_call
from app.workflow.schemas import TaskCommandCreate, TaskWorkerRead
from app.workflow.task_service import TaskCancelled, create_task_from_command, mark_task_failed, mark_task_succeeded
from app.workflow.worker import TaskExecutionContext


P16_TASK_TYPE = "P16_MINIMAX_H3_GENERATION"
P16_SEGMENT_TASK_TYPE = "P16_MINIMAX_H3_SEGMENT_REGENERATE"
P16_TASK_TYPES = frozenset({P16_TASK_TYPE, P16_SEGMENT_TASK_TYPE})


def _max_attempts_per_segment(settings: Settings | None = None) -> int:
    return (settings or Settings()).p16_max_attempts_per_segment


def _generation_sequence(db: Session, project_id: str) -> int:
    latest = db.scalar(
        select(func.max(ReplicaGenerationSelectionCandidate.generation_sequence)).where(
            ReplicaGenerationSelectionCandidate.project_id == project_id
        )
    )
    return int(latest or 0) + 1


def _fingerprint(
    inputs,
    sequence: int,
    provider: H3GenerationProvider,
    *,
    task_type: str = P16_TASK_TYPE,
    target_segment_id: str | None = None,
    base_generated_video: ArtifactNode | None = None,
) -> str:
    skill = get_professional_skill("video-generation-qc")
    return sha(
        {
            "task": task_type,
            "inputs": [
                [node.id, node.revision, node.input_fingerprint]
                for node in (inputs.storyboard_artifact, inputs.segments_artifact, inputs.assets_artifact)
            ],
            "target_segment_id": target_segment_id,
            "base_generated_video": (
                [base_generated_video.id, base_generated_video.revision, base_generated_video.input_fingerprint]
                if base_generated_video is not None
                else None
            ),
            "generation_sequence": sequence,
            "provider_profile": provider.profile(),
            "max_attempts_per_segment": _max_attempts_per_segment(),
            "duration_tolerance_us": duration_tolerance_us(),
            "skill": [skill.id, skill.version],
            "schema_version": P16_SCHEMA_VERSION,
        }
    )


def _find_segment(inputs, generation_segment_id: str) -> GenerationSegment:
    segment = next(
        (item for item in inputs.segments.segments if item.generation_segment_id == generation_segment_id),
        None,
    )
    if segment is None:
        raise AppError(
            "P16_GENERATION_SEGMENT_NOT_FOUND",
            "要重做的 GenerationSegment 不属于 CURRENT H3 Prompt",
            status_code=404,
            details={"generation_segment_id": generation_segment_id},
        )
    return segment


def _load_current_generated_video_base(
    db: Session,
    project_id: str,
    inputs,
) -> tuple[ArtifactNode, ReplicaGeneratedVideoContent]:
    artifact = db.scalar(
        select(ArtifactNode).where(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == ArtifactType.GENERATED_VIDEO.value,
            ArtifactNode.validity == ArtifactValidity.CURRENT,
            ArtifactNode.is_current.is_(True),
        )
    )
    if artifact is None:
        raise AppError("P16_CURRENT_VIDEO_REQUIRED", "单分镜重做前必须先有 CURRENT 生成视频", status_code=409)
    row = db.scalar(select(ReplicaGeneratedVideoRevision).where(ReplicaGeneratedVideoRevision.artifact_id == artifact.id))
    if row is None:
        raise AppError("P16_GENERATED_VIDEO_CONTENT_MISSING", "CURRENT GENERATED_VIDEO 缺少 typed revision", status_code=500)
    content = ReplicaGeneratedVideoContent.model_validate(row.content_json)
    if [
        content.target_storyboard_artifact_id,
        content.generation_segments_artifact_id,
        content.target_assets_artifact_id,
    ] != input_artifact_ids(inputs):
        raise AppError("P16_CURRENT_VIDEO_STALE", "当前视频不属于最新五步主链输入，请先重新生成整批视频", status_code=409)
    expected_ids = {item.generation_segment_id for item in inputs.segments.segments}
    actual_ids = {item.generation_segment_id for item in content.clips}
    if actual_ids != expected_ids:
        raise AppError("P16_CURRENT_VIDEO_COVERAGE_INVALID", "CURRENT GENERATED_VIDEO 没有完整覆盖 GenerationSegment", status_code=409)
    return artifact, content


def get_runtime_readiness(db: Session, project_id: str) -> H3RuntimeReadinessRead:
    project = get_project(db, project_id)
    if project.project_type != ProjectType.REPLICA:
        raise AppError("P16_REPLICA_ONLY", "视频生成 Runtime 当前只允许 REPLICA 项目", status_code=422)
    settings = Settings()
    try:
        provider = build_h3_generation_provider(settings)
    except AppError as exc:
        if exc.code != "P16_PROVIDER_NOT_CONFIGURED":
            raise
        return H3RuntimeReadinessRead(
            runtime_mode=settings.p16_h3_runtime,
            state=H3RuntimeReadinessState.NOT_CONFIGURED,
            ready=False,
            provider="minimax-cloud",
            model=settings.p16_minimax_model,
            base_url=settings.p16_minimax_base_url,
            message=exc.message,
        )
    return provider.readiness()


def _set_task_checkpoint_fields(db: Session, task: Task, values: dict) -> Task:
    current = dict(task.checkpoint_json or {})
    changed = False
    for key, value in values.items():
        if key not in current or current[key] != value:
            current[key] = value
            changed = True
    if changed:
        task.checkpoint_json = current
        db.add(task)
        db.commit()
        db.refresh(task)
    return task


def create_generation_task(db: Session, *, project_id: str, idempotency_key: str) -> Task:
    project = get_project(db, project_id)
    inputs = load_inputs(db, project)
    provider = build_h3_generation_provider(Settings())
    provider.assert_ready()
    sequence = _generation_sequence(db, project_id)
    task = create_task_from_command(
        db,
        project_id=project_id,
        idempotency_key=idempotency_key,
        payload=TaskCommandCreate(
            task_type=P16_TASK_TYPE,
            task_name="生成视频并执行技术质检",
            input_fingerprint=_fingerprint(inputs, sequence, provider),
            input_artifact_ids=input_artifact_ids(inputs),
            max_attempts=3,
        ),
    )
    return _set_task_checkpoint_fields(db, task, {"p16_generation_sequence": sequence})


def create_segment_regeneration_task(
    db: Session,
    *,
    project_id: str,
    generation_segment_id: str,
    idempotency_key: str,
) -> Task:
    project = get_project(db, project_id)
    inputs = load_inputs(db, project)
    segment = _find_segment(inputs, generation_segment_id)
    base_artifact, _base_content = _load_current_generated_video_base(db, project_id, inputs)
    provider = build_h3_generation_provider(Settings())
    provider.assert_ready()
    sequence = _generation_sequence(db, project_id)
    task = create_task_from_command(
        db,
        project_id=project_id,
        idempotency_key=idempotency_key,
        payload=TaskCommandCreate(
            task_type=P16_SEGMENT_TASK_TYPE,
            task_name=f"重做视频分镜 · Segment {segment.segment_number}",
            input_fingerprint=_fingerprint(
                inputs,
                sequence,
                provider,
                task_type=P16_SEGMENT_TASK_TYPE,
                target_segment_id=generation_segment_id,
                base_generated_video=base_artifact,
            ),
            input_artifact_ids=[*input_artifact_ids(inputs), base_artifact.id],
            episode_id=segment.episode_id,
            max_attempts=3,
        ),
    )
    return _set_task_checkpoint_fields(
        db,
        task,
        {
            "p16_generation_sequence": sequence,
            "p16_target_segment_id": generation_segment_id,
            "p16_base_generated_video_artifact_id": base_artifact.id,
        },
    )


def replace_generation_task_for_retry_if_needed(db: Session, *, project_id: str, task: Task) -> Task | None:
    if task.task_type not in P16_TASK_TYPES or task.status not in {TaskStatus.FAILED, TaskStatus.INTERRUPTED}:
        return None
    if task.status == TaskStatus.FAILED and task.attempt >= task.max_attempts:
        return None

    project = get_project(db, project_id)
    inputs = load_inputs(db, project)
    provider = build_h3_generation_provider()
    provider.assert_ready()
    sequence = int((task.checkpoint_json or {}).get("p16_generation_sequence") or 0)
    if sequence <= 0:
        return None

    target_segment_id = (task.checkpoint_json or {}).get("p16_target_segment_id")
    if task.task_type == P16_SEGMENT_TASK_TYPE:
        if not isinstance(target_segment_id, str) or not target_segment_id:
            return None
        _find_segment(inputs, target_segment_id)
        base_artifact, _ = _load_current_generated_video_base(db, project_id, inputs)
        current_ids = [*input_artifact_ids(inputs), base_artifact.id]
        current_fingerprint = _fingerprint(
            inputs,
            sequence,
            provider,
            task_type=P16_SEGMENT_TASK_TYPE,
            target_segment_id=target_segment_id,
            base_generated_video=base_artifact,
        )
    else:
        current_ids = input_artifact_ids(inputs)
        current_fingerprint = _fingerprint(inputs, sequence, provider)

    inputs_changed = sorted(set(task.input_artifact_ids_json or [])) != sorted(set(current_ids))
    if not inputs_changed and current_fingerprint == task.input_fingerprint:
        return None

    if task.task_type == P16_SEGMENT_TASK_TYPE:
        replacement = create_segment_regeneration_task(
            db,
            project_id=project_id,
            generation_segment_id=target_segment_id,
            idempotency_key=f"p16-segment-retry-{task.id}-{current_fingerprint[:16]}",
        )
    else:
        replacement = create_generation_task(
            db,
            project_id=project_id,
            idempotency_key=f"p16-runtime-retry-{task.id}-{current_fingerprint[:16]}",
        )
    return _set_task_checkpoint_fields(
        db,
        replacement,
        {
            "p16_replaces_task_id": task.id,
            "p16_replaces_failed_task_id": task.id if task.status == TaskStatus.FAILED else None,
        },
    )


def _claim(db: Session, task_id: str, worker_id: str) -> Task | None:
    task = db.get(Task, task_id)
    if task is None or task.task_type not in P16_TASK_TYPES or task.status != TaskStatus.QUEUED or task.attempt >= task.max_attempts:
        return None
    now = utc_now()
    result = db.execute(
        update(Task)
        .where(Task.id == task_id, Task.status == TaskStatus.QUEUED, Task.attempt < Task.max_attempts)
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


def _next_attempt_number(db: Session, segments_artifact_id: str, segment_id: str) -> int:
    latest = db.scalar(
        select(func.max(ReplicaGenerationAttempt.attempt_number)).where(
            ReplicaGenerationAttempt.generation_segments_artifact_id == segments_artifact_id,
            ReplicaGenerationAttempt.generation_segment_id == segment_id,
        )
    )
    return int(latest or 0) + 1


def _attempt_media_url(project_id: str, attempt_id: str) -> str:
    return f"/api/v3/projects/{project_id}/video-generation/media/{attempt_id}"


def _generate_attempt(
    db: Session,
    *,
    task: TaskWorkerRead,
    inputs,
    provider: H3GenerationProvider,
    segment: GenerationSegment,
) -> ReplicaGenerationAttempt:
    attempt_number = _next_attempt_number(db, inputs.segments_artifact.id, segment.generation_segment_id)
    safe_segment = hashlib.sha256(segment.generation_segment_id.encode("utf-8")).hexdigest()[:16]
    provider_payload = {
        "contract": P16_CONTRACT,
        "runtime_mode": provider.profile().get("runtime_mode"),
        "generation_segment_id": segment.generation_segment_id,
        "attempt_number": attempt_number,
        "prompt_fingerprint": sha({"prompt": segment.generation_prompt, "negative": segment.negative_prompt}),
        "planned_duration_us": segment.duration_us,
        "requested_duration_seconds": provider.requested_duration(segment),
        "output_ratio": segment.output_ratio,
        "reference_conditions": [
            {
                "picture_index": item.picture_index,
                "target_asset_id": item.target_asset_id,
                "target_entity_id": item.target_entity_id,
                "asset_type": item.asset_type,
                "reference_id": item.reference_id,
                "reference_role": item.reference_role,
                "reference_sha256": item.reference_sha256,
            }
            for item in segment.reference_conditions
        ],
        "provider_profile": provider.profile(),
    }

    def remote_call(job: ProviderJob) -> ProviderDispatchResult:
        output_path = storage_dir(task.project_id, task.id) / f"{safe_segment}-a{attempt_number}-{job.id}.mp4"
        generated = provider.generate_to_file(segment, output_path)
        probe = probe_video(output_path)
        tolerance = duration_tolerance_us()
        expected_us = generated.requested_duration_seconds * 1_000_000
        issues: list[str] = []
        if abs(probe.duration_us - expected_us) > tolerance:
            issues.append(
                f"duration mismatch: actual={probe.duration_us}us expected={expected_us}us tolerance={tolerance}us"
            )
        return ProviderDispatchResult(
            value={
                "storage_filename": output_path.name,
                "media_sha256": sha256_file(output_path),
                "mime_type": "video/mp4",
                "duration_us": probe.duration_us,
                "width": probe.width,
                "height": probe.height,
                "codec_name": probe.codec_name,
                "issues": issues,
                "requested_duration_seconds": generated.requested_duration_seconds,
            },
            remote_job_id=generated.remote_job_id,
            completed=True,
        )

    job, dispatched = dispatch_provider_call(
        db,
        task_id=task.id,
        provider=provider.provider_name,
        model=provider.model_name,
        capability=Capability.VIDEO_GENERATION,
        payload=provider_payload,
        artifact_id=inputs.segments_artifact.id,
        remote_call=remote_call,
    )
    value = dict(dispatched.value or {})
    attempt = ReplicaGenerationAttempt(
        project_id=task.project_id,
        target_storyboard_artifact_id=inputs.storyboard_artifact.id,
        generation_segments_artifact_id=inputs.segments_artifact.id,
        target_assets_artifact_id=inputs.assets_artifact.id,
        generated_by_task_id=task.id,
        generation_segment_id=segment.generation_segment_id,
        attempt_number=attempt_number,
        provider_job_id=job.id,
        prompt_fingerprint=provider_payload["prompt_fingerprint"],
        remote_job_id=job.remote_job_id,
        storage_filename=str(value["storage_filename"]),
        media_url="PENDING",
        media_sha256=str(value["media_sha256"]),
        mime_type=str(value["mime_type"]),
        actual_duration_us=int(value["duration_us"]),
        width=int(value["width"]),
        height=int(value["height"]),
        codec_name=str(value["codec_name"]),
        technical_qc_status=TechnicalQcStatus.FAIL.value if value.get("issues") else TechnicalQcStatus.PASS.value,
        technical_qc_issues_json=list(value.get("issues") or []),
    )
    db.add(attempt)
    db.flush()
    attempt.media_url = _attempt_media_url(task.project_id, attempt.id)
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt


def _selected_clip(segment: GenerationSegment, attempt: ReplicaGenerationAttempt) -> SelectedGenerationClip:
    return SelectedGenerationClip(
        generation_segment_id=segment.generation_segment_id,
        episode_id=segment.episode_id,
        episode_order=segment.episode_order,
        segment_number=segment.segment_number,
        planned_start_us=segment.start_us,
        planned_end_us=segment.end_us,
        planned_duration_us=segment.duration_us,
        requires_lip_sync=segment.requires_lip_sync,
        selected_attempt_id=attempt.id,
        provider_job_id=attempt.provider_job_id,
        media_url=attempt.media_url,
        media_sha256=attempt.media_sha256,
        mime_type=attempt.mime_type,
        actual_duration_us=attempt.actual_duration_us,
        width=attempt.width,
        height=attempt.height,
        codec_name=attempt.codec_name,
    )


def _validate_task_contract(db: Session, task: TaskWorkerRead, inputs, provider: H3GenerationProvider):
    sequence = int((task.checkpoint_json or {}).get("p16_generation_sequence") or 0)
    if sequence <= 0:
        raise AppError("P16_TASK_CHECKPOINT_INVALID", "P16 Task 缺少 generation sequence", status_code=409)
    target_segment_id = (task.checkpoint_json or {}).get("p16_target_segment_id")
    base_content: ReplicaGeneratedVideoContent | None = None
    base_artifact: ArtifactNode | None = None
    if task.task_type == P16_SEGMENT_TASK_TYPE:
        if not isinstance(target_segment_id, str) or not target_segment_id:
            raise AppError("P16_TASK_CHECKPOINT_INVALID", "单分镜重做 Task 缺少 target segment", status_code=409)
        _find_segment(inputs, target_segment_id)
        base_artifact, base_content = _load_current_generated_video_base(db, task.project_id, inputs)
        expected_base_id = (task.checkpoint_json or {}).get("p16_base_generated_video_artifact_id")
        if base_artifact.id != expected_base_id:
            raise AppError("STALE_ARTIFACT_INPUT", "单分镜重做的基线视频已经变化，请重新发起", status_code=409)
        expected_ids = [*input_artifact_ids(inputs), base_artifact.id]
        expected_fingerprint = _fingerprint(
            inputs,
            sequence,
            provider,
            task_type=P16_SEGMENT_TASK_TYPE,
            target_segment_id=target_segment_id,
            base_generated_video=base_artifact,
        )
    else:
        target_segment_id = None
        expected_ids = input_artifact_ids(inputs)
        expected_fingerprint = _fingerprint(inputs, sequence, provider)
    if sorted(set(task.input_artifact_ids_json or [])) != sorted(set(expected_ids)) or task.input_fingerprint != expected_fingerprint:
        raise AppError("STALE_ARTIFACT_INPUT", "P16 输入或 Runtime 已变化，请重新创建生成任务", status_code=409)
    return target_segment_id, base_content


def _persist_candidate(
    factory: sessionmaker[Session],
    task: TaskWorkerRead,
    selected: list[SelectedGenerationClip],
    provider: H3GenerationProvider,
) -> str:
    with factory() as db:
        project = get_project(db, task.project_id)
        inputs = load_inputs(db, project)
        _validate_task_contract(db, task, inputs, provider)
        selected_ids = {item.generation_segment_id for item in selected}
        expected_ids = {item.generation_segment_id for item in inputs.segments.segments}
        if selected_ids != expected_ids:
            raise AppError("P16_SELECTION_COVERAGE_INVALID", "Selection candidate 必须覆盖全部 GenerationSegment", status_code=500)
        for row in db.scalars(
            select(ReplicaGenerationSelectionCandidate).where(
                ReplicaGenerationSelectionCandidate.project_id == task.project_id,
                ReplicaGenerationSelectionCandidate.review_status == SelectionReviewStatus.NEEDS_REVIEW.value,
            )
        ).all():
            row.review_status = SelectionReviewStatus.SUPERSEDED.value
            row.review_reason = "A newer video generation candidate was generated."
            row.reviewed_at = utc_now()
            db.add(row)
        skill = get_professional_skill("video-generation-qc")
        sequence = int((task.checkpoint_json or {}).get("p16_generation_sequence") or 0)
        provenance = P16CandidateProvenance(
            target_storyboard_artifact_id=inputs.storyboard_artifact.id,
            target_storyboard_revision=inputs.storyboard_artifact.revision,
            target_storyboard_fingerprint=inputs.storyboard_artifact.input_fingerprint,
            generation_segments_artifact_id=inputs.segments_artifact.id,
            generation_segments_revision=inputs.segments_artifact.revision,
            generation_segments_fingerprint=inputs.segments_artifact.input_fingerprint,
            target_assets_artifact_id=inputs.assets_artifact.id,
            target_assets_revision=inputs.assets_artifact.revision,
            target_assets_fingerprint=inputs.assets_artifact.input_fingerprint,
            generation_sequence=sequence,
            professional_skill_version=skill.version,
            provider=provider.provider_name,
            model=provider.model_name,
            provider_job_ids=list(dict.fromkeys(item.provider_job_id for item in selected)),
            generated_by_task_id=task.id,
        )
        candidate = ReplicaGenerationSelectionCandidate(
            project_id=task.project_id,
            target_storyboard_artifact_id=inputs.storyboard_artifact.id,
            generation_segments_artifact_id=inputs.segments_artifact.id,
            target_assets_artifact_id=inputs.assets_artifact.id,
            generated_by_task_id=task.id,
            generation_sequence=sequence,
            input_fingerprint=task.input_fingerprint,
            schema_version=P16_SCHEMA_VERSION,
            content_json=P16SelectionCandidateContent(
                target_storyboard_artifact_id=inputs.storyboard_artifact.id,
                generation_segments_artifact_id=inputs.segments_artifact.id,
                target_assets_artifact_id=inputs.assets_artifact.id,
                clips=selected,
            ).model_dump(mode="json"),
            provenance_json=provenance.model_dump(mode="json"),
            review_status=SelectionReviewStatus.NEEDS_REVIEW.value,
        )
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
        return candidate.id


def run_generation_task(factory: sessionmaker[Session], task_id: str) -> None:
    worker_id = f"p16-h3-{uuid4()}"
    with factory() as db:
        claimed = _claim(db, task_id, worker_id)
        if claimed is None:
            return
        snapshot = TaskWorkerRead.model_validate(claimed)
    context = TaskExecutionContext(session_factory=factory, task_id=snapshot.id, worker_id=worker_id)
    base_checkpoint = dict(snapshot.checkpoint_json or {})
    published = False

    def checkpoint(stage: str, progress_percent: int, **extra) -> None:
        context.checkpoint({**base_checkpoint, "stage": stage, **extra}, progress_percent=progress_percent)

    try:
        provider = build_h3_generation_provider()
        with factory() as db:
            project = get_project(db, snapshot.project_id)
            inputs = load_inputs(db, project)
            target_segment_id, base_content = _validate_task_contract(db, snapshot, inputs, provider)
            all_segments = list(inputs.segments.segments)

        if target_segment_id is None:
            work_segments = all_segments
            selected_by_id: dict[str, SelectedGenerationClip] = {}
        else:
            work_segments = [_find_segment(inputs, target_segment_id)]
            assert base_content is not None
            selected_by_id = {item.generation_segment_id: item for item in base_content.clips}

        for index, segment in enumerate(work_segments):
            passed: ReplicaGenerationAttempt | None = None
            for attempt_index in range(_max_attempts_per_segment()):
                checkpoint(
                    "generation",
                    min(88, 5 + int(index / max(1, len(work_segments)) * 80)),
                    generation_segment_id=segment.generation_segment_id,
                    segment_index=index + 1,
                    segment_count=len(work_segments),
                    attempt=attempt_index + 1,
                )
                with factory() as db:
                    current_inputs = load_inputs(db, get_project(db, snapshot.project_id))
                    _validate_task_contract(db, snapshot, current_inputs, provider)
                    passed_candidate = _generate_attempt(
                        db,
                        task=snapshot,
                        inputs=current_inputs,
                        provider=provider,
                        segment=segment,
                    )
                if passed_candidate.technical_qc_status == TechnicalQcStatus.PASS.value:
                    passed = passed_candidate
                    break
            if passed is None:
                raise AppError(
                    "P16_TECHNICAL_QC_EXHAUSTED",
                    "GenerationSegment 在有限尝试内仍未通过技术 QC",
                    status_code=409,
                    details={"generation_segment_id": segment.generation_segment_id},
                )
            selected_by_id[segment.generation_segment_id] = _selected_clip(segment, passed)

        missing = [item.generation_segment_id for item in all_segments if item.generation_segment_id not in selected_by_id]
        if missing:
            raise AppError(
                "P16_SELECTION_COVERAGE_INVALID",
                "生成结果没有完整覆盖全部 GenerationSegment",
                status_code=500,
                details={"missing": missing},
            )
        selected = [selected_by_id[item.generation_segment_id] for item in all_segments]

        # Cancellation is still honored up to the publication boundary. After this checkpoint the
        # candidate + formal current result are published as one business completion and a late
        # cancel request must not turn an already-published result into a cancelled/failed Task.
        checkpoint("publish", 94, selected_segment_count=len(selected))
        candidate_id = _persist_candidate(factory, snapshot, selected, provider)
        with factory() as db:
            from app.p16.review import adopt_selection_candidate

            adopt_selection_candidate(db, project_id=snapshot.project_id, candidate_id=candidate_id)
        published = True

        with factory() as db:
            task = db.get(Task, snapshot.id)
            if task is None:
                return
            if task.status == TaskStatus.RUNNING and task.worker_id == worker_id:
                task.cancel_requested = False
                db.add(task)
                mark_task_succeeded(db, snapshot.id, worker_id=worker_id)
    except TaskCancelled:
        return
    except Exception as exc:
        message = f"P16 视频生成失败（{exc.code}）：{exc.message}" if isinstance(exc, AppError) else f"P16 视频生成失败（{type(exc).__name__}）"
        with factory() as db:
            task = db.get(Task, snapshot.id)
            if task is None or task.status != TaskStatus.RUNNING or task.worker_id != worker_id:
                return
            if published:
                # Formal video publication already committed. Do not report a contradictory failed
                # task merely because a final bookkeeping call raced with shutdown/cancellation.
                task.cancel_requested = False
                db.add(task)
                mark_task_succeeded(db, snapshot.id, worker_id=worker_id)
            else:
                mark_task_failed(db, snapshot.id, safe_error=message, worker_id=worker_id)


def list_generation_attempts(db: Session, project_id: str) -> list:
    get_project(db, project_id)
    rows = list(
        db.scalars(
            select(ReplicaGenerationAttempt)
            .where(ReplicaGenerationAttempt.project_id == project_id)
            .order_by(ReplicaGenerationAttempt.created_at.desc(), ReplicaGenerationAttempt.attempt_number.desc())
        ).all()
    )
    return [attempt_to_read(db, row) for row in rows]


def _candidate_read(row: ReplicaGenerationSelectionCandidate) -> P16SelectionCandidateRead:
    return P16SelectionCandidateRead(
        id=row.id,
        project_id=row.project_id,
        generation_sequence=row.generation_sequence,
        input_fingerprint=row.input_fingerprint,
        review_status=SelectionReviewStatus(row.review_status),
        review_reason=row.review_reason,
        reviewed_at=row.reviewed_at,
        created_at=row.created_at,
        content=P16SelectionCandidateContent.model_validate(row.content_json),
        provenance=P16CandidateProvenance.model_validate(row.provenance_json),
    )


def list_selection_candidates(db: Session, project_id: str) -> list[P16SelectionCandidateRead]:
    get_project(db, project_id)
    rows = list(
        db.scalars(
            select(ReplicaGenerationSelectionCandidate)
            .where(ReplicaGenerationSelectionCandidate.project_id == project_id)
            .order_by(ReplicaGenerationSelectionCandidate.generation_sequence.desc(), ReplicaGenerationSelectionCandidate.created_at.desc())
        ).all()
    )
    return [_candidate_read(row) for row in rows]
