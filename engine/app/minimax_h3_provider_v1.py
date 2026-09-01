"""R7.3 MiniMax H3 implementation of the generic video generation provider."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from engine.app.h3_runtime_v1 import H3RuntimeManager, h3_runtime_manager_v1
from engine.app.video_generation_provider_v1 import (
    VideoGenerationJobStatusV1,
    VideoGenerationMode,
    VideoGenerationRequestV1,
    VideoGenerationSubmissionV1,
)


_TERMINAL_SUCCESS = {"completed", "complete", "succeeded", "success", "ready", "done"}
_TERMINAL_FAILURE = {"failed", "failure", "error", "cancelled", "canceled"}


class MiniMaxH3Provider:
    key = "MINIMAX_H3_LOCAL"

    def __init__(self, runtime: H3RuntimeManager | None = None) -> None:
        self._runtime = runtime or h3_runtime_manager_v1()

    def status(self) -> dict[str, Any]:
        return {
            "provider": self.key,
            **self._runtime.status(),
        }

    def submit(self, request: VideoGenerationRequestV1) -> VideoGenerationSubmissionV1:
        if request.provider != self.key:
            raise ValueError(f"请求 provider={request.provider} 不能交给 {self.key}")
        result = self._runtime.submit_video(
            mode=request.mode,
            prompt=request.prompt,
            conditions=[item.model_dump(mode="json", exclude_none=True) for item in request.conditions],
            duration_seconds=request.duration_seconds,
            short_edge=request.short_edge,
            aspect_ratio=request.aspect_ratio,
            seed=request.seed,
        )
        job_id = str(result.get("id") or "").strip()
        if not job_id:
            raise RuntimeError("MiniMax H3 未返回任务 id")
        return VideoGenerationSubmissionV1(
            provider=self.key,
            mode=request.mode,
            external_job_id=job_id,
            provider_status=_provider_status(result),
            raw=dict(result),
        )

    def get_status(
        self,
        *,
        mode: VideoGenerationMode,
        external_job_id: str,
    ) -> VideoGenerationJobStatusV1:
        result = self._runtime.get_video_status(mode, external_job_id)
        status = _provider_status(result)
        normalized = (status or "").strip().lower()
        failed = normalized in _TERMINAL_FAILURE
        succeeded = normalized in _TERMINAL_SUCCESS
        terminal = failed or succeeded
        return VideoGenerationJobStatusV1(
            provider=self.key,
            mode=mode,
            external_job_id=external_job_id,
            provider_status=status,
            terminal=terminal,
            succeeded=succeeded,
            failed=failed,
            error_message=_provider_error(result) if failed else None,
            raw=dict(result),
        )

    def download(
        self,
        *,
        mode: VideoGenerationMode,
        external_job_id: str,
        destination: Path,
    ) -> Path:
        return self._runtime.download_video(mode, external_job_id, destination)


def _provider_status(result: Mapping[str, Any]) -> str | None:
    for key in ("status", "state", "task_status"):
        value = result.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _provider_error(result: Mapping[str, Any]) -> str | None:
    for key in ("error", "error_message", "message", "detail"):
        value = result.get(key)
        if isinstance(value, Mapping):
            for nested in ("message", "detail", "error"):
                nested_value = value.get(nested)
                if nested_value is not None and str(nested_value).strip():
                    return str(nested_value).strip()[:4000]
        elif value is not None and str(value).strip():
            return str(value).strip()[:4000]
    return None


_PROVIDER = MiniMaxH3Provider()


def minimax_h3_provider_v1() -> MiniMaxH3Provider:
    return _PROVIDER


def get_video_generation_provider_v1(provider: str = "MINIMAX_H3_LOCAL") -> MiniMaxH3Provider:
    if provider != "MINIMAX_H3_LOCAL":
        raise ValueError(f"Unsupported video generation provider: {provider}")
    return _PROVIDER


__all__ = [
    "MiniMaxH3Provider",
    "get_video_generation_provider_v1",
    "minimax_h3_provider_v1",
]
