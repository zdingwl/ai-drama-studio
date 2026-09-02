"""Provider boundary for R10.1 safe non-dialogue background audio.

Business code must never depend directly on audio-separator/UVR model imports. A provider returns
only a separated background/instrumental stem. Residual source speech is still suppressed by the
R10.1 safety layer before any stem is allowed into the final mix.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BackgroundSeparationRequestV1:
    input_path: Path
    output_path: Path
    model_filename: str


class BackgroundAudioProvider(ABC):
    provider_name: str

    @abstractmethod
    def status(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def separate_background(self, request: BackgroundSeparationRequestV1) -> Path:
        raise NotImplementedError


__all__ = ["BackgroundAudioProvider", "BackgroundSeparationRequestV1"]
