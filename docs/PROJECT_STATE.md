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
P6 Final Character renderer           = IMPLEMENTED ON MAIN / USER-LOCAL VISUAL ACCEPTANCE PENDING
P6 Final Scene/Prop fill-back         = IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
P7.1 Localization Source Package      = V1 / IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
P7.2 Localization Draft               = V1 / IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
Stage 04 本土化剧本                  = IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
Stage 05 镜头重制方案                = LOCKED / PLANNED
Stage 06 生成·质检·交付             = LOCKED / PLANNED
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
P7 source_dialogue/source_on_screen_text = immutable downstream source truth
translation/localization/final copy != source truth
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

Accepted user-local evidence:

```text
python -m pytest engine/tests/v2/test_breakdown_character_bridge_v1.py -q
7 passed

real runner = READY
scene_count = 2
person_count = 4
resolved_count = 1
unresolved_count = 3
warnings = []
Scene 1 P2 = RESOLVED -> 人物 001 / FINAL_SHOT_BINDING_SIGNATURE_V1
```

The resolved mapping is an exact unique signature match on Shots `3,4,5,6,9,10,11`. The remaining three people correctly stay unresolved.

Therefore **P5 = FINAL PASS / FROZEN**.

## 6. P6 Final Breakdown read model

P6 is a separate read-only composition layer and does not change G2/P5/Final Binding ownership.

```text
Frozen G2 Scene Timeline
+ Frozen P5 Character resolution
+ current Final ShotSceneBinding / ShotPropBinding
+ current Final Character / Scene / Prop display assets
→ P6 ordinary-user read model
```

Character, Scene and Prop projection remain independently fail-closed. P6 never rewrites the frozen G2 `timeline` object.

Ordinary UI renders:

```text
本场人物 / Shot 人物 -> safe Final Character cover/name or anonymous fallback
最终场景 -> Final Scene only when every Shot in the G2 Scene agrees on one Final Scene
最终道具 -> exact ShotPropBinding Final Props
道具观察 -> original G2 prop facts, kept separate
```

Implementation and acceptance details: `docs/P6_FINAL_BREAKDOWN_READ_MODEL_V1.md`.

Status:

```text
P6 V1 = IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
Final Character renderer = IMPLEMENTED / VISUAL ACCEPTANCE PENDING
Final Scene/Prop fill-back = IMPLEMENTED / USER-LOCAL ACCEPTANCE PENDING
```

Do not mark P6 FINAL PASS until Python tests, real Episode runner, frontend Vitest/typecheck/build, lockfile synchronization and ordinary-user visual review are supplied.

## 7. P7 localization boundary

### P7.1 immutable source

```text
P6 current read model
+ Project source_language / target_language / target_region
→ localization-source-v1
```

P7.1 includes Scene/Shot timing, reference URLs, visual/action facts, verbatim ASR dialogue, verbatim OCR, safe people display, Final Scene/Prop overlays, cinematography and source version anchors.

It does not translate and never treats old `v2_dialogues` rows as current Breakdown source truth.

Details: `docs/P7_LOCALIZATION_SOURCE_V1.md`.

### P7.2 revisioned target copy

P7.2 now makes Stage 04 executable:

```text
P7.1 immutable source snapshot
→ append-only Episode Localization Revision
→ DRAFT
→ IN_REVIEW
→ FINAL
```

Implemented backend:

```text
engine/app/localization_draft_contract_v1.py
engine/app/localization_draft_v1.py
engine/app/localization_draft_workflow_v1.py
engine/app/breakdown_read_model_routes_v1.py
```

Implemented frontend:

```text
frontend/src/types/localization.ts
frontend/src/api/localization.ts
frontend/src/components/LocalizationStageV1.vue
frontend/src/utils/stageStatus.ts
frontend/src/views/ProjectStudioV3.vue
frontend/src/views/ProjectList.vue
```

Write authority rules:

```text
HTTP edits accept source_key + target-side fields only
source_text is not a writable request field
all writes create a new immutable Revision
base_revision_id prevents lost updates
DRAFT can save partial translation/localization work
IN_REVIEW / FINAL require no PENDING rows
IN_REVIEW / FINAL require final_text on every LOCALIZE row
IN_REVIEW cannot be edited until explicitly returned to DRAFT
FINAL cannot be directly edited
```

Stale-source rule:

```text
current P7.1 fingerprint changes
→ draft stale=true / read-only
→ explicit rebase required
→ old edit carries only when source_key + kind + Scene/Shot + timing + source_text all still match exactly
```

Stage 04 state:

```text
no current draft      -> 未开始
DRAFT / partial work  -> 编辑中
IN_REVIEW             -> 待复核
stale source          -> 阻塞
all Episodes FINAL    -> 已完成
```

Stage 04 is now clickable. Stage 05 and Stage 06 remain disabled because they do not yet have their own executable contracts/workspaces.

Details: `docs/P7_LOCALIZATION_DRAFT_V1.md`.

Current status:

```text
P7.1 = IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
P7.2 = IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
Stage 04 = IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
Stage 05 = LOCKED
Stage 06 = LOCKED
```

## 8. P7 acceptance

Deterministic backend tests added:

```text
engine/tests/v2/test_localization_source_v1.py
engine/tests/v2/test_localization_source_routes_v1.py
engine/tests/v2/test_localization_draft_v1.py
engine/tests/v2/test_localization_draft_workflow_v1.py
engine/tests/v2/test_localization_draft_routes_v1.py
```

Read-only real Episode runners:

```text
scripts/run_localization_source_acceptance_v1.py
scripts/run_localization_draft_acceptance_v1.py
```

Frontend Stage 04 state tests are in:

```text
frontend/src/utils/stageStatus.test.ts
```

No assistant-local full pytest/Vitest/vue-tsc/Vite build is claimed.

## 9. Current implementation frontier

```text
1. keep G1 + G2.1-G2.5 + P5 frozen
2. user-local accept P6 when convenient: backend + real runner + frontend + visual
3. user-local accept P7.1/P7.2: deterministic tests + read-only real runners + Stage 04 visual flow
4. P4 Draft-guided Scene/Prop local acceptance remains separately pending
5. next code frontier = Stage 05 versioned Shot Remake Plan / generation-input contract
6. Stage 05 must consume FINAL P7.2 copy + P6/P7 source anchors, not raw mutable UI state
7. Stage 06 remains locked until generation/QC/delivery has its own executable workflow
```

No assistant-local full pytest/CUDA PASS is claimed. Hosted GitHub Actions remain intentionally unused.