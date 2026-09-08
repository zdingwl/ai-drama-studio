from enum import StrEnum

from pydantic import BaseModel

from app.projects.models import Project
from app.skills.models import ArtifactType, Capability
from app.skills.registry import get_root_skill


class PlanStepStatus(StrEnum):
    COMPLETED = "COMPLETED"
    READY = "READY"
    BLOCKED_DEPENDENCY = "BLOCKED_DEPENDENCY"


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


class ProjectExecutionPlan(BaseModel):
    project_id: str
    project_type: str
    skill_id: str
    skill_title: str
    workflow_revision: int
    steps: tuple[ExecutionPlanStep, ...]


def compile_execution_plan(
    project: Project,
    available_artifacts: set[ArtifactType],
) -> ProjectExecutionPlan:
    skill = get_root_skill(project.project_type)
    steps: list[ExecutionPlanStep] = []

    for definition in skill.steps:
        required = set(definition.requires)
        produced = set(definition.produces)
        missing = tuple(item for item in definition.requires if item not in available_artifacts)

        if produced and produced.issubset(available_artifacts):
            status = PlanStepStatus.COMPLETED
        elif required.issubset(available_artifacts):
            status = PlanStepStatus.READY
        else:
            status = PlanStepStatus.BLOCKED_DEPENDENCY

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
            )
        )

    return ProjectExecutionPlan(
        project_id=project.id,
        project_type=project.project_type.value,
        skill_id=skill.id,
        skill_title=skill.title,
        workflow_revision=project.workflow_revision,
        steps=tuple(steps),
    )
