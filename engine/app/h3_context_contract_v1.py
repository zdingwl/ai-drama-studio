"""R8 H3 Context Compiler + GenerationAttempt product contracts."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from engine.app.video_generation_provider_v1 import VideoGenerationRequestV1


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


H3ContextStatus = Literal["READY", "WAITING_REFERENCE", "WAITING_PREVIOUS_OUTPUT", "REVIEW"]
GenerationAttemptStatus = Literal[
    "PLANNED",
    "SUBMITTED",
    "RUNNING",
    "SUCCEEDED",
    "FAILED",
    "STALE",
]


class H3MaterializedConditionV1(_StrictModel):
    type: Literal["image", "video", "audio"]
    role: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=80)
    uri: str = Field(min_length=1, max_length=4096)
    local_path: str = Field(min_length=1, max_length=4096)
    sha256: str = Field(min_length=64, max_length=64)
    source: str = Field(min_length=1, max_length=120)


class H3CompiledContextV1(_StrictModel):
    schema_version: Literal["h3-context-v1"] = "h3-context-v1"
    project_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    segment_id: str = Field(min_length=1)
    segment_input_fingerprint: str = Field(min_length=64, max_length=64)
    context_fingerprint: str = Field(min_length=64, max_length=64)
    status: H3ContextStatus
    reason: str = Field(min_length=1)
    provider: Literal["MINIMAX_H3_LOCAL"] = "MINIMAX_H3_LOCAL"
    mode: Literal["FL2VA", "REF2VA"]
    prompt: str = Field(min_length=1, max_length=24000)
    conditions: list[H3MaterializedConditionV1] = Field(default_factory=list, max_length=12)
    request: VideoGenerationRequestV1 | None = None
    workspace_dir: str = Field(min_length=1)
    created_at: str

    @model_validator(mode="after")
    def _request_matches_status(self) -> "H3CompiledContextV1":
        if self.status == "READY" and self.request is None:
            raise ValueError("READY H3 context must expose an executable request")
        if self.status != "READY" and self.request is not None:
            raise ValueError("blocked H3 context must not expose an executable request")
        if self.request is not None:
            if self.request.mode != self.mode or self.request.provider != self.provider:
                raise ValueError("H3 context request/provider mismatch")
            request_conditions = [item.model_dump(mode="json") for item in self.request.conditions]
            materialized = [
                {"type": item.type, "uri": item.uri, "role": item.role}
                for item in self.conditions
            ]
            if request_conditions != materialized:
                raise ValueError("H3 context materialized conditions do not match request")
        return self


class GenerationAttemptV1(_StrictModel):
    id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    generation_segment_id: str = Field(min_length=1)
    attempt_number: int = Field(ge=1)
    segment_input_fingerprint: str = Field(min_length=64, max_length=64)
    context_fingerprint: str = Field(min_length=64, max_length=64)
    provider: Literal["MINIMAX_H3_LOCAL"] = "MINIMAX_H3_LOCAL"
    mode: Literal["FL2VA", "REF2VA"]
    status: GenerationAttemptStatus
    external_job_id: str | None = None
    provider_status: str | None = None
    request: dict[str, Any]
    output_path: str | None = None
    error_message: str | None = None
    created_at: str
    submitted_at: str | None = None
    completed_at: str | None = None
    updated_at: str

    @model_validator(mode="after")
    def _terminal_fields(self) -> "GenerationAttemptV1":
        if self.status == "SUCCEEDED" and not self.output_path:
            raise ValueError("SUCCEEDED attempt needs output_path")
        if self.status in {"SUBMITTED", "RUNNING", "SUCCEEDED", "FAILED", "STALE"} and not self.external_job_id:
            raise ValueError("submitted attempt needs external_job_id")
        if self.status in {"SUCCEEDED", "FAILED", "STALE"} and not self.completed_at:
            raise ValueError("terminal attempt needs completed_at")
        return self


class GenerationAttemptProjectSummaryV1(_StrictModel):
    schema_version: Literal["generation-attempt-summary-v1"] = "generation-attempt-summary-v1"
    project_id: str = Field(min_length=1)
    attempt_count: int = Field(ge=0)
    succeeded_count: int = Field(ge=0)
    running_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    stale_count: int = Field(ge=0)
    attempts: list[GenerationAttemptV1] = Field(default_factory=list)

    @model_validator(mode="after")
    def _counts_match(self) -> "GenerationAttemptProjectSummaryV1":
        if self.attempt_count != len(self.attempts):
            raise ValueError("attempt_count mismatch")
        if self.succeeded_count != sum(item.status == "SUCCEEDED" for item in self.attempts):
            raise ValueError("succeeded_count mismatch")
        if self.running_count != sum(item.status in {"PLANNED", "SUBMITTED", "RUNNING"} for item in self.attempts):
            raise ValueError("running_count mismatch")
        if self.failed_count != sum(item.status == "FAILED" for item in self.attempts):
            raise ValueError("failed_count mismatch")
        if self.stale_count != sum(item.status == "STALE" for item in self.attempts):
            raise ValueError("stale_count mismatch")
        return self


__all__ = [
    "GenerationAttemptProjectSummaryV1",
    "GenerationAttemptStatus",
    "GenerationAttemptV1",
    "H3CompiledContextV1",
    "H3ContextStatus",
    "H3MaterializedConditionV1",
]
