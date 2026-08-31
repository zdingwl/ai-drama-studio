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
G2 Scene Timeline Contract            = V1 / IMPLEMENTED / USER-LOCAL ACCEPTANCE PENDING
G2 Deterministic Assembler            = V1 / IMPLEMENTED / USER-LOCAL ACCEPTANCE PENDING
G2 Scene-level text LLM               = UNBLOCKED / NOT IMPLEMENTED
Scene Timeline result UI              = UNBLOCKED / NOT IMPLEMENTED
P3 current 02 拉片 Shot-card UI        = IMPLEMENTED / NOT FINAL ACCEPTED
P4 Draft-guided Scene/Prop            = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character                  = PLANNED / PAUSED
same-Shot hard safety                 = PASS / conflicts=0
```

G1 performance/quality tuning is frozen. Do not change Window-v4, Exact-Shot-v3, E6-v2 thresholds,
same-Shot cannot-link, or Character V10.1 identity gates without a new concrete real regression.

G2.1/G2.2 code is implemented but is **not PASS yet**. User-local fixture and final-Run acceptance must happen first.

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
G2 Scene-local P1/P2 != Character identity
G2 Scene Timeline != Final Character / Final Scene / Final Prop truth
ASR-origin dialogue text must remain verbatim in G2
OCR-origin visible text must remain verbatim in G2
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

## 5. G2.1 / G2.2 implementation

G2 now has a read-only ordinary-user result foundation:

```text
Contract:
  engine/app/breakdown_scene_timeline_contract_v1.py

Deterministic assembler:
  engine/app/breakdown_scene_timeline_assembler_v1.py

Tests:
  engine/tests/v2/test_breakdown_scene_timeline_v1.py

Contract document:
  docs/BREAKDOWN_G2_SCENE_TIMELINE_CONTRACT.md
```

The assembler consumes the existing `breakdown_serializer_v1` payload shape and does not modify G1.

Deterministic output:

```text
SceneSegmentDraft
→ user-readable Scene info
→ Scene-local P1/P2/... anonymous people
→ ordered Shots
   → Exact-Shot visual_description (summary only as same-Shot fallback)
   → ShotLocalSubject / ACTION performance
   → DIALOGUE only when origin=ASR, text copied verbatim
   → current-Shot prop occurrences
   → shot type + model_metadata.composition_hint
   → camera motion only when G1 has a reliable non-UNKNOWN value
   → OCR only when origin=OCR, text copied verbatim
→ existing Scene summary as deterministic story-summary baseline
```

Primary output intentionally excludes:

```text
Evidence links / IDs
cluster / cluster_key
confidence
LocalSubject database IDs
subject_A/B observation internals
provider/model diagnostics
search hints
Final Character / Scene / Prop IDs
```

Fail-closed protections include duplicate Scene/Shot ordinals, invalid ranges, Shot escaping its Scene,
Scene ownership mismatch, and duplicate Scene-local LocalSubject identity records.

G2.1/G2.2 deliberately do **not** implement a Scene LLM, persistence, API route or new frontend yet.

## 6. Next work — G2 foundation acceptance, then Scene LLM

Required order:

```text
1. user-local run engine/tests/v2/test_breakdown_scene_timeline_v1.py
2. exercise G2 deterministic assembly against:
   BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
3. verify:
   - Scenes=2
   - Shots=30
   - Scene1 people=2
   - Scene2 people=2
   - Scene-local P* resets and is never Character identity
   - Shot0001 people=[]
   - Shot0001 includes 蓝色玫瑰花束 + 玻璃花瓶
   - dialogue text remains ASR verbatim
   - OCR remains verbatim
   - debug Evidence/cluster/confidence are absent from primary output
4. only after G2.1/G2.2 PASS, implement G2.3 Scene-level pure-text LLM
5. add G2.4 support/source validator
6. add G2.5 Scene Timeline API
7. finally replace the ordinary-user 02 拉片 result surface with G2.6 Scene Timeline UI
```

No more full-model G1 reruns are required unless a new regression appears. Hosted GitHub Actions remain
intentionally unused. G2 regressions must be fixed inside G2 instead of retuning the frozen G1 chain.
