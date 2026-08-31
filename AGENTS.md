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
G2 Scene Timeline Contract            = v1 / implemented / user-local acceptance pending
G2 Deterministic Assembler            = v1 / implemented / user-local acceptance pending
G2 Scene-level text LLM               = UNBLOCKED / NOT IMPLEMENTED
Scene Timeline result UI              = UNBLOCKED / NOT IMPLEMENTED
P5 Draft ↔ Character                  = PAUSED
```

Truth priority:

```text
PROJECT_STATE + CURRENT_IMPLEMENTATION_MANIFEST + current code/tests = executable CURRENT
```

G2.1/G2.2 implementation is not a PASS claim until user-local acceptance is completed.

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
11. docs/BREAKDOWN_G2_SCENE_TIMELINE_CONTRACT.md when working on G2
12. Character docs when relevant
13. current code/tests
14. latest docs/sessions/*.md handoff
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

## 5. E6-v2 continuity rules

```text
Stage1 Window hint:
  listed Shot ordinal = candidate location only
  Exact-Shot appearance must positively support the hint

Stages2..4:
  compact aliases are canonicalized for comparison only
  persisted source appearance text is unchanged
  accepted thresholds are unchanged

Hard safety:
  same-Shot observations = hard cannot-link
  explicit male/female contradiction blocks soft union
  explicit long-hair vs short/bald contradiction blocks soft union
  missing attribute is not conflict
```

Policies:

```text
window hint resolver = window-hint-positive-appearance-support-compact-alias-v2
compact appearance = compact-observation-stable-alias-normalization-v1
```

## 6. Core semantic rules

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

## 7. Character V10.1 is protected

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

## 8. G2 foundation and next safe work

Implemented read-only G2 foundation:

```text
engine/app/breakdown_scene_timeline_contract_v1.py
engine/app/breakdown_scene_timeline_assembler_v1.py
engine/tests/v2/test_breakdown_scene_timeline_v1.py
docs/BREAKDOWN_G2_SCENE_TIMELINE_CONTRACT.md
```

It does not modify the frozen G1 chain and does not create Final assets.

Next safe order:

```text
1. user-local run G2.1/G2.2 tests
2. exercise deterministic assembler on final accepted Run
3. verify 2 Scenes / 30 Shots / Scene-local anonymous people / Shot0001 exact truth / ASR verbatim
4. only after PASS, implement G2.3 Scene-level pure-text LLM
5. add G2.4 support/source validator
6. add G2.5 API
7. add G2.6 ordinary-user Scene Timeline UI
```

Hosted GitHub Actions must not be used; commits use `[skip ci]`.
