# AI Drama Studio — Project State

> **Last synchronized:** 2026-08-31 +08:00  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Branch:** `main`  
> **Architecture:** Reference Video V2 + Breakdown Fast Grounded V2  
> **FastAPI app version:** `2.4.1`  
> **Formal Character runtime:** Character V10.1

## 1. Current truth

```text
P1/P2 implementation acceptance       = CONDITIONAL PASS
Fast Grounded V2 baseline             = APPROVED
Window Context contract               = SEGMENT-INDEX V4 / REAL ACCEPTED / FROZEN
Exact-Shot contract                   = COMPACT-RECONSTRUCTION V3 / REAL PERFORMANCE+SHOT QUALITY POSITIVE
P2-E6 Fusion                          = IMPLEMENTED / TARGETED LOCAL TEST PASS
Fresh final production performance    = PASS / 14.098 min / <=20min YES
Fresh final production Scene boundary = POSITIVE / 2 Scenes
Fresh final production Shot0001       = POSITIVE / subjects=0 / reconstruction props present
Fresh final anonymous continuity      = REGRESSION / Scene1=4 / Scene2=16 LocalSubjects
same-Shot hard safety                 = PASS / conflicts=0
P2.6 Windows / real-model acceptance  = NOT PASS (anonymous continuity regression)
G2 Scene-level text LLM               = BLOCKED / NOT IMPLEMENTED
Scene Timeline result UI              = BLOCKED / NOT IMPLEMENTED
P3 current 02 拉片 Shot-card UI        = IMPLEMENTED / NOT FINAL ACCEPTED
P4 Draft-guided Scene/Prop            = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character                  = PLANNED / PAUSED
```

Character V10.1 remains protected. Performance tuning is frozen. Window-v4 is frozen. Do not loosen
same-Shot cannot-link or Character identity gates. The only current G1 issue is anonymous
LocalSubject continuity under compact Exact-Shot observations.

## 2. Latest final production Run — real truth

```text
Run = BREAKDOWNRUN_dc678fb017ba49128b7340509f02536b
Episode = EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
30 Shots
whole run = 845.898s = 14.098 min
ASR = 15.884s
OCR = 264.235s
VLM = 564.050s
```

Performance gate:

```text
<30min = YES
<=20min = YES
Window Context = 84.910s
Exact-Shot = 459.158s
model load = 6.896s
58 grounding frames
10 total generation attempts
0 MAXED
```

Window real result:

```text
window-0001 | 12 Shots | 22.736s | READY | 276/1600
window-0002 | 12 Shots | 24.092s | READY | 304/1600
window-0003 |  9 Shots | 19.004s | READY | 237/1600
window-0004 |  7 Shots | 18.511s | READY | 233/1600
4/4 READY
```

Exact-Shot real result:

```text
batch1 | Shots 1-5   | 10 frames | 75.501s |  993/4096 | READY | attempts=1
batch2 | Shots 6-10  |  7 frames | 58.314s |  763/4096 | READY | attempts=1
batch3 | Shots 11-15 |  9 frames | 78.236s | 1027/4096 | READY | attempts=1
batch4 | Shots 16-20 | 10 frames | 80.167s | 1055/4096 | READY | attempts=1
batch5 | Shots 21-25 | 11 frames | 84.011s | 1088/4096 | READY | attempts=1
batch6 | Shots 26-30 | 11 frames | 81.942s | 1061/4096 | READY | attempts=1
```

Shot0001 visible truth remains positive:

```text
subjects=0
props=蓝色玫瑰花束, 玻璃花瓶, 遥控器, 书本
summary=蓝色玫瑰花束在玻璃花瓶中
neighbor person leakage=NO
```

Scene segmentation remains positive:

```text
Scene1 = Shots 1-12  | 公寓走廊 | INTERIOR / DAY
Scene2 = Shots 13-30 | 客厅     | INTERIOR / DAY
same_shot_cluster_conflicts=0
```

