"""Provider boundary for local lip-sync runtimes.

Postproduction business code talks only to LipSyncProvider. Provider-specific model/runtime
assumptions stay in adapters so LatentSync can be replaced without rewriting R10 planning.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class LipSyncRequestV1:
    video_path: Path
    audio_path: Path
    output_path: Path
    seed: int = 1247
    inference_steps: int = 20
    guidance_scale: float = 1.5


class LipSyncProvider(Protocol):
    provider_name: str

    def status(self) -> dict[str, Any]: ...

    def render(self, request: LipSyncRequestV1) -> Path: ...


__all__ = ["LipSyncProvider", "LipSyncRequestV1"]
