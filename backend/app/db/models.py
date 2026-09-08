"""Import all SQLAlchemy models so Base.metadata is complete."""

from app.artifacts.models import ArtifactEdge, ArtifactNode
from app.preprocessing.models import ShotAnchor, ShotBoundarySet
from app.projects.models import Project
from app.skills.plan_models import ProjectExecutionPlanRecord, ProjectExecutionPlanStepRecord
from app.sources.models import Episode, SourceAsset, SourceDocument
from app.workflow.models import ProviderJob, Task

__all__ = [
    "ArtifactEdge",
    "ArtifactNode",
    "Episode",
    "Project",
    "ProjectExecutionPlanRecord",
    "ProjectExecutionPlanStepRecord",
    "ProviderJob",
    "ShotAnchor",
    "ShotBoundarySet",
    "SourceAsset",
    "SourceDocument",
    "Task",
]
