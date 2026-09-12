import hashlib
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactEdge, ArtifactNode
from app.artifacts.service import _invalidate_project_plan, _mark_stale_with_downstream
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.time import utc_now
from app.p14.audio_contract import _load_target_audio_inputs
from app.p14.common import _assert_replica, _current_artifact, _latest_artifact, _next_artifact_revision, _sha
from app.p14.models import ReplicaTargetAudioCandidate, ReplicaTargetAudioRevision, ReplicaTimingPlanCandidate
from app.p14.schemas import P14_AUDIO_SCHEMA_VERSION, P14_AUDIO_SKILL_ID, P14ResultStatus, CandidateReviewStatus, ReplicaTargetAudioContent, ReplicaTargetAudioRead, TargetAudioCandidateProvenance, TargetAudioCandidateRead, TargetAudioProvenance, TargetAudioReviewCommand
from app.projects.service import get_project
from app.skills.models import ArtifactType
from app.skills.professional import get_professional_skill


def _audio_candidate_read(row: ReplicaTargetAudioCandidate) -> TargetAudioCandidateRead:
    return TargetAudioCandidateRead(
        id=row.id,
        project_id=row.project_id,
        target_script_artifact_id=row.target_script_artifact_id,
        target_bible_artifact_id=row.target_bible_artifact_id,
        generated_by_task_id=row.generated_by_task_id,
        generation_sequence=row.generation_sequence,
        input_fingerprint=row.input_fingerprint,
        review_status=CandidateReviewStatus(row.review_status),
        review_reason=row.review_reason,
        reviewed_at=row.reviewed_at.isoformat() if row.reviewed_at else None,
        created_at=row.created_at.isoformat(),
        content=ReplicaTargetAudioContent.model_validate(row.content_json),
        provenance=TargetAudioCandidateProvenance.model_validate(row.provenance_json),
    )


def list_target_audio_candidates(db: Session, project_id: str) -> list[TargetAudioCandidateRead]:
    project = get_project(db, project_id)
    _assert_replica(project)
    rows = db.scalars(
        select(ReplicaTargetAudioCandidate)
        .where(ReplicaTargetAudioCandidate.project_id == project_id)
        .order_by(ReplicaTargetAudioCandidate.created_at.desc(), ReplicaTargetAudioCandidate.generation_sequence.desc())
    ).all()
    return [_audio_candidate_read(row) for row in rows]


def get_target_audio(db: Session, project_id: str) -> ReplicaTargetAudioRead:
    project = get_project(db, project_id)
    _assert_replica(project)
    current = _current_artifact(db, project_id, ArtifactType.TARGET_AUDIO)
    latest = current or _latest_artifact(db, project_id, ArtifactType.TARGET_AUDIO)
    if latest is None:
        return ReplicaTargetAudioRead(project_id=project_id, status=P14ResultStatus.NOT_BUILT)
    row = db.scalar(select(ReplicaTargetAudioRevision).where(ReplicaTargetAudioRevision.artifact_id == latest.id))
    if row is None:
        raise AppError("P14_TARGET_AUDIO_CONTENT_MISSING", "TARGET_AUDIO 缺少 typed revision", status_code=500)
    return ReplicaTargetAudioRead(
        project_id=project_id,
        status=P14ResultStatus.CURRENT if current else P14ResultStatus.STALE,
        artifact_id=latest.id,
        revision=latest.revision,
        input_fingerprint=latest.input_fingerprint,
        content=ReplicaTargetAudioContent.model_validate(row.content_json),
        provenance=TargetAudioProvenance.model_validate(row.provenance_json),
    )


def reject_target_audio_candidate(
    db: Session, *, project_id: str, candidate_id: str, command: TargetAudioReviewCommand
) -> TargetAudioCandidateRead:
    project, script_artifact, _script, bible_artifact, _bible = _load_target_audio_inputs(db, project_id)
    candidate = db.get(ReplicaTargetAudioCandidate, candidate_id)
    if candidate is None or candidate.project_id != project.id:
        raise AppError("P14_AUDIO_CANDIDATE_NOT_FOUND", "目标配音候选不存在", status_code=404)
    _validate_audio_review(candidate, script_artifact, bible_artifact, command)
    candidate.review_status = CandidateReviewStatus.REJECTED.value
    candidate.review_reason = command.reason.strip()
    candidate.reviewed_at = utc_now()
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return _audio_candidate_read(candidate)