But anonymous continuity regressed:

```text
Scene1 LocalSubjects = 4   (expected evidence baseline ~=2)
Scene2 LocalSubjects = 16  (expected evidence baseline ~=2)
```

Therefore **P2.6 is NOT PASS** despite the excellent runtime.

## 3. Previous quality baseline for comparison

Previous fresh E6 Run before final compact production combination:

```text
Run = BREAKDOWNRUN_7d27295da479475f92888351bbfb9839
Scenes=2
Scene1 LocalSubjects=2
Scene2 LocalSubjects=2
same_shot_cluster_conflicts=0
Shot0001 subjects=0
```

That proves E6/replay-v3 can reach the correct two-person anonymous continuity on this Episode. The
new regression appeared after the final compact visual contract combination and must be diagnosed
from immutable completed sidecars before any new model rerun.

## 4. Current production visual path

```text
engine/app/breakdown_p2_vlm_continuity_v1.py
→ engine/app/breakdown_p2_vlm_fast_grounded_instrumented_v3.py
→ scripts/run_breakdown_vlm_fast_grounded_qwen3_timed_v5.py
   ├─ Window: scripts/run_breakdown_vlm_window_segment_index_v4.py
   └─ Exact-Shot: scripts/run_breakdown_vlm_exact_shot_compact_v3.py
```

Profiles:

```text
Window = breakdown-p2-vlm-window-context-segment-index-zh-v4
Exact-Shot = breakdown-p2-vlm-exact-shot-compact-reconstruction-zh-v3
Fusion = breakdown-p2-fusion-episode-context-e6-v1
```

Stable inference parameters remain:

```text
Window: 24s / 25% overlap / 1 FPS / 262144 px / 1600 max tokens
Exact-Shot: 1..3 frames / 524288 px / 4096 max tokens / 5 Shots per batch
```

Do not change these performance parameters while debugging continuity.

## 5. Current anonymous continuity chain

```text
Exact-Shot subjects -> Shot-local subject_A/B observations
Window v4 subject_continuity_hints
→ Stage1 Window soft edges + explicit exact-Shot conflict guard
→ Stage2 stable-appearance fallback + conflict guard
→ Stage3 mutual-best cluster bridge
→ Stage4 coherent-component bridge
→ Scene-scoped LocalSubjects
```

Hard rules stay unchanged:

```text
subject_A/B = Shot-local labels only
same-Shot observations = hard cannot-link
LocalSubject != Character
explicit male/female contradiction blocks soft union
explicit long-hair vs short/bald contradiction blocks soft union
missing attribute is not a contradiction
expression/emotion/action/pose/speaking/screen-position/framing are not identity keys
```

## 6. New read-only regression diagnostic

Use the completed final Run; do not rerun Qwen yet:

```powershell
python scripts\inspect_breakdown_subject_continuity_stages.py `
  --run-id BREAKDOWNRUN_dc678fb017ba49128b7340509f02536b
```

It prints, per Scene:

```text
observation_count
relevant Window subject hints
how each hint resolves to Shot-local observations
cluster count after Stage1
cluster count after Stage2
cluster count after Stage3
cluster count after Stage4
final cluster members / appearance examples
```

This is read-only: providers_executed=[] and no Breakdown/Final writes.

## 7. Current decision rule

Do not run another full Episode until the completed-run stage diagnostic identifies the broken
continuity layer and a read-only replay candidate restores the baseline without same-Shot conflicts.

Acceptance target remains:

```text
Scenes=2
Scene1 LocalSubjects ~=2
Scene2 LocalSubjects ~=2
same_shot_cluster_conflicts=0
Shot0001 subjects=0
Shot0001 reconstruction props include blue roses + glass vase
whole-run <30min
```

Performance is already accepted. Only anonymous continuity is open. G2 / Scene Timeline stays
blocked until this regression is resolved and a final production confirmation remains positive.

Hosted GitHub Actions remain intentionally unused.
