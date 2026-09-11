from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.projects.enums import AudioPolicy, ProjectType, SceneStrategy, VIDEO_PROJECT_TYPES
from app.projects.models import Project
from app.projects.schemas import ProjectCreate, ProjectUpdate
from app.skills.registry import get_root_skill


_DEFAULT_SCENE_STRATEGY = {
    ProjectType.REPLICA: SceneStrategy.MIXED,
    ProjectType.REDRAW: SceneStrategy.LOCALIZE,
    ProjectType.TRANSLATION: SceneStrategy.KEEP,
    ProjectType.NOVEL_TO_DRAMA: SceneStrategy.LOCALIZE,
    ProjectType.SCRIPT_TO_DRAMA: SceneStrategy.LOCALIZE,
    ProjectType.SCRIPT_LOCALIZATION: SceneStrategy.LOCALIZE,
}

_DEFAULT_AUDIO_POLICY = {
    ProjectType.REDRAW: AudioPolicy.KEEP_SOURCE_AUDIO,
}

_TARGET_BIBLE_CONFIG_FIELDS = {
    "target_language",
    "target_region",
    "scene_strategy",
    "visual_style",
}


def create_project(db: Session, payload: ProjectCreate) -> Project:
    root_skill = get_root_skill(payload.project_type)
    project = Project(
        name=payload.name.strip(),
        project_type=payload.project_type,
        source_language=payload.source_language,
        target_language=payload.target_language,
        target_region=payload.target_region,
        scene_strategy=payload.scene_strategy or _DEFAULT_SCENE_STRATEGY[payload.project_type],
        audio_policy=payload.audio_policy
        or _DEFAULT_AUDIO_POLICY.get(payload.project_type, AudioPolicy.REGENERATE_AUDIO),
        visual_style=payload.visual_style,
        source_understanding_provider=payload.source_understanding_provider,
        root_skill_id=root_skill.id,
        root_skill_version=root_skill.version,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def list_projects(db: Session) -> list[Project]:
    statement = select(Project).order_by(Project.created_at.desc())
    return list(db.scalars(statement).all())


def get_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise AppError("PROJECT_NOT_FOUND", "项目不存在", status_code=404, details={"project_id": project_id})
    return project


def update_project(db: Session, project_id: str, payload: ProjectUpdate) -> Project:
    project = get_project(db, project_id)
    changes = payload.model_dump(exclude_unset=True)
    actual_changes = {
        field: value
        for field, value in changes.items()
        if getattr(project, field) != value
    }
    if not actual_changes:
        return project

    provider_changed = "source_understanding_provider" in actual_changes
    target_bible_config_changed = bool(_TARGET_BIBLE_CONFIG_FIELDS & set(actual_changes))
    for field, value in actual_changes.items():
        setattr(project, field, value)

    if project.project_type in VIDEO_PROJECT_TYPES and not project.source_language:
        raise AppError("SOURCE_LANGUAGE_REQUIRED", "视频类项目必须选择原始语言", status_code=422)

    from app.skills.plan import invalidate_current_plan

    invalidate_current_plan(db, project)
    project.workflow_revision += 1
    db.add(project)
    db.commit()
    db.refresh(project)

    if provider_changed:
        # The selected provider is part of P7 source-understanding semantics. A result produced by
        # another provider must not remain CURRENT under the new project setting. This propagates
        # STALE to Story/Rhythm through the Artifact Graph while leaving P6 evidence untouched.
        from app.artifacts.service import invalidate_current_artifact_type
        from app.skills.models import ArtifactType

        invalidate_current_artifact_type(
            db,
            project_id=project_id,
            artifact_type=ArtifactType.SOURCE_BIBLE,
        )
        db.refresh(project)

    if target_bible_config_changed:
        # P11 fingerprints target language/region/scene strategy/visual style. A change to any of
        # these settings invalidates the old Target world but must never mutate the Source chain.
        # Invalidate both roots defensively: ADAPTATION_PLAN normally propagates to TARGET_BIBLE
        # through Artifact Graph, while the second call also covers legacy/incomplete graph data.
        from app.artifacts.service import invalidate_current_artifact_type
        from app.skills.models import ArtifactType

        invalidate_current_artifact_type(
            db,
            project_id=project_id,
            artifact_type=ArtifactType.ADAPTATION_PLAN,
        )
        invalidate_current_artifact_type(
            db,
            project_id=project_id,
            artifact_type=ArtifactType.TARGET_BIBLE,
        )
        db.refresh(project)
    return project
