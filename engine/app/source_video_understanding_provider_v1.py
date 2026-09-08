"""Workflow V2 per-Shot source visual understanding Provider boundary.

Whole-Episode story/character/scene/prop understanding is now an explicit upstream stage.  This
provider consumes the materialized Gemini Source Bible and refines exact Shot visual/directing facts
with local Qwen3.8-27B.  It no longer silently falls back to a smaller model.

Hard boundaries:
- visual understanding emits anonymous VLM Evidence only;
- ASR/OCR remain the canonical source-dialogue evidence owners;
- D-ORCA remains the Speaker Attribution provider;
- raw model output never creates Final Character/Scene/Prop or Target-side data;
- every result records both source-video and Source-Bible fingerprints.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Protocol, runtime_checkable

from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app.breakdown_p2_vlm_continuity_v1 import (
    Qwen3VLSemanticProvider as _FastGroundedQwenProvider,
)

SOURCE_VIDEO_PROVIDER_PROFILE = "source-video-understanding-qwen38-with-source-bible-v2"
QWEN38_PROVIDER_NAME = "qwen38-video-understanding"
DEFAULT_QWEN38_MODEL = "Qwen/Qwen3.8-27B"
CANONICAL_DIALOGUE_POLICY = "asr-ocr-owned-visual-provider-cannot-overwrite-v1"
QWEN38_REASONING_POLICY = "non-thinking-structured-visual-json-v1"
SOURCE_BIBLE_ENV = "AI_DRAMA_EPISODE_INTELLIGENCE_PATH"


@runtime_checkable
class SourceVideoUnderstandingProvider(Protocol):
    component: str

    def analyze(self, context: p2.P2RunContext) -> p2.P2ProviderResult:
        ...


def source_video_input_fingerprint(
    context: p2.P2RunContext,
    *,
    model_name: str,
    episode_intelligence_fingerprint: str | None = None,
    provider_profile: str = SOURCE_VIDEO_PROVIDER_PROFILE,
) -> str:
    payload = {
        "schema_version": "source-video-understanding-input-v2",
        "provider_profile": provider_profile,
        "model": model_name,
        "project_id": context.project_id,
        "episode_id": context.episode_id,
        "source_language": context.source_language,
        "source_shot_revision_id": context.source_shot_revision_id,
        "episode_intelligence_fingerprint": episode_intelligence_fingerprint,
        "shots": [
            {
                "revision_item_id": shot.revision_item_id,
                "ordinal": shot.ordinal,
                "start_us": shot.start_us,
                "end_us": shot.end_us,
                "reference_clip_path": shot.reference_clip_path,
            }
            for shot in context.shots
        ],
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(serialized.encode("utf-8")).hexdigest()


class Qwen38VideoUnderstandingProvider(_FastGroundedQwenProvider):
    """Second-pass Shot provider backed by local Qwen3.8-27B and Gemini Source Bible context."""

    component = "VLM"

    def __init__(
        self,
        *args: object,
        model_name: str | None = None,
        model_path: str | None = None,
        python_executable: str | None = None,
        **kwargs: object,
    ) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        runtime_root = repo_root / ".runtime" / "Qwen38Visual"
        default_python = (
            runtime_root / ".venv" / "Scripts" / "python.exe"
            if os.name == "nt"
            else runtime_root / ".venv" / "bin" / "python"
        )
        resolved_model = (
            model_name
            or os.getenv("AI_DRAMA_P2_VLM_MODEL")
            or DEFAULT_QWEN38_MODEL
        ).strip()
        resolved_path = Path(
            model_path
            or os.getenv("AI_DRAMA_P2_VLM_MODEL_PATH")
            or str(runtime_root / "pretrained" / "Qwen3.8-27B")
        ).expanduser()
        resolved_python = Path(
            python_executable
            or os.getenv("AI_DRAMA_P2_VLM_PYTHON")
            or str(default_python)
        ).expanduser()
        if not kwargs.get("runner_script"):
            kwargs["runner_script"] = str(
                repo_root / "scripts" / "run_breakdown_vlm_fast_grounded_qwen38.py"
            )
        self._episode_intelligence_path: str | None = None
        self._episode_intelligence_fingerprint: str | None = None
        super().__init__(
            *args,
            model_name=resolved_model,
            model_path=str(resolved_path),
            python_executable=str(resolved_python),
            **kwargs,
        )

    def set_episode_intelligence_artifact(self, path: str, fingerprint: str) -> None:
        resolved = Path(path)
        if not resolved.is_file():
            raise FileNotFoundError("Gemini Episode Intelligence artifact missing")
        self._episode_intelligence_path = str(resolved.resolve())
        self._episode_intelligence_fingerprint = str(fingerprint).strip()

    def _runtime_missing(self, config):  # type: ignore[no-untyped-def]
        if not self._uses_production_runner:
            return ()
        missing: list[str] = []
        if not config.python_executable.is_file():
            missing.append("isolated Qwen3.8 Python runtime")
        if not config.runner_script.is_file():
            missing.append("Qwen3.8 Fast Grounded runner script")
        if not config.model_path.is_dir():
            missing.append("Qwen3.8-27B checkpoint")
        elif not (config.model_path / "config.json").is_file():
            missing.append("Qwen3.8-27B checkpoint config.json")
        if not self._episode_intelligence_path or not Path(self._episode_intelligence_path).is_file():
            missing.append("Gemini Episode Intelligence Source Bible")
        return tuple(missing)

    def _subprocess_env(self, config):  # type: ignore[no-untyped-def]
        env = super()._subprocess_env(config)
        if not self._episode_intelligence_path:
            raise RuntimeError("Qwen3.8 per-Shot analysis requires Gemini Episode Intelligence")
        env[SOURCE_BIBLE_ENV] = self._episode_intelligence_path
        return env

    def analyze(self, context: p2.P2RunContext) -> p2.P2ProviderResult:
        if self._uses_production_runner and (
            not self._episode_intelligence_path or not self._episode_intelligence_fingerprint
        ):
            return p2.P2ProviderResult(
                component="VLM",
                provider=QWEN38_PROVIDER_NAME,
                model=self.model_name,
                status="NOT_CONFIGURED",
                warnings=("Gemini Episode Intelligence 未准备好，禁止逐镜语义拉片",),
                metadata={
                    "provider_profile": SOURCE_VIDEO_PROVIDER_PROFILE,
                    "canonical_dialogue_policy": CANONICAL_DIALOGUE_POLICY,
                },
            )
        result = super().analyze(context)
        metadata = dict(result.metadata)
        metadata.update({
            "provider_profile": SOURCE_VIDEO_PROVIDER_PROFILE,
            "model_family": "Qwen3.8",
            "input_fingerprint": source_video_input_fingerprint(
                context,
                model_name=self.model_name,
                episode_intelligence_fingerprint=self._episode_intelligence_fingerprint,
            ),
            "source_shot_revision_id": context.source_shot_revision_id,
            "episode_intelligence_fingerprint": self._episode_intelligence_fingerprint,
            "canonical_dialogue_policy": CANONICAL_DIALOGUE_POLICY,
            "reasoning_policy": QWEN38_REASONING_POLICY,
        })
        return p2.P2ProviderResult(
            component=result.component,
            provider=QWEN38_PROVIDER_NAME,
            model=self.model_name,
            status=result.status,
            evidence=result.evidence,
            metadata=metadata,
            warnings=result.warnings,
        )


__all__ = [
    "CANONICAL_DIALOGUE_POLICY",
    "DEFAULT_QWEN38_MODEL",
    "QWEN38_PROVIDER_NAME",
    "QWEN38_REASONING_POLICY",
    "Qwen38VideoUnderstandingProvider",
    "SOURCE_BIBLE_ENV",
    "SOURCE_VIDEO_PROVIDER_PROFILE",
    "SourceVideoUnderstandingProvider",
    "source_video_input_fingerprint",
]
