import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artifacts.enums import ArtifactValidity
from app.artifacts.models import ArtifactNode
from app.core.config import get_settings
from app.core.errors import AppError
from app.p15.models import ReplicaGenerationSegmentsRevision, ReplicaTargetStoryboardRevision
from app.p15.schemas import ReplicaGenerationSegmentsContent, ReplicaTargetStoryboardContent
from app.p16.models import ReplicaGenerationAttempt
from app.p16.schemas import GenerationAttemptRead, TechnicalQcStatus
from app.projects.enums import ProjectType
from app.target_assets.models import ReplicaTargetAssetsRevision
from app.target_assets.schemas import ReplicaTargetAssetsContent
from app.skills.models import ArtifactType
from app.workflow.models import ProviderJob


@dataclass(frozen=True)
class P16Inputs:
    project: object
    storyboard_artifact: ArtifactNode
    storyboard: ReplicaTargetStoryboardContent
    segments_artifact: ArtifactNode
    segments: ReplicaGenerationSegmentsContent
    assets_artifact: ArtifactNode
    assets: ReplicaTargetAssetsContent


def sha(payload: object) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _current(db: Session, project_id: str, artifact_type: ArtifactType) -> ArtifactNode:
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
    if not rows:
        raise AppError("P16_INPUT_REQUIRED", f"P16 需要 CURRENT {artifact_type.value}", status_code=409)
    if len(rows) != 1:
        raise AppError("P16_INPUT_AMBIGUOUS", f"{artifact_type.value} 存在多个 CURRENT Artifact", status_code=409)
    return rows[0]


def load_inputs(db: Session, project) -> P16Inputs:
    if project.project_type != ProjectType.REPLICA:
        raise AppError("P16_REPLICA_ONLY", "P16 视频生成只允许 REPLICA 项目", status_code=422)
    storyboard_artifact = _current(db, project.id, ArtifactType.TARGET_STORYBOARD)
    segments_artifact = _current(db, project.id, ArtifactType.GENERATION_SEGMENTS)
    assets_artifact = _current(db, project.id, ArtifactType.TARGET_ASSETS)
    storyboard_row = db.scalar(
        select(ReplicaTargetStoryboardRevision).where(ReplicaTargetStoryboardRevision.artifact_id == storyboard_artifact.id)
    )
    segments_row = db.scalar(
        select(ReplicaGenerationSegmentsRevision).where(ReplicaGenerationSegmentsRevision.artifact_id == segments_artifact.id)
    )
    assets_row = db.scalar(
        select(ReplicaTargetAssetsRevision).where(ReplicaTargetAssetsRevision.artifact_id == assets_artifact.id)
    )
    if storyboard_row is None or segments_row is None or assets_row is None:
        raise AppError("P16_TYPED_INPUT_MISSING", "P16 CURRENT 输入缺少 typed revision", status_code=500)
    storyboard = ReplicaTargetStoryboardContent.model_validate(storyboard_row.content_json)
    segments = ReplicaGenerationSegmentsContent.model_validate(segments_row.content_json)
    assets = ReplicaTargetAssetsContent.model_validate(assets_row.content_json)
    if segments.target_storyboard_artifact_id != storyboard_artifact.id:
        raise AppError("P16_LINEAGE_MISMATCH", "GENERATION_SEGMENTS 不属于 CURRENT TARGET_STORYBOARD", status_code=409)
    if storyboard.target_assets_artifact_id != assets_artifact.id or segments.target_assets_artifact_id != assets_artifact.id:
        raise AppError("P16_LINEAGE_MISMATCH", "Storyboard / Segments 与 CURRENT TARGET_ASSETS lineage 不一致", status_code=409)
    return P16Inputs(
        project=project,
        storyboard_artifact=storyboard_artifact,
        storyboard=storyboard,
        segments_artifact=segments_artifact,
        segments=segments,
        assets_artifact=assets_artifact,
        assets=assets,
    )


def input_artifact_ids(inputs: P16Inputs) -> list[str]:
    return [inputs.storyboard_artifact.id, inputs.segments_artifact.id, inputs.assets_artifact.id]


def storage_dir(project_id: str, task_id: str) -> Path:
    root = get_settings().artifact_root / "p16_generated_video" / project_id / task_id
    root.mkdir(parents=True, exist_ok=True)
    return root


def attempt_media_path(row: ReplicaGenerationAttempt) -> Path:
    if Path(row.storage_filename).name != row.storage_filename:
        raise AppError("P16_MEDIA_PATH_INVALID", "GenerationAttempt storage filename 无效", status_code=500)
    path = storage_dir(row.project_id, row.generated_by_task_id or "orphan") / row.storage_filename
    if not path.is_file():
        raise AppError("P16_MEDIA_NOT_FOUND", "GenerationAttempt 本地视频不存在", status_code=404)
    return path


def attempt_to_read(db: Session, row: ReplicaGenerationAttempt) -> GenerationAttemptRead:
    job = db.get(ProviderJob, row.provider_job_id)
    if job is None:
        raise AppError("P16_PROVIDER_JOB_MISSING", "GenerationAttempt 缺少 ProviderJob", status_code=500)
    return GenerationAttemptRead(
        id=row.id,
        project_id=row.project_id,
        generation_segment_id=row.generation_segment_id,
        attempt_number=row.attempt_number,
        provider_job_id=row.provider_job_id,
        provider=job.provider,
        model=job.model,
        remote_job_id=row.remote_job_id,
        media_url=row.media_url,
        media_sha256=row.media_sha256,
        mime_type=row.mime_type,
        actual_duration_us=row.actual_duration_us,
        width=row.width,
        height=row.height,
        codec_name=row.codec_name,
        technical_qc_status=TechnicalQcStatus(row.technical_qc_status),
        technical_qc_issues=list(row.technical_qc_issues_json or []),
        created_at=row.created_at,
    )
