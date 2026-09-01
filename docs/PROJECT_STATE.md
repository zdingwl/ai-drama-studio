# AI Drama Studio — Project State

> **Last synchronized:** 2026-09-01 +08:00  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Branch:** `main`  
> **Architecture:** Reference Video V2 + Breakdown Fast Grounded V2  
> **FastAPI app version:** `2.4.1`  
> **Formal Character runtime:** Character V10.1

## 1. Current truth

```text
P1/P2 implementation acceptance       = CONDITIONAL PASS
Fast Grounded V2 baseline             = APPROVED / G1 FROZEN
Window Context contract               = SEGMENT-INDEX V4 / REAL ACCEPTED / PRODUCTION / FROZEN
Exact-Shot contract                   = COMPACT-RECONSTRUCTION V3 / REAL ACCEPTED / PRODUCTION / FROZEN
P2-E6 Fusion                          = E6-V2 / REAL PRODUCTION ACCEPTED / FROZEN
P2.6 Windows / real-model acceptance  = PASS
G2 Scene Timeline Contract            = V1 / FINAL PASS / FROZEN FOUNDATION
G2 Deterministic Assembler            = V1 / FINAL PASS / FROZEN FOUNDATION
G2 Scene Narrative Core               = V1.5 / FINAL PASS / FROZEN
G2 Local Qwen text runtime            = REAL ACCEPTED / FROZEN BASELINE
G2 Source / Support Validator         = V1.5 / FINAL PASS / FROZEN
G2.3/G2.4 real-model acceptance       = PASS
G2.5 Scene Timeline API               = V1 / FINAL PASS / FROZEN
G2.5 Windows/CUDA local acceptance    = PASS
G2.6 ordinary-user result UI          = IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
P3 current 02 拉片 Shot-card UI       = IMPLEMENTED / NOT FINAL ACCEPTED
P4 Draft-guided Scene/Prop            = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character                  = V1 / FINAL PASS / FROZEN
P6 Final Breakdown read model         = V1 / IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
same-Shot hard safety                 = PASS / conflicts=0
```

Frozen layers must not be reopened without a concrete regression.

Repository workflow:

```text
Documentation-only synchronization = edit main directly; do not create a branch or PR.
Code/behavior change = edit main directly by default; do not create a feature branch or PR by default.
Only create/use a branch or PR when the user explicitly asks for one.
Hosted GitHub Actions = not used for acceptance.
All commits = [skip ci].
```

## 2. Accepted production Breakdown reference

```text
Run = BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
Episode = EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
ShotRevision = SHOTREV_1462ac6d9f3948b994fc9bc575fee3a0
Shots = 30
status = READY
whole run ~= 14.017 min
Window = 4/4 READY
Exact-Shot = 6/6 READY
Scenes = 2
LocalSubjects = 4
same-Shot conflicts = 0
Shot0001 subjects = 0
```

Production chain:

```text
Episode Current ShotRevision
→ PROCESSING BreakdownRun
→ Episode ASR
→ OCR
→ one-load Qwen3-VL Fast Grounded
   ├─ Window Segment-index v4
   └─ Exact-Shot Compact-Reconstruction v3
→ immutable exact-Shot VLM_OUTPUT
→ P2-E6-v2 Episode-context Fusion
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

## 3. Hard semantic invariants

```text
Shot = smallest visual evidence/location unit
Exact-Shot visible fact > Window Context
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
subject_A/B = Shot-local labels only
same-Shot observations = hard cannot-link
G2 Scene-local P1/P2 != Character identity
G2 Scene Timeline != Final Character / Final Scene / Final Prop truth
ASR-origin dialogue text = verbatim truth
OCR-origin visible text = verbatim truth
```

Character V10.1 remains protected:

```text
YOLOX Person Detection
→ capture-first Person Evidence
→ mature MOT
→ YoutuReID project identity
→ RESOLVED / UNRESOLVED
→ explicit Shot × known-Character Assignment
→ Final Character Gate
```

Never weaken same-sample cannot-link, face conflict, >=3 independent evidence/images, ambiguity rules, explicit Shot assignment or Final Gate because of Breakdown hints.

## 4. Frozen G2 status

```text
G2.1 Scene Timeline Contract = FINAL PASS / FROZEN FOUNDATION
G2.2 Deterministic Assembler = FINAL PASS / FROZEN FOUNDATION
G2.3 Scene Narrative = FINAL PASS / FROZEN
G2.4 Source/Support Validator = FINAL PASS / FROZEN
G2.5 Scene Timeline API = FINAL PASS / FROZEN
```

Accepted G2 evidence includes:

```text
G2.1/G2.2 tests = 4 passed
G2.3/G2.4 regression = 15 passed
G2.5 API tests = 12 passed
G2.5 materialization = 2 titles + 2 summaries + 0 warnings
```

G2.6 is implemented on `main` but remains user-local acceptance pending. Do not mark G2.6 FINAL PASS until frontend test/typecheck/build and visual review are supplied.

## 5. P5 Draft ↔ Character final acceptance

P5 merged from PR #17, merge commit:

```text
ab4b11716f5c1c5ead7367119d1b2d787defe8f9
```

Frozen authority direction:

```text
Final ShotCharacterBinding
→ exact current ShotRevision-safe Scene-local presence signatures
→ unique one-to-one exact match only
→ safely resolve anonymous Breakdown display
```

P5 does not create identity, rewrite LocalSubject, use dialogue/ASR names/relationships/appearance as identity authority, modify Character V10.1, modify Final Gate, or write Final bindings.

User-local deterministic acceptance:

```text
python -m pytest engine/tests/v2/test_breakdown_character_bridge_v1.py -q
7 passed
```

Real Episode acceptance:

```text
status = READY
scene_count = 2
person_count = 4
resolved_count = 1
unresolved_count = 3
warnings = []

