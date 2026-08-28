# AI Drama Studio — Current Implementation Manifest

> Purpose: compact **code-aligned CURRENT manifest**.  
> Last synchronized: **2026-08-28 18:12 +08:00**

## Repository baseline

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Architecture: Reference Video V2
FastAPI app version: 2.4.1
Formal Character runtime: Character V10.1
P1/P2 implementation acceptance: CONDITIONAL PASS
P2-E1 Episode-context Fusion: IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2.6 Windows / real-model acceptance: NOT PASSED
P3 Structured Draft UI: IMPLEMENTED / UI ACCEPTANCE IN PROGRESS
P4 Draft-guided Scene/Prop: IMPLEMENTED / LOCAL ACCEPTANCE PENDING
```

## Product flow

```text
Episode source / proxy / audio
→ Shot Detection + ShotRevision (timing boundary, not semantic boundary)
→ Episode ASR / OCR
→ Video Understanding
→ Episode-context Fusion
→ anonymous structured Breakdown Draft
→ Draft-guided Character / Scene / Prop Evidence
→ Global Asset Resolution / Final Bindings
→ identity/asset fill-back
→ Final Breakdown
→ remake
```

Core product rule:

```text
Shot = smallest review/render unit
Shot != maximum AI semantic context
```

Semantic boundary:

```text
LocalSubject / 人物A != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
raw Evidence / Draft != Final binding truth
```

## Current Shot/media baseline

```text
FFprobe authoritative timing
FFmpeg preprocess/proxy/audio
integer microseconds
TransNetV2 Shot boundaries
ShotRevision / ShotRevisionItem history
per-Shot Reference Clip / thumbnail / keyframes
manual boundary edit / split / merge / rerun / restore
```

Historical Breakdown anchors to exact ShotRevision/ShotRevisionItem, never guessed from Current Shot IDs.

## P1 executable infrastructure

```text
engine/app/breakdown_models_v1.py
engine/app/breakdown_service_v1.py
engine/app/breakdown_validator_v1.py
engine/app/breakdown_serializer_v1.py
engine/app/breakdown_routes_v1.py
engine/app/shot_revision_v2.py
```

Lifecycle:

```text
PROCESSING / READY / READY_WITH_WARNINGS / FAILED / STALE
```

P1 implementation is part of the current **CONDITIONAL PASS**. This is not real-model quality acceptance.

## P2 executable chain

Formal production entry:

```text
engine/app/breakdown_p2_pipeline_v1.py
profile = breakdown-p2-full-v1

create frozen BreakdownRun
→ ASR
→ OCR
→ current Qwen3-VL visual semantics
→ Episode-context E1 Fusion
→ P1 validator
→ publish READY / READY_WITH_WARNINGS
```

Implemented components:

```text
P2.1 engine/app/breakdown_p2_sidecar_v1.py
P2.2 engine/app/breakdown_p2_asr_v1.py
P2.3 engine/app/breakdown_p2_ocr_v1.py
P2.4 engine/app/breakdown_p2_vlm_v1.py
P2.4 runtime compatibility engine/app/breakdown_p2_vlm_runtime_v1.py
P2.5 legacy baseline engine/app/breakdown_p2_fusion_v1.py
P2-E1 production Fusion engine/app/breakdown_p2_fusion_episode_v2.py
P2.6 engine/app/breakdown_p2_pipeline_v1.py
P2.6 engine/app/breakdown_p2_acceptance_v1.py
```

Current production Fusion sub-profile:

```text
breakdown-p2-fusion-episode-context-e1-v2
```

The top-level pipeline profile remains `breakdown-p2-full-v1` for API/Run compatibility; the exact Fusion sub-profile is recorded in component/provider provenance.

### P2-E1 current behavior

Scene continuity:

```text
missing / UNKNOWN / generic scene hint
→ inherit current Scene Segment

compatible specific hint
病房 → 医院病房
客厅 → 家中客厅
→ keep same Scene, prefer more specific anchor

