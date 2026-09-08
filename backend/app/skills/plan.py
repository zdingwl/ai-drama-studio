import hashlib
import json
from enum import StrEnum

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.artifacts.service import get_current_artifacts
from app.core.errors import AppError
from app.projects.models import Project
from app.projects.service import get_project
from app.skills.capabilities import CAPABILITY_BY_ID
from app.skills.models import ArtifactType, Capability, CapabilityAvailability, RootSkillDefinition
from app.skills.plan_models import ProjectExecutionPlanRecord, ProjectExecutionPlanStepRecord
from app.skills.registry import get_bound_root_skill


class PlanStepStatus(StrEnum):
    COMPLETED = "COMPLETED"
    READY = "READY"
    BLOCKED_DEPENDENCY = "BLOCKED_DEPENDENCY"
    WAITING_CAPABILITY = "WAITING_CAPABILITY"


class ExecutionPlanStep(BaseModel):
    id: str
    phase: str
    title: str
    description: str
    status: PlanStepStatus
    capabilities: tuple[Capability, ...]
    requires: tuple[ArtifactType, ...]
    produces: tuple[ArtifactType, ...]
    missing_artifacts: tuple[ArtifactType, ...] = ()
    unavailable_capabilities: tuple[Capability, ...] = ()


class ProjectExecutionPlan(BaseModel):
    id: str
    project_id: str
    project_type: str
    skill_id: str
    skill_title: str
    skill_version: str
    workflow_revision: int
    revision: int
    input_fingerprint: str
    is_current: bool
    steps: tuple[ExecutionPlanStep, ...]


def _step_status(
    *,
    skill_step,
    available_artifacts: set[ArtifactType],
) -> tuple[PlanStepStatus, tuple[ArtifactType, ...], tuple[Capability, ...]]:
    required = set(skill_step.requires)
    produced = set(skill_step.produces)
    missing = tuple(item for item in skill_step.requires if item not in available_artifacts)
    unavailable = tuple(
        capability
        for capability in skill_step.capabilities
        if CAPABILITY_BY_ID[capability].availability != CapabilityAvailability.AVAILABLE
    )

    if produced and produced.issubset(available_artifacts):
        return PlanStepStatus.COMPLETED, missing, unavailable
    if not required.issubset(available_artifacts):
        return PlanStepStatus.BLOCKED_DEPENDENCY, missing, unavailable
    if unavailable:
        return PlanStepStatus.WAITING_CAPABILITY, missing, unavailable
    return PlanStepStatus.READY, missing, unavailable


def compile_execution_plan_steps(
    skill: RootSkillDefinition,
    available_artifacts: set[ArtifactType],
) -> tuple[ExecutionPlanStep, ...]:
    steps: list[ExecutionPlanStep] = []
    for definition in skill.steps:
        status, missing, unavailable = _step_status(
            skill_step=definition,
            available_artifacts=available_artifacts,
        )
        steps.append(
            ExecutionPlanStep(
                id=definition.id,
                phase=definition.phase,
                title=definition.title,
                description=definition.description,
                status=status,
                capabilities=definition.capabilities,
                requires=definition.requires,
                produces=definition.produces,
                missing_artifacts=missing,
                unavailable_capabilities=unavailable,
            )
        )
    return tuple(steps)


