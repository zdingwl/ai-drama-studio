# Session Handoff — Window v4 accepted / Exact-Shot diagnostic next

## Accepted real Window-only result

Completed frozen Run:

```text
BREAKDOWNRUN_7d27295da479475f92888351bbfb9839
```

Accepted candidate/profile promoted to production:

```text
breakdown-p2-vlm-window-context-segment-index-zh-v4
```

Real Window-only output:

```text
Host window materialization: 4.735s
Model load: 5.882s
Window Context total: 41.920s
Runner total: 48.900s
window-0001: 12 Shots | 10.821s | READY | 276/1600
window-0002: 12 Shots | 12.157s | READY | 304/1600
window-0003:  9 Shots |  9.249s | READY | 237/1600
window-0004:  7 Shots |  9.639s | READY | 233/1600
```

Acceptance interpretation:

```text
4/4 READY
0 MAXED
0 invalid JSON
0 segment range errors
Window token/truncation problem resolved
```

Window v4 is now frozen unless future real regression evidence appears.

## Production routing

```text
engine/app/breakdown_p2_vlm_fast_grounded_instrumented_v2.py
WINDOW_PROMPT_PROFILE = breakdown-p2-vlm-window-context-segment-index-zh-v4
runner = scripts/run_breakdown_vlm_fast_grounded_qwen3_timed_v3.py
window adapter = scripts/run_breakdown_vlm_window_segment_index_v4.py
```

v3/v2 Window implementations remain rollback/history.

## Quality baseline remains positive

Fresh E6 production Run before v4 promotion:

```text
whole run = 30.334 min
Scenes=2
Scene1 LocalSubjects=2
Scene2 LocalSubjects=2
Shot0001 subjects=[] / blue roses + glass vase
same_shot_cluster_conflicts=0
```

Fusion remains frozen. Character V10.1 remains protected.

## Next measured bottleneck

Fresh Run timing:

```text
Exact-Shot = 1076.135s
old Window Context = 465.062s
OCR = 240.770s
ASR = 17.951s
```

Do not blindly change Exact-Shot max tokens/resolution/frame ratios/batch size.

New read-only diagnostic:

```powershell
python scripts/diagnose_breakdown_exact_shot_batches.py `
  --run-id BREAKDOWNRUN_7d27295da479475f92888351bbfb9839 `
  --batches 1,4,6
```

It runs production Window v4 once plus only selected Exact-Shot batches and reports real output token
counts, MAXED state, adaptive attempt count, frame count and elapsed time. It writes no DB/sidecar/
Draft/Final assets.

After those measurements, optimize only the demonstrated Exact-Shot bottleneck, then run one final
fresh production E6 + Window-v4 full Breakdown for final `<30min` and quality confirmation.
