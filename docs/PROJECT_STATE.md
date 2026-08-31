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
Fast Grounded V2 baseline             = APPROVED / G1 FROZEN
Window Context contract               = SEGMENT-INDEX V4 / REAL ACCEPTED / PRODUCTION / FROZEN
Exact-Shot contract                   = COMPACT-RECONSTRUCTION V3 / REAL ACCEPTED / PRODUCTION / FROZEN
P2-E6 Fusion                          = E6-V2 / REAL PRODUCTION ACCEPTED / FROZEN
Replay-v5 continuity                  = REAL ACCEPTED / promoted into E6-v2
P2.6 Windows / real-model acceptance  = PASS
G2 Scene-level text LLM               = UNBLOCKED / NOT IMPLEMENTED
Scene Timeline result UI              = UNBLOCKED / NOT IMPLEMENTED
P3 current 02 拉片 Shot-card UI        = IMPLEMENTED / NOT FINAL ACCEPTED
P4 Draft-guided Scene/Prop            = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character                  = PLANNED / PAUSED
same-Shot hard safety                 = PASS / conflicts=0
```

G1 performance/quality tuning is frozen. Do not change Window-v4, Exact-Shot-v3, E6-v2 thresholds,
same-Shot cannot-link, or Character V10.1 identity gates without a new concrete real regression.

## 2. Final P2.6 production acceptance Run

```text
Run = BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
Episode = EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
ShotRevision = SHOTREV_1462ac6d9f3948b994fc9bc575fee3a0
Shots = 30
status = READY
is_current = true
started_at = 2026-08-31T06:57:22.353834
completed_at = 2026-08-31T07:11:23.392582
whole run ~= 841.039s = 14.017 min
```

Provider timings:

```text
ASR = 15.275958s
OCR = 264.916802s
VLM = 559.267248s
```

VLM production truth:

```text
Window profile = breakdown-p2-vlm-window-context-segment-index-zh-v4
Exact-Shot profile = breakdown-p2-vlm-exact-shot-compact-reconstruction-zh-v3
Window = 4/4 READY
Exact-Shot = 6/6 READY
Window Context = 84.3492s
Exact-Shot = 455.284273s
generation attempts = 10
MAXED = 0
missing Shot semantic = 0
failed Window = 0
failed Exact-Shot grounding = 0
```

Fusion production truth:

```text
Fusion profile = breakdown-p2-fusion-episode-context-e6-v2
Fusion status = READY
scene_segment = 2
local_subject = 4
cluster_count = 4
merged_cluster_count = 4
observation_count = 46
same_shot_cluster_conflicts = 0
Scene1 = Shots 1-12 / 公寓走廊 / LocalSubjects=2
Scene2 = Shots 13-30 / 客厅 / LocalSubjects=2
```

Shot0001 truth:

```text
subjects = 0
summary = 蓝色玫瑰花束在玻璃花瓶中
props include:
- 蓝色玫瑰花束
- 玻璃花瓶
- 遥控器
- 书本
neighbor person leakage = NO
```

Therefore the final real gate is satisfied:

```text
Fusion=e6-v2                         PASS
Window=v4                            PASS
Exact-Shot=v3                        PASS
Scenes=2                             PASS
Scene1 LocalSubjects=2               PASS
Scene2 LocalSubjects=2               PASS
same-Shot conflicts=0                PASS
Shot0001 subjects=0                  PASS
Shot0001 roses + glass vase props    PASS
whole-run <30min                     PASS
whole-run <=20min                    PASS
```

**P2.6 = PASS.**

## 3. Accepted production chain

```text
Episode Current ShotRevision
→ frozen PROCESSING BreakdownRun
→ Episode ASR (faster-whisper large-v3)
→ OCR (RapidOCR PP-OCRv6-small)
→ one-load Qwen3-VL Fast Grounded
   ├─ Window Segment-index v4
   └─ Exact-Shot Compact-Reconstruction v3
→ immutable VLM_OUTPUT sidecar
→ P2-E6-v2 Episode-context Fusion
   ├─ corridor-family Scene policy + DIRECT NEW_SCENE safeguard
   ├─ ASR_SEGMENT dialogue truth + Shot projection
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

Continuity policies:

```text
Window hint resolver = window-hint-positive-appearance-support-compact-alias-v2
Compact appearance = compact-observation-stable-alias-normalization-v1
Subject continuity = compact-alias-normalized-after-evidence-gated-window-hint-plus-coherent-component-distinctive-attire-hard-same-shot-v3
same-Shot cannot-link = hard
```

## 4. Hard invariants

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

Character V10.1 remains protected:

```text
YOLOX Person Detection
→ capture-first Person Evidence
→ mature MOT
→ YoutuReID project identity
→ RESOLVED / UNRESOLVED
→ explicit Shot × known-Character Assignment
→ Final Character Gate
```

## 5. Next work — G2 / Scene Timeline

P2.6 no longer blocks downstream work. The next implementation stage is **G2 Scene-level text organization +
Scene Timeline result surface**.

G2 must consume accepted G1/P2 evidence; it must not replace or reinterpret source truth:

```text
SceneSegmentDraft -> Scene-level organization unit
ShotSemanticDraft -> visual Shot facts
ASR_SEGMENT -> dialogue text truth
OCR -> visible text evidence
LocalSubject -> anonymous Scene-scoped people only
DraftPropHint -> reconstruction/search hint only
```

Recommended order:

```text
1. freeze G1 acceptance fixtures and production profiles
2. define G2 Scene Timeline data/output contract
3. implement deterministic Scene Timeline assembler first
4. add Scene-level pure-text LLM only for readable summary/organization where needed
5. build the user-facing Scene Timeline result UI
6. keep raw Evidence/diagnostics out of the primary user result unless explicitly requested
```

No more full-model G1 reruns are required unless a new regression appears. Hosted GitHub Actions remain
intentionally unused.
