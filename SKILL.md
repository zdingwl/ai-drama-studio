---
name: ai-drama-studio-reference-video-v2
version: 3.23.0
description: Reference Video V2 / Fast Grounded Breakdown V2 / Character V10.1；G1/P2.6、G2.1-G2.5、P5 已真实验收并冻结；P6、P7.1、P7.2/Stage 04 已实现待用户本机验收；Stage 05-06 仍锁定。
---

# AI Drama Studio — Reference Video V2 / Fast Grounded Breakdown V2 / Character V10.1

## 0. 恢复项目上下文

必须先读取 GitHub 当前仓库事实：

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/CURRENT_IMPLEMENTATION_MANIFEST.md
→ relevant current phase docs/contracts
→ Character docs when relevant
→ current code/tests
→ latest docs/sessions/*.md handoff
```

Downstream work additionally reads:

```text
docs/P6_FINAL_BREAKDOWN_READ_MODEL_V1.md
docs/P7_LOCALIZATION_SOURCE_V1.md
docs/P7_LOCALIZATION_DRAFT_V1.md
```

Executable CURRENT = `PROJECT_STATE + CURRENT_IMPLEMENTATION_MANIFEST + current code/tests`.

### Git workflow

```text
文档同步 / 状态文档修正：默认直接修改 main，不新建分支或 PR。
代码/行为修改：默认直接修改 main，不新建 feature branch 或 PR。
只有用户明确要求使用分支或 PR 时，才创建/使用分支或 PR。
所有提交使用 [skip ci]；Hosted GitHub Actions 不作为本项目验收手段。
```

## 1. Current baseline

```text
Architecture: Reference Video V2 + Breakdown Fast Grounded V2
Formal Character runtime: Character V10.1
P1/P2 implementation acceptance: CONDITIONAL PASS
Fast Grounded G1: REAL ACCEPTED / PRODUCTION / FROZEN
Window Context: Segment-index v4 / REAL ACCEPTED / FROZEN
Exact-Shot: Compact-reconstruction v3 / REAL ACCEPTED / FROZEN
P2-E6 Fusion: E6-v2 / REAL PRODUCTION ACCEPTED / FROZEN
P2.6 Windows / real-model acceptance: PASS
G2.1-G2.5: FINAL PASS / FROZEN
G2.6 ordinary-user Scene Timeline UI: IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
P4 Draft-guided Scene/Prop: IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character: v1 / FINAL PASS / FROZEN
P6 Final Breakdown read model: v1 / IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
P6 Final Character renderer: IMPLEMENTED / VISUAL ACCEPTANCE PENDING
P6 Final Scene/Prop fill-back: IMPLEMENTED / USER-LOCAL ACCEPTANCE PENDING
P7.1 Localization Source Package: v1 / IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
P7.2 Localization Draft: v1 / IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
Stage 04 本土化剧本: IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
Stage 05 镜头重制方案: LOCKED / PLANNED
Stage 06 生成·质检·交付: LOCKED / PLANNED
```

Do not reopen frozen layers without a concrete regression.

## 2. Frozen production flow

```text
Original Episode
→ Preprocess
→ Shot Detection + frozen ShotRevision
→ PROCESSING BreakdownRun
→ Episode ASR
→ OCR
→ one-load Qwen3-VL Fast Grounded
   ├─ Window Segment-index v4
   └─ Exact-Shot Compact-reconstruction v3
→ immutable exact-Shot VLM_OUTPUT
→ P2-E6-v2 Episode-context Fusion
→ anonymous P1 Draft
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
same_shot_cluster_conflicts = 0
```

## 3. Core semantic boundaries

> **先看懂，再识别，再回填。**

> **Shot 是最小视觉证据与定位单位，不是连续理解的上下文上限。**

> **Exact-Shot visible fact > Window Context.**

> **Scene Timeline 是最终用户阅读拉片结果的主要单位。**

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
subject_A/B = Shot-local observation labels only
same-Shot observations = hard cannot-link
G2 Scene-local P1/P2 != Character identity
G2 Scene Timeline != Final Character / Final Scene / Final Prop truth
ASR-origin dialogue text = verbatim truth
OCR-origin visible text = verbatim truth
P7 source_dialogue/source_on_screen_text = immutable downstream source truth
translated/localized/final copy != source truth
```

## 4. Character V10.1 / frozen G2 + P5

Never weaken Character identity safety because of Breakdown/localization hints.

G2.1 through G2.5 are frozen. G2.3 LLM MAY write only readable title/summary; it MUST NOT own timestamps, boundaries, people identity/count, Shot facts, ASR/OCR, props, cinematography or Final Assets.

P5 authority remains:

```text
Final ShotCharacterBinding
→ Scene-local deterministic exact presence-signature reconciliation
→ resolve anonymous Breakdown person only when uniquely safe
```

Accepted P5 evidence:

```text
unit contract = 7 passed
real Episode runner = READY
scene_count = 2
person_count = 4
resolved_count = 1
unresolved_count = 3
Scene1 P2 -> 人物 001 / FINAL_SHOT_BINDING_SIGNATURE_V1
```

Other three people remain unresolved. **P5 = FINAL PASS / FROZEN**.

## 5. P6 implemented composition

P6 reads only frozen/current truth:

```text
P5 RESOLVED -> existing Final Character id/name/cover
P5 UNRESOLVED -> 人物N
all exact Shots in one G2 Scene agree on one Final Scene -> final_scene
current ShotPropBinding -> final_props
G2 props remain separate visible-observation truth
```

Never use Draft/G2 prose or label similarity as Final Scene/Prop authority. P6 must not mutate G2 Timeline, P5 resolution, Final bindings, ASR or OCR.

Detailed contract/tests: `docs/P6_FINAL_BREAKDOWN_READ_MODEL_V1.md`.

## 6. P7.1 immutable localization source

```text
current P6 read model
+ Project source_language / target_language / target_region
→ localization-source-v1
```

It carries version anchors, Scene/Shot references, visual description, action/performance, verbatim source dialogue, verbatim OCR, safe person display, Final Scene, G2 observed props separate from Final Props, and cinematography.

Rules:

```text
source_dialogue[].source_text = immutable
source_on_screen_text[].source_text = immutable
Scene-local P* = internal join only, not downstream Character identity
translated_text/localized_text/final_text = forbidden inside P7.1 source package
old Dialogue/Asset/Voice/Generation tables = not current P7 source authority
```

Endpoint:

```text
GET /api/episodes/{episode_id}/localization-source
```

Detailed boundary/tests: `docs/P7_LOCALIZATION_SOURCE_V1.md`.

## 7. P7.2 revisioned Localization Draft / Stage 04

Stage 04 now has real persistent business state.

```text
P7.1 immutable source snapshot
→ append-only Episode Localization Revision
→ DRAFT
→ IN_REVIEW
→ FINAL
```

Write request owns only target-side fields:

```text
source_key
decision
translated_text
localized_text
final_text
note
```

`source_text` is not writable.

Decisions:

```text
PENDING
LOCALIZE
KEEP_SOURCE
OMIT
```

Hard rules:

```text
all writes create a new Revision
base_revision_id prevents lost updates
DRAFT may save partial translation/localization work
IN_REVIEW / FINAL require no PENDING rows
IN_REVIEW / FINAL require final_text for every LOCALIZE row
IN_REVIEW must explicitly return to DRAFT before editing
FINAL is immutable
source fingerprint mismatch -> stale/read-only
stale draft requires explicit rebase
rebase carries old edits only when source_key + kind + Scene/Shot + timing + source_text all match exactly
```

Stage 04 states:

```text
no draft -> 未开始
DRAFT -> 编辑中
IN_REVIEW -> 待复核
stale -> 阻塞
all Episodes FINAL -> 已完成
```

UI now shows source text read-only beside Shot context and editable translation/localized/final fields, plus save/review/return/finalize/rebase and Revision history.

Detailed workflow/tests: `docs/P7_LOCALIZATION_DRAFT_V1.md`.

## 8. Testing / CI discipline

Do not claim assistant-local full pytest/CUDA execution. User-local evidence is acceptance truth. Hosted GitHub Actions must not be used; commits use `[skip ci]`.

P7.2 has deterministic tests plus a read-only real Episode audit runner; it must not create or mutate production draft state during acceptance.

## 9. Immediate safe work

```text
1. keep G1 + G2.1-G2.5 + P5 frozen
2. user-local accept P6 when available
3. user-local accept P7.1/P7.2 backend + real read-only runners + Stage 04 frontend/visual flow
4. P4 Scene/Prop local acceptance remains separately pending
5. next code frontier = Stage 05 versioned Shot Remake Plan / generation-input contract
6. Stage 05 must consume FINAL P7.2 copy + version-safe P6/P7 anchors
7. keep Stage 06 locked until its own executable generation/QC/delivery workflow exists
```