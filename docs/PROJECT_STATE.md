# AI Drama Studio — Project State

> **Last synchronized:** 2026-08-28 12:12 +08:00  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Branch:** `main`  
> **Architecture:** Reference Video V2  
> **FastAPI app version:** `2.4.1`  
> **Formal Character runtime:** Character V10.1  
> **Breakdown-first:** **P1/P2 IMPLEMENTATION CONDITIONAL PASS / P2.6 REAL-MODEL ACCEPTANCE NOT PASSED / P3 UI IMPLEMENTED, ACCEPTANCE IN PROGRESS**

## 1. Current-state source of truth

New-conversation recovery order:

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/CURRENT_IMPLEMENTATION_MANIFEST.md
→ docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
→ docs/BREAKDOWN_DRAFT_DATA_CONTRACT.md
→ docs/BREAKDOWN_P2_SIDECAR_CONTRACT.md
→ docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md
→ docs/ASSET_CHARACTER_RECOGNITION_V10_1.md when Character is involved
→ latest docs/sessions/* Breakdown handoff
→ current code/tests
```

Truth split:

```text
PROJECT_STATE + CURRENT_IMPLEMENTATION_MANIFEST + code/tests = executable CURRENT
BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN = accepted product/phase plan
BREAKDOWN_DRAFT_DATA_CONTRACT = frozen P1 Draft contract
BREAKDOWN_P2_SIDECAR_CONTRACT = frozen P2 Evidence/Fusion contract
BREAKDOWN_P2_LOCAL_ACCEPTANCE = P2 production/Windows/real-video acceptance procedure + current gate
```

## 2. Accepted product flow

```text
Original Video
→ Preprocess
→ Shot Detection
→ Shot + Reference Clip
→ ASR / OCR / Video Understanding
→ anonymous structured Breakdown Draft
→ Draft-guided Character / Scene / Prop evidence extraction
→ Global Asset Resolution + Final Shot Bindings
→ identity/asset fill-back
→ Final Breakdown
→ remake
```

Core principle:

> **先看懂，再识别，再回填。**

Semantic boundary:

```text
人物A / LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
raw Evidence / Draft != Final binding truth
```

## 3. Reference Video V2 baseline

Formal media chain remains:

```text
Project / Episode
→ FFprobe / FFmpeg preprocess
→ TransNetV2 Shot boundaries
→ integer microseconds
→ ShotRevision / ShotRevisionItem
→ per-Shot Reference Clip / thumbnail / keyframes
```

Historical semantic data anchors to exact `ShotRevision / ShotRevisionItem`. Current `Shot.id` is not a permanent cross-revision historical anchor. Heavy media/model work remains sequential by default.

## 4. P1 — implementation accepted conditionally

Formal modules:

```text
engine/app/breakdown_models_v1.py
engine/app/breakdown_service_v1.py
engine/app/breakdown_validator_v1.py
engine/app/breakdown_serializer_v1.py
engine/app/breakdown_routes_v1.py
engine/app/shot_revision_v2.py
```

Run lifecycle:

```text
PROCESSING / READY / READY_WITH_WARNINGS / FAILED / STALE
```

P1 implementation, lifecycle, history anchoring and validator behavior are accepted as part of the current **P1/P2 implementation CONDITIONAL PASS**. This is an implementation acceptance, not a real-model quality certification.

## 5. P2 — implementation accepted conditionally

Implemented production chain:

```text
P2.1 immutable Provider/raw Evidence sidecar
P2.2 faster-whisper ASR
P2.3 RapidOCR / PP-OCRv6 OCR
P2.4 Qwen3-VL anonymous visual semantics
P2.5 deterministic Fusion
P2.6 production orchestrator / API / Windows runner / preflight / acceptance report
```

Formal production profile:

```text
engine/app/breakdown_p2_pipeline_v1.py
profile = breakdown-p2-full-v1
ASR → OCR → VLM → Fusion → P1 validator
```

Formal endpoints:

```text
POST /api/episodes/{episode_id}/tasks/breakdown
POST /api/projects/{project_id}/tasks/breakdown-batch
GET  /api/breakdown/p2/runtime-preflight
POST /api/breakdown-runs/{run_id}/p2-acceptance
```

Batch Breakdown remains strictly sequential by `Episode.sort_order`, globally serialized for heavy P2 work.

### Current P2 acceptance status

User implementation review result:

```text
P1/P2 implementation acceptance = CONDITIONAL PASS
```

This means architecture/contracts/persistence/orchestration are conditionally accepted. It does **not** mean P2.6 real-video quality passed.

## 6. P2.6 Windows / real-model acceptance — NOT PASSED

Current factual result from the user's Windows acceptance attempt:

```text
P2.6 Windows / real-model acceptance = NOT PASSED
blocking runtime/model gap           = OCR + Qwen model/runtime not fully provisioned
real short-drama full-chain run      = NOT COMPLETED
human acceptance PASS report         = NOT AVAILABLE
```

Required next gate:

```text
1. complete OCR runtime/model provisioning
2. complete Qwen3-VL model provisioning
3. use a real short-drama sample
4. run ASR → OCR → VLM → Fusion → P1 validator
5. generate P2 acceptance report
6. complete explicit human review
7. required scores >= 4/5 and no blocking issues
```

Only then may P2.6 become `PASS`. Until that happens, do not write `P2 ACCEPTED`, `P2 CLOSED`, or claim that Qwen3-VL / OCR / full multimodal quality has passed real-video acceptance.

The P2.6 code/tooling remains implemented; the **runtime/real-model acceptance gate is what failed**.

## 7. P3 — Structured Draft UI is implemented on main

P3 is no longer `NEXT`.

Current `02 拉片` contains:

```text
镜头边界
→ ShotCacheManagerV51
→ ShotWorkbenchV4

Structured Draft
→ single/batch P2 Breakdown task controls
→ Breakdown Run history / STALE state
→ SceneSegmentDraft
→ ShotSemanticDraft + exact historical Reference Clip
→ anonymous LocalSubject / ShotLocalSubject
→ dialogue / action / OCR / visual / audio timeline
→ DraftPropHint / occurrences
→ Evidence provenance
```

P3 consumes formal P2 APIs and does not duplicate ASR/OCR/VLM/Fusion in Vue.

Current P3 status:

```text
implementation on main       = IMPLEMENTED
browser/local UI acceptance  = IN PROGRESS
fully accepted/closed        = NO
```

The Shot Boundary overflow regression was fixed on `main` in merge commit `1cb8624b885850935e902cb6c9ac2273c490d2b3`.

## 8. Formal Character V10.1 — unchanged

```text
YOLOX Person Detection
→ capture-first Person Evidence
→ mature MOT
→ YoutuReID project-level identity
→ RESOLVED / UNRESOLVED
→ explicit Shot × known-Character Assignment
→ Final Character Gate
→ Character + ShotCharacterBinding
```

Protected invariants remain:

```text
new identity requires >=3 independent Shots / >=3 model-usable images
same-sample cannot-link
high-quality Face hard conflicts
explicit Shot Assignment is current Final binding source
VLM/Draft cannot create Character
ASR speaker cannot create Character
```

## 9. Scene / Prop reality

P2 produces semantic hints only. Existing asset-side `SceneCandidate / ShotSceneEvidence` and `PropCandidate / ShotPropEvidence` remain separate. Draft-guided Scene/Prop evidence extraction is P4; Draft↔Character safe integration is P5.

## 10. Current phase pointer

```text
P0 planning/contracts                          = COMPLETE
P1 implementation                              = CONDITIONAL PASS
P2 implementation                              = CONDITIONAL PASS
  P2.1 sidecar                                 = IMPLEMENTED
  P2.2 ASR                                     = IMPLEMENTED
  P2.3 OCR                                     = IMPLEMENTED, real runtime/model gate incomplete
  P2.4 VLM                                     = IMPLEMENTED, Qwen model gate incomplete
  P2.5 Fusion                                  = IMPLEMENTED
  P2.6 orchestration/acceptance tooling        = IMPLEMENTED
P2.6 Windows/real-model acceptance             = NOT PASSED
P3 02 拉片 Structured Draft UI                 = IMPLEMENTED / UI ACCEPTANCE IN PROGRESS
P4 Draft-guided Scene / Prop evidence          = PLANNED
P5 Draft ↔ Character safe integration          = PLANNED
P6 Final fill-back + renderers                 = PLANNED
P7 downstream remake integration               = PLANNED
```

P2 remains forbidden from writing Final Character/Scene/Prop assets or Final Shot bindings.

## 11. Validation / CI truth

GitHub hosted Actions are intentionally not used for this work because hosted CI quota should not be consumed. Do not report historical CI as fresh acceptance.

The authoritative outstanding release gate is now concrete, not generic:

> **补齐 OCR 与 Qwen 模型/runtime，然后在用户 Windows 机器用真实短剧跑完整 P2 链并完成人工验收。**

## 12. Next safe work

Two acceptance tracks remain active:

```text
A. P2.6 runtime acceptance
   → provision OCR + Qwen
   → real short-drama full-chain run
   → acceptance report + human review

B. P3 UI acceptance
   → continue browser verification of 02 拉片 Structured Draft / 镜头边界
```

Do not advance project truth to P2.6 PASS or P3 CLOSED until the corresponding acceptance evidence exists.
