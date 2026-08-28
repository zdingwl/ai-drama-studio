# P2 VLM Windows torchvision fallback masking fix

Status: FIX IMPLEMENTED / LOCAL WINDOWS RE-ACCEPTANCE REQUIRED

## Observed failure

A real BreakdownRun still reported:

`Shot 1 VLM inference failed: KeyError: 'video_fps'`

after Windows had already been configured to prefer decord.

## Root cause

`qwen-vl-utils` 0.0.14 honors `FORCE_QWENVL_VIDEO_READER` when selecting the first video backend, but its `fetch_video()` implementation catches any backend exception and unconditionally retries `VIDEO_READER_BACKENDS["torchvision"]`.

The torchvision reader then reads `info["video_fps"]`; on the affected Windows Reference Clip that metadata key is absent, so the fallback masks the real decoder failure with `KeyError('video_fps')`.

## Fix

Added `scripts/run_breakdown_vlm_qwen3_strict_reader.py`.

When `FORCE_QWENVL_VIDEO_READER` is `decord` or `torchcodec`, the launcher:

1. imports `qwen_vl_utils.vision_process` inside the isolated Qwen runtime;
2. synchronizes its module-level forced-reader value and clears the backend cache;
3. redirects `VIDEO_READER_BACKENDS["torchvision"]` to the explicitly forced backend;
4. starts the existing diagnostic runner.

Therefore the library can no longer replace a decord/TorchCodec failure with the unrelated torchvision `video_fps` failure. The P2 provider remains fail-closed; the real decoder exception is preserved by the diagnostic transport.

The production provider now defaults to the strict-reader launcher. Windows still defaults to decord.

`setup_breakdown_vlm_runtime.ps1` now validates the strict-reader runner with the Windows decord profile.

## Scope

No changes to:
- P2 semantic prompt/schema
- Fusion
- Draft contracts
- P3 UI semantics
- Character V10.1

## Acceptance

1. Pull latest main.
2. Run `scripts/setup_breakdown_vlm_runtime.ps1` and require READY.
3. Restart backend.
4. Start a NEW BreakdownRun.
5. Confirm `KeyError: 'video_fps'` no longer appears.
6. If the forced decoder truly fails, preserve and review the real decord/TorchCodec error instead.

P2.6 real-model acceptance remains NOT PASSED until the real short-drama full chain and human acceptance report pass.
