"""R7.3 provider boundary for local/remote video generation backends.

Business code must depend on this contract instead of importing MiniMax/SGLang directly.
The first production implementation is MINIMAX_H3_LOCAL, but the boundary intentionally
keeps provider-specific job payloads out of remake planning.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator


VideoGenerationProviderKey = Literal["MINIMAX_H3_LOCAL"]
VideoGenerationMode = Literal["FL2VA", "REF2VA"]
VideoConditionType = Literal["image", "video", "audio"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VideoGenerationConditionV1(_StrictModel):
    type: VideoConditionType
    uri: str = Field(min_length=1, max_length=4096)
    role: str | None = Field(default=None, max_length=80)


class VideoGenerationRequestV1(_StrictModel):
    provider: VideoGenerationProviderKey = "MINIMAX_H3_LOCAL"
    mode: VideoGenerationMode
    prompt: str = Field(min_length=1, max_length=24000)
    conditions: list[VideoGenerationConditionV1] = Field(default_factory=list, max_length=12)
    duration_seconds: int = Field(ge=4, le=15)
    short_edge: int = Field(default=768, ge=256, le=2048)
    aspect_ratio: str = Field(default="auto", min_length=1, max_length=32)
    seed: int = Field(default=0, ge=0, le=2_147_483_647)

    @model_validator(mode="after")
    def _conditions_match_mode(self) -> "VideoGenerationRequestV1":
        image_count = sum(item.type == "image" for item in self.conditions)
        video_count = sum(item.type == "video" for item in self.conditions)
        audio_count = sum(item.type == "audio" for item in self.conditions)
        if self.mode == "FL2VA":
            if video_count or audio_count or image_count > 2:
                raise ValueError("FL2VA 仅允许 0-2 张 image 条件")
        else:
            if image_count > 9 or video_count > 3 or audio_count > 3:
                raise ValueError("REF2VA 条件超过 H3 官方数量限制")
            if audio_count and not (image_count or video_count):
                raise ValueError("REF2VA audio 不能作为唯一条件")
        return self


class VideoGenerationSubmissionV1(_StrictModel):
    provider: VideoGenerationProviderKey
    mode: VideoGenerationMode
    external_job_id: str = Field(min_length=1, max_length=256)
    provider_status: str | None = Field(default=None, max_length=80)
    raw: dict[str, Any] = Field(default_factory=dict)


class VideoGenerationJobStatusV1(_StrictModel):
    provider: VideoGenerationProviderKey
    mode: VideoGenerationMode
    external_job_id: str = Field(min_length=1, max_length=256)
    provider_status: str | None = Field(default=None, max_length=80)
    terminal: bool = False
    succeeded: bool = False
    failed: bool = False
    error_message: str | None = Field(default=None, max_length=4000)
    raw: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class VideoGenerationProvider(Protocol):
    key: VideoGenerationProviderKey

    def status(self) -> dict[str, Any]: ...

    def submit(self, request: VideoGenerationRequestV1) -> VideoGenerationSubmissionV1: ...

    def get_status(
        self,
        *,
        mode: VideoGenerationMode,
        external_job_id: str,
    ) -> VideoGenerationJobStatusV1: ...

    def download(
        self,
        *,
        mode: VideoGenerationMode,
        external_job_id: str,
        destination: Path,
    ) -> Path: ...


__all__ = [
    "VideoGenerationConditionV1",
    "VideoGenerationJobStatusV1",
    "VideoGenerationMode",
    "VideoGenerationProvider",
    "VideoGenerationProviderKey",
    "VideoGenerationRequestV1",
    "VideoGenerationSubmissionV1",
]
