from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.artifacts.enums import ArtifactValidity
from app.artifacts.models import ArtifactNode
from app.core.errors import AppError
from app.skills.models import ArtifactType
from app.source_analysis.models import SourceStoryboardDraftRevision
from app.source_analysis.schemas import (
    StoryboardDraftRead,
    StoryboardDraftStatus,
    StoryboardShotEditCommand,
    StoryboardShotOverride,
)
from app.source_analysis.script_service import get_source_script
from app.source_snapshot.service import get_source_video_snapshot


def _status_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _current_snapshot_artifact(db: Session, project_id: str) -> ArtifactNode | None:
    return db.scalar(
        select(ArtifactNode).where(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == ArtifactType.SOURCE_VIDEO_SNAPSHOT.value,
            ArtifactNode.validity == ArtifactValidity.CURRENT,
            ArtifactNode.is_current.is_(True),
        )
    )


def _latest_draft(db: Session, project_id: str) -> SourceStoryboardDraftRevision | None:
    return db.scalar(
        select(SourceStoryboardDraftRevision)
        .where(SourceStoryboardDraftRevision.project_id == project_id)
        .order_by(SourceStoryboardDraftRevision.revision.desc())
        .limit(1)
    )


def _parse_overrides(row: SourceStoryboardDraftRevision | None) -> list[StoryboardShotOverride]:
    if row is None:
        return []
    try:
        return [StoryboardShotOverride.model_validate(item) for item in (row.overrides_json or [])]
    except Exception as exc:
        raise AppError("STORYBOARD_DRAFT_INVALID", "分镜编辑草稿数据无法解析", status_code=500) from exc


def get_storyboard_draft(db: Session, project_id: str) -> StoryboardDraftRead:
    snapshot = get_source_video_snapshot(db, project_id)
    current_snapshot = _current_snapshot_artifact(db, project_id)
    latest = _latest_draft(db, project_id)
    if latest is None:
        return StoryboardDraftRead(
            project_id=project_id,
            status=StoryboardDraftStatus.NOT_BUILT,
            revision=None,
            base_source_current=_status_value(snapshot.status) == "CURRENT",
            overrides=[],
        )
    current = current_snapshot is not None and latest.source_snapshot_artifact_id == current_snapshot.id
    return StoryboardDraftRead(
        project_id=project_id,
        status=StoryboardDraftStatus.CURRENT if current else StoryboardDraftStatus.STALE,
        revision=latest.revision,
        base_source_current=_status_value(snapshot.status) == "CURRENT",
        overrides=_parse_overrides(latest),
    )


def edit_storyboard_draft(
    db: Session,
    *,
    project_id: str,
    command: StoryboardShotEditCommand,
) -> StoryboardDraftRead:
    snapshot = get_source_video_snapshot(db, project_id)
    current_snapshot = _current_snapshot_artifact(db, project_id)
    if _status_value(snapshot.status) != "CURRENT" or current_snapshot is None:
        raise AppError("SOURCE_ANALYSIS_NOT_READY", "请先完成当前原片解析，再修改分镜", status_code=409)

    source_script = get_source_script(db, project_id)
    source_shots = {
        shot.shot_anchor_id: shot
        for scene in source_script.scenes
        for shot in scene.shots
    }
    source_shot = source_shots.get(command.shot_anchor_id)
    if source_shot is None:
        raise AppError("STORYBOARD_DRAFT_SHOT_NOT_FOUND", "要修改的镜头不属于当前原片结果", status_code=404)

    latest = _latest_draft(db, project_id)
    latest_revision = latest.revision if latest is not None else None
    if command.expected_revision != latest_revision:
        raise AppError(
            "STORYBOARD_DRAFT_REVISION_CONFLICT",
            "分镜草稿已被更新，请刷新后再保存",
            status_code=409,
            details={"expected_revision": command.expected_revision, "current_revision": latest_revision},
        )

    valid_shot_ids = set(source_shots)
    latest_is_on_current_source = latest is not None and latest.source_snapshot_artifact_id == current_snapshot.id
    overrides = (
        {
            item.shot_anchor_id: item
            for item in _parse_overrides(latest)
            if item.shot_anchor_id in valid_shot_ids
        }
        if latest_is_on_current_source
        else {}
    )
    if command.reset_to_source:
        overrides.pop(command.shot_anchor_id, None)
    else:
        overrides[command.shot_anchor_id] = StoryboardShotOverride(
            shot_anchor_id=command.shot_anchor_id,
            visual_description=command.visual_description or source_shot.visual_description,
            shot_size=command.shot_size if command.shot_size is not None else source_shot.shot_size,
            composition=command.composition if command.composition is not None else source_shot.composition,
            angle_or_type=command.angle_or_type if command.angle_or_type is not None else source_shot.angle_or_type,
            movement=command.movement if command.movement is not None else source_shot.movement,
            focal_length_dof=(
                command.focal_length_dof if command.focal_length_dof is not None else source_shot.focal_length_dof
            ),
        )

    next_revision = int(
        db.scalar(
            select(func.max(SourceStoryboardDraftRevision.revision)).where(
                SourceStoryboardDraftRevision.project_id == project_id
            )
        )
        or 0
    ) + 1
    row = SourceStoryboardDraftRevision(
        project_id=project_id,
        source_snapshot_artifact_id=current_snapshot.id,
        revision=next_revision,
        overrides_json=[
            item.model_dump(mode="json")
            for item in sorted(overrides.values(), key=lambda value: value.shot_anchor_id)
        ],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return get_storyboard_draft(db, project_id)
