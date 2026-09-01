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
P5 Draft ↔ Character                  = v1 / FINAL PASS / FROZEN
```

Truth priority:

```text
PROJECT_STATE + CURRENT_IMPLEMENTATION_MANIFEST + current code/tests = executable CURRENT
```

Do not reopen any frozen layer without a concrete regression.

### Repository workflow

```text
Documentation-only synchronization/update:
  -> edit main directly
  -> do not create a branch or PR

Code/behavior changes:
  -> edit main directly by default
  -> do not create a feature branch or PR by default
  -> only create/use a branch or PR when the user explicitly asks for one

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
5. relevant Breakdown plans/contracts
6. Character docs when relevant
7. current code/tests
8. latest docs/sessions/*.md handoff
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

Accepted production reference:

```text
Run = BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
Episode = EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
ShotRevision = SHOTREV_1462ac6d9f3948b994fc9bc575fee3a0
Shots = 30
Scenes = 2
LocalSubjects = 4
same-Shot conflicts = 0
```

## 4. Core semantic rules

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
ASR-origin DIALOGUE text = verbatim source truth
OCR-origin text = verbatim source truth
```

Dynamic expression/emotion/action/pose/speaking/screen position/framing are not identity keys.

## 5. Character V10.1 is protected

```text
YOLOX Person Detection
→ capture-first Person Evidence
→ mature MOT
→ YoutuReID project identity
→ RESOLVED / UNRESOLVED
→ explicit Shot × known-Character Assignment
→ Final Character Gate
```

Never relax same-sample cannot-link, face conflict, >=3 independent evidence/images, ambiguity rules, explicit Shot assignment or Final Gate because of Breakdown hints.

## 6. P5 frozen identity bridge

Frozen direction only:

```text
Final ShotCharacterBinding
→ deterministic Scene-local exact presence reconciliation
→ resolve Breakdown anonymous display when uniquely safe
```

P5 never uses Breakdown prose, ASR names/speaker labels, relationship terms, role hints, appearance summaries or P1/P2 labels as identity authority.

Accepted user-local evidence:

```text
unit tests = 7 passed
real runner = READY
people = 4
resolved = 1
unresolved = 3
warnings = []
Scene1 P2 -> 人物 001 / FINAL_SHOT_BINDING_SIGNATURE_V1
```

The other three anonymous people correctly remain unresolved. **P5 = FINAL PASS / FROZEN.**

## 7. G2 frozen foundation

G2.1 through G2.5 are frozen. G2.3 LLM authority remains deliberately narrow:

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

G2.6 is present on `main` and consumes frozen G2.5, but remains user-local acceptance pending.

## 8. Current implementation frontier

```text
1. keep G1 + G2.1-G2.5 + P5 frozen
2. finish G2.6 UI acceptance when needed
3. P4 Draft-guided Scene/Prop local acceptance is still pending
4. next code frontier = P6 Final identity/asset fill-back + final Breakdown read model/renderers
```

P6 rules:

```text
RESOLVED P5 person -> may render existing Final Character name/assets
UNRESOLVED P5 person -> remain anonymous 人物N
P6 must compose, not mutate, frozen G2/P5
ASR/OCR/frozen Shot facts remain unchanged
no prose/speaker/name fallback for identity
```

Hosted GitHub Actions must not be used; commits use `[skip ci]`.
