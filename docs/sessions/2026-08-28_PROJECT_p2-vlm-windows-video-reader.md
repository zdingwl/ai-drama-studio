# P2 VLM Windows video reader compatibility

Date: 2026-08-28

## Symptom

Production P2 VLM reached the real Qwen3-VL Shot inference path but failed with:

`VLM Provider status=FAILED ... Shot 1 VLM inference failed: KeyError: 'video_fps'`

## Root cause

The error is raised by qwen-vl-utils' torchvision video fallback when torchvision returns video metadata without `video_fps`. Current qwen-vl-utils prefers TorchCodec, then decord, then torchvision, but a selected reader failure is caught and retried with torchvision. On Windows this can mask the original decode/path problem with the unrelated `video_fps` KeyError.

The official TransVLM inference dependency set includes `qwen-vl-utils>=0.0.14` and `decord>=0.6.0`.

## Fix

- `engine/app/breakdown_p2_vlm_runtime_v1.py`
  - Windows production subprocess defaults `FORCE_QWENVL_VIDEO_READER=decord`.
  - Explicit override is available through `AI_DRAMA_P2_VLM_VIDEO_READER=decord|torchcodec|torchvision`.
  - invalid overrides fail closed.
- `scripts/run_breakdown_vlm_qwen3_diagnostic.py`
  - Windows sends a native absolute file path instead of `file:///D:/...` to the selected video backend.
  - when decord is selected, the runner validates that the Reference Clip opens, has >=2 frames, and has a positive finite FPS before entering Qwen processing.
  - original per-Shot failure diagnostics remain preserved.
- `scripts/setup_breakdown_vlm_runtime.ps1`
  - verifies `qwen-vl-utils>=0.0.14` and `decord`.
  - self-checks the production diagnostic runner.
- `engine/tests/unit/test_breakdown_p2_vlm_runtime_v1.py`
  - covers reader override propagation and invalid-reader fail-closed behavior.

## Acceptance truth

This is a runtime compatibility correction only. It does not change P2.6 acceptance status.

- P1/P2 implementation acceptance: CONDITIONAL PASS
- P2.6 Windows / real-model acceptance: NOT PASSED

Retry sequence:

1. pull latest `main`
2. run `scripts/setup_breakdown_vlm_runtime.ps1`
3. restart backend
4. create a fresh BreakdownRun
5. inspect the new VLM result; historical FAILED runs remain immutable
