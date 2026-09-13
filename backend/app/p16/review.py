from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactEdge, ArtifactNode
from app.artifacts.service import _invalidate_project_plan, _mark_stale_with_downstream
from app.core.errors import AppError
from app.core.time import utc_now
from app.p16.common import attempt_media_path, input_artifact_ids, load_inputs, sha
from app.p16.media import probe_video, sha256_file
from app.p16.models import (
    ReplicaGeneratedVideoRevision,
    ReplicaGenerationAttempt,
    ReplicaGenerationSelectionCandidate,
    ReplicaGenerationSelectionRevision,
)
from app.p16.runtime import _candidate_read
from app.p16.schemas import (
    GenerationSelectionItem,
    P16ArtifactProvenance,
    P16CandidateProvenance,
    P16ResultStatus,
    P16ReviewCommand,
    P16SelectionCandidateRead,
    P16SelectionCandidateContent,
    P16_SCHEMA_VERSION,
    ReplicaGeneratedVideoContent,
    ReplicaGeneratedVideoRead,
    ReplicaGenerationSelectionContent,
    ReplicaGenerationSelectionRead,
    SelectionReviewStatus,
    TechnicalQcStatus,
)
from app.projects.service import get_project
from app.skills.models import ArtifactType
from app.skills.professional import get_professional_skill


def _current_or_latest(db: Session, project_id: str, artifact_type: ArtifactType) -> tuple[ArtifactNode | None, ArtifactNode | None]:
    current = db.scalar(
        select(ArtifactNode).where(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == artifact_type.value,
            ArtifactNode.validity == ArtifactValidity.CURRENT,
            ArtifactNode.is_current.is_(True),
        )
    )
    latest = current or db.scalar(
        select(ArtifactNode)
        .where(ArtifactNode.project_id == project_id, ArtifactNode.artifact_type == artifact_type.value)
        .order_by(ArtifactNode.revision.desc(), ArtifactNode.created_at.desc())
        .limit(1)
    )
    return current, latest


def get_generated_video(db: Session, project_id: str) -> ReplicaGeneratedVideoRead:
    get_project(db, project_id)
    current, latest = _current_or_latest(db, project_id, ArtifactType.GENERATED_VIDEO)
    if latest is None:
        return ReplicaGeneratedVideoRead(project_id=project_id, status=P16ResultStatus.NOT_BUILT)
    row = db.scalar(select(ReplicaGeneratedVideoRevision).where(ReplicaGeneratedVideoRevision.artifact_id == latest.id))
    if row is None:
        raise AppError("P16_GENERATED_VIDEO_CONTENT_MISSING", "GENERATED_VIDEO 缺少 typed revision", status_code=500)
    return ReplicaGeneratedVideoRead(
        project_id=project_id,
        status=P16ResultStatus.CURRENT if current is not None else P16ResultStatus.STALE,
        artifact_id=latest.id,
        revision=latest.revision,
        input_fingerprint=latest.input_fingerprint,
        content=ReplicaGeneratedVideoContent.model_validate(row.content_json),
        provenance=P16ArtifactProvenance.model_validate(row.provenance_json),
    )


def get_generation_selection(db: Session, project_id: str) -> ReplicaGenerationSelectionRead:
    get_project(db, project_id)
    current, latest = _current_or_latest(db, project_id, ArtifactType.GENERATION_SELECTION)
    if latest is None:
        return ReplicaGenerationSelectionRead(project_id=project_id, status=P16ResultStatus.NOT_BUILT)
    row = db.scalar(
        select(ReplicaGenerationSelectionRevision).where(ReplicaGenerationSelectionRevision.artifact_id == latest.id)
    )
    if row is None:
        raise AppError("P16_SELECTION_CONTENT_MISSING", "GENERATION_SELECTION 缺少 typed revision", status_code=500)
    return ReplicaGenerationSelectionRead(
        project_id=project_id,
        status=P16ResultStatus.CURRENT if current is not None else P16ResultStatus.STALE,
        artifact_id=latest.id,
        revision=latest.revision,
        input_fingerprint=latest.input_fingerprint,
        content=ReplicaGenerationSelectionContent.model_validate(row.content_json),
        provenance=P16ArtifactProvenance.model_validate(row.provenance_json),
    )


def _review_context(db: Session, project_id: str, candidate_id: str, command: P16ReviewCommand):
    project = get_project(db, project_id)
    inputs = load_inputs(db, project)
    candidate = db.get(ReplicaGenerationSelectionCandidate, candidate_id)
    if candidate is None or candidate.project_id != project_id:
        raise AppError("P16_SELECTION_CANDIDATE_NOT_FOUND", "视频 Selection candidate 不存在", status_code=404)
    if candidate.review_status != SelectionReviewStatus.NEEDS_REVIEW.value:
        raise AppError("P16_SELECTION_CANDIDATE_NOT_REVIEWABLE", "视频 Selection candidate 已审核或失效", status_code=409)
    expected = [
        command.expected_target_storyboard_artifact_id,
        command.expected_generation_segments_artifact_id,
        command.expected_target_assets_artifact_id,
    ]
    if expected != input_artifact_ids(inputs) or candidate.generation_sequence != command.expected_generation_sequence:
        raise AppError("P16_REVIEW_INPUT_CHANGED", "P16 当前正式输入或 candidate sequence 已变化", status_code=409)
    if [candidate.target_storyboard_artifact_id, candidate.generation_segments_artifact_id, candidate.target_assets_artifact_id] != expected:
        raise AppError("P16_SELECTION_CANDIDATE_STALE", "Selection candidate 不属于当前正式生产输入", status_code=409)
    return project, inputs, candidate


