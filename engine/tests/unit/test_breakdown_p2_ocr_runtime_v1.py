from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from engine.app.breakdown_p2_ocr_runtime_v1 import RapidOCROCRProvider


def test_ppocrv6_uses_canonical_multilingual_recognition_profile() -> None:
    provider = RapidOCROCRProvider(engine_factory=lambda params: object())

    for source_language in ("zh-CN", "en", "ja", "ko", "ar", "fr", "th", ""):
        assert provider._recognition_language(source_language) == "ch"

    params = provider._engine_params(recognition_language="ch", use_cuda=False)
    assert params["Det.lang_type"] == "ch"
    assert params["Rec.lang_type"] == "ch"
    assert params["Det.ocr_version"] == "PP-OCRv6"
    assert params["Rec.ocr_version"] == "PP-OCRv6"


def test_production_factory_does_not_reintroduce_multilingual_detector_alias(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeEngineType:
        ONNXRUNTIME = "onnxruntime-enum"

    class FakeLangDet:
        CH = "det-ch-enum"

    class FakeLangRec:
        CH = "rec-ch-enum"

    class FakeOCRVersion:
        PPOCRV6 = "ppocrv6-enum"

    def fake_model_type(value: str) -> str:
        return f"model:{value}"

    def fake_rapidocr(*, params):
        captured.update(params)
        return object()

    fake_module = SimpleNamespace(
        EngineType=FakeEngineType,
        LangDet=FakeLangDet,
        LangRec=FakeLangRec,
        ModelType=fake_model_type,
        OCRVersion=FakeOCRVersion,
        RapidOCR=fake_rapidocr,
    )
    monkeypatch.setitem(sys.modules, "rapidocr", fake_module)

    provider = RapidOCROCRProvider()
    params = provider._engine_params(recognition_language="ch", use_cuda=False)
    provider._production_engine_factory(params)

    assert captured["Det.lang_type"] == FakeLangDet.CH
    assert captured["Rec.lang_type"] == FakeLangRec.CH
    assert captured["Det.ocr_version"] == FakeOCRVersion.PPOCRV6
    assert captured["Rec.ocr_version"] == FakeOCRVersion.PPOCRV6


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
