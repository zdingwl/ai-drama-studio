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
P7.2 Localization Draft               = v1 / IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
Stage 04 本土化剧本                  = IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
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

For current downstream work also read:

```text
docs/P6_FINAL_BREAKDOWN_READ_MODEL_V1.md
docs/P7_LOCALIZATION_SOURCE_V1.md
docs/P7_LOCALIZATION_DRAFT_V1.md
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

## 5. Character V10.1 / P5 protection

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

P5 authority remains one-way:

```text
Final ShotCharacterBinding
→ deterministic Scene-local exact presence reconciliation
→ resolve Breakdown anonymous display when uniquely safe
```

P5 never uses prose, ASR names/speaker labels, relationships, appearance summaries or P1/P2 labels as identity authority. **P5 = FINAL PASS / FROZEN.**

## 6. P6 boundary

P6 is composition only:

```text
P5 RESOLVED -> safe Final Character display
P5 UNRESOLVED -> anonymous 人物N
all exact Shots in a G2 Scene agree on one Final Scene -> final_scene
ShotPropBinding -> final_props
G2 props remain separate observation truth
```

P6 must never mutate G2/P5/Final bindings or ASR/OCR truth.

## 7. P7 localization boundary

### P7.1 immutable source

```text
current P6 read model
+ Project source_language / target_language / target_region
→ localization-source-v1
```

P7.1 may carry safe Final Character/Scene/Prop display data but does not infer or rewrite them. Scene-local P* remains internal join state only.

Do not put target copy inside P7.1 source truth.

### P7.2 revisioned target copy

Stage 04 is now executable through append-only Episode Localization Revisions.

Supported state:

```text
DRAFT -> IN_REVIEW
IN_REVIEW -> DRAFT or FINAL
FINAL -> immutable
```

Supported decisions:

```text
PENDING
LOCALIZE
KEEP_SOURCE
OMIT
```

Hard P7.2 rules:

```text
write request never accepts source_text
all writes create a new Revision
base_revision_id prevents lost updates
DRAFT may save partial translated/localized copy
IN_REVIEW / FINAL require no PENDING entries
IN_REVIEW / FINAL require final_text for every LOCALIZE entry
IN_REVIEW must explicitly return to DRAFT before editing
source fingerprint mismatch -> stale/read-only -> explicit rebase
rebase carries edits only across exact source-key/kind/Scene/Shot/time/source-text equality
```

Stage 04 states:

```text
no draft -> 未开始
DRAFT -> 编辑中
IN_REVIEW -> 待复核
stale -> 阻塞
all Episodes FINAL -> 已完成
```

Stage 05/06 remain locked.

## 8. Current implementation frontier

```text
1. keep G1 + G2.1-G2.5 + P5 frozen
2. user-local accept P6 when available
3. user-local accept P7.1/P7.2 backend + real read-only runners + Stage 04 visual flow
4. P4 local acceptance remains separately pending
5. next code frontier = Stage 05 versioned Shot Remake Plan / generation-input contract
6. Stage 05 must consume FINAL P7.2 copy plus version-safe P6/P7 anchors
7. keep Stage 06 locked until its own generation/QC/delivery workflow exists
```

P6 acceptance: `docs/P6_FINAL_BREAKDOWN_READ_MODEL_V1.md`.  
P7.1 source: `docs/P7_LOCALIZATION_SOURCE_V1.md`.  
P7.2 revision workflow: `docs/P7_LOCALIZATION_DRAFT_V1.md`.

Hosted GitHub Actions must not be used; commits use `[skip ci]`.