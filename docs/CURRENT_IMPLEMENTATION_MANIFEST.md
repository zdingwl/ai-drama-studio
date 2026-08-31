# AI Drama Studio — Current Implementation Manifest

> Purpose: code-aligned CURRENT manifest.  
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
G2.6 ordinary-user Scene Timeline UI: IMPLEMENTED / USER-LOCAL ACCEPTANCE PENDING
P3 current 02 拉片 Shot-card UI: IMPLEMENTED / NOT FINAL ACCEPTED
P4 Draft-guided Scene/Prop: IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character: IMPLEMENTED ON PR #17 / USER-LOCAL ACCEPTANCE PENDING / NOT MERGED
```

G1 and all accepted G2 layers through G2.5 are frozen until a concrete regression appears. Character V10.1 remains protected.

Repository workflow:

```text
Documentation-only synchronization -> direct main, no docs-only branch/PR.
Code/behavior changes -> feature branch + Draft PR by default.
Explicit user request for direct main -> follow the explicit request.
Hosted GitHub Actions -> not acceptance evidence.
All commits -> [skip ci].
```

## Final real acceptance evidence — G1 / G2.1 / G2.2

```text
Run = BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
Episode = EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
ShotRevision = SHOTREV_1462ac6d9f3948b994fc9bc575fee3a0
status = READY
whole run ~= 841.039s = 14.017 min
ASR = 15.275958s
OCR = 264.916802s
VLM = 559.267248s
Window Context = 84.3492s
Exact-Shot = 455.284273s
Window = 4/4 READY
Exact-Shot = 6/6 READY
MAXED = 0
scene_segment = 2
local_subject = 4
same_shot_cluster_conflicts = 0
Scene1 = Shots 1-12 / 公寓走廊 / LocalSubjects=2
Scene2 = Shots 13-30 / 客厅 / LocalSubjects=2
Shot0001 subjects=0
Shot0001 props include 蓝色玫瑰花束 + 玻璃花瓶
```

G2.1/G2.2 accepted evidence:

```text
python -m pytest engine/tests/v2/test_breakdown_scene_timeline_v1.py -q
4 passed

scenes = 2
shots = 30
people = [2, 2]
shot1_people = []
shot1_props = ['遥控器', '蓝色玫瑰花束', '玻璃花瓶', '书本']
warnings = []
```

Therefore:

```text
G1/P2.6 = PASS / FROZEN
G2.1 Scene Timeline Contract = FINAL PASS / FROZEN FOUNDATION
G2.2 Deterministic Assembler = FINAL PASS / FROZEN FOUNDATION
```

## Frozen production chain

```text
Episode Current ShotRevision
→ frozen PROCESSING BreakdownRun
→ ASR
→ OCR
→ Qwen3-VL one model load
   ├─ Window Segment-index v4
   └─ Exact-Shot Compact-reconstruction v3
→ immutable VLM_OUTPUT sidecar
→ P2-E6-v2 Fusion
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

Production modules:

```text
P2 sidecar                         engine/app/breakdown_p2_sidecar_v1.py
ASR                                engine/app/breakdown_p2_asr_v1.py
OCR                                engine/app/breakdown_p2_ocr_runtime_v1.py
Production VLM provider            engine/app/breakdown_p2_vlm_fast_grounded_instrumented_v3.py
Production continuity wrapper      engine/app/breakdown_p2_vlm_continuity_v1.py
Window production v4               scripts/run_breakdown_vlm_window_segment_index_v4.py
Exact-Shot production v3           scripts/run_breakdown_vlm_exact_shot_compact_v3.py
Production E6-v2 Fusion            engine/app/breakdown_p2_fusion_episode_v6.py
Orchestrator                       engine/app/breakdown_p2_pipeline_v1.py
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
G2 Scene Timeline != Final Scene / Final Prop / Final Character truth
ASR-origin DIALOGUE text is copied verbatim by G2
OCR-origin text is copied verbatim by G2
```

Character V10.1 remains unchanged:

```text
YOLOX -> capture-first evidence -> mature MOT -> YoutuReID
-> RESOLVED/UNRESOLVED -> explicit Shot Assignment -> Final Gate
```

P5 identity authority is one-way only:

```text
Final ShotCharacterBinding
-> deterministic Scene-local presence reconciliation
-> anonymous Breakdown display resolution when uniquely safe
```

Breakdown prose, dialogue/ASR names, relationship terms, role hints and appearance text cannot create or override Character identity.

## G2 frozen Scene Timeline behavior

