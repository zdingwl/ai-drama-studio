"""P2.3 RapidOCR runtime compatibility layer.

RapidOCR 3.9.x PP-OCRv6 small/medium uses one multilingual recognition model.  The
canonical v6 configuration uses the ``ch`` recognition profile even when the source
video language is not Chinese; the source language remains preserved on Evidence.

This layer also keeps the production fail-closed behaviour while retaining a short,
non-secret runtime error hint in Provider warnings/metadata so Windows acceptance is
diagnosable instead of collapsing to a generic ``OCR engine load failed`` message.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app.breakdown_p2_ocr_v1 import RapidOCROCRProvider as _BaseRapidOCROCRProvider


class _CapturingOCREngine:
    def __init__(self, engine: Any, on_error: Callable[[BaseException], None]) -> None:
        self._engine = engine
        self._on_error = on_error

    def __call__(self, image: Any) -> Any:
        try:
            return self._engine(image)
        except Exception as exc:
            self._on_error(exc)
            raise


class RapidOCROCRProvider(_BaseRapidOCROCRProvider):
    """Production OCR provider with PP-OCRv6-compatible language/runtime diagnostics."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._last_engine_error: str | None = None
        self._last_frame_error: str | None = None
        super().__init__(*args, **kwargs)

    @staticmethod
    def _recognition_language(source_language: str) -> str:
        # RapidOCR >=3.9 PP-OCRv6 small/medium is a shared multilingual model.
        # Using legacy per-language profiles (latin/korean/arabic/...) can make
        # RapidOCR reject an otherwise valid v6 configuration.  Keep the actual
        # project language in Evidence metadata; use the canonical v6 profile here.
        return "ch"

    @staticmethod
    def _safe_error(exc: BaseException, *, max_len: int = 500) -> str:
        text = " ".join(str(exc).strip().split())
        if not text:
            text = type(exc).__name__
        return f"{type(exc).__name__}: {text[:max_len]}"

    def _capture_frame_error(self, exc: BaseException) -> None:
        self._last_frame_error = self._safe_error(exc)

    def _load_engine(self, recognition_language: str) -> tuple[Any, str, tuple[str, ...]]:
        try:
            engine, device, warnings = super()._load_engine(recognition_language)
        except Exception as exc:
            self._last_engine_error = self._safe_error(exc)
            raise

        if not isinstance(engine, _CapturingOCREngine):
            engine = _CapturingOCREngine(engine, self._capture_frame_error)
            # The base provider caches the engine and later calls it directly.
            self._engine = engine
        return engine, device, warnings

    def analyze(self, context: p2.P2RunContext) -> p2.P2ProviderResult:
        self._last_engine_error = None
        self._last_frame_error = None
        result = super().analyze(context)

        warnings = list(result.warnings)
        metadata: dict[str, Any] = dict(result.metadata)
        changed = False

        if result.status == "FAILED" and self._last_engine_error:
            metadata["runtime_error"] = self._last_engine_error
            warnings = [
                self._last_engine_error
                if item == "OCR engine load failed"
                else item
                for item in warnings
            ]
            if not any(self._last_engine_error in item for item in warnings):
                warnings.append(f"OCR engine load failed: {self._last_engine_error}")
            changed = True

        if result.status == "FAILED" and self._last_frame_error:
            metadata["last_frame_inference_error"] = self._last_frame_error
            warnings.append(f"Last OCR frame inference error: {self._last_frame_error}")
            changed = True

        if not changed:
            return result

        return p2.P2ProviderResult(
            component=result.component,
            provider=result.provider,
            model=result.model,
            status=result.status,
            evidence=result.evidence,
            metadata=metadata,
            warnings=tuple(dict.fromkeys(warnings)),
        )
