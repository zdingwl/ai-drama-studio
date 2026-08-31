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
P2.6 Windows / real-model acceptance  = PASS
G2 Scene Timeline Contract            = V1 / FINAL PASS / FROZEN FOUNDATION
G2 Deterministic Assembler            = V1 / FINAL PASS / FROZEN FOUNDATION
G2 Scene Narrative Core               = V1.5 / FINAL PASS / FROZEN
G2 Local Qwen text runtime            = REAL ACCEPTED / FROZEN BASELINE
G2 Source / Support Validator         = V1.5 / FINAL PASS / FROZEN
G2.3/G2.4 real-model acceptance       = PASS
G2.5 Scene Timeline API               = NOT IMPLEMENTED
G2.6 ordinary-user result UI          = NOT IMPLEMENTED
P3 current 02 拉片 Shot-card UI        = IMPLEMENTED / NOT FINAL ACCEPTED
P4 Draft-guided Scene/Prop            = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character                  = PLANNED / PAUSED
same-Shot hard safety                 = PASS / conflicts=0
```

G1 performance/quality tuning is frozen. G2.1/G2.2 and G2.3/G2.4 are also frozen after accepted real evidence. Do not change Window-v4, Exact-Shot-v3, E6-v2, G2 Timeline truth ownership, G2 Narrative provenance rules, same-Shot cannot-link, or Character V10.1 identity gates without a new concrete regression.

## 2. Final P2.6 production acceptance Run

```text
Run = BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
Episode = EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
ShotRevision = SHOTREV_1462ac6d9f3948b994fc9bc575fee3a0
Shots = 30
status = READY
is_current = true
whole run ~= 841.039s = 14.017 min
ASR = 15.275958s
OCR = 264.916802s
VLM = 559.267248s
Window Context = 84.3492s
Exact-Shot = 455.284273s
Window = 4/4 READY
Exact-Shot = 6/6 READY
MAXED = 0
```

Fusion production truth:

```text
Fusion profile = breakdown-p2-fusion-episode-context-e6-v2
scene_segment = 2
local_subject = 4
same_shot_cluster_conflicts = 0
Scene1 = Shots 1-12 / 公寓走廊 / LocalSubjects=2
Scene2 = Shots 13-30 / 客厅 / LocalSubjects=2
Shot0001 subjects = 0
Shot0001 props = 遥控器 / 蓝色玫瑰花束 / 玻璃花瓶 / 书本
```

**P2.6 = PASS / G1 = FROZEN.**

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

## 5. G2.1 / G2.2 final acceptance

Frozen modules:

```text
engine/app/breakdown_scene_timeline_contract_v1.py
engine/app/breakdown_scene_timeline_assembler_v1.py
engine/tests/v2/test_breakdown_scene_timeline_v1.py
docs/BREAKDOWN_G2_SCENE_TIMELINE_CONTRACT.md
```

Acceptance evidence:

```text
python -m pytest engine/tests/v2/test_breakdown_scene_timeline_v1.py -q
4 passed

scenes = 2
shots = 30
people = [2, 2]
shot1_people = []
shot1_props = ['遥控器', '蓝色玫瑰花束', '玻璃花瓶', '书本']
warnings = []
```

Therefore:

```text
G2.1 = FINAL PASS / FROZEN FOUNDATION
G2.2 = FINAL PASS / FROZEN FOUNDATION
```

## 6. G2.3 / G2.4 final acceptance

Frozen modules/baseline:

```text
engine/app/breakdown_scene_narrative_contract_v1.py
engine/app/breakdown_scene_grounding_v1.py
engine/app/breakdown_scene_narrative_v1.py
engine/app/breakdown_scene_narrative_validator_v1.py
engine/app/breakdown_scene_narrative_qwen3_v1.py
scripts/run_breakdown_scene_narrative_qwen3.py
scripts/run_breakdown_g2_scene_narrative_acceptance_v1.py
engine/tests/v2/test_breakdown_scene_narrative_v1.py
engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py
engine/tests/v2/test_breakdown_scene_narrative_real_regression_v1.py
docs/BREAKDOWN_G2_SCENE_NARRATIVE_CONTRACT.md
```

Prompt profile:

```text
breakdown-g2-scene-narrative-zh-v1.5
```

User-local regression evidence:

```text
python -m pytest engine/tests/v2/test_breakdown_scene_narrative_v1.py engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py engine/tests/v2/test_breakdown_scene_narrative_real_regression_v1.py -q
15 passed
```

Real-model evidence on the same accepted Run:

```text
preflight = READY / cuda / missing=[]
runner_diagnostics = Scene1 READY, Scene2 READY
scenes = 2
shots = 30
people = [2, 2]
shot1_people = []
shot1_props = ['遥控器', '蓝色玫瑰花束', '玻璃花瓶', '书本']
overlay_status = READY
warnings = []
shot_objects_unchanged = YES
structure_gate = PASS
narrative_gate = PASS
acceptance_machine_gate = PASS
```

Accepted Narrative:

```text
Scene1 title = 走廊争花
Scene1 summary = 老年女性质问年轻女性为何将花放在自家花瓶，年轻女性称花在走廊，双方争执并最终以给钱解决，年轻女性愤怒指责对方。

Scene2 title = 客厅争执
Scene2 summary = 人物2指责人物1对邻居偷花一事不作为，称其结婚八年从未支持过自己，人物1则表示自己会自行解决。
```

Human review = PASS. Scene2 high-impact ASR content remains explicitly attributed and does not become Final identity/relationship truth. Shot objects stay unchanged.

Therefore:

```text
G2.3 Scene Narrative = FINAL PASS / FROZEN
G2.4 Source/Support Validator = FINAL PASS / FROZEN
Local Qwen text runtime = REAL ACCEPTED / FROZEN BASELINE
```

## 7. G2 Narrative frozen boundaries

LLM MAY write only:

```text
readable_title
story_summary
```

LLM MUST NOT own/rewrite:

```text
Scene/Shot timestamps or boundaries
people identity/count
Shot visual facts
performance/action facts
ASR dialogue
OCR
prop existence
shot type
composition
camera motion
Final Character / Final Scene / Final Prop
```

ASR rules:

```text
Visual/Timeline facts may be stated directly.
Ordinary ASR claims must remain attributed speech/argument content.
Sensitive event terms may be explicit topics or explicitly attributed statements.
Relationship identity terms remain topic-only and cannot bind anonymous people.
Dialogue names cannot bind anonymous people.
Chinese/Arabic quantities must be supported by final provenance.
```

## 8. Next action

```text
1. keep G1 + G2.1/G2.2 + G2.3/G2.4 frozen
2. implement G2.5 Scene Timeline API
3. API should return direct ordinary-user Scene Timeline data, not engineering evidence
4. preserve title/story_summary overlay without exposing support Fxxxx in primary UI
5. implement G2.6 ordinary-user result UI after API acceptance
```

No assistant-local pytest/CUDA PASS is claimed. Hosted GitHub Actions remain intentionally unused.
