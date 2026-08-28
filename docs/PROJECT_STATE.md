# AI Drama Studio — Project State

> **Last synchronized:** 2026-08-28 16:03 +08:00  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Branch:** `main`  
> **Architecture:** Reference Video V2  
> **FastAPI app version:** `2.4.1`  
> **Formal Character runtime:** Character V10.1  
> **Breakdown-first:** **P1/P2 IMPLEMENTATION CONDITIONAL PASS / P2.6 REAL-MODEL ACCEPTANCE NOT PASSED / P3 UI IMPLEMENTED, ACCEPTANCE IN PROGRESS / P4 IMPLEMENTED, LOCAL ACCEPTANCE PENDING**

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
→ latest docs/sessions/* Breakdown/P4 handoff
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

Historical semantic data anchors to exact ShotRevision/ShotRevisionItem. Current `Shot.id` is not a permanent cross-revision historical anchor. Heavy media/model work remains sequential by default.

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

### P2.4 Chinese Draft generation

Production Qwen3-VL now uses:

```text
prompt_profile = breakdown-p2-vlm-zh-draft-v1
draft_text_language = zh-CN
```

VLM-generated Scene / Shot / anonymous-subject / action-event / prop prose is generated as Simplified Chinese at P2.4 source. Machine JSON/enums remain stable English tokens; ASR dialogue and OCR observations preserve raw source text. A language gate fails closed when high-value VLM prose is clearly not Chinese. Historical Runs remain immutable; only new BreakdownRuns receive this policy.

### Current P2 acceptance status

User implementation review result:

```text
P1/P2 implementation acceptance = CONDITIONAL PASS
```

This means architecture/contracts/persistence/orchestration are conditionally accepted. It does **not** mean P2.6 real-video quality passed.

## 6. P2.6 Windows / real-model acceptance — NOT PASSED

Current authoritative gate remains:

```text
P2.6 Windows / real-model acceptance = NOT PASSED
real short-drama acceptance evidence = INCOMPLETE
human acceptance PASS report         = NOT AVAILABLE
```

Runtime compatibility/provisioning fixes have been implemented for OCR and Qwen3-VL, including Windows diagnostics and the Chinese Draft profile, but they do not by themselves constitute a real-model acceptance PASS.

Required close gate:

```text
1. provision/verify OCR runtime + model
2. provision/verify Qwen3-VL runtime + model
3. use a real short-drama sample
4. run ASR → OCR → VLM → Fusion → P1 validator
5. generate P2 acceptance report
6. complete explicit human review
7. required scores >= 4/5 and no blocking issues
```

Only then may P2.6 become `PASS`. Until that happens, do not write `P2 ACCEPTED`, `P2 CLOSED`, or claim that full multimodal quality has passed real-video acceptance.

## 7. P3 — Structured Draft UI is implemented on main

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

The Stage 02 Shot Boundary overflow regression was fixed on main. P3 visual/localization fixes continue to be accepted through browser testing; do not mark P3 CLOSED until the user explicitly accepts it.

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

P4 does not modify any Character V10.1 resolver, threshold, tracking, identity or Final Gate code.

## 9. P4 — Draft-guided Scene / Prop Evidence implemented

P4 backend first implementation is now present:

```text
engine/app/breakdown_asset_guidance_v1.py
profile = breakdown-asset-guidance-p4-v1

engine/app/asset_semantics_p4_v1.py
engine/app/asset_routes_v3.py -> P4 semantic entrypoint
```

Formal flow:

```text
current READY BreakdownRun
+ exact current ShotRevision
→ Shot-level SceneSearchGuide / PropSearchGuide
→ current Shot thumbnail re-verification
→ existing SceneCandidate / ShotSceneEvidence
→ existing PropCandidate / ShotPropEvidence
```

Safety gates:

```text
STALE/history/FAILED/PROCESSING Draft = never guidance
no ordinal/timestamp history guessing
Draft Scene/Prop = hypothesis only
Draft prop must be visually observed again before candidate evidence
observed=false = no PropCandidate from that hint
verified prop threshold >= 0.45
unguided discovered key prop threshold >= 0.68
valid Qwen localization can be stored as xyxy_norm bbox Evidence
```

No-Draft projects fall back to the existing unguided `asset_semantics_v3` path.

P4 status:

```text
implementation                 = IMPLEMENTED
local/model acceptance         = PENDING
Final Scene/Prop quality PASS  = NO
```

The existing Final Asset/Revision workflow remains unchanged. P4 does not create a direct `Draft -> Final Scene/Prop` path.

## 10. Current phase pointer

```text
P0 planning/contracts                          = COMPLETE
P1 implementation                              = CONDITIONAL PASS
P2 implementation                              = CONDITIONAL PASS
  P2.1 sidecar                                 = IMPLEMENTED
  P2.2 ASR                                     = IMPLEMENTED
  P2.3 OCR                                     = IMPLEMENTED; real acceptance pending
  P2.4 VLM                                     = IMPLEMENTED; Chinese Draft source policy added
  P2.5 Fusion                                  = IMPLEMENTED
  P2.6 orchestration/acceptance tooling        = IMPLEMENTED
P2.6 Windows/real-model acceptance             = NOT PASSED
P3 02 拉片 Structured Draft UI                 = IMPLEMENTED / UI ACCEPTANCE IN PROGRESS
P4 Draft-guided Scene / Prop evidence          = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character safe integration          = PLANNED
P6 Final fill-back + renderers                 = PLANNED
P7 downstream remake integration               = PLANNED
```

P2/P3/P4 remain forbidden from treating Draft prose as Final identity truth. P4 may write asset-side Scene/Prop Evidence through existing Candidate tables but cannot let Draft bypass visual verification.

## 11. Validation / CI truth

GitHub hosted Actions are intentionally not used for this work because hosted CI quota should not be consumed. Do not report historical CI as fresh acceptance.

Current outstanding real gates are concrete:

```text
P2.6 real short-drama full-chain + human acceptance
P3 browser/local UI acceptance
P4 local asset-model acceptance on a project with current Structured Draft
```

## 12. Next safe work

Three acceptance tracks are active:

```text
A. P2.6 runtime/quality acceptance
   → strict preflight
   → real short-drama full chain
   → acceptance report + human review

B. P3 UI acceptance
   → continue browser verification of 02 拉片 Structured Draft / 镜头边界

C. P4 local acceptance
   → current READY Structured Draft
   → 03 资产 / 资产提取
   → verify Draft-guided Scene/Prop results + provenance + rejected false hints
```

After P4 local behavior is accepted, the next planned implementation is P5 Draft ↔ Character safe integration. Do not advance project truth to P2.6 PASS, P3 CLOSED, P4 quality PASS or P5 IMPLEMENTED without the corresponding evidence/code.