def _validate_audio_review(
    candidate: ReplicaTargetAudioCandidate,
    script_artifact: ArtifactNode,
    bible_artifact: ArtifactNode,
    command: TargetAudioReviewCommand,
) -> None:
    if candidate.review_status != CandidateReviewStatus.NEEDS_REVIEW.value:
        raise AppError("P14_AUDIO_CANDIDATE_NOT_REVIEWABLE", "目标配音候选当前状态不能再次审核", status_code=409)
    if command.expected_target_script_artifact_id != script_artifact.id or candidate.target_script_artifact_id != script_artifact.id:
        raise AppError("P14_AUDIO_SCRIPT_CHANGED", "Target Script 已变化，请重新生成目标配音", status_code=409)
    if command.expected_target_bible_artifact_id != bible_artifact.id or candidate.target_bible_artifact_id != bible_artifact.id:
        raise AppError("P14_AUDIO_BIBLE_CHANGED", "Target Bible 已变化，请重新生成目标配音", status_code=409)
    if command.expected_generation_sequence != candidate.generation_sequence:
        raise AppError("P14_AUDIO_CANDIDATE_CHANGED", "目标配音候选生成序列已变化", status_code=409)


def _assert_candidate_media(candidate: ReplicaTargetAudioCandidate, content: ReplicaTargetAudioContent) -> None:
    if not candidate.generated_by_task_id:
        raise AppError("P14_AUDIO_MEDIA_LINEAGE_MISSING", "目标配音候选缺少生成 Task lineage", status_code=409)
    for clip in content.clips:
        path = resolve_target_audio_media_path(candidate.project_id, candidate.generated_by_task_id, clip.clip_id)
        if hashlib.sha256(path.read_bytes()).hexdigest() != clip.media_sha256:
            raise AppError(
                "P14_AUDIO_MEDIA_HASH_MISMATCH",
                "目标配音媒体与候选 hash 不一致，禁止发布",
                status_code=409,
                details={"utterance_id": clip.utterance_id},
            )


