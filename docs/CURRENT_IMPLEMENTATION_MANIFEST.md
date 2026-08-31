# AI Drama Studio — Current Implementation Manifest

> Purpose: code-aligned executable CURRENT manifest.  
> Last synchronized: **2026-08-31 +08:00**

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
P5 Draft ↔ Character: IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING
```

Executable CURRENT = `PROJECT_STATE + this manifest + current code/tests`.

## Repository workflow

```text
Documentation-only synchronization -> direct main; no docs-only branch/PR.
Code/behavior changes -> feature branch + Draft PR by default.
Explicit user request for direct main/merge -> follow that explicit request.
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

Profiles:

```text
Window = breakdown-p2-vlm-window-context-segment-index-zh-v4
Exact-Shot = breakdown-p2-vlm-exact-shot-compact-reconstruction-zh-v3
Fusion = breakdown-p2-fusion-episode-context-e6-v2
Pipeline = breakdown-p2-full-v1
```

Accepted production reference:

```text
Run = BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
Episode = EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
ShotRevision = SHOTREV_1462ac6d9f3948b994fc9bc575fee3a0
Shots = 30
status = READY
Scenes = 2
LocalSubjects = 4
same-Shot conflicts = 0
Shot0001 subjects = 0
```

Detailed acceptance evidence remains in `docs/PROJECT_STATE.md` and the G2 acceptance/session documents.

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

### G2.1 / G2.2

```text
engine/app/breakdown_scene_timeline_contract_v1.py
engine/app/breakdown_scene_timeline_assembler_v1.py
engine/tests/v2/test_breakdown_scene_timeline_v1.py
```

Accepted baseline: `4 passed`, 2 Scenes, 30 Shots, `[2,2]` anonymous people.

### G2.3 / G2.4

```text
engine/app/breakdown_scene_narrative_contract_v1.py
engine/app/breakdown_scene_grounding_v1.py
engine/app/breakdown_scene_narrative_v1.py
engine/app/breakdown_scene_narrative_validator_v1.py
engine/app/breakdown_scene_narrative_qwen3_v1.py
```

LLM authority remains narrow:

```text
MAY: readable_title, story_summary
MUST NOT: timestamps, boundaries, people identity/count, Shot facts,
          ASR/OCR truth, props, cinematography, Final Assets
```

Accepted regression baseline: `15 passed` + real local Qwen acceptance.

### G2.5 Scene Timeline API

```text
engine/app/breakdown_scene_timeline_result_v1.py
engine/app/breakdown_scene_timeline_routes_v1.py
scripts/materialize_breakdown_g2_scene_timeline_v1.py
```

Primary endpoints:

```text
GET /api/episodes/{episode_id}/scene-timeline
GET /api/breakdown-runs/{run_id}/scene-timeline
```

Rules:

```text
GET never starts a model.
Narrative is explicitly materialized.
Invalid/missing/stale Narrative falls back to deterministic G2.2.
Persisted Narrative is revalidated through frozen G2.4.
Ordinary response hides support Fxxxx, source_fingerprint, Evidence IDs,
cluster/LocalSubject IDs, confidence, provider/model and raw validator diagnostics.
```

Accepted G2.5 baseline: `12 passed`; accepted Run materialization = 2 titles + 2 summaries + 0 warnings.

## G2.6 ordinary-user UI

Implementation is on `main`:

```text
frontend/src/api/scene-timeline.ts
frontend/src/components/SceneTimelineResultsV1.vue
frontend/src/components/BreakdownStageV1.vue
frontend/src/types/scene-timeline.ts
frontend/src/utils/sceneTimelineUi.ts
frontend/src/utils/sceneTimelineUi.test.ts
frontend/src/scene-timeline-g2-6-overrides.css
```

Primary visible order:

```text
Scene title/story summary
→ Scene environment/people
→ Shot preview/reference clip
→ visual
→ action/performance
→ dialogue
→ props
→ cinematography
→ OCR/on-screen text
```

Status: **IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING**.

Do not claim FINAL PASS until user-local frontend test/typecheck/build and visual review are supplied.

## P5 Breakdown ↔ Character safe bridge

PR #17 is merged and closed. Merge commit:

```text
ab4b11716f5c1c5ead7367119d1b2d787defe8f9
```

Implementation now on `main`:

```text
engine/app/breakdown_character_bridge_contract_v1.py
engine/app/breakdown_character_bridge_v1.py
engine/tests/v2/test_breakdown_character_bridge_v1.py
scripts/run_breakdown_p5_character_bridge_acceptance_v1.py
docs/P5_BREAKDOWN_CHARACTER_BRIDGE_V1.md
docs/sessions/2026-08-31_P5_breakdown-character-bridge-implementation.md
```

Authority direction:

```text
Final ShotCharacterBinding
→ current ShotRevision-safe Scene-local presence signatures
→ unique one-to-one match only
→ anonymous LocalSubject display may resolve to existing Final Character
```

P5 is read-only and fail-closed. It does not create identity, rewrite LocalSubject, modify Character V10.1, modify Final Gate, or write Final bindings. Dialogue/ASR names, relationship terms, role hints and appearance prose are excluded from identity authority. Ambiguous/always-co-occurring people stay `UNRESOLVED`.

Status: **IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING**.

Required local acceptance:

```powershell
python -m pytest engine/tests/v2/test_breakdown_character_bridge_v1.py -q
python scripts/run_breakdown_p5_character_bridge_acceptance_v1.py EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
```

Do not mark P5 FINAL PASS until those user-local results and the real mapping review are supplied.

## Next required action

```text
1. keep G1 + G2.1-G2.5 frozen
2. finish G2.6 local UI acceptance when needed
3. complete P5 local deterministic + real-Episode acceptance
4. keep P5 non-final until real mappings are reviewed
5. after accepted P5, implement P6 Final identity/asset fill-back + final Breakdown renderers
```
