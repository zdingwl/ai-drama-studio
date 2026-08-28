# P2 OCR PP-OCRv6 detector compatibility fix

Date: 2026-08-28

## User-observed Windows failure

`setup_breakdown_ocr_runtime.ps1` reached the real RapidOCR 3.9.2 runtime and failed while constructing the PP-OCRv6 small detector:

```text
ValueError: Unsupported det.lang_type='multi' for PP-OCRv6 small model.
```

The environment itself was present:

- rapidocr 3.9.2
- onnxruntime 1.21.1
- opencv 4.11.0
- CPU/CUDA/TensorRT ONNX providers visible

## Root cause

The original P2.3 provider emitted `Det.lang_type=multi`, and its production factory also hard-coded `LangDet.MULTI`. The first runtime compatibility pass only normalized the recognition side, so the detector was still forced back to `multi`.

RapidOCR PP-OCRv6 small/medium uses shared multilingual v6 checkpoints; the stable RapidOCR 3.9.2 compatibility profile is now pinned to `ch` for both detector and recognizer model resolution while the real project source language remains on Evidence.

## Fix

`engine/app/breakdown_p2_ocr_runtime_v1.py` now:

- returns `ch` as the PP-OCRv6 recognition compatibility profile;
- overrides `_engine_params()` so both `Det.lang_type` and `Rec.lang_type` are `ch`;
- overrides `_production_engine_factory()` so the base provider cannot reintroduce `LangDet.MULTI`;
- preserves existing runtime error diagnostics and fail-closed behavior.

Unit coverage in `engine/tests/unit/test_breakdown_p2_ocr_runtime_v1.py` verifies both parameter construction and enum conversion.

## Acceptance truth

P2.6 Windows / real-model acceptance remains **NOT PASSED**. Retest OCR runtime first:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_breakdown_ocr_runtime.ps1
```

Only after OCR self-check reaches READY should a fresh BreakdownRun be created for the complete P2 chain.