Scene 1 P1 = UNRESOLVED
Scene 1 P2 = RESOLVED -> 人物 001 / FINAL_SHOT_BINDING_SIGNATURE_V1
Scene 2 P1 = UNRESOLVED
Scene 2 P2 = UNRESOLVED
```

The resolved mapping is an exact unique signature match on Shots `3,4,5,6,9,10,11`. The remaining three people correctly stay unresolved because no unique exact Final Character signature exists.

Upstream Character truth observed for the same project:

```text
Content Run = CONTENT_RUN_d6f66f45b758459cad69207a4eb81e60
profile = f05-assets-v10.1-person-evidence-model-classification
resolved CharacterCandidates = 3
AssetRevision = ASSETREV_d387044c48824c2da67ba61e833dcc6f / revision 14 / AUTO
Final Characters = 3
Episode Final ShotCharacterBindings = 29
```

Therefore:

```text
P5 = FINAL PASS / FROZEN
```

## 6. P6 Final Breakdown read model

P6 is implemented as a separate read-only composition layer:

```text
Frozen G2 Scene Timeline
+
Frozen P5 Scene-local Character resolution
+
Current AssetRevision / existing Final Character display data
→ P6 ordinary-user read model
```

Current implementation:

```text
engine/app/breakdown_read_model_contract_v1.py
engine/app/breakdown_read_model_v1.py
engine/app/breakdown_read_model_routes_v1.py
GET /api/episodes/{episode_id}/breakdown-read-model
frontend/src/utils/breakdownReadModelUi.ts
frontend ordinary episode reading -> P6 endpoint
```

Identity safety:

```text
RESOLVED P5 person + exact current anchors -> may display existing Final Character name/cover metadata
UNRESOLVED P5 person -> remain anonymous 人物N
run/revision/Scene/P*/asset/Character mismatch -> all identity display falls back to anonymous
Breakdown prose/ASR/OCR -> never becomes identity authority
G2 Timeline object -> never mutated by backend P6
```

Tests have been added for backend composition/route and frontend projection, but they are not yet user-local accepted. An isolated `tsc --strict` compile of the new frontend P6 type/projection core passed in the assistant execution environment; full repository clone/test was not possible there because `github.com` DNS was unavailable.

Detailed boundary and acceptance commands: `docs/P6_FINAL_BREAKDOWN_READ_MODEL_V1.md`.

Status:

```text
P6 = V1 / IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
```

Do not mark P6 FINAL PASS until Python tests, frontend Vitest/typecheck/build, lockfile synchronization, and ordinary-user visual review are supplied.

## 7. Current implementation frontier

```text
1. keep G1 + G2.1-G2.5 + P5 frozen
2. finish G2.6 ordinary-user UI local acceptance when needed
3. P4 Draft-guided Scene/Prop still needs local acceptance
4. finish P6 user-local acceptance and final visual asset rendering polish
5. P6 must continue to compose frozen G2 + frozen P5 without mutating either
```

No assistant-local full pytest/CUDA PASS is claimed. Hosted GitHub Actions remain intentionally unused.