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
from app.p15.schemas import ReplicaGenerationSegmentsContent
from app.p16.models import ReplicaGenerationAttempt
from app.p16.schemas import GenerationAttemptRead, TechnicalQcStatus
from app.projects.enums import ProjectType
from app.replica_pipeline.models import ReplicaAssetImageRevision, ReplicaH3PromptRevision, ReplicaLocalizedStoryboardRevision
from app.replica_pipeline.schemas import ReplicaAssetImagesContent, ReplicaLocalizedStoryboardContent
from app.replica_pipeline.h3_audit import require_valid_segments
from app.skills.models import ArtifactType
from app.target_assets.schemas import ReferenceMediaRole, TargetAssetType
from app.workflow.models import ProviderJob


@dataclass(frozen=True)
class P16Inputs:
    project: object
    storyboard_artifact: ArtifactNode
    storyboard: ReplicaLocalizedStoryboardContent
    segments_artifact: ArtifactNode
    segments: ReplicaGenerationSegmentsContent
    assets_artifact: ArtifactNode
    assets: ReplicaAssetImagesContent


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


def _validate_reference_contract(*, assets_artifact: ArtifactNode, assets: ReplicaAssetImagesContent, segments: ReplicaGenerationSegmentsContent) -> None:
    """Fail closed if Step 4 reference slots no longer exactly resolve to Step 3 media."""
    asset_by_id = {asset.target_asset_id: asset for asset in assets.assets}
    for segment in segments.segments:
        conditions_by_asset: dict[str, list] = {}
        for condition in segment.reference_conditions:
            asset = asset_by_id.get(condition.target_asset_id)
            if asset is None:
                raise AppError("P16_REFERENCE_CONTRACT_MISMATCH", "H3 reference slot 指向不存在的 CURRENT target asset", status_code=409, details={"generation_segment_id": segment.generation_segment_id, "target_asset_id": condition.target_asset_id})
            if asset.target_entity_id != condition.target_entity_id or asset.asset_type.value != condition.asset_type:
                raise AppError("P16_REFERENCE_CONTRACT_MISMATCH", "H3 reference slot 的 target entity / asset type 与 CURRENT 资产不一致", status_code=409, details={"generation_segment_id": segment.generation_segment_id, "reference_id": condition.reference_id})
            media = next((item for item in asset.reference_media if item.reference_id == condition.reference_id), None)
            if media is None or media.role.value != condition.reference_role or media.uri != condition.reference_uri or media.sha256 != condition.reference_sha256 or media.storage_relpath != condition.storage_relpath:
                raise AppError("P16_REFERENCE_CONTRACT_MISMATCH", "H3 reference slot 的 role/URI/hash/path 与 CURRENT 资产媒体不一致", status_code=409, details={"generation_segment_id": segment.generation_segment_id, "reference_id": condition.reference_id})
            conditions_by_asset.setdefault(asset.target_asset_id, []).append(condition)

        for asset_ref in segment.target_asset_refs:
            if asset_ref.target_assets_artifact_id != assets_artifact.id:
                raise AppError("P16_REFERENCE_CONTRACT_MISMATCH", "GenerationSegment target_asset_ref 不属于 CURRENT TARGET_ASSETS", status_code=409, details={"generation_segment_id": segment.generation_segment_id, "target_asset_id": asset_ref.target_asset_id})
            asset = asset_by_id.get(asset_ref.target_asset_id)
            if asset is None or asset.target_asset_revision != asset_ref.target_asset_revision or asset.target_entity_id != asset_ref.target_entity_id or asset.asset_type != asset_ref.asset_type:
                raise AppError("P16_REFERENCE_CONTRACT_MISMATCH", "GenerationSegment target_asset_ref 与 CURRENT TARGET_ASSETS 不一致", status_code=409, details={"generation_segment_id": segment.generation_segment_id, "target_asset_id": asset_ref.target_asset_id})
            if asset_ref.asset_type == TargetAssetType.CHARACTER:
                roles = {item.reference_role for item in conditions_by_asset.get(asset_ref.target_asset_id, [])}
                if ReferenceMediaRole.FACE.value not in roles or not roles.intersection({ReferenceMediaRole.FULL_BODY.value, ReferenceMediaRole.FULL_BODY_FRONT.value}):
                    raise AppError(
                        "P16_CHARACTER_IDENTITY_REFERENCES_REQUIRED",
                        "人物视频生成必须同时携带 FACE + 正面 FULL_BODY Ref2VA 身份参考；请重新完成步骤 3/4",
                        status_code=409,
                        details={"generation_segment_id": segment.generation_segment_id, "target_asset_id": asset_ref.target_asset_id, "actual_roles": sorted(roles)},
                    )


def load_inputs(db: Session, project) -> P16Inputs:
    if project.project_type != ProjectType.REPLICA:
        raise AppError("P16_REPLICA_ONLY", "P16 视频生成只允许 REPLICA 项目", status_code=422)
    storyboard_artifact = _current(db, project.id, ArtifactType.TARGET_STORYBOARD)
    segments_artifact = _current(db, project.id, ArtifactType.GENERATION_SEGMENTS)
    assets_artifact = _current(db, project.id, ArtifactType.TARGET_ASSETS)
    h3_prompt_row = db.scalar(
        select(ReplicaH3PromptRevision).where(ReplicaH3PromptRevision.artifact_id == segments_artifact.id)
    )
    storyboard_row = db.scalar(
        select(ReplicaLocalizedStoryboardRevision).where(ReplicaLocalizedStoryboardRevision.artifact_id == storyboard_artifact.id)
    )
    assets_row = db.scalar(
        select(ReplicaAssetImageRevision).where(ReplicaAssetImageRevision.artifact_id == assets_artifact.id)
    )
    if h3_prompt_row is None or storyboard_row is None or assets_row is None:
        raise AppError(
            "P16_FIVE_STEP_INPUT_REQUIRED",
            "视频生成只接受五步主链结果：本土化分镜 + CURRENT 正式资产图 + 对应模型 Prompt Skill 输出",
            status_code=409,
        )
    storyboard = ReplicaLocalizedStoryboardContent.model_validate(storyboard_row.content_json)
    segments = ReplicaGenerationSegmentsContent.model_validate(h3_prompt_row.content_json)
    assets = ReplicaAssetImagesContent.model_validate(assets_row.content_json)
    if segments.target_storyboard_artifact_id != storyboard_artifact.id or assets.target_storyboard_artifact_id != storyboard_artifact.id:
        raise AppError("P16_LINEAGE_MISMATCH", "H3 Prompt / 资产图不属于 CURRENT 本土化分镜", status_code=409)
    if segments.target_assets_artifact_id != assets_artifact.id:
        raise AppError("P16_LINEAGE_MISMATCH", "H3 Prompt 不属于 CURRENT 资产图", status_code=409)
    if any(not segment.prompt_skill_id or not segment.prompt_skill_version or not segment.prompt_contract for segment in segments.segments):
        raise AppError("P16_PROMPT_SKILL_REQUIRED", "视频生成禁止消费没有模型专属 Prompt Skill provenance 的提示词", status_code=409)
    if any(not segment.reference_conditions for segment in segments.segments if segment.target_asset_refs):
        raise AppError("P16_REFERENCE_CONDITION_REQUIRED", "有正式资产引用的镜头必须使用 H3 多参考 reference_conditions", status_code=409)
    _validate_reference_contract(assets_artifact=assets_artifact, assets=assets, segments=segments)
    require_valid_segments(segments.segments)
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
