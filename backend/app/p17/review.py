from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactEdge, ArtifactNode
from app.artifacts.service import _invalidate_project_plan, _mark_stale_with_downstream
from app.core.errors import AppError
from app.core.time import utc_now
from app.p17.common import input_artifact_ids, load_inputs, resolve_episode_media, sha
from app.p17.media import probe_video, sha256_file
from app.p17.models import ReplicaFinalOutputRevision, ReplicaPostCandidate
from app.p17.runtime import _candidate_read
from app.p17.schemas import (
    P17ArtifactProvenance,
    P17CandidateProvenance,
    P17ResultStatus,
    P17ReviewCommand,
    P17_SCHEMA_VERSION,
    PostCandidateRead,
    PostReviewStatus,
    ReplicaFinalOutputContent,
    ReplicaFinalOutputRead,
)
from app.projects.service import get_project
from app.skills.models import ArtifactType
from app.skills.professional import get_professional_skill


def _current_or_latest(db: Session, project_id: str) -> tuple[ArtifactNode | None, ArtifactNode | None]:
    current = db.scalar(
        select(ArtifactNode).where(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == ArtifactType.FINAL_OUTPUT.value,
            ArtifactNode.validity == ArtifactValidity.CURRENT,
            ArtifactNode.is_current.is_(True),
        )
    )
    latest = current or db.scalar(
        select(ArtifactNode)
        .where(ArtifactNode.project_id == project_id, ArtifactNode.artifact_type == ArtifactType.FINAL_OUTPUT.value)
        .order_by(ArtifactNode.revision.desc(), ArtifactNode.created_at.desc())
        .limit(1)
    )
    return current, latest


def get_final_output(db: Session, project_id: str) -> ReplicaFinalOutputRead:
    get_project(db, project_id)
    current, latest = _current_or_latest(db, project_id)
    if latest is None:
        return ReplicaFinalOutputRead(project_id=project_id, status=P17ResultStatus.NOT_BUILT)
    row = db.scalar(select(ReplicaFinalOutputRevision).where(ReplicaFinalOutputRevision.artifact_id == latest.id))
    if row is None:
        raise AppError("P17_FINAL_OUTPUT_CONTENT_MISSING", "FINAL_OUTPUT 缺少 typed revision", status_code=500)
    return ReplicaFinalOutputRead(
        project_id=project_id,
        status=P17ResultStatus.CURRENT if current is not None else P17ResultStatus.STALE,
        artifact_id=latest.id,
        revision=latest.revision,
        input_fingerprint=latest.input_fingerprint,
        content=ReplicaFinalOutputContent.model_validate(row.content_json),
        provenance=P17ArtifactProvenance.model_validate(row.provenance_json),
    )


def _review_context(db: Session, project_id: str, candidate_id: str, command: P17ReviewCommand):
    project = get_project(db, project_id)
    inputs = load_inputs(db, project)
    candidate = db.get(ReplicaPostCandidate, candidate_id)
    if candidate is None or candidate.project_id != project_id:
        raise AppError("P17_CANDIDATE_NOT_FOUND", "Post candidate 不存在", status_code=404)
    if candidate.review_status != PostReviewStatus.NEEDS_REVIEW.value:
        raise AppError("P17_CANDIDATE_NOT_REVIEWABLE", "Post candidate 已审核或失效", status_code=409)
    expected = [
        command.expected_generation_selection_artifact_id,
        command.expected_target_audio_artifact_id,
        command.expected_target_script_artifact_id,
        command.expected_timing_plan_artifact_id,
    ]
    if expected != input_artifact_ids(inputs) or candidate.generation_sequence != command.expected_generation_sequence:
        raise AppError("P17_REVIEW_INPUT_CHANGED", "P17 当前正式输入或 candidate sequence 已变化", status_code=409)
    candidate_ids = [
        candidate.generation_selection_artifact_id,
        candidate.target_audio_artifact_id,
        candidate.target_script_artifact_id,
        candidate.timing_plan_artifact_id,
    ]
    if candidate_ids != expected:
        raise AppError("P17_CANDIDATE_STALE", "Post candidate 不属于当前正式输入", status_code=409)
    return project, inputs, candidate


def _validate_candidate_media(candidate: ReplicaPostCandidate, content: ReplicaFinalOutputContent) -> None:
    if not candidate.generated_by_task_id:
        raise AppError("P17_MEDIA_LINEAGE_MISSING", "Post candidate 缺少生成 Task lineage", status_code=409)
    for episode in content.episodes:
        video = resolve_episode_media(candidate.project_id, candidate.generated_by_task_id, episode.episode_id, "video")
        subtitle = resolve_episode_media(candidate.project_id, candidate.generated_by_task_id, episode.episode_id, "subtitle")
        if sha256_file(video) != episode.video_sha256:
            raise AppError("P17_VIDEO_HASH_MISMATCH", "最终 Episode 视频 SHA256 已变化", status_code=409, details={"episode_id": episode.episode_id})
        if sha256_file(subtitle) != episode.subtitle_sha256:
            raise AppError("P17_SUBTITLE_HASH_MISMATCH", "最终 Episode 字幕 SHA256 已变化", status_code=409, details={"episode_id": episode.episode_id})
        probe = probe_video(video)
        if probe.duration_us != episode.duration_us or probe.width != episode.width or probe.height != episode.height or probe.codec_name != episode.codec_name:
            raise AppError("P17_FINAL_MEDIA_PROBE_CHANGED", "最终 Episode 视频重新 ffprobe 与 candidate 记录不一致", status_code=409)


