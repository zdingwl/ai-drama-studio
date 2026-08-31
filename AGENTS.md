# AI Drama Studio — Agent Entry Rules

Current architecture: **Reference Video V2 + Breakdown Fast Grounded V2**.  
Formal Character baseline: **Character V10.1 + explicit Shot Character Assignment**.

## 1. Executable CURRENT

```text
P1/P2 implementation acceptance       = CONDITIONAL PASS
Fast Grounded G1                      = REAL ACCEPTED / PRODUCTION / FROZEN
Window Context                         = Segment-index v4 / accepted / frozen
Exact-Shot                             = Compact-reconstruction v3 / accepted / frozen
P2-E6 anonymous continuity Fusion     = E6-v2 / real production accepted / frozen
P2.6 Windows / real-model acceptance  = PASS
G2 Scene Timeline Contract            = v1 / FINAL PASS / FROZEN FOUNDATION
G2 Deterministic Assembler            = v1 / FINAL PASS / FROZEN FOUNDATION
G2 Scene Narrative Core               = v1 / IMPLEMENTED / USER-LOCAL TEST PENDING
G2 Local Qwen text runtime            = v1 / IMPLEMENTED / USER-LOCAL TEST PENDING
G2 Source / Support Validator         = v1 / IMPLEMENTED / USER-LOCAL TEST PENDING
G2.3/G2.4 real-model acceptance       = PENDING
G2.5 Scene Timeline API               = NOT IMPLEMENTED
G2.6 ordinary-user result UI          = NOT IMPLEMENTED
P5 Draft ↔ Character                  = PAUSED
```

Truth priority:

```text
PROJECT_STATE + CURRENT_IMPLEMENTATION_MANIFEST + current code/tests = executable CURRENT
```

G2.1/G2.2 regression tests (`4 passed`) and final accepted real-Run smoke check both passed on 2026-08-31.
Treat the deterministic Scene Timeline foundation as frozen unless a concrete G2 regression is demonstrated.
G2.3/G2.4 implementation is not a PASS claim until user-local tests and final real-model acceptance pass.

## 2. Recovery order

Always read repository truth before old chat/history:

```text
1. AGENTS.md
2. SKILL.md
3. docs/PROJECT_STATE.md
4. docs/CURRENT_IMPLEMENTATION_MANIFEST.md
5. docs/BREAKDOWN_FAST_GROUNDED_V2_PLAN.md
6. docs/BREAKDOWN_EPISODE_CONTEXT_PLAN.md
7. docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
8. docs/BREAKDOWN_DRAFT_DATA_CONTRACT.md
9. docs/BREAKDOWN_P2_SIDECAR_CONTRACT.md
10. docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md
11. docs/BREAKDOWN_G2_SCENE_TIMELINE_CONTRACT.md
12. docs/BREAKDOWN_G2_SCENE_NARRATIVE_CONTRACT.md when working on G2.3+
13. Character docs when relevant
14. current code/tests
15. latest docs/sessions/*.md handoff
```

## 3. Frozen production Breakdown chain

```text
Episode Current ShotRevision
→ frozen PROCESSING BreakdownRun
→ Episode ASR
→ OCR
→ one-load Qwen3-VL Fast Grounded
   ├─ Window Context v4
   └─ Exact-Shot compact v3
→ immutable exact-Shot VLM_OUTPUT sidecar
→ P2-E6-v2 Episode-context Fusion
   ├─ accepted Scene policy + DIRECT NEW_SCENE safeguard
   ├─ ASR_SEGMENT dialogue truth
   └─ replay-v5 compact-safe anonymous continuity
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Production profiles:

```text
Window = breakdown-p2-vlm-window-context-segment-index-zh-v4
Exact-Shot = breakdown-p2-vlm-exact-shot-compact-reconstruction-zh-v3
Fusion = breakdown-p2-fusion-episode-context-e6-v2
Pipeline = breakdown-p2-full-v1
```

Do not tune this chain without a new concrete real regression.

## 4. Final P2.6 accepted evidence

```text
Run = BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
status = READY
whole run ~= 14.017 min
Window = 4/4 READY
Exact-Shot = 6/6 READY
MAXED = 0
Scenes = 2
Scene1 LocalSubjects = 2
Scene2 LocalSubjects = 2
same-Shot conflicts = 0
Shot0001 subjects = 0
Shot0001 props include blue roses + glass vase
Fusion = breakdown-p2-fusion-episode-context-e6-v2
```

P2.6 is PASS. G1 is frozen.

## 5. Core semantic rules

> **先看懂，再识别，再回填。**

> **Shot 是最小视觉证据与定位单位，不是连续理解的上下文上限。**

> **Exact-Shot visible fact > Window Context.**

> **Scene Timeline 是最终用户阅读拉片结果的主要单位。**

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
raw Evidence / Draft != Final binding truth
subject_A/B = Shot-local labels only
same-Shot person observations = hard cannot-link
G2 Scene-local P1/P2 refs != Character identity
G2 Scene Timeline != Final Character / Final Scene / Final Prop truth
ASR-origin DIALOGUE text is verbatim source truth
OCR-origin text is verbatim source truth
```

