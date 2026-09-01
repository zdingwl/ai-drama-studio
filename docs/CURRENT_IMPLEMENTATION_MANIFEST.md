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
Stage 04 本土化剧本: LOCKED / REVISIONED DRAFT NOT IMPLEMENTED
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

Backend:

```text
engine/app/breakdown_read_model_contract_v1.py
engine/app/breakdown_read_model_v1.py
engine/app/breakdown_read_model_routes_v1.py
engine/app/breakdown_final_asset_overlay_v1.py
engine/tests/v2/test_breakdown_read_model_v1.py
engine/tests/v2/test_breakdown_read_model_routes_v1.py
engine/tests/v2/test_breakdown_final_asset_overlay_v1.py
engine/tests/v2/test_breakdown_read_model_asset_independence_v1.py
scripts/run_breakdown_p6_read_model_acceptance_v1.py
```

Frontend:

```text
frontend/src/types/breakdown-read-model.ts
frontend/src/types/scene-timeline.ts
frontend/src/utils/breakdownReadModelUi.ts
frontend/src/utils/breakdownReadModelUi.test.ts
frontend/src/utils/breakdownReadModelAssetsUi.test.ts
frontend/src/utils/sceneTimelineUi.ts
frontend/src/utils/sceneTimelineUi.test.ts
frontend/src/api/scene-timeline.ts
frontend/src/components/SceneTimelineResultsV1.vue
```

Rules:

```text
P5 RESOLVED -> safe Final Character display
P5 UNRESOLVED -> anonymous 人物N
one G2 Scene -> Final Scene only when all its exact current Shots bind one same Final Scene
Final Prop -> only exact ShotPropBinding
G2 prop observations remain separate
Character and Scene/Prop fail-closed domains are independent
frozen G2 timeline is never rewritten
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
→ localization-source-v1
```

The package carries:

```text
BreakdownRun / ShotRevision / AssetRevision anchors
Scene/Shot timing + reference URLs
visual description + performance
verbatim source dialogue
verbatim OCR source text
safe person display / optional Final Character
Final Scene
G2 observed props separate from Final Props
cinematography
```

Scene-local P* refs are internal join keys only and are not exported as downstream person identity objects.

Old/future-facing `Dialogue / Asset / Voice / Generation` tables in `studio_v2.py` are not current P7 authority. P7.1 performs no translation, creates no localization revision and writes no business state.

Tests explicitly cover verbatim ASR/OCR preservation, safe identity projection, G2 observed Prop vs Final Prop separation, version mismatch rejection, non-current source rejection and strict rejection of downstream `localized_text` inside the source contract.

Real runner:

```text
python scripts/run_localization_source_acceptance_v1.py <EPISODE_ID>
```

Required signal:

```text
source_truth_preserved = true
```

Status: **P7.1 V1 / IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING**.

## Current frontier

```text
1. keep G1 + G2.1-G2.5 + P5 frozen
2. user-local accept P6 when available
3. user-local accept P7.1 source package
4. P4 local acceptance remains separately pending
5. next code frontier = P7.2 revisioned Localization Draft persistence + edit/review contract
6. unlock Stage 04 only after a real editable/revisioned localization workflow exists
7. keep Stage 05/06 locked until their own executable workflows exist
```

No assistant-local full pytest/CUDA PASS is claimed. Hosted GitHub Actions remain intentionally unused.
