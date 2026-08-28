# P2 OCR runtime failure correction

> Date: 2026-08-28  
> Phase: P2.6 Windows / real-model acceptance  
> Status: **FIX IMPLEMENTED / LOCAL WINDOWS RE-ACCEPTANCE REQUIRED**

## Observed failure

```text
OCR Provider status=FAILED，P2 pipeline fail closed
```

This is a real P2 fail-closed gate, not a P3 display issue.

## Root-cause correction

The original P2.3 adapter mapped project source languages to legacy RapidOCR recognition profiles such as `latin`, `korean`, `arabic`, etc. For RapidOCR 3.9.x PP-OCRv6 small/medium, production now uses the canonical shared multilingual `ch` recognition profile while preserving the actual project source language on Evidence.

New compatibility adapter:

```text
engine/app/breakdown_p2_ocr_runtime_v1.py
```

Formal production pipeline and CLI now instantiate that adapter.

## Diagnostics improvement

Provider FAILED warnings now retain a bounded runtime exception hint, and the P2 pipeline includes the first Provider warning in the raised task error. Fail-closed behavior is unchanged.

A Windows OCR self-check was added:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_breakdown_ocr_runtime.ps1
```

It verifies RapidOCR, OpenCV, ONNX Runtime, PP-OCRv6 model initialization and one blank-frame inference before a full Episode P2 rerun.

## Acceptance boundary

This code fix does **not** mark P2.6 PASS. The user must still:

```text
OCR self-check READY
Qwen3-VL runtime/model READY
new real-video BreakdownRun
ASR -> OCR -> VLM -> Fusion completes
human acceptance report PASS
```

Old failed BreakdownRuns remain immutable history and must not be rewritten.