Dynamic expression/emotion/action/pose/speaking/screen position/framing are not identity keys.

## 6. Character V10.1 is protected

```text
YOLOX Person Detection
→ capture-first Person Evidence
→ mature MOT
→ YoutuReID project identity
→ RESOLVED / UNRESOLVED
→ explicit Shot × known-Character Assignment
→ Final Character Gate
```

Never relax same-sample cannot-link, face conflict, >=3 independent evidence rule, ambiguity rules,
explicit Shot assignment or Final Gate because of Breakdown hints.

## 7. G2.1 / G2.2 frozen foundation

Accepted read-only G2 foundation:

```text
engine/app/breakdown_scene_timeline_contract_v1.py
engine/app/breakdown_scene_timeline_assembler_v1.py
engine/tests/v2/test_breakdown_scene_timeline_v1.py
docs/BREAKDOWN_G2_SCENE_TIMELINE_CONTRACT.md
```

Accepted evidence:

```text
python -m pytest engine/tests/v2/test_breakdown_scene_timeline_v1.py -q
4 passed

Run = BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
scenes = 2
shots = 30
people = [2, 2]
shot1_people = []
shot1_props = ['遥控器', '蓝色玫瑰花束', '玻璃花瓶', '书本']
warnings = []
```

Do not change G2.1/G2.2 truth ownership to accommodate an LLM.

## 8. G2.3 / G2.4 implemented boundary

Implemented modules:

```text
engine/app/breakdown_scene_narrative_contract_v1.py
engine/app/breakdown_scene_grounding_v1.py
engine/app/breakdown_scene_narrative_v1.py
engine/app/breakdown_scene_narrative_validator_v1.py
engine/app/breakdown_scene_narrative_qwen3_v1.py
scripts/run_breakdown_scene_narrative_qwen3.py
engine/tests/v2/test_breakdown_scene_narrative_v1.py
engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py
docs/BREAKDOWN_G2_SCENE_NARRATIVE_CONTRACT.md
```

G2.3 LLM authority is deliberately narrow:

```text
LLM MAY write:
  readable_title
  story_summary

LLM MUST NOT own or rewrite:
  Scene/Shot timestamps
  people count or identity
  Shot visual facts
  performance/action facts
  ASR dialogue
  OCR text
  prop existence
  shot type
  composition
  camera motion
  Final Character/Scene/Prop
```

Every non-null Narrative claim must cite current Scene `Fxxxx` support facts. Overlay application rechecks
Run/ShotRevision/Episode anchors and a per-Scene SHA-256 source fingerprint. Unsupported claims are discarded;
deterministic Timeline remains usable.

The local model path reuses the existing isolated `Qwen3-VL-4B-Instruct` base checkpoint in **text-only** mode.
The new G2 runner loads the model once, processes Scenes sequentially, and never opens video/images.

## 9. Next safe order

```text
1. user-local run G2.3/G2.4 unit/contract tests
2. user-local G2 local Qwen runtime preflight
3. real text-only Qwen acceptance on BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
4. verify Narrative only changes title/story_summary and Shot facts remain byte-for-structure unchanged
5. mark G2.3/G2.4 FINAL PASS only after real acceptance
6. add G2.5 API
7. add G2.6 ordinary-user Scene Timeline UI last
```

If G2.3/G2.4 fails, fix those layers. Do not retune G1 or alter the frozen G2.1/G2.2 foundation to hide the regression.

Hosted GitHub Actions must not be used; commits use `[skip ci]`.