```text
Scene
→ scene info
→ anonymous people (P1/P2 internally, 人物1/人物2 for display)
→ Shots
   → Exact-Shot visual description
   → visible people / grounded performance
   → ASR-only dialogue
   → Shot prop occurrences
   → shot type / Exact-Shot composition / reliable camera motion
   → OCR-only on-screen text
→ deterministic Scene summary baseline
→ validated Narrative title/story_summary overlay
```

Primary ordinary-user output excludes Evidence IDs, cluster data, confidence, LocalSubject DB IDs, support Fxxxx and provider/model diagnostics.

## G2.3 / G2.4 frozen architecture

Modules:

```text
Narrative Contract                  engine/app/breakdown_scene_narrative_contract_v1.py
Grounding Packet builder            engine/app/breakdown_scene_grounding_v1.py
Scene Narrative organizer           engine/app/breakdown_scene_narrative_v1.py
Source / Support Validator          engine/app/breakdown_scene_narrative_validator_v1.py
Local Qwen text adapter             engine/app/breakdown_scene_narrative_qwen3_v1.py
Local one-load text runner          scripts/run_breakdown_scene_narrative_qwen3.py
Real acceptance runner              scripts/run_breakdown_g2_scene_narrative_acceptance_v1.py
Narrative tests                     engine/tests/v2/test_breakdown_scene_narrative_v1.py
Qwen adapter tests                  engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py
Real regression tests               engine/tests/v2/test_breakdown_scene_narrative_real_regression_v1.py
Contract document                   docs/BREAKDOWN_G2_SCENE_NARRATIVE_CONTRACT.md
```

Formal flow:

```text
FINAL PASS scene-timeline-v1
→ one Scene Grounding Packet
→ stable Fxxxx facts
→ per-Scene SHA-256 source_fingerprint
→ text-only local Qwen3-VL-4B-Instruct
   one model load / Scenes sequential
→ Narrative Candidate
→ deterministic Source/Support Validator
→ Validated Narrative Overlay
→ apply overlay to title/story_summary only
```

Prompt profile:

```text
breakdown-g2-scene-narrative-zh-v1.5
```

LLM authority:

```text
MAY write:
  readable_title
  story_summary

MUST NOT own or rewrite:
  timestamps
  Scene/Shot boundaries
  people count/identity
  Shot visual facts
  performance/action facts
  ASR dialogue
  OCR
  prop existence
  shot type
  composition
  camera motion
  Final Character / Scene / Prop
```

ASR remains a restricted Narrative source: ordinary claims need attribution; sensitive event terms need topic/attribution; relationship identity terms are topic-only; dialogue names cannot bind anonymous people; numeric quantities must be provenance-backed.

## G2.3 / G2.4 final acceptance evidence

```text
python -m pytest engine/tests/v2/test_breakdown_scene_narrative_v1.py engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py engine/tests/v2/test_breakdown_scene_narrative_real_regression_v1.py -q
15 passed
```

Real-model acceptance on `BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4`:

```text
preflight = READY / cuda / missing=[]
runner Scene1 = READY
runner Scene2 = READY
overlay_status = READY
warnings = []
shot_objects_unchanged = YES
structure_gate = PASS
narrative_gate = PASS
acceptance_machine_gate = PASS
```

Accepted output:

```text
Scene1 = 走廊争花
老年女性质问年轻女性为何将花放在自家花瓶，年轻女性称花在走廊，双方争执并最终以给钱解决，年轻女性愤怒指责对方。

Scene2 = 客厅争执
人物2指责人物1对邻居偷花一事不作为，称其结婚八年从未支持过自己，人物1则表示自己会自行解决。
```

Human review = PASS. No Final identity/relationship binding was created and all frozen Shot objects remained unchanged.

Therefore:

```text
G2.3 = FINAL PASS / FROZEN
G2.4 = FINAL PASS / FROZEN
Local Qwen text runtime = REAL ACCEPTED / FROZEN BASELINE
```

## G2.5 frozen Scene Timeline API

Modules / contract:

```text
Scene Timeline result resolver        engine/app/breakdown_scene_timeline_result_v1.py
Scene Timeline read routes            engine/app/breakdown_scene_timeline_routes_v1.py
Narrative materializer                scripts/materialize_breakdown_g2_scene_timeline_v1.py
Result tests                          engine/tests/v2/test_breakdown_scene_timeline_result_v1.py
Route tests                           engine/tests/v2/test_breakdown_scene_timeline_routes_v1.py
API contract                          docs/BREAKDOWN_G2_SCENE_TIMELINE_API_V1.md
```

Primary endpoints:

```text
GET /api/episodes/{episode_id}/scene-timeline
GET /api/breakdown-runs/{run_id}/scene-timeline
```

Formal G2.5 flow:

