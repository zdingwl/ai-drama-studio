"""Workflow V2 source-video understanding Provider boundary.

Module 3 business code depends on ``SourceVideoUnderstandingProvider`` rather than a concrete
model class. Qwen3.8-27B remains available as the higher-capacity visual provider, but base
Breakdown must not be blocked by an unaccepted heavyweight runtime. Production therefore uses a
runtime-aware stable-first policy: when the already-provisioned Qwen3-VL-4B Fast Grounded runtime
is ready, it is preferred for the base Shot facts; Qwen3.8 is used when explicitly requested or
when the stable runtime is unavailable.

Hard boundaries:
- visual understanding emits anonymous VLM Evidence only;
- ASR/OCR remain the canonical source-dialogue evidence owners;
- D-ORCA remains the Speaker Attribution provider;
- raw model output never creates Final Character/Scene/Prop or Target-side data;
- every result records the actual provider/model profile and a deterministic input fingerprint.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app.breakdown_p2_vlm_continuity_v1 import (
    Qwen3VLSemanticProvider as _FastGroundedQwenProvider,
)

SOURCE_VIDEO_PROVIDER_PROFILE = "source-video-understanding-qwen38-v1"
STABLE_SOURCE_VIDEO_PROVIDER_PROFILE = "source-video-understanding-qwen3vl4b-stable-v1"
SOURCE_VIDEO_RUNTIME_SELECTION_PROFILE = "source-video-runtime-stable-first-v1"
SOURCE_VIDEO_RUNTIME_MODE_ENV = "AI_DRAMA_SOURCE_VIDEO_RUNTIME"
DEFAULT_SOURCE_VIDEO_RUNTIME_MODE = "AUTO_STABLE"
QWEN38_PROVIDER_NAME = "qwen38-video-understanding"
DEFAULT_QWEN38_MODEL = "Qwen/Qwen3.8-27B"
CANONICAL_DIALOGUE_POLICY = "asr-ocr-owned-visual-provider-cannot-overwrite-v1"
QWEN38_REASONING_POLICY = "non-thinking-structured-visual-json-v1"

_STABLE_WINDOW_MAX_NEW_TOKENS = 800
_STABLE_EXACT_SHOT_MAX_PIXELS = 393_216
_STABLE_GROUNDING_MAX_NEW_TOKENS = 1_536
_STABLE_GROUNDING_BATCH_SIZE = 5


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


def _runtime_mode() -> str:
    raw = (os.getenv(SOURCE_VIDEO_RUNTIME_MODE_ENV) or DEFAULT_SOURCE_VIDEO_RUNTIME_MODE).strip().upper()
    aliases = {
        "AUTO": "AUTO_STABLE",
        "STABLE": "AUTO_STABLE",
        "AUTO_STABLE": "AUTO_STABLE",
        "QWEN3VL4B": "QWEN3VL4B",
        "QWEN3-VL-4B": "QWEN3VL4B",
        "QWEN38": "QWEN38",
        "QWEN3.8": "QWEN38",
    }
    return aliases.get(raw, "AUTO_STABLE")


def _stable_provider() -> _FastGroundedQwenProvider:
    """Build the lighter, already-established Fast Grounded runtime for base Shot facts.

    The compact caps are intentionally below the historical 4096-token exact-Shot ceiling. The
    accepted Window-v4 output was already only a few hundred tokens, and base Breakdown needs
    concise structured facts rather than long prose. Environment variables accepted by the base
    provider can still override most runtime paths/device settings.
    """

    return _FastGroundedQwenProvider(
        max_new_tokens=_STABLE_WINDOW_MAX_NEW_TOKENS,
        exact_shot_max_pixels=_STABLE_EXACT_SHOT_MAX_PIXELS,
        grounding_max_new_tokens=_STABLE_GROUNDING_MAX_NEW_TOKENS,
        grounding_batch_size=_STABLE_GROUNDING_BATCH_SIZE,
    )


def _provider_runtime_ready(provider: Any, source_language: str) -> bool:
    """Side-effect-free local runtime readiness check for provider selection."""

    try:
        config = provider._runtime_config(source_language)
        missing = provider._runtime_missing(config)
    except Exception:
        return False
    return not tuple(missing or ())


def _annotate_runtime_selection(
    result: p2.P2ProviderResult,
    *,
    context: p2.P2RunContext,
    mode: str,
    selected: str,
    provider_profile: str,
    selection_reason: str,
    extra_warnings: tuple[str, ...] = (),
) -> p2.P2ProviderResult:
    metadata = dict(result.metadata)
    metadata.update({
        "provider_profile": provider_profile,
        "runtime_selection_profile": SOURCE_VIDEO_RUNTIME_SELECTION_PROFILE,
        "runtime_selection_mode": mode,
        "runtime_selection": selected,
        "runtime_selection_reason": selection_reason,
        "input_fingerprint": source_video_input_fingerprint(
            context,
            model_name=result.model,
            provider_profile=provider_profile,
        ),
        "source_shot_revision_id": context.source_shot_revision_id,
        "canonical_dialogue_policy": CANONICAL_DIALOGUE_POLICY,
    })
    warnings = tuple(dict.fromkeys((*result.warnings, *extra_warnings)))
    return p2.P2ProviderResult(
        component=result.component,
        provider=result.provider,
        model=result.model,
        status=result.status,
        evidence=result.evidence,
        metadata=metadata,
        warnings=warnings,
    )


class Qwen38VideoUnderstandingProvider(_FastGroundedQwenProvider):
    """Source visual provider with Qwen3.8 plus a stable-first production runtime policy.

    Qwen3.8 owns a dedicated isolated runtime under ``.runtime/Qwen38Visual``. It intentionally
    does not reuse the TransVLM virtualenv because TransVLM has its own Qwen3-VL/custom-flow model
    dependency surface. Both runtimes may still share host FFmpeg binaries through the inherited
    runtime contract.

    Base Breakdown reliability takes precedence over model novelty. In normal production mode the
    provider first uses the existing Qwen3-VL-4B Fast Grounded runtime when it is actually ready.
    Qwen3.8 is then a fallback or an explicit opt-in via ``AI_DRAMA_SOURCE_VIDEO_RUNTIME=QWEN38``.
    This prevents an unaccepted Qwen3.8 checkpoint/runtime from blocking the entire drama pipeline.
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

    def _analyze_qwen38(self, context: p2.P2RunContext) -> p2.P2ProviderResult:
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

    def analyze(self, context: p2.P2RunContext) -> p2.P2ProviderResult:
        # Unit/injected runners intentionally exercise the concrete Qwen3.8 seam directly.
        if not self._uses_production_runner:
            return self._analyze_qwen38(context)

        mode = _runtime_mode()
        stable_failure_warning: tuple[str, ...] = ()

        if mode != "QWEN38":
            stable = _stable_provider()
            stable_ready = _provider_runtime_ready(stable, context.source_language)
            if mode == "QWEN3VL4B" or stable_ready:
                try:
                    stable_result = stable.analyze(context)
                except Exception as exc:
                    if mode == "QWEN3VL4B":
                        raise
                    stable_failure_warning = (
                        f"stable Qwen3-VL-4B runtime failed; falling back to Qwen3.8 ({type(exc).__name__})",
                    )
                else:
                    selected = _annotate_runtime_selection(
                        stable_result,
                        context=context,
                        mode=mode,
                        selected="QWEN3VL4B",
                        provider_profile=STABLE_SOURCE_VIDEO_PROVIDER_PROFILE,
                        selection_reason=(
                            "explicit stable runtime"
                            if mode == "QWEN3VL4B"
                            else "ready stable runtime preferred for base Breakdown"
                        ),
                    )
                    if mode == "QWEN3VL4B" or selected.status == "READY":
                        return selected
                    stable_failure_warning = (
                        f"stable Qwen3-VL-4B returned {selected.status}; falling back to Qwen3.8",
                    )

        qwen38_result = self._analyze_qwen38(context)
        return _annotate_runtime_selection(
            qwen38_result,
            context=context,
            mode=mode,
            selected="QWEN38",
            provider_profile=SOURCE_VIDEO_PROVIDER_PROFILE,
            selection_reason=(
                "explicit Qwen3.8 runtime"
                if mode == "QWEN38"
                else "stable runtime unavailable or failed"
            ),
            extra_warnings=stable_failure_warning,
        )


__all__ = [
    "CANONICAL_DIALOGUE_POLICY",
    "DEFAULT_QWEN38_MODEL",
    "DEFAULT_SOURCE_VIDEO_RUNTIME_MODE",
    "QWEN38_PROVIDER_NAME",
    "QWEN38_REASONING_POLICY",
    "SOURCE_VIDEO_PROVIDER_PROFILE",
    "SOURCE_VIDEO_RUNTIME_MODE_ENV",
    "SOURCE_VIDEO_RUNTIME_SELECTION_PROFILE",
    "STABLE_SOURCE_VIDEO_PROVIDER_PROFILE",
    "Qwen38VideoUnderstandingProvider",
    "SourceVideoUnderstandingProvider",
    "source_video_input_fingerprint",
]
