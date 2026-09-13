import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import AppError
from app.core.time import utc_now
from app.p14.audio_review import resolve_target_audio_media_path
from app.p16.common import attempt_media_path
from app.p16.models import ReplicaGenerationAttempt
from app.p17.common import P17Inputs, episode_key, episode_sidecar_path, input_artifact_ids, load_inputs, sha, storage_dir
from app.p17.media import (
    concatenate_videos,
    create_silence_audio,
    extract_audio_window,
    final_duration_tolerance_us,
    mux_formal_audio,
    normalize_video,
    overlay_audio,
    probe_video,
    sha256_file,
    write_srt,
)
from app.p17.models import ReplicaPostCandidate
from app.p17.provider import LipSyncConfig, LocalHttpLipSyncProvider
from app.p17.schemas import (
    FinalEpisodeOutput,
    P17CandidateProvenance,
    P17_SCHEMA_VERSION,
    PostCandidateRead,
    PostReviewStatus,
    ReplicaFinalOutputContent,
)
from app.projects.service import get_project
from app.skills.models import Capability
from app.skills.professional import get_professional_skill
from app.workflow.models import ProviderJob, Task, TaskStatus
from app.workflow.provider_service import ProviderDispatchResult, dispatch_provider_call
from app.workflow.schemas import TaskCommandCreate, TaskWorkerRead
from app.workflow.task_service import checkpoint_task, create_task_from_command, mark_task_failed, mark_task_succeeded


P17_TASK_TYPE = "P17_REPLICA_POST_PRODUCTION"


def _needs_lip_sync(inputs: P17Inputs) -> bool:
    return any(item.requires_lip_sync for item in inputs.generated_video.clips)


def _provider(inputs: P17Inputs) -> LocalHttpLipSyncProvider | None:
    return LocalHttpLipSyncProvider(LipSyncConfig.from_env()) if _needs_lip_sync(inputs) else None


def _generation_sequence(db: Session, project_id: str) -> int:
    latest = db.scalar(select(func.max(ReplicaPostCandidate.generation_sequence)).where(ReplicaPostCandidate.project_id == project_id))
    return int(latest or 0) + 1


def _fingerprint(inputs: P17Inputs, sequence: int, provider: LocalHttpLipSyncProvider | None) -> str:
    skill = get_professional_skill("post-production")
    return sha(
        {
            "task": P17_TASK_TYPE,
            "inputs": [[node.id, node.revision, node.input_fingerprint] for node in (
                inputs.selection_artifact,
                inputs.target_audio_artifact,
                inputs.target_script_artifact,
                inputs.timing_artifact,
            )],
            "generated_video": [
                inputs.generated_video_artifact.id,
                inputs.generated_video_artifact.revision,
                inputs.generated_video_artifact.input_fingerprint,
            ],
            "generation_sequence": sequence,
            "lip_sync": provider.profile() if provider is not None else "NOT_REQUIRED",
            "duration_tolerance_us": final_duration_tolerance_us(),
            "skill": [skill.id, skill.version],
            "schema_version": P17_SCHEMA_VERSION,
        }
    )


def create_post_task(db: Session, *, project_id: str, idempotency_key: str) -> Task:
    project = get_project(db, project_id)
    inputs = load_inputs(db, project)
    provider = _provider(inputs)
    sequence = _generation_sequence(db, project_id)
    task = create_task_from_command(
        db,
        project_id=project_id,
        idempotency_key=idempotency_key,
        payload=TaskCommandCreate(
            task_type=P17_TASK_TYPE,
            task_name="口型、字幕、音频与最终成片",
            input_fingerprint=_fingerprint(inputs, sequence, provider),
            input_artifact_ids=input_artifact_ids(inputs),
            max_attempts=3,
        ),
    )
    if not (task.checkpoint_json or {}).get("p17_generation_sequence"):
        task.checkpoint_json = {**(task.checkpoint_json or {}), "p17_generation_sequence": sequence}
        db.add(task)
        db.commit()
        db.refresh(task)
    return task


def _claim(db: Session, task_id: str, worker_id: str) -> Task | None:
    task = db.get(Task, task_id)
    if task is None or task.task_type != P17_TASK_TYPE or task.status != TaskStatus.QUEUED or task.attempt >= task.max_attempts:
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


