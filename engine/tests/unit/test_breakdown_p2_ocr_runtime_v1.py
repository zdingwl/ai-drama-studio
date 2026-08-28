from __future__ import annotations

import pytest

from engine.app.breakdown_p2_ocr_runtime_v1 import RapidOCROCRProvider


def test_ppocrv6_uses_canonical_multilingual_recognition_profile() -> None:
    provider = RapidOCROCRProvider(engine_factory=lambda params: object())

    for source_language in ("zh-CN", "en", "ja", "ko", "ar", "fr", "th", ""):
        assert provider._recognition_language(source_language) == "ch"


def test_engine_load_failure_keeps_runtime_detail() -> None:
    def fail_factory(params):
        raise ValueError("Unsupported OCR configuration")

    provider = RapidOCROCRProvider(
        device="cpu",
        engine_factory=fail_factory,
        cuda_available=lambda: False,
    )

    with pytest.raises(ValueError, match="Unsupported OCR configuration"):
        provider._load_engine("ch")

    assert provider._last_engine_error == "ValueError: Unsupported OCR configuration"


def test_frame_inference_failure_is_captured() -> None:
    class FailingEngine:
        def __call__(self, image):
            raise RuntimeError("ONNX execution failed")

    provider = RapidOCROCRProvider(
        device="cpu",
        engine_factory=lambda params: FailingEngine(),
        cuda_available=lambda: False,
    )
    engine, actual_device, warnings = provider._load_engine("ch")

    assert actual_device == "cpu"
    assert warnings == ()
    with pytest.raises(RuntimeError, match="ONNX execution failed"):
        engine(object())
    assert provider._last_frame_error == "RuntimeError: ONNX execution failed"
