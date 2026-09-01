"""Product coordinator for R5 target dialogue.

Human review is item-local. One uncertain line must not block TTS for every other READY
line in the project, so audio materialization always runs for READY rows when requested.
"""
from __future__ import annotations

from typing import Any

from engine.app.target_dialogue_v1 import (
    generate_target_dialogue_text_v1,
    materialize_target_dialogue_audio_v1,
)


def run_target_dialogue_pipeline_v1(project_id: str, *, synthesize_audio: bool = True) -> dict[str, Any]:
    text_bundle = generate_target_dialogue_text_v1(project_id)
    if not synthesize_audio:
        return text_bundle
    return materialize_target_dialogue_audio_v1(project_id)


__all__ = ["run_target_dialogue_pipeline_v1"]
