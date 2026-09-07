"""Workflow V2 source-video understanding Provider boundary.

Module 3 business code depends on ``SourceVideoUnderstandingProvider`` rather than a concrete
model class. The current production implementation is Qwen3.8-27B, while the accepted Breakdown
Fast Grounded visual pipeline remains the evidence/runtime implementation underneath.

Hard boundaries:
- visual understanding emits anonymous VLM Evidence only;
- ASR/OCR remain the canonical source-dialogue evidence owners;
- D-ORCA remains the Speaker Attribution provider;
- raw model output never creates Final Character/Scene/Prop or Target-side data;
- every result records the provider/model profile and a deterministic input fingerprint.
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

SOURCE_VIDEO_PROVIDER_PROFILE = "source-video-understanding-qwen38-v1"
QWEN38_PROVIDER_NAME = "qwen38-video-understanding"
DEFAULT_QWEN38_MODEL = "Qwen/Qwen3.8-27B"
CANONICAL_DIALOGUE_POLICY = "asr-ocr-owned-visual-provider-cannot-overwrite-v1"


@runtime_checkable
class SourceVideoUnderstandingProvider(Protocol):
    """Business-facing source visual-understanding contract for module 3."""

    component: str

    def analyze(self, context: p2.P2RunContext) -> p2.P2ProviderResult:
        """Return traceable source-visual evidence without writing business truth directly."""
        ...


def source_video_input_fingerprint(
    context: p2.P2RunContext,
    *,
    model_name: str,
    provider_profile: str = SOURCE_VIDEO_PROVIDER_PROFILE,
) -> str:
    """Fingerprint immutable source anchors and model profile consumed by visual inference."""

    payload = {
        "schema_version": "source-video-understanding-input-v1",
        "provider_profile": provider_profile,
        "model": model_name,
        "project_id": context.project_id,
        "episode_id": context.episode_id,
        "source_language": context.source_language,
        "source_shot_revision_id": context.source_shot_revision_id,
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
    """Current module-3 main visual provider backed by local Qwen3.8-27B.

    Qwen3.8 owns a dedicated isolated runtime under ``.runtime/Qwen38Visual``. It intentionally
    does not reuse the TransVLM virtualenv because TransVLM has its own Qwen3-VL/custom-flow model
    dependency surface. Both runtimes may still share host FFmpeg binaries through the inherited
    runtime contract.

    The underlying Fast Grounded implementation keeps exact frozen Shot frames authoritative and
    uses Episode windows only for conservative scene/continuity context. Its semantic normalizer
    is deliberately whitelist-only, so dialogue/source_text fields returned by the model are
    discarded before a ``VLM_OUTPUT`` can be persisted.
    """

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
        super().__init__(
            *args,
            model_name=resolved_model,
            model_path=str(resolved_path),
            python_executable=str(resolved_python),
            **kwargs,
        )

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
        return tuple(missing)

    def analyze(self, context: p2.P2RunContext) -> p2.P2ProviderResult:
        result = super().analyze(context)
        metadata = dict(result.metadata)
        metadata.update({
            "provider_profile": SOURCE_VIDEO_PROVIDER_PROFILE,
            "model_family": "Qwen3.8",
            "input_fingerprint": source_video_input_fingerprint(
                context,
                model_name=self.model_name,
            ),
            "source_shot_revision_id": context.source_shot_revision_id,
            "canonical_dialogue_policy": CANONICAL_DIALOGUE_POLICY,
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
    "Qwen38VideoUnderstandingProvider",
    "SOURCE_VIDEO_PROVIDER_PROFILE",
    "SourceVideoUnderstandingProvider",
    "source_video_input_fingerprint",
]
