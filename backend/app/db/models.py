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
from app.p14.models import (
    IndexTTSVoiceMetadata,
    ReplicaTargetAudioCandidate,
    ReplicaTargetAudioRevision,
    ReplicaTimingPlanCandidate,
    ReplicaTimingPlanRevision,
)
from app.p15.models import (
    ReplicaGenerationSegmentsRevision,
    ReplicaStoryboardCandidate,
    ReplicaTargetStoryboardRevision,
)
from app.p16.models import (
    ReplicaGeneratedVideoRevision,
    ReplicaGenerationAttempt,
    ReplicaGenerationSelectionCandidate,
    ReplicaGenerationSelectionRevision,
)
from app.p17.models import ReplicaFinalOutputRevision, ReplicaPostCandidate
from app.preprocessing.models import ShotAnchor, ShotBoundarySet
from app.projects.models import Project
from app.replica_pipeline.models import (
    ReplicaAssetImageCandidate,
    ReplicaAssetImageRevision,
    ReplicaH3PromptRevision,
    ReplicaLocalizedStoryboardCandidate,
    ReplicaLocalizedStoryboardRevision,
)
from app.shot_breakdown.models import SourceShotFactsRevision
from app.skills.plan_models import ProjectExecutionPlanRecord, ProjectExecutionPlanStepRecord
from app.source_analysis.models import SourceStoryboardDraftRevision
from app.source_resolution.models import SourceResolutionRevision
from app.source_script.models import SourceScriptRevision
from app.source_snapshot.models import SourceVideoSnapshotRevision
from app.sources.models import Episode, SourceAsset, SourceDocument
from app.target_assets.models import ReplicaTargetAssetsCandidate, ReplicaTargetAssetsRevision
from app.target_bible.models import ReplicaTargetRevision
from app.target_script.models import ReplicaTargetScriptRevision
from app.understanding.models import SourceBibleRevision
from app.workflow.models import ProviderJob, Task

__all__ = [
    "ArtifactEdge",
    "ArtifactNode",
    "AsrEvidenceSegment",
    "Episode",
    "IndexTTSVoiceMetadata",
    "OcrEvidenceObservation",
    "Project",
    "ProjectExecutionPlanRecord",
    "ProjectExecutionPlanStepRecord",
    "ProviderJob",
    "ReplicaFinalOutputRevision",
    "ReplicaAssetImageCandidate",
    "ReplicaAssetImageRevision",
    "ReplicaGeneratedVideoRevision",
    "ReplicaGenerationAttempt",
    "ReplicaGenerationSelectionCandidate",
    "ReplicaGenerationSelectionRevision",
    "ReplicaGenerationSegmentsRevision",
    "ReplicaPostCandidate",
    "ReplicaH3PromptRevision",
    "ReplicaLocalizedStoryboardCandidate",
    "ReplicaLocalizedStoryboardRevision",
    "ReplicaStoryboardCandidate",
    "ReplicaTargetAssetsCandidate",
    "ReplicaTargetAssetsRevision",
    "ReplicaTargetAudioCandidate",
    "ReplicaTargetAudioRevision",
    "ReplicaTargetRevision",
    "ReplicaTargetScriptRevision",
    "ReplicaTargetStoryboardRevision",
    "ReplicaTimingPlanCandidate",
    "ReplicaTimingPlanRevision",
    "ShotAnchor",
    "ShotBoundarySet",
    "ShotDialogueProjection",
    "SourceAsset",
    "SourceBibleRevision",
    "SourceDialogueUtterance",
    "SourceDocument",
    "SourceEvidenceSet",
    "SourceResolutionRevision",
    "SourceScriptRevision",
    "SourceShotFactsRevision",
    "SourceStoryboardDraftRevision",
    "SourceVideoSnapshotRevision",
    "SourceVisualTextSpan",
    "Task",
]
