# 2026-08-28 — P2-E2 runtime failure hardening

## User-observed failures

Real Windows/Qwen rerun first exposed:

```text
window-0001 VLM inference failed: ValueError: model output JSON object is invalid
```

After the first JSON fallback patch, another real rerun exposed only the generic production error:

```text
VLM Provider status=FAILED，P2 pipeline fail closed；P2-E2 VLM inference failed
```

This second message means the E2 window runner failed at the subprocess/runtime boundary before a usable per-window result reached the parent process. The old production wrapper stored subprocess diagnostics in metadata but did not promote them to the first Provider warning, so the UI hid the actionable cause.

## Changes now on main

### 1. Rapid-cut output strategy hardened

File:

```text
scripts/run_breakdown_vlm_qwen3_episode_windows.py
```

New policy:

```text
<= 6 target Shots
  -> one normal structured response
  -> compact adaptive fallback only on structured-output failure

> 6 target Shots
  -> skip the giant all-Shot JSON response
  -> compact target batches of at most 6
  -> if a batch still fails structured validation, recursively split the target set
```

Every batch still receives the same full continuous video window and the complete Shot boundary list. This is output batching only; visual context does not return to isolated per-Shot clips.

Generation ceiling was reduced to 6144 tokens. The runner no longer tries very large 8k-12k structured generations for rapid-cut windows. CUDA cache cleanup is best-effort between repeated full-window passes.

Runner startup/model-load failures now print one sanitized `P2-E2 FATAL ...` line before returning a non-zero exit code.

### 2. Production error detail surfaced

File:

```text
engine/app/breakdown_p2_vlm_runtime_v1.py
```

For non-READY E2 results, `subprocess_failure_detail` and `window_failure_details` are promoted into the first Provider warning. The pipeline already surfaces the first warning, so the next failure should show the real model/runtime cause instead of only `P2-E2 VLM inference failed`.

### 3. Coverage

Updated/added:

```text
engine/tests/v2/test_breakdown_p2_vlm_episode_window_runner.py
engine/tests/v2/test_breakdown_p2_vlm_runtime_diagnostics.py
```

Coverage includes pre-emptive rapid-cut batching, recursive structured-output splitting, bounded generation budget, and production diagnostic promotion.

## Commits

```text
8f29cddc  fix(p2): stabilize E2 rapid-cut window inference [skip ci]
200d48c0  fix(p2): surface E2 runtime failure detail [skip ci]
b3878f99  test(p2): cover adaptive E2 output batching [skip ci]
013b9375  test(p2): surface E2 subprocess diagnostics [skip ci]
```

## Acceptance truth

No acceptance status is upgraded by this patch.

```text
P2-E1 local-real = PENDING
P2-E2 local-real Qwen/Windows = PENDING
P2-E3 local-real = PENDING
P2.6 Windows/real-model = NOT PASSED
```

Next action: pull latest `main` and rerun the same Episode. If it still fails, capture the new first-line failure; it should now contain `P2-E2 runtime detail:` with the actionable CUDA/model/decord/runner/structured-output cause.
