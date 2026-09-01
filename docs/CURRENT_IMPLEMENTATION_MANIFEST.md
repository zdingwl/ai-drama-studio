# AI Drama Studio — Current Implementation Manifest

> Purpose: code-aligned executable CURRENT manifest.  
> Last synchronized: **2026-09-01 +08:00**

## Repository baseline

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Architecture: Reference Video V2 + Breakdown Fast Grounded V2
FastAPI app version: 2.4.1
Formal Character runtime: Character V10.1

P1/P2 implementation acceptance: CONDITIONAL PASS
Fast Grounded G1: REAL ACCEPTED / PRODUCTION / FROZEN
Window Context: SEGMENT-INDEX V4 / REAL ACCEPTED / PRODUCTION / FROZEN
Exact-Shot: COMPACT-RECONSTRUCTION V3 / REAL ACCEPTED / PRODUCTION / FROZEN
P2-E6 Fusion: E6-V2 / REAL PRODUCTION ACCEPTED / FROZEN
P2.6 Windows / real-model acceptance: PASS
G2.1-G2.5: FINAL PASS / FROZEN
G2.6 ordinary-user Scene Timeline UI: IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
P4 Draft-guided Scene/Prop: IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character: V1 / FINAL PASS / FROZEN
P6 Final Breakdown read model: V1 / IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
P6 Final Character renderer: IMPLEMENTED / VISUAL ACCEPTANCE PENDING
P6 Final Scene/Prop fill-back: IMPLEMENTED / USER-LOCAL ACCEPTANCE PENDING
P7.1 Localization Source Package: V1 / IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
P7.2 Localization Draft: V1 / IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
Stage 04 本土化剧本: IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
Stage 05 镜头重制方案: LOCKED / PLANNED
Stage 06 生成·质检·交付: LOCKED / PLANNED
```

Executable CURRENT = `PROJECT_STATE + this manifest + current code/tests`.

## Repository workflow

```text
Documentation-only synchronization -> direct main; do not create a branch or PR.
Code/behavior changes -> direct main by default; do not create a feature branch or PR by default.
Only create/use a branch or PR when the user explicitly asks for one.
Hosted GitHub Actions -> not acceptance evidence.
All commits -> [skip ci].
```

## Frozen production Breakdown chain

```text
Episode Current ShotRevision
→ PROCESSING BreakdownRun
→ Episode ASR
→ OCR
→ Qwen3-VL one model load
   ├─ Window Segment-index v4
   └─ Exact-Shot Compact-Reconstruction v3
→ immutable exact-Shot VLM_OUTPUT
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

