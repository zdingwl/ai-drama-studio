"""Import all SQLAlchemy models so Base.metadata is complete."""

from app.artifacts.models import ArtifactEdge, ArtifactNode
from app.evidence.models import (
    AsrEvidenceSegment,
    OcrEvidenceObservation,
    ShotDialogueProjection,
    SourceDialogueUtterance,
    SourceEvidenceSet,
    SourceVisualTextSpan,
)
from app.preprocessing.models import ShotAnchor, ShotBoundarySet
from app.projects.models import Project
from app.skills.plan_models import ProjectExecutionPlanRecord, ProjectExecutionPlanStepRecord
from app.sources.models import Episode, SourceAsset, SourceDocument
from app.understanding.models import SourceBibleRevision
from app.workflow.models import ProviderJob, Task

__all__ = [
    "ArtifactEdge",
    "ArtifactNode",
    "AsrEvidenceSegment",
    "Episode",
    "OcrEvidenceObservation",
    "Project",
    "ProjectExecutionPlanRecord",
    "ProjectExecutionPlanStepRecord",
    "ProviderJob",
    "ShotAnchor",
    "ShotBoundarySet",
    "ShotDialogueProjection",
    "SourceAsset",
    "SourceBibleRevision",
    "SourceDialogueUtterance",
    "SourceDocument",
    "SourceEvidenceSet",
    "SourceVisualTextSpan",
    "Task",
]