def reject_selection_candidate(db: Session, *, project_id: str, candidate_id: str, command: P16ReviewCommand) -> P16SelectionCandidateRead:
    _project, _inputs, candidate = _review_context(db, project_id, candidate_id, command)
    candidate.review_status = SelectionReviewStatus.REJECTED.value
    candidate.review_reason = command.reason
    candidate.reviewed_at = utc_now()
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return _candidate_read(candidate)


def _next_revision(db: Session, project_id: str, artifact_type: ArtifactType) -> int:
    latest = db.scalar(
        select(func.max(ArtifactNode.revision)).where(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == artifact_type.value,
        )
    )
    return int(latest or 0) + 1


def _artifact_provenance(candidate: ReplicaGenerationSelectionCandidate, *, reviewed_at, reason: str, supersedes: str | None) -> P16ArtifactProvenance:
    base = P16CandidateProvenance.model_validate(candidate.provenance_json)
    return P16ArtifactProvenance(
        **base.model_dump(),
        selection_candidate_id=candidate.id,
        reviewed_at=reviewed_at,
        review_reason=reason,
        supersedes_artifact_id=supersedes,
    )


def accept_selection_candidate(db: Session, *, project_id: str, candidate_id: str, command: P16ReviewCommand) -> ReplicaGenerationSelectionRead:
    project, inputs, candidate = _review_context(db, project_id, candidate_id, command)
    candidate_content = P16SelectionCandidateContent.model_validate(candidate.content_json)
    expected_segments = {item.generation_segment_id for item in inputs.segments.segments}
    if {item.generation_segment_id for item in candidate_content.clips} != expected_segments:
        raise AppError("P16_SELECTION_COVERAGE_INVALID", "Selection candidate 没有完整覆盖全部 GenerationSegment", status_code=409)

    for clip in candidate_content.clips:
        attempt = db.get(ReplicaGenerationAttempt, clip.selected_attempt_id)
        if attempt is None or attempt.project_id != project_id:
            raise AppError("P16_SELECTED_ATTEMPT_MISSING", "选中的 GenerationAttempt 不存在", status_code=409)
        if attempt.technical_qc_status != TechnicalQcStatus.PASS.value:
            raise AppError("P16_SELECTED_ATTEMPT_QC_FAILED", "只有 Technical QC PASS 的 attempt 才能正式入选", status_code=409)
        if attempt.generation_segments_artifact_id != inputs.segments_artifact.id:
            raise AppError("P16_SELECTED_ATTEMPT_STALE", "选中的 GenerationAttempt 不属于 CURRENT GENERATION_SEGMENTS", status_code=409)
        path = attempt_media_path(attempt)
        if sha256_file(path) != attempt.media_sha256:
            raise AppError("P16_SELECTED_MEDIA_HASH_MISMATCH", "选中的视频媒体 SHA256 已变化", status_code=409)
        probe = probe_video(path)
        if probe.duration_us != attempt.actual_duration_us or probe.width != attempt.width or probe.height != attempt.height or probe.codec_name != attempt.codec_name:
            raise AppError("P16_SELECTED_MEDIA_PROBE_CHANGED", "选中的视频媒体重新 ffprobe 与 Attempt 记录不一致", status_code=409)

    previous_video_current, previous_video = _current_or_latest(db, project_id, ArtifactType.GENERATED_VIDEO)
    previous_selection_current, previous_selection = _current_or_latest(db, project_id, ArtifactType.GENERATION_SELECTION)
    skill = get_professional_skill("video-generation-qc")
    reviewed_at = utc_now()
    generated_content = ReplicaGeneratedVideoContent(
        target_storyboard_artifact_id=inputs.storyboard_artifact.id,
        generation_segments_artifact_id=inputs.segments_artifact.id,
        target_assets_artifact_id=inputs.assets_artifact.id,
        clips=candidate_content.clips,
    )
    video_artifact = ArtifactNode(
        project_id=project_id,
        artifact_type=ArtifactType.GENERATED_VIDEO.value,
        namespace=ArtifactNamespace.PRODUCTION,
        label="正式生成视频片段",
        revision=_next_revision(db, project_id, ArtifactType.GENERATED_VIDEO),
        input_fingerprint=sha({"candidate_id": candidate.id, "content": generated_content.model_dump(mode="json")}),
        skill_id=skill.id,
        skill_version=skill.version,
        validity=ArtifactValidity.CURRENT,
        is_current=True,
        metadata_json={"schema_version": P16_SCHEMA_VERSION, "clip_count": len(generated_content.clips), "selection_candidate_id": candidate.id},
    )
    try:
        roots = [item for item in (previous_video_current, previous_selection_current) if item is not None]
        if roots:
            _mark_stale_with_downstream(db, roots)
        db.add(video_artifact)
        db.flush()
        selection_content = ReplicaGenerationSelectionContent(
            target_storyboard_artifact_id=inputs.storyboard_artifact.id,
            generation_segments_artifact_id=inputs.segments_artifact.id,
            target_assets_artifact_id=inputs.assets_artifact.id,
            generated_video_artifact_id=video_artifact.id,
            selections=[
                GenerationSelectionItem(
                    generation_segment_id=clip.generation_segment_id,
                    selected_attempt_id=clip.selected_attempt_id,
                )
                for clip in generated_content.clips
            ],
        )
        selection_artifact = ArtifactNode(
            project_id=project_id,
            artifact_type=ArtifactType.GENERATION_SELECTION.value,
            namespace=ArtifactNamespace.PRODUCTION,
            label="视频生成正式选片",
            revision=_next_revision(db, project_id, ArtifactType.GENERATION_SELECTION),
            input_fingerprint=sha({"generated_video_artifact_id": video_artifact.id, "content": selection_content.model_dump(mode="json")}),
            skill_id=skill.id,
            skill_version=skill.version,
            validity=ArtifactValidity.CURRENT,
            is_current=True,
            metadata_json={"schema_version": P16_SCHEMA_VERSION, "selection_count": len(selection_content.selections), "selection_candidate_id": candidate.id},
        )
        db.add(selection_artifact)
        db.flush()
        video_prov = _artifact_provenance(candidate, reviewed_at=reviewed_at, reason=command.reason, supersedes=previous_video.id if previous_video else None)
        selection_prov = _artifact_provenance(candidate, reviewed_at=reviewed_at, reason=command.reason, supersedes=previous_selection.id if previous_selection else None)
        db.add(
            ReplicaGeneratedVideoRevision(
                project_id=project_id,
                artifact_id=video_artifact.id,
                selection_candidate_id=candidate.id,
                generated_by_task_id=candidate.generated_by_task_id,
                schema_version=P16_SCHEMA_VERSION,
                content_json=generated_content.model_dump(mode="json"),
                provenance_json=video_prov.model_dump(mode="json"),
            )
        )
        db.add(
            ReplicaGenerationSelectionRevision(
                project_id=project_id,
                artifact_id=selection_artifact.id,
                generated_video_artifact_id=video_artifact.id,
                selection_candidate_id=candidate.id,
                generated_by_task_id=candidate.generated_by_task_id,
                schema_version=P16_SCHEMA_VERSION,
                content_json=selection_content.model_dump(mode="json"),
                provenance_json=selection_prov.model_dump(mode="json"),
            )
        )
        db.add(ArtifactEdge(project_id=project_id, source_node_id=inputs.segments_artifact.id, target_node_id=video_artifact.id, relation_type=ArtifactRelationType.DERIVED_FROM))
        db.add(ArtifactEdge(project_id=project_id, source_node_id=inputs.storyboard_artifact.id, target_node_id=video_artifact.id, relation_type=ArtifactRelationType.USES))
        db.add(ArtifactEdge(project_id=project_id, source_node_id=inputs.assets_artifact.id, target_node_id=video_artifact.id, relation_type=ArtifactRelationType.USES))
        db.add(ArtifactEdge(project_id=project_id, source_node_id=video_artifact.id, target_node_id=selection_artifact.id, relation_type=ArtifactRelationType.DERIVED_FROM))
        db.add(ArtifactEdge(project_id=project_id, source_node_id=inputs.storyboard_artifact.id, target_node_id=selection_artifact.id, relation_type=ArtifactRelationType.USES))
        db.add(ArtifactEdge(project_id=project_id, source_node_id=inputs.segments_artifact.id, target_node_id=selection_artifact.id, relation_type=ArtifactRelationType.USES))
        if previous_video is not None:
            db.add(ArtifactEdge(project_id=project_id, source_node_id=video_artifact.id, target_node_id=previous_video.id, relation_type=ArtifactRelationType.SUPERSEDES))
        if previous_selection is not None:
            db.add(ArtifactEdge(project_id=project_id, source_node_id=selection_artifact.id, target_node_id=previous_selection.id, relation_type=ArtifactRelationType.SUPERSEDES))
        candidate.review_status = SelectionReviewStatus.ACCEPTED.value
        candidate.review_reason = command.reason
        candidate.reviewed_at = reviewed_at
        db.add(candidate)
        for other in db.scalars(
            select(ReplicaGenerationSelectionCandidate).where(
                ReplicaGenerationSelectionCandidate.project_id == project_id,
                ReplicaGenerationSelectionCandidate.id != candidate.id,
                ReplicaGenerationSelectionCandidate.review_status == SelectionReviewStatus.NEEDS_REVIEW.value,
            )
        ).all():
            other.review_status = SelectionReviewStatus.SUPERSEDED.value
            other.review_reason = "Another selection candidate was accepted."
            other.reviewed_at = reviewed_at
            db.add(other)
        _invalidate_project_plan(db, project)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return get_generation_selection(db, project_id)
