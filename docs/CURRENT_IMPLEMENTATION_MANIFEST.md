# AI Drama Studio — Current Implementation Manifest

> Purpose: compact **code-aligned CURRENT manifest**.  
> Last synchronized: **2026-08-28 12:12 +08:00**

## Repository baseline

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Architecture: Reference Video V2
FastAPI app version: 2.4.1
Formal Character runtime: Character V10.1
P1/P2 implementation acceptance: CONDITIONAL PASS
P2.6 Windows / real-model acceptance: NOT PASSED
P3 Structured Draft UI: IMPLEMENTED ON MAIN / UI ACCEPTANCE IN PROGRESS
```

## Product flow

```text
Shot + Reference Clip
→ ASR / OCR / Video Understanding
→ anonymous structured Breakdown Draft
→ Draft-guided Character / Scene / Prop Evidence
→ Global Asset Resolution / Final Bindings
→ identity/asset fill-back
→ Final Breakdown
→ remake
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
→ VLM
→ deterministic Fusion
→ P1 validator
→ publish READY / READY_WITH_WARNINGS
```

Implemented components:

```text
P2.1 engine/app/breakdown_p2_sidecar_v1.py
P2.2 engine/app/breakdown_p2_asr_v1.py
P2.3 engine/app/breakdown_p2_ocr_v1.py
P2.4 engine/app/breakdown_p2_vlm_v1.py
P2.5 engine/app/breakdown_p2_fusion_v1.py
P2.6 engine/app/breakdown_p2_pipeline_v1.py
P2.6 engine/app/breakdown_p2_acceptance_v1.py
```

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
```

P2.6 Windows / real-model acceptance:

```text
status                         = NOT PASSED
OCR runtime/model provisioning = INCOMPLETE
Qwen3-VL model provisioning    = INCOMPLETE
real short-drama full chain    = NOT COMPLETED
human acceptance PASS          = NOT AVAILABLE
```

Required close gate:

```text
provision OCR + Qwen
→ real short-drama sample
→ ASR → OCR → VLM → Fusion → P1 validator
→ P2 acceptance report
→ human required scores >= 4/5
→ no blocking issues
```

Do not translate `IMPLEMENTED` into `ACCEPTED`. P2.6 remains failed/not-passed until the real Windows/model gate succeeds.

## P3 current executable UI

P3 is **not NEXT anymore**. The first Structured Draft workbench is on `main`.

Important frontend modules:

```text
frontend/src/types/breakdown.ts
frontend/src/api/breakdown.ts
frontend/src/components/BreakdownDraftV1.vue
frontend/src/components/BreakdownTaskBarV1.vue
frontend/src/components/BreakdownStageV1.vue
frontend/src/views/ProjectStudioV3.vue
```

Current UI behavior:

```text
02 拉片
├─ 镜头边界
│  ├─ ShotCacheManagerV51
│  └─ ShotWorkbenchV4
└─ Structured Draft
   ├─ P2 single/batch tasks
   ├─ Run history / STALE
   ├─ Scene / Shot Draft
   ├─ anonymous subjects
   ├─ dialogue/action/OCR timeline
   ├─ prop hints
   ├─ exact historical Reference Clip
   └─ Evidence provenance
```

P3 status:

```text
implementation = IMPLEMENTED ON MAIN
browser/UI acceptance = IN PROGRESS
fully accepted/closed = NO
```

The Stage 02 Shot Boundary scrolling regression was fixed in main merge commit `1cb8624b885850935e902cb6c9ac2273c490d2b3`.

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

Draft/VLM/ASR context cannot override Character V10.1 hard evidence gates.

## Scene / Prop boundary

P2 scene/prop output is semantic hint only. Existing SceneCandidate/ShotSceneEvidence and PropCandidate/ShotPropEvidence remain asset-side evidence. Draft-guided asset extraction begins in P4.

## Validation / CI reality

```text
GitHub hosted Actions = intentionally not used
historical CI = historical only
P2.6 real Windows/model acceptance = NOT PASSED
```

## Phase pointer

```text
P0 COMPLETE
P1 implementation CONDITIONAL PASS
P2 implementation CONDITIONAL PASS
P2.6 Windows / real-model acceptance NOT PASSED
P3 Structured Draft UI IMPLEMENTED / UI ACCEPTANCE IN PROGRESS
P4 Draft-guided Scene/Prop PLANNED
P5 Draft ↔ Character safe integration PLANNED
P6 Final fill-back/renderers PLANNED
P7 remake integration PLANNED
```

Next acceptance work is to provision OCR + Qwen and run the real short-drama P2.6 chain, while continuing P3 browser/UI verification.
