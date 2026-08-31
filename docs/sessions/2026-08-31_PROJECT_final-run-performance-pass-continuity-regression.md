# Session handoff — final production performance PASS / anonymous continuity regression

Date: 2026-08-31 +08:00

## Current final production Run

```text
Run = BREAKDOWNRUN_dc678fb017ba49128b7340509f02536b
Episode = EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
whole run = 845.898s = 14.098 min
ASR = 15.884s
OCR = 264.235s
VLM = 564.050s
```

Performance:

```text
<30min YES
<=20min YES
Window Context = 84.910s
Exact-Shot = 459.158s
model load = 6.896s
Window 4/4 READY
Exact-Shot batches 6/6 READY
0 MAXED
```

Shot/Scene truth:

```text
Shot0001 subjects=0
props=蓝色玫瑰花束, 玻璃花瓶, 遥控器, 书本
Scenes=2
Scene1 = Shots 1-12 / 公寓走廊
Scene2 = Shots 13-30 / 客厅
same_shot_cluster_conflicts=0
```

Regression:

```text
Scene1 LocalSubjects=4
Scene2 LocalSubjects=16
previous accepted E6 quality baseline was 2 / 2
```

Therefore performance is accepted but P2.6 is NOT PASS.

## Current production contracts

```text
Window = breakdown-p2-vlm-window-context-segment-index-zh-v4
Exact-Shot = breakdown-p2-vlm-exact-shot-compact-reconstruction-zh-v3
Fusion = breakdown-p2-fusion-episode-context-e6-v1
```

Do not change Window timing/size, Exact-Shot frame ratios/resolution/token cap/batch size, or
Character V10.1 while debugging this regression.

## New diagnostic

```text
engine/app/breakdown_g1_subject_continuity_stage_diagnostics_v1.py
scripts/inspect_breakdown_subject_continuity_stages.py
```

Run locally:

```powershell
python scripts\inspect_breakdown_subject_continuity_stages.py `
  --run-id BREAKDOWNRUN_dc678fb017ba49128b7340509f02536b
```

It is completed-run/read-only and reports:

```text
Window subject hints + resolved Shot-local observations
Stage1 cluster count / unions
Stage2 cluster count / fallback pairs / unions
Stage3 cluster bridge count
Stage4 component bridge count
final clusters + appearance examples
```

## Likely hypotheses — not yet proven

1. Compact-v3 appearance phrases are lexically shorter than the previous quality baseline
   (`灰衣`, `白上衣`, `灰卫衣`, etc.), while the accepted E6 stable-feature vocabulary expects
   more canonical terms (`灰色`, `白色`, `上衣`, etc.). This may reduce Stage2/3/4 similarity.
2. Window-v4 was previously accepted for JSON/token/Scene behavior, but its `subject_continuity_hints`
   were not separately accepted as an identity-resolution coverage gate. Stage1 may resolve too few
   hints under compact exact observations.

Do not change policy from these hypotheses alone. First run the stage diagnostic on the immutable
final Run.

## Next action

1. `git pull`
2. `python -m py_compile engine/app/breakdown_g1_subject_continuity_stage_diagnostics_v1.py scripts/inspect_breakdown_subject_continuity_stages.py`
3. run the stage diagnostic above
4. use its output to identify the broken stage
5. build a read-only replay candidate against the same completed sidecars
6. require approximately 2 LocalSubjects per Scene and conflicts=0 before production promotion
7. no new Qwen full Episode until read-only replay is positive

Hosted GitHub Actions remain unused.