strong location contradiction
or explicit INT ↔ EXT contradiction
→ create new Scene Segment
```

Dialogue continuity:

```text
ASR_SEGMENT = Episode-time dialogue text truth
Shot DIALOGUE TimelineEvent = projection of that full dialogue onto an intersecting Shot
```

Cross-Shot projections carry:

```text
dialogue_group_id
asr_segment_id
dialogue_source_start_us / dialogue_source_end_us
projection_start_us / projection_end_us
projection_index / projection_count
continues_from_previous_shot / continues_to_next_shot
```

ASR_WORD remains immutable raw Evidence and is attached back to projections as SUPPORT provenance. Historical sidecars are not rewritten.

### P2-E2/E3/E4 status

```text
P2-E2 overlapping continuous-window Qwen3-VL = PLANNED / NOT IMPLEMENTED
P2-E3 contextual per-Shot refinement            = PLANNED
P2-E4 final Episode-context Fusion              = PLANNED
```

Important limitation: current P2.4 Qwen still analyzes one Reference Clip at a time. E1 fixes Fusion continuity but is **not** a claim that full Episode continuous visual understanding is already complete.

The accepted migration plan is documented in:

```text
docs/BREAKDOWN_EPISODE_CONTEXT_PLAN.md
```

### P2.4 Chinese Draft generation

P2.4 production natural-language semantics use:

```text
scripts/breakdown_vlm_prompt_zh_v1.py
prompt_profile = breakdown-p2-vlm-zh-draft-v1
draft_text_language = zh-CN
```

Scene/Shot/subject/event/prop VLM prose is generated in Simplified Chinese at source and guarded before READY. ASR/OCR raw source text remains untranslated. Machine JSON/enums remain stable.

Formal APIs:

```text
POST /api/episodes/{episode_id}/tasks/breakdown
POST /api/projects/{project_id}/tasks/breakdown-batch
GET  /api/breakdown/p2/runtime-preflight
POST /api/breakdown-runs/{run_id}/p2-acceptance
```

Batch execution is sequential by `Episode.sort_order`; heavy P2 work is globally serialized.

## P2 status discipline

Implementation review:

```text
P1/P2 implementation acceptance = CONDITIONAL PASS
P2-E1 code implementation       = IMPLEMENTED
P2-E1 local-real acceptance     = PENDING
```

P2.6 Windows / real-model acceptance:

```text
status                      = NOT PASSED
real short-drama full chain = acceptance evidence incomplete
human acceptance PASS       = NOT AVAILABLE
```

OCR/Qwen compatibility and provisioning helpers are implemented, but implementation/runtime readiness is not equivalent to real-model quality PASS.

Required close gate now includes the Episode-context production Fusion:

```text
strict preflight
→ real short-drama sample
→ ASR → OCR → VLM → Episode-context E1 Fusion → P1 validator
→ verify cross-Shot dialogue continuity + same-scene closeups
→ P2 acceptance report
→ human required scores >= 4/5
→ no blocking issues
```

## P3 current executable UI

Important frontend modules:

```text
frontend/src/types/breakdown.ts
frontend/src/api/breakdown.ts
frontend/src/components/BreakdownTaskBarV1.vue
frontend/src/components/BreakdownResultsV1.vue
frontend/src/components/BreakdownStageV1.vue
frontend/src/components/ShotWorkbenchV4.vue
frontend/src/views/ProjectStudioV3.vue
```

Current user-facing structure:

```text
02 拉片
├─ 镜头管理
│  └─ simplified Shot review/edit workbench
└─ 拉片结果
   ├─ P2 single/batch tasks
   ├─ Scene / Shot results
   ├─ anonymous subjects
   ├─ dialogue / action / OCR timeline
   ├─ prop hints
   └─ exact historical Reference Clip
```

Technical Evidence/provenance remains in backend but is no longer the primary normal-user presentation.

P3 status:

```text
implementation = IMPLEMENTED
browser/UI acceptance = IN PROGRESS
fully accepted/closed = NO
```

## P4 current executable backend

P4 reuses the existing asset Evidence containers and Final Asset workflow; it does not create parallel Scene/Prop tables.

```text
engine/app/breakdown_asset_guidance_v1.py
profile = breakdown-asset-guidance-p4-v1

engine/app/asset_semantics_p4_v1.py
engine/app/asset_routes_v3.py -> P4 semantic entrypoint
```

Guidance gate:

```text
BreakdownRun is_current=true
status READY / READY_WITH_WARNINGS
source_shot_revision_id == current ShotRevision
exact ShotRevisionItem anchor
current original_shot_id still exists
```

No stale/history ordinal/timestamp guessing is permitted.

Scene flow:

```text
SceneSegmentDraft soft hint
→ current Shot image verification
→ scene MATCH / CONFLICT / UNKNOWN
→ existing SceneCandidate / ShotSceneEvidence
→ provenance in evidence_json
```

Prop flow:

```text
DraftPropOccurrence target
→ current Shot image verification
→ observed=false => reject hint
→ observed=true + confidence >= 0.45 => PropCandidate Evidence
→ unprompted discovery requires confidence >= 0.68
→ valid localization may write xyxy_norm ShotPropEvidence.bbox_json
```

If no current revision-safe Draft exists, P4 falls back to `asset_semantics_v3` unchanged.

P4 status:

```text
implementation = IMPLEMENTED
local/model acceptance = PENDING
model-quality PASS = NO
```

P4 stays implemented, but further P5 identity integration is paused until the Episode-context Breakdown semantic baseline is locally accepted.

## Formal Character V10.1 baseline — unchanged

```text
YOLOX Person Detection
YoutuReID primary project-level identity
YuNet / SFace Face support/conflict
mature MOT
>=3 independent Shots / >=3 usable images for new identity
same-sample cannot-link
high-quality Face hard conflict
explicit Shot × known-Character Assignment
Final Character Gate
```

Draft/VLM/ASR context cannot override Character V10.1 hard evidence gates. E1 does not modify Character code.

## Validation / CI reality

```text
GitHub hosted Actions = intentionally not used
historical CI = historical only
P2-E1 local-real acceptance = PENDING
P2.6 real Windows/model acceptance = NOT PASSED
P3 UI acceptance = IN PROGRESS
P4 local/model acceptance = PENDING
```

New E1 unit coverage:

```text
engine/tests/v2/test_breakdown_p2_fusion_episode_v2.py
```

It covers weak/unknown scene inheritance, strong scene changes, compatible location specificity, non-destructive ASR projection input, and full-sentence cross-Shot dialogue projection. These tests were added to the repository; this session did not use hosted CI and does not claim a fresh executed PASS.

## Phase pointer

```text
P0 COMPLETE
P1 implementation CONDITIONAL PASS
P2 implementation CONDITIONAL PASS
P2-E1 Episode-context Fusion IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E2 continuous-window VLM PLANNED
P2-E3 contextual Shot refinement PLANNED
P2-E4 final Episode-context Fusion PLANNED
P2.6 Windows / real-model acceptance NOT PASSED
P3 拉片 UI IMPLEMENTED / UI ACCEPTANCE IN PROGRESS
P4 Draft-guided Scene/Prop IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character safe integration PLANNED / PAUSED UNTIL EPISODE-CONTEXT BASELINE
P6 Final fill-back/renderers PLANNED
P7 remake integration PLANNED
```

Next safe work is to run P2-E1 on a real short-drama Episode and inspect cross-Shot dialogue + same-scene closeups. After E1 behavior is accepted, implement P2-E2 overlapping continuous-window VLM before advancing P5.