## Hard semantic invariants

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
G2 Scene-local P1/P2 refs != Character identity
G2 Scene Timeline != Final Character / Final Scene / Final Prop truth
ASR-origin dialogue text = verbatim truth
OCR-origin visible text = verbatim truth
P7 source_dialogue/source_on_screen_text = immutable downstream source truth
translated/localized/final copy must never overwrite P7 source fields
```

Character V10.1 hard gates remain protected. Do not weaken identity logic because of Breakdown or localization hints.

## P5 frozen Character bridge

```text
Final ShotCharacterBinding
→ current ShotRevision-safe Scene-local presence signatures
→ unique exact one-to-one match only
→ safely resolve anonymous display
```

Accepted user-local evidence:

```text
unit tests = 7 passed
real runner = READY
people = 4
resolved = 1
unresolved = 3
Scene1 P2 -> 人物 001 / FINAL_SHOT_BINDING_SIGNATURE_V1
```

Status: **P5 V1 / FINAL PASS / FROZEN**.

## P6 Final Breakdown read model

```text
frozen G2 Scene Timeline
+ frozen P5 Character resolution
+ current exact Final Scene / Prop bindings
→ ordinary-user P6 read model
```

Rules:

```text
P5 RESOLVED -> safe Final Character display
P5 UNRESOLVED -> anonymous 人物N
one G2 Scene -> Final Scene only when all exact current Shots bind one same Final Scene
Final Prop -> only exact ShotPropBinding
G2 prop observations remain separate
Character and Scene/Prop fail-closed domains are independent
frozen G2 timeline is never rewritten
```

Endpoint:

```text
GET /api/episodes/{episode_id}/breakdown-read-model
```

Status: **P6 V1 / IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING**.

## P7.1 Localization Source Package

Implementation:

```text
engine/app/localization_source_contract_v1.py
engine/app/localization_source_v1.py
engine/app/breakdown_read_model_routes_v1.py
engine/tests/v2/test_localization_source_v1.py
engine/tests/v2/test_localization_source_routes_v1.py
scripts/run_localization_source_acceptance_v1.py
docs/P7_LOCALIZATION_SOURCE_V1.md
```

Endpoint:

```text
GET /api/episodes/{episode_id}/localization-source
```

Authority direction:

```text
current P6 read model
+ Project source_language / target_language / target_region
→ immutable localization-source-v1
```

The package carries version anchors, Scene/Shot context, reference URLs, verbatim ASR/OCR source text, safe person display, Final Scene/Props and cinematography. It performs no translation and writes no business state.

Status: **P7.1 V1 / IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING**.

## P7.2 Localization Draft / Stage 04

### Backend

```text
engine/app/localization_draft_contract_v1.py
engine/app/localization_draft_v1.py
engine/app/localization_draft_workflow_v1.py
engine/app/breakdown_read_model_routes_v1.py
```

Persistence:

```text
v2_localization_revisions
```

Every write creates a new immutable Episode-level Revision with:

```text
source BreakdownRun / ShotRevision / AssetRevision anchors
source fingerprint
immutable P7.1 source snapshot
separate target-side edits snapshot
status / kind / note / revision number
```

Supported decisions:

```text
PENDING
LOCALIZE
KEEP_SOURCE
OMIT
```

`LOCALIZE` target layers:

```text
translated_text
localized_text
final_text
```

Write boundary rules:

```text
source_text is never accepted from edit requests
base_revision_id prevents lost updates
DRAFT may save partial target copy
IN_REVIEW / FINAL require zero PENDING rows
IN_REVIEW / FINAL require final_text for every LOCALIZE row
IN_REVIEW cannot be PATCH-ed until explicitly returned to DRAFT
FINAL is immutable
stale source blocks write/review/finalize until explicit rebase
```

Rebase only carries an old edit when `source_key + kind + Scene/Shot + timing + source_text` all match exactly.

API:

```text
GET   /api/episodes/{episode_id}/localization-draft
POST  /api/episodes/{episode_id}/localization-draft
PATCH /api/episodes/{episode_id}/localization-draft
POST  /api/episodes/{episode_id}/localization-draft/status
POST  /api/episodes/{episode_id}/localization-draft/rebase
GET   /api/episodes/{episode_id}/localization-revisions
GET   /api/localization-revisions/{revision_id}
```

### Frontend

```text
frontend/src/types/localization.ts
frontend/src/api/localization.ts
frontend/src/components/LocalizationStageV1.vue
frontend/src/utils/stageStatus.ts
frontend/src/views/ProjectStudioV3.vue
frontend/src/views/ProjectList.vue
```

Stage 04 ordinary-user workflow:

```text
select Episode
→ create draft from current P7.1 source
→ read source text beside Shot context
→ choose processing decision
→ edit translation / localized rewrite / final copy
→ save new Revision
→ send to review
→ return to edit OR finalize
```

Truthful Stage 04 state:

```text
no draft          -> not_started / 未开始
DRAFT             -> editing / 编辑中
IN_REVIEW         -> review / 待复核
stale source      -> blocked / 阻塞
all Episodes FINAL-> completed / 已完成
```

Stage 04 is now enabled in the project shell and project dashboard. Stage 05/06 remain disabled.

### Tests / audit

```text
engine/tests/v2/test_localization_draft_v1.py
engine/tests/v2/test_localization_draft_workflow_v1.py
engine/tests/v2/test_localization_draft_routes_v1.py
frontend/src/utils/stageStatus.test.ts
scripts/run_localization_draft_acceptance_v1.py
```

The real P7.2 runner is read-only. It never creates or modifies the current production draft.

Status: **P7.2 V1 / Stage 04 IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING**.

## Current frontier

```text
1. keep G1 + G2.1-G2.5 + P5 frozen
2. user-local accept P6 when available
3. user-local accept P7.1/P7.2 backend + real read-only audit + Stage 04 frontend/visual flow
4. P4 local acceptance remains separately pending
5. next code frontier = Stage 05 versioned Shot Remake Plan / generation-input contract
6. Stage 05 must consume FINAL P7.2 + version-safe P6/P7 source anchors, not mutable UI state
7. Stage 06 remains locked until its generation/QC/delivery workflow exists
```

No assistant-local full pytest/Vitest/vue-tsc/Vite/CUDA PASS is claimed. Hosted GitHub Actions remain intentionally unused.