def plan_input_fingerprint(project: Project, skill: RootSkillDefinition, artifact_rows) -> str:
    payload = {
        "project": {
            "id": project.id,
            "project_type": project.project_type.value,
            "source_language": project.source_language,
            "target_language": project.target_language,
            "target_region": project.target_region,
            "scene_strategy": project.scene_strategy.value,
            "audio_policy": project.audio_policy.value,
            "visual_style": project.visual_style,
            "workflow_revision": project.workflow_revision,
            "root_skill_id": project.root_skill_id,
            "root_skill_version": project.root_skill_version,
        },
        "skill": {"id": skill.id, "version": skill.version},
        "artifacts": [
            {
                "id": item.id,
                "artifact_type": item.artifact_type,
                "namespace": item.namespace.value,
                "revision": item.revision,
                "input_fingerprint": item.input_fingerprint,
            }
            for item in sorted(artifact_rows, key=lambda row: (row.artifact_type, row.id))
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def invalidate_current_plan(db: Session, project: Project) -> None:
    if project.current_plan_id:
        plan = db.get(ProjectExecutionPlanRecord, project.current_plan_id)
        if plan is not None:
            plan.is_current = False
            db.add(plan)
    project.current_plan_id = None
    db.add(project)


def _record_to_response(db: Session, project: Project, record: ProjectExecutionPlanRecord) -> ProjectExecutionPlan:
    skill = get_bound_root_skill(
        project_type=project.project_type,
        skill_id=record.root_skill_id,
        skill_version=record.root_skill_version,
    )
    rows = list(
        db.scalars(
            select(ProjectExecutionPlanStepRecord)
            .where(ProjectExecutionPlanStepRecord.plan_id == record.id)
            .order_by(ProjectExecutionPlanStepRecord.position.asc())
        ).all()
    )
    steps = tuple(
        ExecutionPlanStep(
            id=row.step_key,
            phase=row.phase,
            title=row.title,
            description=row.description,
            status=PlanStepStatus(row.status),
            capabilities=tuple(Capability(item) for item in row.capabilities_json),
            requires=tuple(ArtifactType(item) for item in row.requires_json),
            produces=tuple(ArtifactType(item) for item in row.produces_json),
            missing_artifacts=tuple(ArtifactType(item) for item in row.missing_artifacts_json),
            unavailable_capabilities=tuple(Capability(item) for item in row.unavailable_capabilities_json),
        )
        for row in rows
    )
    return ProjectExecutionPlan(
        id=record.id,
        project_id=project.id,
        project_type=project.project_type.value,
        skill_id=record.root_skill_id,
        skill_title=skill.title,
        skill_version=record.root_skill_version,
        workflow_revision=record.workflow_revision,
        revision=record.revision,
        input_fingerprint=record.input_fingerprint,
        is_current=record.is_current,
        steps=steps,
    )


def get_current_execution_plan(db: Session, project_id: str) -> ProjectExecutionPlan:
    project = get_project(db, project_id)
    if project.current_plan_id is None:
        raise AppError("PLAN_NOT_COMPILED", "当前项目还没有可用执行计划", status_code=404)
    record = db.get(ProjectExecutionPlanRecord, project.current_plan_id)
    if record is None or not record.is_current:
        raise AppError("PLAN_NOT_COMPILED", "当前项目还没有可用执行计划", status_code=404)
    return _record_to_response(db, project, record)


def compile_and_persist_execution_plan(db: Session, project_id: str) -> ProjectExecutionPlan:
    project = get_project(db, project_id)
    try:
        skill = get_bound_root_skill(
            project_type=project.project_type,
            skill_id=project.root_skill_id,
            skill_version=project.root_skill_version,
        )
    except RuntimeError as exc:
        raise AppError(
            "ROOT_SKILL_VERSION_UNAVAILABLE",
            "项目绑定的 Root Skill 版本当前不可用",
            status_code=409,
            details={"skill_id": project.root_skill_id, "skill_version": project.root_skill_version},
        ) from exc

    artifacts = get_current_artifacts(db, project_id)
    fingerprint = plan_input_fingerprint(project, skill, artifacts)

    if project.current_plan_id:
        existing = db.get(ProjectExecutionPlanRecord, project.current_plan_id)
        if existing is not None and existing.is_current and existing.input_fingerprint == fingerprint:
            return _record_to_response(db, project, existing)
        invalidate_current_plan(db, project)

    available_types = {item.type_enum for item in artifacts}
    compiled_steps = compile_execution_plan_steps(skill, available_types)
    latest_revision = db.scalar(
        select(func.max(ProjectExecutionPlanRecord.revision)).where(
            ProjectExecutionPlanRecord.project_id == project.id
        )
    )
    record = ProjectExecutionPlanRecord(
        project_id=project.id,
        revision=(latest_revision or 0) + 1,
        input_fingerprint=fingerprint,
        root_skill_id=skill.id,
        root_skill_version=skill.version,
        workflow_revision=project.workflow_revision,
        is_current=True,
    )
    db.add(record)
    db.flush()

    for position, step in enumerate(compiled_steps):
        db.add(
            ProjectExecutionPlanStepRecord(
                plan_id=record.id,
                position=position,
                step_key=step.id,
                phase=step.phase,
                title=step.title,
                description=step.description,
                status=step.status.value,
                capabilities_json=[item.value for item in step.capabilities],
                requires_json=[item.value for item in step.requires],
                produces_json=[item.value for item in step.produces],
                missing_artifacts_json=[item.value for item in step.missing_artifacts],
                unavailable_capabilities_json=[item.value for item in step.unavailable_capabilities],
            )
        )

    project.current_plan_id = record.id
    db.add(project)
    db.commit()
    db.refresh(record)
    db.refresh(project)
    return _record_to_response(db, project, record)