def reject_post_candidate(db: Session, *, project_id: str, candidate_id: str, command: P17ReviewCommand) -> PostCandidateRead:
    _project, _inputs, candidate = _review_context(db, project_id, candidate_id, command)
    candidate.review_status = PostReviewStatus.REJECTED.value
    candidate.review_reason = command.reason
    candidate.reviewed_at = utc_now()
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return _candidate_read(candidate)


def _next_revision(db: Session, project_id: str) -> int:
    latest = db.scalar(select(func.max(ArtifactNode.revision)).where(ArtifactNode.project_id == project_id, ArtifactNode.artifact_type == ArtifactType.FINAL_OUTPUT.value))
    return int(latest or 0) + 1


def accept_post_candidate(db: Session, *, project_id: str, candidate_id: str, command: P17ReviewCommand) -> ReplicaFinalOutputRead:
    project, inputs, candidate = _review_context(db, project_id, candidate_id, command)
    content = ReplicaFinalOutputContent.model_validate(candidate.content_json)
    if [
        content.generation_selection_artifact_id,
        content.target_audio_artifact_id,
        content.target_script_artifact_id,
        content.timing_plan_artifact_id,
    ] != input_artifact_ids(inputs):
        raise AppError("P17_CANDIDATE_CONTENT_STALE", "Post candidate content lineage 与当前正式输入不一致", status_code=409)
    _validate_candidate_media(candidate, content)

    previous_current, previous_latest = _current_or_latest(db, project_id)
    reviewed_at = utc_now()
    base = P17CandidateProvenance.model_validate(candidate.provenance_json)
    provenance = P17ArtifactProvenance(
        **base.model_dump(),
        candidate_id=candidate.id,
        reviewed_at=reviewed_at,
        review_reason=command.reason,
        supersedes_artifact_id=previous_latest.id if previous_latest is not None else None,
    )
    skill = get_professional_skill("post-production")
    artifact = ArtifactNode(
        project_id=project_id,
        artifact_type=ArtifactType.FINAL_OUTPUT.value,
        namespace=ArtifactNamespace.PRODUCTION,
        label="复刻最终成片",
        revision=_next_revision(db, project_id),
        input_fingerprint=sha({"candidate_id": candidate.id, "content": content.model_dump(mode="json")}),
        skill_id=skill.id,
        skill_version=skill.version,
        validity=ArtifactValidity.CURRENT,
        is_current=True,
        metadata_json={"schema_version": P17_SCHEMA_VERSION, "episode_count": len(content.episodes), "candidate_id": candidate.id},
    )
    try:
        if previous_current is not None:
            _mark_stale_with_downstream(db, [previous_current])
        db.add(artifact)
        db.flush()
        db.add(
            ReplicaFinalOutputRevision(
                project_id=project_id,
                artifact_id=artifact.id,
                generation_selection_artifact_id=inputs.selection_artifact.id,
                target_audio_artifact_id=inputs.target_audio_artifact.id,
                target_script_artifact_id=inputs.target_script_artifact.id,
                timing_plan_artifact_id=inputs.timing_artifact.id,
                candidate_id=candidate.id,
                generated_by_task_id=candidate.generated_by_task_id,
                schema_version=P17_SCHEMA_VERSION,
                content_json=content.model_dump(mode="json"),
                provenance_json=provenance.model_dump(mode="json"),
            )
        )
        db.add(ArtifactEdge(project_id=project_id, source_node_id=inputs.selection_artifact.id, target_node_id=artifact.id, relation_type=ArtifactRelationType.DERIVED_FROM))
        db.add(ArtifactEdge(project_id=project_id, source_node_id=inputs.target_audio_artifact.id, target_node_id=artifact.id, relation_type=ArtifactRelationType.USES))
        db.add(ArtifactEdge(project_id=project_id, source_node_id=inputs.target_script_artifact.id, target_node_id=artifact.id, relation_type=ArtifactRelationType.USES))
        db.add(ArtifactEdge(project_id=project_id, source_node_id=inputs.timing_artifact.id, target_node_id=artifact.id, relation_type=ArtifactRelationType.USES))
        if previous_latest is not None:
            db.add(ArtifactEdge(project_id=project_id, source_node_id=artifact.id, target_node_id=previous_latest.id, relation_type=ArtifactRelationType.SUPERSEDES))
        candidate.review_status = PostReviewStatus.ACCEPTED.value
        candidate.review_reason = command.reason
        candidate.reviewed_at = reviewed_at
        db.add(candidate)
        for other in db.scalars(
            select(ReplicaPostCandidate).where(
                ReplicaPostCandidate.project_id == project_id,
                ReplicaPostCandidate.id != candidate.id,
                ReplicaPostCandidate.review_status == PostReviewStatus.NEEDS_REVIEW.value,
            )
        ).all():
            other.review_status = PostReviewStatus.SUPERSEDED.value
            other.review_reason = "Another final-output candidate was accepted."
            other.reviewed_at = reviewed_at
            db.add(other)
        _invalidate_project_plan(db, project)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return get_final_output(db, project_id)