def _checkpoint(factory: sessionmaker[Session], task_id: str, worker_id: str, progress: int, **values: object) -> None:
    with factory() as db:
        task = db.get(Task, task_id)
        if task is None:
            raise AppError("TASK_NOT_FOUND", "P17 Task 不存在", status_code=404)
        checkpoint = dict(task.checkpoint_json or {})
        checkpoint.update(values)
        checkpoint_task(db, task_id, checkpoint=checkpoint, progress_percent=progress, worker_id=worker_id)


def _episode_groups(inputs: P17Inputs) -> list[tuple[str, int, list]]:
    grouped: dict[tuple[int, str], list] = {}
    for clip in inputs.generated_video.clips:
        grouped.setdefault((clip.episode_order, clip.episode_id), []).append(clip)
    result: list[tuple[str, int, list]] = []
    for (order, episode_id), clips in sorted(grouped.items()):
        clips.sort(key=lambda item: item.segment_number)
        cursor = 0
        seen_numbers: set[int] = set()
        for clip in clips:
            if clip.segment_number in seen_numbers:
                raise AppError("P17_SEGMENT_ORDER_INVALID", "Episode 内 segment_number 重复", status_code=409)
            seen_numbers.add(clip.segment_number)
            if clip.planned_duration_us != clip.planned_end_us - clip.planned_start_us:
                raise AppError("P17_SEGMENT_TIMING_INVALID", "正式选片 planned duration 无效", status_code=409)
            if clip.planned_start_us != cursor:
                raise AppError(
                    "P17_SEGMENT_TIMELINE_GAP",
                    "GenerationSelection 的 Episode segment 时间轴必须从 0 连续覆盖，P17 不静默补造视觉内容",
                    status_code=409,
                    details={"episode_id": episode_id, "expected_start_us": cursor, "actual_start_us": clip.planned_start_us},
                )
            cursor = clip.planned_end_us
        if cursor <= 0:
            raise AppError("P17_EPISODE_DURATION_INVALID", "Episode production timeline 无有效时长", status_code=409)
        result.append((episode_id, order, clips))
    if not result:
        raise AppError("P17_SELECTION_EMPTY", "GENERATION_SELECTION 没有正式视频片段", status_code=409)
    return result


def _validated_attempt(db: Session, inputs: P17Inputs, clip) -> tuple[ReplicaGenerationAttempt, Path]:
    attempt = db.get(ReplicaGenerationAttempt, clip.selected_attempt_id)
    if attempt is None or attempt.project_id != inputs.project.id:
        raise AppError("P17_SELECTED_ATTEMPT_MISSING", "正式选片对应的 GenerationAttempt 不存在", status_code=409)
    if attempt.generation_segment_id != clip.generation_segment_id:
        raise AppError("P17_SELECTED_ATTEMPT_MISMATCH", "GenerationAttempt 与 selected segment 不匹配", status_code=409)
    if attempt.generation_segments_artifact_id != inputs.generated_video.generation_segments_artifact_id:
        raise AppError("P17_SELECTED_ATTEMPT_STALE", "GenerationAttempt 不属于正式 Selection 的 segment lineage", status_code=409)
    path = attempt_media_path(attempt)
    if sha256_file(path) != clip.media_sha256 or clip.media_sha256 != attempt.media_sha256:
        raise AppError("P17_SELECTED_MEDIA_HASH_MISMATCH", "正式选片视频 SHA256 已变化", status_code=409)
    probe = probe_video(path)
    if probe.duration_us != attempt.actual_duration_us or probe.width != attempt.width or probe.height != attempt.height:
        raise AppError("P17_SELECTED_MEDIA_PROBE_CHANGED", "正式选片视频重新 ffprobe 与 GenerationAttempt 记录不一致", status_code=409)
    return attempt, path


