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
Window Context contract               = SEGMENT-INDEX V4 / REAL ACCEPTED / PRODUCTION / FROZEN
Exact-Shot contract                   = COMPACT-RECONSTRUCTION V3 / REAL ACCEPTED / PRODUCTION / FROZEN
P2-E6 Fusion                          = E6-V2 PRODUCTION PROMOTED / LOCAL PRODUCTION REGRESSION PENDING
Replay-v5 continuity                  = REAL ACCEPTED / Scene1=2 / Scene2=2 / conflicts=0
Fresh production performance          = PASS / 14.098 min / <=20min YES
Fresh production Scene boundary       = POSITIVE / 2 Scenes
Fresh production Shot0001             = POSITIVE / subjects=0 / reconstruction props present
Previous E6-v1 production continuity  = REGRESSION / Scene1=4 / Scene2=16
same-Shot hard safety                 = PASS / conflicts=0
P2.6 Windows / real-model acceptance  = NOT FINAL PASS (E6-v2 production confirmation pending)
G2 Scene-level text LLM               = BLOCKED / NOT IMPLEMENTED
Scene Timeline result UI              = BLOCKED / NOT IMPLEMENTED
P3 current 02 拉片 Shot-card UI        = IMPLEMENTED / NOT FINAL ACCEPTED
P4 Draft-guided Scene/Prop            = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character                  = PLANNED / PAUSED
```

Performance tuning, Window-v4 and Exact-Shot-v3 are frozen. Character V10.1 is protected. Do not
loosen same-Shot cannot-link or Final identity gates.

## 2. Latest full production Run — performance/visual truth baseline

```text
Run = BREAKDOWNRUN_dc678fb017ba49128b7340509f02536b
Episode = EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
30 Shots
whole run = 845.898s = 14.098 min
ASR = 15.884s
OCR = 264.235s
VLM = 564.050s
```

```text
<30min = YES
<=20min = YES
Window Context = 84.910s
Exact-Shot = 459.158s
model load = 6.896s
58 grounding frames
10 generation attempts
0 MAXED
```

Window:

```text
window-0001 | 12 Shots | READY | 276/1600
window-0002 | 12 Shots | READY | 304/1600
window-0003 |  9 Shots | READY | 237/1600
window-0004 |  7 Shots | READY | 233/1600
4/4 READY
```

Exact-Shot:

```text
batch1 |  993/4096 | READY | attempts=1
batch2 |  763/4096 | READY | attempts=1
batch3 | 1027/4096 | READY | attempts=1
batch4 | 1055/4096 | READY | attempts=1
batch5 | 1088/4096 | READY | attempts=1
batch6 | 1061/4096 | READY | attempts=1
```

Shot0001:

```text
subjects=0
props=蓝色玫瑰花束, 玻璃花瓶, 遥控器, 书本
summary=蓝色玫瑰花束在玻璃花瓶中
neighbor person leakage=NO
```

Scene segmentation:

```text
Scene1 = Shots 1-12  | 公寓走廊 | INTERIOR / DAY
Scene2 = Shots 13-30 | 客厅     | INTERIOR / DAY
same_shot_cluster_conflicts=0
```

The same Run exposed the E6-v1 anonymous continuity regression:

```text
Scene1 LocalSubjects=4
Scene2 LocalSubjects=16
```

## 3. Continuity root cause and accepted replay-v5 fix

Read-only Stage diagnostics proved the dominant fault was Stage1 Window hint resolution. The legacy
resolver auto-bound the only visible person in a Shot even when the hint appearance disagreed. This
allowed a white-clothed-woman hint to absorb a gray-hoodie man and vice versa.

Replay-v4 fixed Stage1 with evidence-gated hint resolution. Real completed-run replay became:

```text
Scene1 LocalSubjects=2
Scene2 LocalSubjects=3
conflicts=0
```

The remaining singleton was compact alias drift (`灰卫衣` vs `灰色连帽衫`). Replay-v5 added only a
comparison-view canonicalization for Stages 2..4; original VLM appearance text remains unchanged and
all accepted thresholds/hard guards remain unchanged.

User-local replay-v5 evidence:

```text
12 targeted replay tests PASS
providers_executed=[]
mutates_breakdown_run=false
mutates_final_assets=false
Candidate Scenes=2
Scene1 LocalSubjects=2
Scene2 LocalSubjects=2
same_shot_cluster_conflicts=0
```

Accepted continuity policies:

```text
Window hint resolver = window-hint-positive-appearance-support-compact-alias-v2
Compact appearance   = compact-observation-stable-alias-normalization-v1
```

## 4. Current production Fusion — E6 v2

Production module remains:

```text
engine/app/breakdown_p2_fusion_episode_v6.py
```

Production profile is now:

```text
breakdown-p2-fusion-episode-context-e6-v2
```

E6-v2 keeps the existing Scene/dialogue/Draft logic and promotes replay-v5 subject clustering only:

```text
Stage1 Window hint
  -> ordinal is candidate presence only
  -> Exact-Shot stable appearance must positively support the hint

