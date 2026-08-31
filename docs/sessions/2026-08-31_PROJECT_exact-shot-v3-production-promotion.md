# Handoff — Exact-Shot Compact v3 production promotion

Date: 2026-08-31

## Accepted real evidence

Reference completed Run:

```text
BREAKDOWNRUN_7d27295da479475f92888351bbfb9839
```

Window v4 remains accepted/frozen:

```text
4/4 READY
41.920s Window Context
233..304 output tokens
```

Exact-Shot original selected batches:

```text
batch1 85.693s / 2158 tokens
batch4 97.333s / 2374 tokens
batch6 96.481s / 2277 tokens
```

Compact v2 improved performance but failed Shot1 structured-prop quality.

Reconstruction-safe Compact v3 user-local tests:

```text
3/3 PASS
```

Real v3 selected batches:

```text
batch1 36.421s /  993 tokens / READY
batch4 58.451s / 1055 tokens / READY
batch6 44.921s / 1061 tokens / READY
```

Quality examples:

```text
Shot1 subjects=0 | props=蓝色玫瑰花束, 玻璃花瓶, 遥控器, 书本
Shot3 subjects=2 | props=黑色塑料袋
Shot16 subjects=2 | props=手机
Shot26 subjects=1 | props=花瓶, 书本
Shot27 subjects=2 | props=手机, 玫瑰
Shot30 subjects=2 | props=手机
```

## Production promotion

Production VLM chain is now:

```text
breakdown_p2_vlm_continuity_v1
→ breakdown_p2_vlm_fast_grounded_instrumented_v3
→ run_breakdown_vlm_fast_grounded_qwen3_timed_v5.py
   ├─ Window v4
   └─ Exact-Shot compact-reconstruction v3
```

Profiles:

```text
Window = breakdown-p2-vlm-window-context-segment-index-zh-v4
Exact-Shot = breakdown-p2-vlm-exact-shot-compact-reconstruction-zh-v3
Fusion = breakdown-p2-fusion-episode-context-e6-v1
```

No changes to:

```text
Window duration/overlap/FPS/max pixels/token cap
Exact-Shot frame ratios
Exact-Shot 524288 max pixels
Exact-Shot 4096 max new tokens
5-Shot top-level batch size
E6 Fusion policy
Character V10.1
```

## Next gate

1. User runs cheap production-routing tests.
2. If green, run exactly one fresh full production Breakdown on the same reference Episode.
3. Inspect G1 summary and VLM performance.
4. Require:
   - Window v4 profile
   - Exact-Shot v3 profile
   - ~2 correct Scenes
   - ~2 anonymous people per real Scene
   - same-shot conflicts=0
   - Shot1 subjects=0
   - Shot1 props include blue roses + glass vase
   - whole Run <30 minutes
5. If all pass, stop G1 tuning and review P2.6 final PASS. Then G2 / Scene Timeline may begin.

Do not run hosted GitHub Actions.