def _build_episode_audio(inputs: P17Inputs, *, episode_id: str, episode_duration_us: int, workdir: Path) -> tuple[Path, list]:
    audio_by_id = {clip.utterance_id: clip for clip in inputs.target_audio.clips}
    script_by_id = {line.utterance_id: line for episode in inputs.target_script.episodes for line in episode.dialogue}
    timings = sorted(
        (item for item in inputs.timing.items if item.episode_id == episode_id),
        key=lambda item: (item.planned_speech_start_us, item.utterance_number),
    )
    for item in timings:
        if item.planned_speech_end_us > episode_duration_us:
            raise AppError("P17_DIALOGUE_OUTSIDE_EPISODE", "Target dialogue timing 超出最终 Episode production timeline", status_code=409)
    base = workdir / "dialogue-0000.wav"
    create_silence_audio(base, episode_duration_us)
    current = base
    for index, item in enumerate(timings, start=1):
        clip = audio_by_id[item.utterance_id]
        if clip.episode_id != episode_id:
            raise AppError("P17_AUDIO_EPISODE_MISMATCH", "TARGET_AUDIO clip Episode 与 TIMING_PLAN 不一致", status_code=409)
        media = resolve_target_audio_media_path(inputs.project.id, inputs.target_audio_task_id, clip.clip_id)
        if sha256_file(media) != clip.media_sha256:
            raise AppError("P17_AUDIO_MEDIA_HASH_MISMATCH", "正式 Target Audio 媒体 SHA256 已变化", status_code=409)
        output = workdir / f"dialogue-{index:04d}.wav"
        overlay_audio(current, media, output, item.planned_speech_start_us)
        if current != base:
            current.unlink(missing_ok=True)
        current = output
    final_audio = workdir / "formal-dialogue.wav"
    if current == base:
        base.replace(final_audio)
    else:
        base.unlink(missing_ok=True)
        current.replace(final_audio)
    subtitle_rows = [
        (
            item.utterance_number,
            item.planned_speech_start_us,
            item.planned_speech_end_us,
            script_by_id[item.utterance_id].final_target_dialogue,
        )
        for item in timings
    ]
    return final_audio, subtitle_rows


def _lip_sync_segment(
    db: Session,
    *,
    task: TaskWorkerRead,
    inputs: P17Inputs,
    provider: LocalHttpLipSyncProvider,
    clip,
    video_path: Path,
    audio_path: Path,
    output_path: Path,
    width: int,
    height: int,
) -> str:
    payload = {
        "contract": "local-http-lip-sync-v1",
        "generation_segment_id": clip.generation_segment_id,
        "selected_attempt_id": clip.selected_attempt_id,
        "selected_video_sha256": sha256_file(video_path),
        "segment_audio_sha256": sha256_file(audio_path),
        "planned_duration_us": clip.planned_duration_us,
        "model": provider.model_name,
    }

    def remote_call(job: ProviderJob) -> ProviderDispatchResult:
        result = provider.run(video_path=video_path, audio_path=audio_path, segment_id=clip.generation_segment_id)
        raw = output_path.with_suffix(".provider")
        raw.write_bytes(result.output_bytes)
        probe_video(raw)
        return ProviderDispatchResult(
            value={"storage_filename": raw.name, "mime_type": result.mime_type},
            remote_job_id=result.remote_job_id,
            completed=True,
        )

    job, dispatched = dispatch_provider_call(
        db,
        task_id=task.id,
        provider=provider.provider_name,
        model=provider.model_name,
        capability=Capability.LIP_SYNC,
        payload=payload,
        artifact_id=inputs.selection_artifact.id,
        remote_call=remote_call,
    )
    raw_path = output_path.with_suffix(".provider")
    if not raw_path.is_file() or str((dispatched.value or {}).get("storage_filename")) != raw_path.name:
        raise AppError("P17_LIP_SYNC_MEDIA_MISSING", "Lip Sync ProviderJob 成功但本地媒体缺失", status_code=502)
    normalize_video(raw_path, output_path, duration_us=clip.planned_duration_us, width=width, height=height)
    raw_path.unlink(missing_ok=True)
    return job.id


def _media_url(project_id: str, task_id: str, episode_id: str, kind: str) -> str:
    return f"/api/v3/projects/{project_id}/final-output/media/{task_id}/{episode_id}/{kind}"


