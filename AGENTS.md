# AI Drama Studio — Agent Entry Rules

Current architecture: **Reference Video V2 + Breakdown Fast Grounded V2**.  
Formal Character baseline: **Character V10.1 + explicit Shot Character Assignment**.

## 1. Executable CURRENT

```text
P1/P2 implementation acceptance       = CONDITIONAL PASS
Fast Grounded G1                      = REAL ACCEPTED / PRODUCTION / FROZEN
Window Context                        = Segment-index v4 / accepted / frozen
Exact-Shot                            = Compact-reconstruction v3 / accepted / frozen
P2-E6 anonymous continuity Fusion     = E6-v2 / real production accepted / frozen
P2.6 Windows / real-model acceptance  = PASS
G2 Scene Timeline Contract            = v1 / FINAL PASS / FROZEN FOUNDATION
G2 Deterministic Assembler            = v1 / FINAL PASS / FROZEN FOUNDATION
G2 Scene Narrative Core               = v1.5 / FINAL PASS / FROZEN
G2 Local Qwen text runtime            = REAL ACCEPTED / FROZEN BASELINE
G2 Source / Support Validator         = v1.5 / FINAL PASS / FROZEN
G2.3/G2.4 real-model acceptance       = PASS
G2.5 Scene Timeline API               = v1 / FINAL PASS / FROZEN
G2.5 Windows/CUDA local acceptance    = PASS
G2.6 ordinary-user result UI          = IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
P4 Draft-guided Scene/Prop            = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character                  = IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
```

Truth priority:

```text
PROJECT_STATE + CURRENT_IMPLEMENTATION_MANIFEST + current code/tests = executable CURRENT
```

G1 and G2.1/G2.2 are frozen. G2.3/G2.4 and G2.5 are also frozen after user-local regression + real-model acceptance on 2026-08-31. Do not reopen any frozen layer without a concrete new regression.

### Repository workflow

```text
Documentation-only synchronization/update:
  -> edit main directly
  -> do not create a branch or PR only for docs

Code/behavior changes:
  -> use a feature branch + Draft PR by default
  -> if the user explicitly asks to change/merge directly on main, follow that instruction

All commits:
  -> include [skip ci]
  -> do not use hosted GitHub Actions as acceptance evidence
```

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
12. docs/BREAKDOWN_G2_SCENE_NARRATIVE_CONTRACT.md
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

## 4. Final accepted evidence

Frozen G1/P2.6 Run:

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
Shot0001 props include 蓝色玫瑰花束 + 玻璃花瓶
Fusion = breakdown-p2-fusion-episode-context-e6-v2
```

G2.1/G2.2 accepted evidence:

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

G2.3/G2.4 final accepted evidence:

```text
python -m pytest engine/tests/v2/test_breakdown_scene_narrative_v1.py engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py engine/tests/v2/test_breakdown_scene_narrative_real_regression_v1.py -q
15 passed

preflight = READY / cuda / missing=[]
runner Scene1 = READY
runner Scene2 = READY
overlay_status = READY
warnings = []
shot_objects_unchanged = YES
structure_gate = PASS
narrative_gate = PASS
acceptance_machine_gate = PASS
```

Accepted Narrative examples:

```text
Scene1 title = 走廊争花
Scene1 summary = 老年女性质问年轻女性为何将花放在自家花瓶，年轻女性称花在走廊，双方争执并最终以给钱解决，年轻女性愤怒指责对方。

Scene2 title = 客厅争执
Scene2 summary = 人物2指责人物1对邻居偷花一事不作为，称其结婚八年从未支持过自己，人物1则表示自己会自行解决。
```

Human review accepted these as Scene-level Narrative: ASR claims remain explicitly attributed, no Final identity is created, and frozen Shot objects are unchanged.

G2.5 accepted evidence:

```text
python -m pytest engine/tests/v2/test_breakdown_scene_timeline_result_v1.py engine/tests/v2/test_breakdown_scene_timeline_routes_v1.py -q
12 passed

materialize accepted Run:
scene_count = 2
accepted_title_count = 2
accepted_summary_count = 2
warning_count = 0
runtime_profile = breakdown-g2-scene-narrative-qwen3-local-v1
```

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

Never relax same-sample cannot-link, face conflict, >=3 independent evidence rule, ambiguity rules, explicit Shot assignment or Final Gate because of Breakdown hints.

P5 identity reconciliation is one-way only:

```text
Final ShotCharacterBinding
→ deterministic Scene-local presence reconciliation
→ resolve Breakdown anonymous display when uniquely safe
```

Breakdown dialogue, ASR names, relationship terms, appearance prose and role hints must never become Character identity authority.

## 7. G2 frozen foundation

Frozen modules include:

```text
engine/app/breakdown_scene_timeline_contract_v1.py
engine/app/breakdown_scene_timeline_assembler_v1.py
engine/app/breakdown_scene_narrative_contract_v1.py
engine/app/breakdown_scene_grounding_v1.py
engine/app/breakdown_scene_narrative_v1.py
engine/app/breakdown_scene_narrative_validator_v1.py
engine/app/breakdown_scene_narrative_qwen3_v1.py
engine/app/breakdown_scene_timeline_result_v1.py
engine/app/breakdown_scene_timeline_routes_v1.py
scripts/run_breakdown_scene_narrative_qwen3.py
scripts/run_breakdown_g2_scene_narrative_acceptance_v1.py
scripts/materialize_breakdown_g2_scene_timeline_v1.py
```

G2.3 LLM authority remains deliberately narrow:

```text
LLM MAY write:
  readable_title
  story_summary

LLM MUST NOT own or rewrite:
  Scene/Shot timestamps or boundaries
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

ASR may support Narrative only as attributed speech/argument content. High-impact event claims must remain attributed or explicit topics. Relationship terms such as 丈夫/妻子/父亲/男友 remain topic-only and cannot bind anonymous people. Numeric quantities must be supported by final provenance.

## 8. Current implementation frontier

G2.6 is present on `main` and consumes the frozen G2.5 Scene Timeline API. It is not FINAL PASS until user-local frontend commands and visual review are observed.

P5 is now present on `main` through merged PR #17. Merge commit: `ab4b11716f5c1c5ead7367119d1b2d787defe8f9`. P5 is still **USER-LOCAL ACCEPTANCE PENDING** and is not FINAL PASS.

Current safe order:

```text
1. keep G1 + G2.1/G2.2 + G2.3/G2.4 + G2.5 frozen
2. finish user-local G2.6 UI acceptance when needed
3. run P5 user-local deterministic + real-Episode acceptance
4. do not mark P5 FINAL PASS without user-local evidence
5. after accepted P5, implement P6 Final identity/asset fill-back + final Breakdown renderers
```

Hosted GitHub Actions must not be used; commits use `[skip ci]`.