def accept_target_audio_candidate(
    db: Session, *, project_id: str, candidate_id: str, command: TargetAudioReviewCommand
) -> ReplicaTargetAudioRead:
    project, script_artifact, _script, bible_artifact, _bible = _load_target_audio_inputs(db, project_id)
    candidate = db.get(ReplicaTargetAudioCandidate, candidate_id)
    if candidate is None or candidate.project_id != project.id:
        raise AppError("P14_AUDIO_CANDIDATE_NOT_FOUND", "目标配音候选不存在", status_code=404)
    _validate_audio_review(candidate, script_artifact, bible_artifact, command)
    content = ReplicaTargetAudioContent.model_validate(candidate.content_json)
    _assert_candidate_media(candidate, content)
    candidate_provenance = TargetAudioCandidateProvenance.model_validate(candidate.provenance_json)
    previous_current = _current_artifact(db, project_id, ArtifactType.TARGET_AUDIO)
    previous_latest = _latest_artifact(db, project_id, ArtifactType.TARGET_AUDIO)
    if previous_current is not None:
        _mark_stale_with_downstream(db, [previous_current])
    fingerprint = _sha({"candidate_id": candidate.id, "content": content.model_dump(mode="json")})
    skill = get_professional_skill(P14_AUDIO_SKILL_ID)
    artifact = ArtifactNode(
        project_id=project_id,
        artifact_type=ArtifactType.TARGET_AUDIO.value,
        namespace=ArtifactNamespace.PRODUCTION,
        label="目标配音",
        revision=_next_artifact_revision(db, project_id, ArtifactType.TARGET_AUDIO),
        input_fingerprint=fingerprint,
        skill_id=skill.id,
        skill_version=skill.version,
        validity=ArtifactValidity.CURRENT,
        is_current=True,
        metadata_json={"schema_version": P14_AUDIO_SCHEMA_VERSION, "clip_count": len(content.clips)},
    )
    reviewed_at = utc_now()
    provenance = TargetAudioProvenance(
        **candidate_provenance.model_dump(),
        candidate_id=candidate.id,
        reviewed_at=reviewed_at.isoformat(),
        review_reason=command.reason.strip(),
        supersedes_artifact_id=previous_latest.id if previous_latest else None,
    )
    try:
        db.add(artifact)
        db.flush()
        db.add(
            ReplicaTargetAudioRevision(
                project_id=project_id,
                artifact_id=artifact.id,
                target_script_artifact_id=script_artifact.id,
                target_bible_artifact_id=bible_artifact.id,
                candidate_id=candidate.id,
                generated_by_task_id=candidate.generated_by_task_id,
                schema_version=P14_AUDIO_SCHEMA_VERSION,
                content_json=content.model_dump(mode="json"),
                provenance_json=provenance.model_dump(mode="json"),
            )
        )
        db.add(ArtifactEdge(project_id=project_id, source_node_id=script_artifact.id, target_node_id=artifact.id, relation_type=ArtifactRelationType.DERIVED_FROM))
        db.add(ArtifactEdge(project_id=project_id, source_node_id=bible_artifact.id, target_node_id=artifact.id, relation_type=ArtifactRelationType.USES))
        if previous_latest is not None:
            db.add(ArtifactEdge(project_id=project_id, source_node_id=artifact.id, target_node_id=previous_latest.id, relation_type=ArtifactRelationType.SUPERSEDES))
        for other in db.scalars(
            select(ReplicaTargetAudioCandidate).where(
                ReplicaTargetAudioCandidate.project_id == project_id,
                ReplicaTargetAudioCandidate.review_status == CandidateReviewStatus.NEEDS_REVIEW.value,
                ReplicaTargetAudioCandidate.id != candidate.id,
            )
        ).all():
            other.review_status = CandidateReviewStatus.SUPERSEDED.value
            other.review_reason = "A newer target-audio candidate was explicitly accepted."
            other.reviewed_at = reviewed_at
            db.add(other)

        # Any still-pending timing candidate was computed from the previous CURRENT audio.
        # Once a new TARGET_AUDIO is accepted it must never remain reviewable or surface as
        # the apparent overflow state for the new audio revision.
        for pending_timing in db.scalars(
            select(ReplicaTimingPlanCandidate).where(
                ReplicaTimingPlanCandidate.project_id == project_id,
                ReplicaTimingPlanCandidate.review_status == CandidateReviewStatus.NEEDS_REVIEW.value,
            )
        ).all():
            pending_timing.review_status = CandidateReviewStatus.SUPERSEDED.value
            pending_timing.review_reason = "TARGET_AUDIO changed before this timing candidate was reviewed."
            pending_timing.reviewed_at = reviewed_at
            db.add(pending_timing)

        candidate.review_status = CandidateReviewStatus.ACCEPTED.value
        candidate.review_reason = command.reason.strip()
        candidate.reviewed_at = reviewed_at
        db.add(candidate)
        _invalidate_project_plan(db, project)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(artifact)
    return ReplicaTargetAudioRead(
        project_id=project_id,
        status=P14ResultStatus.CURRENT,
        artifact_id=artifact.id,
        revision=artifact.revision,
        input_fingerprint=artifact.input_fingerprint,
        content=content,
        provenance=provenance,
    )


def resolve_target_audio_media_path(project_id: str, task_id: str, clip_id: str) -> Path:
    project_segment = Path(project_id).name
    task_segment = Path(task_id).name
    clip_segment = Path(clip_id).name
    if project_segment != project_id or task_segment != task_id or clip_segment != clip_id:
        raise AppError("P14_AUDIO_MEDIA_PATH_INVALID", "目标配音媒体路径无效", status_code=422)
    sidecar = get_settings().artifact_root / "p14_target_audio" / project_id / task_id / f"{clip_id}.json"
    if not sidecar.is_file():
        raise AppError("P14_AUDIO_MEDIA_NOT_FOUND", "目标配音媒体不存在", status_code=404)
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        media_name = payload["storage_filename"]
    except Exception as exc:
        raise AppError("P14_AUDIO_MEDIA_INVALID", "目标配音媒体索引损坏", status_code=500) from exc
    media_path = sidecar.parent / Path(str(media_name)).name
    if not media_path.is_file():
        raise AppError("P14_AUDIO_MEDIA_NOT_FOUND", "目标配音媒体不存在", status_code=404)
    return media_path