def _build_episode(
    factory: sessionmaker[Session],
    *,
    task: TaskWorkerRead,
    inputs: P17Inputs,
    provider: LocalHttpLipSyncProvider | None,
    episode_id: str,
    episode_order: int,
    clips: list,
) -> tuple[FinalEpisodeOutput, list[str]]:
    root = storage_dir(task.project_id, task.id)
    workdir = root / f"work-{episode_order:04d}-{episode_key(episode_id)}"
    workdir.mkdir(parents=True, exist_ok=True)
    episode_duration_us = clips[-1].planned_end_us
    formal_audio, subtitle_rows = _build_episode_audio(inputs, episode_id=episode_id, episode_duration_us=episode_duration_us, workdir=workdir)
    subtitle_filename = f"episode-{episode_order:04d}-{episode_key(episode_id)}.srt"
    subtitle_path = root / subtitle_filename
    write_srt(subtitle_path, subtitle_rows)

    width = clips[0].width
    height = clips[0].height
    normalized_paths: list[Path] = []
    provider_job_ids: list[str] = []
    lip_synced_count = 0
    for clip in clips:
        with factory() as db:
            fresh_inputs = load_inputs(db, get_project(db, task.project_id))
            if input_artifact_ids(fresh_inputs) != task.input_artifact_ids_json:
                raise AppError("STALE_ARTIFACT_INPUT", "P17 输入在后期过程中发生变化", status_code=409)
            _attempt, selected_path = _validated_attempt(db, fresh_inputs, clip)
        base_path = workdir / f"segment-{clip.segment_number:04d}-base.mp4"
        normalize_video(selected_path, base_path, duration_us=clip.planned_duration_us, width=width, height=height)
        final_segment = workdir / f"segment-{clip.segment_number:04d}-final.mp4"
        if clip.requires_lip_sync:
            if provider is None:
                raise AppError("P17_LIP_SYNC_NOT_CONFIGURED", "存在需要口型同步的正式 segment，但 Lip Sync Runtime 未配置", status_code=409)
            segment_audio = workdir / f"segment-{clip.segment_number:04d}.wav"
            extract_audio_window(formal_audio, segment_audio, clip.planned_start_us, clip.planned_duration_us)
            with factory() as db:
                provider_job_ids.append(
                    _lip_sync_segment(
                        db,
                        task=task,
                        inputs=load_inputs(db, get_project(db, task.project_id)),
                        provider=provider,
                        clip=clip,
                        video_path=base_path,
                        audio_path=segment_audio,
                        output_path=final_segment,
                        width=width,
                        height=height,
                    )
                )
            lip_synced_count += 1
            base_path.unlink(missing_ok=True)
            segment_audio.unlink(missing_ok=True)
        else:
            base_path.replace(final_segment)
        normalized_paths.append(final_segment)

    video_only = workdir / "episode-video-only.mp4"
    concatenate_videos(normalized_paths, video_only)
    video_filename = f"episode-{episode_order:04d}-{episode_key(episode_id)}.mp4"
    video_path = root / video_filename
    mux_formal_audio(video_only, formal_audio, video_path, episode_duration_us)
    final_probe = probe_video(video_path)
    tolerance = final_duration_tolerance_us()
    if abs(final_probe.duration_us - episode_duration_us) > tolerance:
        raise AppError(
            "P17_FINAL_DURATION_MISMATCH",
            "最终 Episode 时长与 production timeline 超出容差",
            status_code=409,
            details={"episode_id": episode_id, "actual_duration_us": final_probe.duration_us, "planned_duration_us": episode_duration_us, "tolerance_us": tolerance},
        )
    output = FinalEpisodeOutput(
        episode_id=episode_id,
        episode_order=episode_order,
        video_url=_media_url(task.project_id, task.id, episode_id, "video"),
        video_sha256=sha256_file(video_path),
        duration_us=final_probe.duration_us,
        width=final_probe.width,
        height=final_probe.height,
        codec_name=final_probe.codec_name,
        subtitle_url=_media_url(task.project_id, task.id, episode_id, "subtitle"),
        subtitle_sha256=sha256_file(subtitle_path),
        lip_synced_segment_count=lip_synced_count,
        segment_count=len(clips),
    )
    sidecar = {
        "episode_id": episode_id,
        "video_filename": video_filename,
        "subtitle_filename": subtitle_filename,
        "video_sha256": output.video_sha256,
        "subtitle_sha256": output.subtitle_sha256,
    }
    episode_sidecar_path(task.project_id, task.id, episode_id).write_text(
        json.dumps(sidecar, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    return output, provider_job_ids


def _provenance(inputs: P17Inputs, *, sequence: int, task_id: str, provider_job_ids: list[str]) -> P17CandidateProvenance:
    skill = get_professional_skill("post-production")
    return P17CandidateProvenance(
        generation_selection_artifact_id=inputs.selection_artifact.id,
        generation_selection_revision=inputs.selection_artifact.revision,
        generation_selection_fingerprint=inputs.selection_artifact.input_fingerprint,
        target_audio_artifact_id=inputs.target_audio_artifact.id,
        target_audio_revision=inputs.target_audio_artifact.revision,
        target_audio_fingerprint=inputs.target_audio_artifact.input_fingerprint,
        target_script_artifact_id=inputs.target_script_artifact.id,
        target_script_revision=inputs.target_script_artifact.revision,
        target_script_fingerprint=inputs.target_script_artifact.input_fingerprint,
        timing_plan_artifact_id=inputs.timing_artifact.id,
        timing_plan_revision=inputs.timing_artifact.revision,
        timing_plan_fingerprint=inputs.timing_artifact.input_fingerprint,
        generation_sequence=sequence,
        professional_skill_version=skill.version,
        lip_sync_provider_job_ids=list(dict.fromkeys(provider_job_ids)),
        generated_by_task_id=task_id,
    )


def _persist_candidate(factory: sessionmaker[Session], task: TaskWorkerRead, content: ReplicaFinalOutputContent, provider_job_ids: list[str]) -> None:
    with factory() as db:
        inputs = load_inputs(db, get_project(db, task.project_id))
        if input_artifact_ids(inputs) != task.input_artifact_ids_json:
            raise AppError("STALE_ARTIFACT_INPUT", "P17 输入已变化，不能发布 Post candidate", status_code=409)
        sequence = int((task.checkpoint_json or {}).get("p17_generation_sequence") or 0)
        if sequence <= 0:
            raise AppError("P17_TASK_CHECKPOINT_INVALID", "P17 Task 缺少 generation sequence", status_code=500)
        for pending in db.scalars(
            select(ReplicaPostCandidate).where(
                ReplicaPostCandidate.project_id == task.project_id,
                ReplicaPostCandidate.review_status == PostReviewStatus.NEEDS_REVIEW.value,
            )
        ).all():
            pending.review_status = PostReviewStatus.SUPERSEDED.value
            pending.review_reason = "A newer final-output candidate was generated."
            pending.reviewed_at = utc_now()
            db.add(pending)
        db.add(
            ReplicaPostCandidate(
                project_id=task.project_id,
                generation_selection_artifact_id=inputs.selection_artifact.id,
                target_audio_artifact_id=inputs.target_audio_artifact.id,
                target_script_artifact_id=inputs.target_script_artifact.id,
                timing_plan_artifact_id=inputs.timing_artifact.id,
                generated_by_task_id=task.id,
                generation_sequence=sequence,
                input_fingerprint=task.input_fingerprint,
                schema_version=P17_SCHEMA_VERSION,
                content_json=content.model_dump(mode="json"),
                provenance_json=_provenance(inputs, sequence=sequence, task_id=task.id, provider_job_ids=provider_job_ids).model_dump(mode="json"),
                review_status=PostReviewStatus.NEEDS_REVIEW.value,
            )
        )
        db.commit()


def _mark_after_success_failed(factory: sessionmaker[Session], task_id: str, message: str) -> None:
    with factory() as db:
        task = db.get(Task, task_id)
        if task is None:
            return
        now = utc_now()
        task.status = TaskStatus.FAILED
        task.progress_percent = min(task.progress_percent, 99)
        task.last_error = message[:1000]
        task.finished_at = now
        task.updated_at = now
        db.add(task)
        db.commit()


def run_post_task(factory: sessionmaker[Session], task_id: str) -> None:
    worker_id = f"p17-post-{uuid4()}"
    with factory() as db:
        claimed = _claim(db, task_id, worker_id)
        if claimed is None:
            return
        snapshot = TaskWorkerRead.model_validate(claimed)
    try:
        with factory() as db:
            inputs = load_inputs(db, get_project(db, snapshot.project_id))
            sequence = int((snapshot.checkpoint_json or {}).get("p17_generation_sequence") or 0)
            provider = _provider(inputs)
            if snapshot.input_artifact_ids_json != input_artifact_ids(inputs) or snapshot.input_fingerprint != _fingerprint(inputs, sequence, provider):
                raise AppError("STALE_ARTIFACT_INPUT", "P17 输入或 Runtime 配置已变化，请重新创建任务", status_code=409)
            groups = _episode_groups(inputs)
        _checkpoint(factory, snapshot.id, worker_id, 5, stage="prepare_episode_post")
        episodes: list[FinalEpisodeOutput] = []
        provider_job_ids: list[str] = []
        for index, (episode_id, episode_order, clips) in enumerate(groups):
            with factory() as db:
                current_inputs = load_inputs(db, get_project(db, snapshot.project_id))
            output, jobs = _build_episode(
                factory,
                task=snapshot,
                inputs=current_inputs,
                provider=provider,
                episode_id=episode_id,
                episode_order=episode_order,
                clips=clips,
            )
            episodes.append(output)
            provider_job_ids.extend(jobs)
            _checkpoint(
                factory,
                snapshot.id,
                worker_id,
                min(95, 5 + int(((index + 1) / len(groups)) * 90)),
                stage="episode_post_complete",
                completed_episode_ids=[item.episode_id for item in episodes],
            )
        with factory() as db:
            final_inputs = load_inputs(db, get_project(db, snapshot.project_id))
        content = ReplicaFinalOutputContent(
            generation_selection_artifact_id=final_inputs.selection_artifact.id,
            target_audio_artifact_id=final_inputs.target_audio_artifact.id,
            target_script_artifact_id=final_inputs.target_script_artifact.id,
            timing_plan_artifact_id=final_inputs.timing_artifact.id,
            episodes=episodes,
        )
        with factory() as db:
            finished = mark_task_succeeded(db, snapshot.id, worker_id=worker_id)
        if finished.status == TaskStatus.CANCELLED:
            return
        try:
            _persist_candidate(factory, snapshot, content, provider_job_ids)
        except Exception as exc:
            message = f"P17 candidate 发布失败（{exc.code}）：{exc.message}" if isinstance(exc, AppError) else f"P17 candidate 发布失败（{type(exc).__name__}）"
            _mark_after_success_failed(factory, snapshot.id, message)
    except Exception as exc:
        message = f"P17 后期失败（{exc.code}）：{exc.message}" if isinstance(exc, AppError) else f"P17 后期失败（{type(exc).__name__}）"
        with factory() as db:
            task = db.get(Task, snapshot.id)
            if task is not None and task.status == TaskStatus.RUNNING and task.worker_id == worker_id:
                mark_task_failed(db, snapshot.id, safe_error=message, worker_id=worker_id)


def _candidate_read(row: ReplicaPostCandidate) -> PostCandidateRead:
    return PostCandidateRead(
        id=row.id,
        project_id=row.project_id,
        generation_sequence=row.generation_sequence,
        input_fingerprint=row.input_fingerprint,
        review_status=PostReviewStatus(row.review_status),
        review_reason=row.review_reason,
        reviewed_at=row.reviewed_at,
        created_at=row.created_at,
        content=ReplicaFinalOutputContent.model_validate(row.content_json),
        provenance=P17CandidateProvenance.model_validate(row.provenance_json),
    )


def list_post_candidates(db: Session, project_id: str) -> list[PostCandidateRead]:
    get_project(db, project_id)
    rows = list(
        db.scalars(
            select(ReplicaPostCandidate)
            .where(ReplicaPostCandidate.project_id == project_id)
            .order_by(ReplicaPostCandidate.generation_sequence.desc(), ReplicaPostCandidate.created_at.desc())
        ).all()
    )
    return [_candidate_read(row) for row in rows]
