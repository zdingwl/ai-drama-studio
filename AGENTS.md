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
G2.1-G2.5                             = FINAL PASS / FROZEN
G2.6 ordinary-user result UI          = IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
P4 Draft-guided Scene/Prop            = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character                  = v1 / FINAL PASS / FROZEN
P6 Final Breakdown read model         = v1 / IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
P6 Final Character renderer           = IMPLEMENTED / VISUAL ACCEPTANCE PENDING
P6 Final Scene/Prop fill-back         = IMPLEMENTED / USER-LOCAL ACCEPTANCE PENDING
P7.1 Localization Source Package      = v1 / IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
Stage 04 本土化剧本                  = LOCKED / REVISIONED DRAFT NOT IMPLEMENTED
Stage 05 镜头重制方案                = LOCKED / PLANNED
Stage 06 生成·质检·交付             = LOCKED / PLANNED
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
5. relevant current phase docs/contracts
6. Character docs when relevant
7. current code/tests
8. latest docs/sessions/*.md handoff
```

For downstream work also read:

```text
docs/P6_FINAL_BREAKDOWN_READ_MODEL_V1.md
docs/P7_LOCALIZATION_SOURCE_V1.md
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
P7 source_dialogue/source_on_screen_text = immutable downstream source truth
translated/localized/final copy != source truth
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

Never relax same-sample cannot-link, face conflict, >=3 independent evidence/images, ambiguity rules, explicit Shot assignment or Final Gate because of Breakdown/localization hints.

## 6. P5 frozen identity bridge

```text
Final ShotCharacterBinding
→ deterministic Scene-local exact presence reconciliation
→ resolve Breakdown anonymous display when uniquely safe
```

P5 never uses prose, ASR names/speaker labels, relationships, appearance summaries or P1/P2 labels as identity authority.

Accepted user-local evidence:

```text
unit tests = 7 passed
real runner = READY
people = 4
resolved = 1
unresolved = 3
Scene1 P2 -> 人物 001 / FINAL_SHOT_BINDING_SIGNATURE_V1
```

**P5 = FINAL PASS / FROZEN.**

## 7. P6 composition boundary

P6 is composition only:

```text
P5 RESOLVED -> safe Final Character display
P5 UNRESOLVED -> anonymous 人物N
all exact Shots in a G2 Scene agree on one Final Scene -> final_scene
ShotPropBinding -> final_props
G2 props remain separate observation truth
```

Character and Scene/Prop overlays fail closed independently. P6 must never mutate G2/P5/Final bindings or ASR/OCR truth.

## 8. P7.1 localization source boundary

P7.1 is now implemented as a read-only current-source package:

```text
current P6 read model
+ Project source_language / target_language / target_region
→ localization-source-v1
```

It may carry safe Final Character/Scene/Prop display data but may not infer or rewrite them. Scene-local P* is internal join state only and is not downstream business identity.

Immutable P7 source fields include:

```text
source_dialogue[].source_text
source_on_screen_text[].source_text
visual_description
performance
observed_props
cinematography
```

Do not put `translated_text`, `localized_text` or `final_text` inside the P7.1 source package. Those belong to the next revisioned Localization Draft layer.

Old/future-facing `Dialogue / Asset / Voice / Generation` tables in `studio_v2.py` are not current P7 source authority and must not be silently adopted without version-safe migration/design.

## 9. Current implementation frontier

```text
1. keep G1 + G2.1-G2.5 + P5 frozen
2. user-local accept P6 when available
3. user-local accept P7.1 source package on a real Episode
4. P4 local acceptance remains separately pending
5. next code frontier = P7.2 revisioned Localization Draft persistence + edit/review contract
6. unlock Stage 04 only after real editable/revisioned localization behavior exists
7. keep Stage 05/06 locked until their own executable workflows exist
```

P6 acceptance: `docs/P6_FINAL_BREAKDOWN_READ_MODEL_V1.md`.  
P7.1 boundary/acceptance: `docs/P7_LOCALIZATION_SOURCE_V1.md`.

Hosted GitHub Actions must not be used; commits use `[skip ci]`.
