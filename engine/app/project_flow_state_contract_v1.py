"""Workflow V2 unified project flow-state API contract.

Project / Review Center / Output must consume the same snapshot instead of inferring
business completion independently.  The contract deliberately separates data validity,
business readiness and task execution.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


FlowValidity = Literal["NOT_BUILT", "CURRENT", "STALE"]
FlowReadiness = Literal["READY", "BLOCKED_REVIEW", "BLOCKED_DEPENDENCY", "WAITING_RUNTIME"]
FlowExecution = Literal["IDLE", "QUEUED", "PROCESSING", "SUCCEEDED", "FAILED", "INTERRUPTED"]
FlowOverallStatus = Literal[
    "PROCESSING",
    "BLOCKED_REVIEW",
    "BLOCKED_DEPENDENCY",
    "WAITING_RUNTIME",
    "READY_TO_CONTINUE",
    "FAILED",
    "COMPLETE",
]
FlowActionKind = Literal["NONE", "NAVIGATE", "COMMAND", "WAIT", "RETRY"]


class ProjectFlowActiveCommandV1(BaseModel):
    task_id: str
    task_type: str
    execution: FlowExecution
    title: str
    stage_key: str | None = None
    stage_label: str | None = None
    progress_mode: str | None = None
    progress_percent: float | None = None
    message: str | None = None
    updated_at: str | None = None


class ProjectFlowNextActionV1(BaseModel):
    action_key: str
    kind: FlowActionKind
    label: str
    reason: str
    enabled: bool = True
    target_surface: Literal["PROJECT", "REVIEW", "OUTPUT"] | None = None
    command_key: Literal["PREPARE_REMAKE", "H3_GENERATE_READY", "POSTPRODUCTION"] | None = None


class ProjectFlowReviewSummaryV1(BaseModel):
    open_count: int = 0
    blocking_count: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)


class ProjectFlowRuntimeItemV1(BaseModel):
    key: str
    label: str
    checked: bool = False
    ready: bool | None = None
    reason_code: str | None = None
    detail: str | None = None


class ProjectFlowRuntimeSummaryV1(BaseModel):
    blocking_runtime_count: int = 0
    items: list[ProjectFlowRuntimeItemV1] = Field(default_factory=list)


class ProjectFlowEpisodeV1(BaseModel):
    episode_id: str
    sort_order: int
    title: str
    preprocess_status: str | None = None
    shot_count: int = 0
    current_shot_revision_id: str | None = None
    current_breakdown_run_id: str | None = None


class ProjectFlowStageV1(BaseModel):
    stage_key: str
    ordinal: int
    label: str
    validity: FlowValidity
    readiness: FlowReadiness
    execution: FlowExecution
    consumable: bool
    reason_code: str
    reason: str
    current_input_fingerprint: str | None = None
    built_input_fingerprint: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    open_review_cases: int = 0
    active_command: ProjectFlowActiveCommandV1 | None = None
    warnings: list[str] = Field(default_factory=list)
    last_success: str | None = None


class ProjectFlowStateV1(BaseModel):
    schema_version: Literal["project-flow-state-v1"] = "project-flow-state-v1"
    project_id: str
    revision: str
    generated_at: str
    overall_status: FlowOverallStatus
    can_continue: bool
    next_action: ProjectFlowNextActionV1
    active_command: ProjectFlowActiveCommandV1 | None = None
    review_summary: ProjectFlowReviewSummaryV1
    runtime_summary: ProjectFlowRuntimeSummaryV1
    episodes: list[ProjectFlowEpisodeV1] = Field(default_factory=list)
    stages: list[ProjectFlowStageV1] = Field(default_factory=list)


__all__ = [
    "FlowActionKind",
    "FlowExecution",
    "FlowOverallStatus",
    "FlowReadiness",
    "FlowValidity",
    "ProjectFlowActiveCommandV1",
    "ProjectFlowEpisodeV1",
    "ProjectFlowNextActionV1",
    "ProjectFlowReviewSummaryV1",
    "ProjectFlowRuntimeItemV1",
    "ProjectFlowRuntimeSummaryV1",
    "ProjectFlowStageV1",
    "ProjectFlowStateV1",
]
