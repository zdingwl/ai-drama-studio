from enum import StrEnum

from pydantic import BaseModel, Field

from app.workflow.schemas import TaskRead


class ReplicaProductAction(StrEnum):
    UPLOAD_SOURCE = "UPLOAD_SOURCE"
    ANALYZE_SOURCE = "ANALYZE_SOURCE"
    GENERATE_ADAPTATION = "GENERATE_ADAPTATION"
    REVIEW_ADAPTATION = "REVIEW_ADAPTATION"
    CAST_VOICES = "CAST_VOICES"
    REVIEW_AUDIO = "REVIEW_AUDIO"
    FIX_DIALOGUE_DURATION = "FIX_DIALOGUE_DURATION"
    GENERATE_VIDEO = "GENERATE_VIDEO"
    REVIEW_VIDEO = "REVIEW_VIDEO"
    BUILD_FINAL = "BUILD_FINAL"
    REVIEW_FINAL = "REVIEW_FINAL"
    COMPLETE = "COMPLETE"


class ReplicaProductStepStatus(StrEnum):
    WAITING = "WAITING"
    READY = "READY"
    WORKING = "WORKING"
    NEEDS_ACTION = "NEEDS_ACTION"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class ReplicaProductStepRead(BaseModel):
    key: str
    title: str
    status: ReplicaProductStepStatus
    summary: str


class ReplicaProductPendingRead(BaseModel):
    target_assets_candidate_id: str | None = None
    target_audio_candidate_id: str | None = None
    timing_candidate_id: str | None = None
    video_candidate_id: str | None = None
    final_candidate_id: str | None = None
    timing_overflow_count: int = Field(default=0, ge=0)


class ReplicaProductWorkflowRead(BaseModel):
    project_id: str
    next_action: ReplicaProductAction
    headline: str
    description: str
    progress_percent: int = Field(ge=0, le=100)
    active_task: TaskRead | None = None
    last_error: str | None = None
    steps: list[ReplicaProductStepRead]
    pending: ReplicaProductPendingRead

