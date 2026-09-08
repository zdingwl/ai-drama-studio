from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.workflow.models import TaskStatus


_SHA256_PATTERN = r"^[0-9a-f]{64}$"


class TaskCommandCreate(BaseModel):
    task_type: str = Field(min_length=1, max_length=64)
    task_name: str = Field(min_length=1, max_length=160)
    input_fingerprint: str = Field(pattern=_SHA256_PATTERN)
    input_artifact_ids: list[str] = Field(default_factory=list, max_length=256)
    plan_id: str | None = Field(default=None, max_length=36)
    plan_step_key: str | None = Field(default=None, max_length=96)
    episode_id: str | None = Field(default=None, max_length=36)
    max_attempts: int = Field(default=3, ge=1, le=10)


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    task_name: str
    progress_percent: int
    status: TaskStatus
    last_error: str | None
    attempt: int
    max_attempts: int
    can_retry: bool
    can_cancel: bool
    can_resume: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class TaskWorkerRead(BaseModel):
    """Internal worker-facing task state. Never expose this schema from user GET endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    task_type: str
    task_name: str
    input_fingerprint: str
    input_artifact_ids_json: list[str]
    plan_id: str | None
    plan_step_key: str | None
    episode_id: str | None
    status: TaskStatus
    progress_percent: int
    attempt: int
    max_attempts: int
    checkpoint_json: dict
    cancel_requested: bool
    worker_id: str | None
    heartbeat_at: datetime | None