Stages2..4
  -> compare a canonicalized compact appearance view
  -> keep original thresholds
  -> keep original explicit conflict guards

all stages
  -> same-Shot hard cannot-link
  -> LocalSubject remains anonymous Scene-scoped evidence, never Character identity
```

Production metadata now records:

```text
window_hint_resolution_policy
compact_appearance_policy
subject_continuity_policy
same_shot_cannot_link=hard
promotion_source=g1-read-only-replay-v5-real-accepted
```

## 5. Current production Breakdown chain

```text
Episode Current ShotRevision
→ frozen PROCESSING BreakdownRun
→ ASR
→ OCR
→ one-load Qwen3-VL
   ├─ Window Segment-index v4
   └─ Exact-Shot Compact-Reconstruction v3
→ immutable VLM_OUTPUT sidecar
→ P2-E6-v2 Episode-context Fusion
   ├─ accepted Scene policy
   ├─ ASR_SEGMENT dialogue truth
   └─ replay-v5 compact-safe anonymous continuity
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Profiles:

```text
Window = breakdown-p2-vlm-window-context-segment-index-zh-v4
Exact-Shot = breakdown-p2-vlm-exact-shot-compact-reconstruction-zh-v3
Fusion = breakdown-p2-fusion-episode-context-e6-v2
Pipeline = breakdown-p2-full-v1
```

## 6. Hard invariants

```text
Shot = smallest visual evidence/location unit
Exact-Shot visible fact > Window Context
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
subject_A/B = Shot-local labels only
same-Shot observations = hard cannot-link
explicit male/female contradiction blocks soft union
explicit long-hair vs short/bald contradiction blocks soft union
missing attribute is not a contradiction
expression/emotion/action/pose/speaking/screen position/framing are not identity keys
```

Character V10.1 remains unchanged:

```text
YOLOX -> capture-first evidence -> mature MOT -> YoutuReID
-> RESOLVED/UNRESOLVED -> explicit Shot Assignment -> Final Gate
```

## 7. Next required action

Do not tune VLM or performance further.

First run the cheap E6-v2 production regression suite. If green, execute exactly one final fresh
production Breakdown and require:

```text
Fusion profile = breakdown-p2-fusion-episode-context-e6-v2
Window profile = ...segment-index-zh-v4
Exact-Shot profile = ...compact-reconstruction-zh-v3
Scenes=2
Scene1 LocalSubjects=2
Scene2 LocalSubjects=2
same_shot_cluster_conflicts=0
Shot0001 subjects=0
Shot0001 props include blue roses + glass vase
whole-run <30min
```

Only after this fresh production confirmation may P2.6 be reviewed for final PASS and G2 / Scene
Timeline work begin. Hosted GitHub Actions remain intentionally unused.
