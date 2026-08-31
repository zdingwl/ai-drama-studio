# 2026-08-31 — E6 Fusion freeze + Fast Grounded VLM timing

## Accepted quality state

User-local E6/v3 targeted suite:

```text
12 tests PASS
```

Reference immutable Run replay v3:

```text
Run = BREAKDOWNRUN_85be6db2faa94901a2a6db932c71ed62
Candidate Scenes = 2
Scene1 = Shots 1-12 / 公寓走廊 / LocalSubjects=2
Scene2 = Shots 13-30 / 客厅 / LocalSubjects=2
same_shot_cluster_conflicts = 0
```

Fusion quality tuning is frozen unless a later real regression provides concrete evidence.
Production Fusion is E6; E5/E4 remain rollback baselines. Character V10.1 remains untouched.

## Performance truth

Previous full Run:

```text
whole = 33.705 min
ASR = 17.1s
OCR = 265.9s
VLM = 1738.0s
```

The old VLM timing only measured Provider total, so it could not separate FFmpeg preparation,
model load, Window Context and Exact-Shot grounding.

## New timing implementation

Production stable VLM runtime now routes through:

```text
breakdown_p2_vlm_continuity_v1.py
→ breakdown_p2_vlm_runtime_v1.py
→ breakdown_p2_vlm_fast_grounded_instrumented_v2.py
→ scripts/run_breakdown_vlm_fast_grounded_qwen3_timed.py
```

Semantic base remains `breakdown_p2_vlm_fast_grounded_v1.py`; prompts/sampling/token limits/batch
size are unchanged.

Persisted performance profile:

```text
breakdown-p2-vlm-performance-timing-v1
```

Measures:

```text
Host:
- Window clip materialization total/per-window
- Exact-Shot FFmpeg frame extraction total/per-shot
- subprocess wall
- total frame count

Qwen runner:
- model load
- Window Context total/per-window
- Exact-Shot total/per-top-level-batch
- per-batch shot/frame counts
- runner total
```

CUDA is synchronized around measured inference stages when available.

Read-only summary after a fresh completed Run:

```powershell
python scripts\inspect_breakdown_vlm_performance.py --run-id <NEW_RUN_ID>
```

## Next local gate

```powershell
git pull

python -m pytest `
  engine/tests/v2/test_breakdown_p2_fast_grounded_v1.py `
  engine/tests/v2/test_breakdown_p2_vlm_performance_instrumentation_v1.py `
  -q

python -m py_compile `
  engine/app/breakdown_p2_vlm_fast_grounded_instrumented_v2.py `
  scripts/run_breakdown_vlm_fast_grounded_qwen3_timed.py `
  scripts/inspect_breakdown_vlm_performance.py
```

If green, execute one fresh E6 full production Run. Do not change Fusion first. Inspect detailed
performance, then optimize only the measured dominant cost center. G2/Scene Timeline remains blocked
until fresh E6 quality + performance acceptance.
