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

G2 Scene Timeline Contract: V1 / FINAL PASS / FROZEN FOUNDATION
G2 Deterministic Assembler: V1 / FINAL PASS / FROZEN FOUNDATION
G2 Scene Narrative Core: V1.5 / FINAL PASS / FROZEN
G2 Local Qwen text runtime: REAL ACCEPTED / FROZEN BASELINE
G2 Source / Support Validator: V1.5 / FINAL PASS / FROZEN
G2.3/G2.4 real-model acceptance: PASS
G2.5 Scene Timeline API: V1 / FINAL PASS / FROZEN
G2.5 Windows/CUDA local acceptance: PASS
G2.6 ordinary-user Scene Timeline UI: IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING

P3 current 02 拉片 Shot-card UI: IMPLEMENTED / NOT FINAL ACCEPTED
P4 Draft-guided Scene/Prop: IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character: V1 / FINAL PASS / FROZEN
P6 Final Breakdown read model: V1 / IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
P6 Final Character renderer: IMPLEMENTED ON MAIN / USER-LOCAL VISUAL ACCEPTANCE PENDING
P6 Final Scene/Prop fill-back: IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
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
Shot = smallest visual evidence/location unit
Exact-Shot visible fact > Window Context
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
subject_A/B = Shot-local observation labels only
same-Shot observations = hard cannot-link
G2 Scene-local P1/P2 refs != Character identity
G2 Scene Timeline != Final Character / Final Scene / Final Prop truth
ASR-origin dialogue text = verbatim truth
OCR-origin visible text = verbatim truth
```

## Character V10.1 protected baseline

```text
YOLOX Person Detection
→ capture-first Person Evidence
→ mature MOT
→ YoutuReID project identity
→ RESOLVED / UNRESOLVED
→ explicit Shot × known-Character Assignment
→ Final Character Gate
```

Do not weaken same-sample cannot-link, face conflict, >=3 independent evidence, ambiguity rules, explicit Shot assignment, or Final Gate because of Breakdown hints.

## Frozen G2 architecture

Frozen through G2.5:

```text
G2.1 Timeline Contract
G2.2 Deterministic Assembler
G2.3 Scene Narrative
G2.4 Source/Support Validator
G2.5 Scene Timeline API
```

Accepted baselines:

```text
G2.1/G2.2 = 4 passed
G2.3/G2.4 = 15 passed + real local Qwen acceptance
G2.5 = 12 passed + 2 accepted titles + 2 summaries + 0 warnings
```

G2.6 ordinary-user UI is implemented on `main` but still needs user-local frontend test/typecheck/build + visual review.

## P5 Breakdown ↔ Character safe bridge

Frozen implementation:

```text
engine/app/breakdown_character_bridge_contract_v1.py
engine/app/breakdown_character_bridge_v1.py
engine/tests/v2/test_breakdown_character_bridge_v1.py
scripts/run_breakdown_p5_character_bridge_acceptance_v1.py
docs/P5_BREAKDOWN_CHARACTER_BRIDGE_V1.md
```

Authority direction:

```text
Final ShotCharacterBinding
→ current ShotRevision-safe Scene-local presence signatures
→ unique exact one-to-one match only
→ anonymous LocalSubject display may resolve to existing Final Character
```

Excluded identity authority:

```text
Breakdown prose
dialogue / ASR names
speaker labels
relationships
role hints
appearance summaries
P1/P2 labels themselves
```

Accepted user-local evidence:

```text
unit contract: 7 passed
real runner: READY
scenes = 2
people = 4
resolved = 1
unresolved = 3
warnings = []
Scene1 P2 -> 人物 001 / FINAL_SHOT_BINDING_SIGNATURE_V1
```

Status: **P5 V1 / FINAL PASS / FROZEN**.

## P6 Final Breakdown read model

P6 is a separate read-only composition layer:

```text
Frozen G2 Scene Timeline
+
Frozen P5 Character resolution
+
current Final ShotSceneBinding / ShotPropBinding
+
current Final Character / Scene / Prop display assets
→ independent P6 display overlays
→ ordinary-user result
```

Backend implementation:

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

Frontend implementation:

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

Read endpoint:

```text
GET /api/episodes/{episode_id}/breakdown-read-model
```

Character rule:

```text
P5 RESOLVED + exact current anchors -> existing Final Character id/name/cover
P5 UNRESOLVED -> 人物N
```

Final Scene rule:

```text
exact current ShotRevision
→ every Shot inside one G2 Scene has ShotSceneBinding
→ all bindings point to the same existing Final Scene
→ display-only final_scene
otherwise final_scene = null
```

Final Prop rule:

```text
current ShotPropBinding -> display-only final_props[] for that Shot
G2 props[] remains independent visible-observation truth
no Draft/G2 string similarity is an asset binding authority
```

Fail-closed domains are independent:

```text
bad Character overlay -> people anonymous, safe Final Scene/Prop retained
bad Scene/Prop overlay -> final_scene/final_props cleared, safe Character retained
```

Backend preserves frozen G2 under `timeline`. Frontend applies a second exact Scene/Shot overlay check before adding display-only `final_character`, `final_scene`, `final_props`. Historical Run reading remains frozen G2.5 and never receives current Final assets.

Ordinary-user renderer:

```text
Scene hero -> 本场人物: Character cover/name
Shot inspector -> 人物: Character cover/name
Scene hero -> 最终场景: Final Scene cover/name card
Shot inspector -> 最终道具: Final Prop cards
Shot inspector -> 道具观察: original frozen G2 prop facts
```

Acceptance evidence currently available:

```text
backend/route/asset-overlay/independence tests = ADDED / NOT USER-LOCAL RUN YET
frontend Character/Scene/Prop projection tests = ADDED / NOT USER-LOCAL RUN YET
isolated P6 TypeScript display types/projection `tsc --strict` = PASS in assistant environment
isolated avatar helper `tsc --strict` = PASS in assistant environment
full Vue typecheck/build = NOT RUN; vue/compiler-sfc/vue-tsc unavailable in assistant environment
full repository pytest/Vitest = NOT CLAIMED
```

Real runner reports Character + Final Scene + G2 Prop vs Final Prop and requires `timeline_preserved=true`.

Status: **P6 V1 / IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING**.

Do not mark P6 FINAL PASS before Python tests, real Episode runner, frontend Vitest/typecheck/build, lockfile synchronization and ordinary-user visual review.

## Current frontier

```text
1. keep G1 + G2.1-G2.5 + P5 frozen
2. user-local accept P6 end-to-end
3. close G2.6 visual acceptance together with P6 result-page review
4. P4 Draft-guided Scene/Prop local acceptance remains separately pending
5. then continue the next product workflow stage without reopening frozen recognition layers
```

P6 remains composition only. Final Character uses P5 RESOLVED authority; Final Scene/Prop use explicit Final Shot bindings. It must not mutate frozen G2, P5, ASR/OCR truth or Final bindings.