```text
READY/READY_WITH_WARNINGS Breakdown Run
→ frozen deterministic G2.2 Scene Timeline
→ optional materialized validated Narrative artifact
→ Run/Revision/Scene fingerprint check
→ frozen G2.4 claim replay/revalidation
→ title/story_summary overlay only
→ strict scene-timeline-v1 leak guard
→ ordinary-user read response
```

Frozen G2.5 rules:

```text
GET is read-only and never starts Qwen or any model.
Narrative generation is explicit and materialized into the Run workspace.
Missing Narrative -> deterministic G2.2 fallback + user-readable warning.
Stale/invalid Narrative -> deterministic G2.2 fallback + user-readable warning.
Raw validator/model diagnostics never enter the primary response.
Primary API never exposes support Fxxxx, source_fingerprint, Evidence IDs, cluster keys, LocalSubject DB IDs, confidence, provider/model metadata, or Final Asset IDs.
```

## G2.5 final user-local acceptance evidence

Real Run materialization:

```text
python scripts/materialize_breakdown_g2_scene_timeline_v1.py BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4 --device cuda
scene_count = 2
accepted_title_count = 2
accepted_summary_count = 2
warning_count = 0
artifact = scene-timeline/narrative-overlay-v1.json
runtime_profile = breakdown-g2-scene-narrative-qwen3-local-v1
```

New G2.5 test boundary:

```text
python -m pytest engine/tests/v2/test_breakdown_scene_timeline_result_v1.py engine/tests/v2/test_breakdown_scene_timeline_routes_v1.py -q
12 passed
```

Frozen G2 regression command completed with 19 passing test dots and no failure/error output in the supplied user-local terminal result.

Therefore:

```text
G2.5 Scene Timeline API = FINAL PASS / FROZEN
G2.5 Windows/CUDA local acceptance = PASS
```

## G2.6 ordinary-user Scene Timeline UI

Implementation is present on `main`.

Primary modules:

```text
frontend/src/api/scene-timeline.ts
frontend/src/components/BreakdownStageV1.vue
frontend/src/components/SceneTimelineResultsV1.vue
frontend/src/types/scene-timeline.ts
frontend/src/utils/sceneTimelineUi.ts
frontend/src/utils/sceneTimelineUi.test.ts
frontend/src/scene-timeline-g2-6-overrides.css
```

Primary result path consumes frozen G2.5 directly:

```text
GET /api/episodes/{episode_id}/scene-timeline
```

Visible order:

```text
Scene title/story summary
→ Scene environment / people
→ Shot cards
   → preview/reference clip
   → visual
   → people
   → action/performance
   → dialogue
   → props
   → cinematography
   → OCR/on-screen text
```

Engineering evidence/support/internal IDs/confidence/provider/model diagnostics are excluded from the ordinary page.

Status:

```text
G2.6 = IMPLEMENTED / USER-LOCAL ACCEPTANCE PENDING
```

No FINAL PASS is claimed until the user supplies frontend test/typecheck/build and visual acceptance.

## P5 Draft ↔ Character implementation frontier

P5 implementation currently exists on Draft PR #17 and is not in `main`.

Implementation files on that PR:

```text
engine/app/breakdown_character_bridge_contract_v1.py
engine/app/breakdown_character_bridge_v1.py
engine/tests/v2/test_breakdown_character_bridge_v1.py
scripts/run_breakdown_p5_character_bridge_acceptance_v1.py
docs/P5_BREAKDOWN_CHARACTER_BRIDGE_V1.md
docs/sessions/2026-08-31_P5_breakdown-character-bridge-implementation.md
```

V1 rule:

```text
current READY Breakdown + exact current ShotRevision anchors
+ current Final Asset Revision
+ Final ShotCharacterBinding only
→ Scene-local exact presence signatures
→ unique one-to-one match = RESOLVED
→ ambiguous / duplicate / partial mismatch = UNRESOLVED
```

P5 does not write LocalSubject, Character, Final bindings or Character V10.1 identity state. Dialogue, ASR names, relationship terms, role hints and appearance prose are excluded from identity authority.

Status:

```text
IMPLEMENTED ON PR #17 / USER-LOCAL ACCEPTANCE PENDING / NOT MERGED
```

## Testing / CI discipline

Do not claim assistant-local pytest/CUDA execution. User-local results are acceptance truth. Hosted GitHub Actions remain unused; commits use `[skip ci]`.

## Next required action

```text
1. keep G1 + G2.1-G2.5 frozen
2. finish G2.6 user-local frontend acceptance when needed
3. run P5 deterministic test + accepted real-Episode inspection
4. merge P5 only after acceptance unless the user explicitly asks for direct main
5. after accepted P5, implement P6 Final identity/asset fill-back + final Breakdown renderers
```
