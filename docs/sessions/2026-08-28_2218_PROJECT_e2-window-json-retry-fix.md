# E2 Episode-window JSON runtime fix

Date: 2026-08-28 22:18 +08:00

## Observed real-run failure

A production Breakdown rerun reached E2 Qwen3-VL and failed on the first continuous window with:

```text
VLM Provider status=FAILED，P2 pipeline fail closed；window-0001 VLM inference failed: ValueError: model output JSON object is invalid
```

This is real local-runtime evidence, so P2-E2/P2-E3/P2.6 acceptance remain pending / NOT PASSED.

## Root cause in current code

`scripts/run_breakdown_vlm_qwen3_episode_windows.py` previously requested one verbose JSON object for every Shot inside a 20-40 second window while using a fixed `max_new_tokens` default/floor of 4096. Short-drama windows can contain many rapid cuts, making the generated JSON long enough to end before the closing brace. `base._first_json_object()` then correctly failed closed with `model output JSON object is invalid`.

The failure occurs inside E2 before E3 contextual refinement runs.

## Fix on main

Commit:

```text
050daed6c6bc2c196865567fa63dc5c0609d3fb1
fix(p2): retry oversized E2 window JSON safely [skip ci]
```

Changed runner behavior:

1. Generation budget now grows with target Shot count, with a bounded 12288-token ceiling instead of relying on a fixed 4096 cap for large windows.
2. Prompt now explicitly requires strict complete JSON and shorter descriptions.
3. If full-window JSON/coverage/language validation still fails, the runner retries the **same continuous video window** in compact groups of up to 6 target Shots.
4. Retry prompts still contain all Shot boundaries and the full video window, so this is not a regression to isolated per-Shot visual analysis.
5. Compact batch outputs are deterministically merged and revalidated against every Shot in the original window.
6. If compact retry also fails, E2 still fails closed and reports batch/budget diagnostics; malformed model output is never silently accepted or repaired into guessed semantics.

## Protected boundaries

No P1/P2 database schema, API, sidecar source type, Character V10.1 gate, Final Asset truth, ASR/OCR raw text, or historical BreakdownRun is changed.

## Acceptance state

The patch has been committed but has not been executed in this connector session against the user's Windows/Qwen/CUDA runtime. The affected Episode must be rerun. Only a new BreakdownRun can validate the fix; the failed historical Run remains immutable.
