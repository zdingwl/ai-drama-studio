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

PR #17 merged and closed. Merge commit:

```text
ab4b11716f5c1c5ead7367119d1b2d787defe8f9
```

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

P5 is read-only and fail-closed. It does not create identity, modify Character V10.1, modify Final Gate, rewrite LocalSubject, or write Final bindings.

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
Scene1 P1 -> UNRESOLVED
Scene2 P1 -> UNRESOLVED
Scene2 P2 -> UNRESOLVED
```

The accepted resolved signature is exact on Shots `3,4,5,6,9,10,11`; unresolved people correctly remain anonymous.

Upstream real Character data used by this acceptance:

```text
resolved CharacterCandidates = 3
Final Characters = 3
Episode Final ShotCharacterBindings = 29
AssetRevision = revision 14 / AUTO
```

Status: **P5 V1 / FINAL PASS / FROZEN**.

## P6 Final Breakdown read model

P6 is a separate read-only composition layer. It does not change G2 or P5 ownership.

Implementation:

```text
engine/app/breakdown_read_model_contract_v1.py
engine/app/breakdown_read_model_v1.py
engine/app/breakdown_read_model_routes_v1.py
engine/tests/v2/test_breakdown_read_model_v1.py
engine/tests/v2/test_breakdown_read_model_routes_v1.py
frontend/src/types/breakdown-read-model.ts
frontend/src/types/scene-timeline.ts
frontend/src/utils/breakdownReadModelUi.ts
frontend/src/utils/breakdownReadModelUi.test.ts
frontend/src/api/scene-timeline.ts
docs/P6_FINAL_BREAKDOWN_READ_MODEL_V1.md
```

Read endpoint:

```text
GET /api/episodes/{episode_id}/breakdown-read-model
```

Composition direction:

```text
Frozen G2 Scene Timeline
+
Frozen P5 current Scene-local resolution
+
current AssetRevision + existing Final Character id/name/cover
→ P6 identity overlay
→ ordinary-user display projection
```

Fail-closed gates include:

```text
same Episode
same BreakdownRun
same ShotRevision
same current AssetRevision
consistent P5 aggregate counts
exact Scene ordinal set
exact Scene-local P* set
matching anonymous display row
current Character id/name matches P5 resolution
```

Any mismatch keeps the whole Episode identity display anonymous. `UNRESOLVED` P5 people always remain `人物N`.

Backend response preserves the entire frozen G2 payload under `timeline`; identity is a separate overlay. The frontend ordinary Episode reader consumes P6 and changes display-only person names/assets after a second validation gate. Historical Run reading continues to use frozen G2.5 without current Character projection.

Acceptance evidence currently available:

```text
P6 backend deterministic tests = added / NOT USER-LOCAL RUN YET
P6 route tests = added / NOT USER-LOCAL RUN YET
P6 frontend Vitest = added / NOT USER-LOCAL RUN YET
isolated new frontend P6 core `tsc --strict` = PASS in assistant execution environment
full repository clone/test = unavailable in assistant environment (github.com DNS resolution failed)
```

Status: **P6 V1 / IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING**.

Do not mark P6 FINAL PASS before Python tests, frontend Vitest/typecheck/build, lockfile synchronization, and visual review.

## Current frontier

```text
1. keep G1 + G2.1-G2.5 + P5 frozen
2. finish G2.6 local UI acceptance when needed
3. P4 Scene/Prop local acceptance remains pending
4. finish P6 user-local acceptance and final visual asset rendering polish
```

P6 must remain a separate composition layer. It may render Final Character names/assets only for P5 `RESOLVED` people; `UNRESOLVED` people remain `人物N`. It must not mutate frozen G2, P5, ASR/OCR truth, or Final Character bindings.