# AI Drama Studio — Project State

> **Last synchronized:** 2026-08-28 10:17 +08:00  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Branch:** `main`  
> **Architecture:** Reference Video V2  
> **FastAPI app version:** `2.4.1`  
> **Formal Character runtime:** Character V10.1  
> **Breakdown-first:** **P2 IMPLEMENTATION COMPLETE / REAL-VIDEO ACCEPTANCE PENDING / P3 NEXT**

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
BREAKDOWN_P2_LOCAL_ACCEPTANCE = P2 production/Windows/real-video acceptance procedure
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

The first Breakdown is anonymous semantic Evidence:

```text
人物A / subject_A / LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
```

P2 never writes Final assets or Final Shot bindings.

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

Historical semantic data anchors to exact `ShotRevision / ShotRevisionItem`. Current `Shot.id` is not a permanent cross-revision historical anchor.

Heavy media/model work remains sequential by default.

## 4. Breakdown P1 — COMPLETE

Formal modules:

```text
engine/app/breakdown_models_v1.py
engine/app/breakdown_service_v1.py
engine/app/breakdown_validator_v1.py
engine/app/breakdown_serializer_v1.py
engine/app/breakdown_routes_v1.py
engine/app/shot_revision_v2.py
```

Formal data domain:

```text
engine.app.studio_v2.Base
+ data_v2/studio_v2.sqlite3
```

ADD-only Draft tables:

```text
v2_breakdown_runs
v2_scene_segment_drafts
v2_shot_semantic_drafts
v2_local_subjects
v2_shot_local_subjects
v2_timeline_events
v2_timeline_event_subjects
v2_draft_prop_hints
v2_draft_prop_occurrences
v2_breakdown_evidence_links
```

Run lifecycle:

```text
PROCESSING / READY / READY_WITH_WARNINGS / FAILED / STALE
```

READY requires the real P1 validator. Successful publish atomically switches Current; failed runs never replace the prior Current. New Current ShotRevision marks incompatible active Breakdown Runs STALE without deleting history.

## 5. Breakdown P2 — IMPLEMENTATION COMPLETE

### P2.1 Provider/raw Evidence sidecar — COMPLETE

```text
engine/app/breakdown_p2_sidecar_v1.py
schema = breakdown-p2-evidence-v1
```

Frozen Provider input comes from the Run's exact source ShotRevision/ShotRevisionItems, Reference Clips, Episode audio and project source language. Provider results are validated, Final-ID leakage is rejected recursively and normalized output is persisted as fingerprinted immutable JSON sidecars.

### P2.2 ASR — COMPLETE

```text
engine/app/breakdown_p2_asr_v1.py
faster-whisper==1.2.1
default model = large-v3
word_timestamps = true
```

Outputs anonymous `ASR_SEGMENT + ASR_WORD` in Episode source integer microseconds. Speaker is not mapped to Character.

### P2.3 OCR — COMPLETE / FROZEN

```text
engine/app/breakdown_p2_ocr_v1.py
rapidocr==3.9.2
PP-OCRv6 small
ONNX Runtime
default CPU
```

Samples exact historical Reference Clips across the Shot. Every OCR Observation keeps exact historical Shot anchor, point time, confidence and geometry. Repeated observations remain raw Evidence until Fusion. Do not redo OCR without a concrete regression.

### P2.4 VLM — COMPLETE

```text
engine/app/breakdown_p2_vlm_v1.py
scripts/run_breakdown_vlm_qwen3.py
scripts/setup_breakdown_vlm_runtime.ps1
provider = qwen3-vl
model = Qwen/Qwen3-VL-4B-Instruct
```

Uses the existing isolated TransVLM Python/CUDA environment but a separate base Qwen3-VL content-semantic checkpoint. It emits strict anonymous shot-bound scene/shot/subject/action/prop semantics. It does not transcribe ASR/OCR content and does not identify Final assets.

### P2.5 deterministic Fusion — COMPLETE

```text
engine/app/breakdown_p2_fusion_v1.py
```

Fusion:

```text
validate immutable ASR/OCR/VLM sidecars
→ exact ASR cross-Shot splitting using word timing
→ OCR temporal stitching/dedupe
→ VLM ratio → source microseconds
→ conservative SceneSegmentDraft
→ ShotSemanticDraft full Shot coverage
→ anonymous LocalSubject / ShotLocalSubject
→ TimelineEvent / participants
→ DraftPropHint / occurrences
→ precise BreakdownEvidenceLink provenance
→ real P1 validator
→ publish READY / READY_WITH_WARNINGS
```

Anonymous subject grouping is deliberately conservative. If the same normalized appearance appears for two people in the same Shot, that appearance becomes cannot-link for cross-Shot grouping within that segment; the system prefers duplicate anonymous LocalSubjects over a false identity merge.

### P2.6 production orchestration + local acceptance tooling — IMPLEMENTED

Production orchestrator:

```text
engine/app/breakdown_p2_pipeline_v1.py
profile = breakdown-p2-full-v1
ASR → OCR → VLM → Fusion
```

Formal endpoints:

```text
POST /api/episodes/{episode_id}/tasks/breakdown
POST /api/projects/{project_id}/tasks/breakdown-batch
GET  /api/breakdown/p2/runtime-preflight
POST /api/breakdown-runs/{run_id}/p2-acceptance
```

Batch Breakdown is strictly sequential by `Episode.sort_order`.

Local/Windows tools:

```text
scripts/run_breakdown_p2.py
scripts/run_breakdown_p2_windows.ps1
scripts/p2_acceptance_review_template.json
docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md
```

Acceptance module:

```text
engine/app/breakdown_p2_acceptance_v1.py
schema = breakdown-p2-acceptance-v1
```

It checks runtime presence, exact sidecar/Fusion/full-Shot structural coverage and explicit human real-video review. Machine checks alone cannot produce `PASS`.

## 6. P2 implementation vs real-video acceptance

Current factual status:

```text
P2 production code / APIs / CLI / Windows runner / acceptance harness = COMPLETE
repository real short-drama sample                               = ABSENT
real user Windows GPU end-to-end inference in this development session = NOT EXECUTED
real-video acceptance report status                              = PENDING
```

Therefore do **not** claim that Qwen3-VL 4B, faster-whisper large-v3 or PP-OCRv6 small has already won a real-video quality benchmark in this session.

A true P2 acceptance close requires a real short-drama Run plus explicit review report with:

```text
structural checks PASS
required human scores >= 4/5
no blocking issues
= acceptance PASS
```

The code needed to perform that acceptance is complete. See `docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md`.

## 7. Formal Character V10.1 — unchanged

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

P2 did not change Character thresholds, identity resolver, Face hard-conflict behavior, assignment source or Final Gate.

## 8. Current Scene / Prop reality

P2 produces semantic hints only. Existing asset-side `SceneCandidate / ShotSceneEvidence` and `PropCandidate / ShotPropEvidence` remain separate. Draft-guided Scene/Prop evidence extraction is P4; Draft↔Character safe integration is P5.

## 9. Phase pointer

```text
P0 planning/contracts                          = COMPLETE
P1 Draft data/runtime/history                  = COMPLETE
P2 anonymous Breakdown implementation          = CODE COMPLETE
  P2.1 sidecar                                 = COMPLETE
  P2.2 ASR                                     = COMPLETE
  P2.3 OCR                                     = COMPLETE
  P2.4 VLM                                     = COMPLETE
  P2.5 Fusion                                  = COMPLETE
  P2.6 production/acceptance tooling           = COMPLETE
  real-video acceptance execution              = PENDING
P3 02 拉片 structured Draft UI                 = NEXT
P4 Draft-guided Scene / Prop evidence          = PLANNED
P5 Draft ↔ Character safe integration          = PLANNED
P6 Final fill-back + renderers                 = PLANNED
P7 downstream remake integration               = PLANNED
```

P2 remains forbidden from writing:

```text
Character
Scene
Prop
AssetRevision
ShotCharacterBinding
ShotSceneBinding
ShotPropBinding
```

## 10. Validation reality

No GitHub Actions were run or checked for this P2.6 work because the user explicitly requested not to consume hosted CI quota.

Historical hosted results remain only historical facts; do not present them as fresh P2.6 acceptance. New P2.6 Python modules and focused tests were syntax-compiled locally during development, but the repository is not available as a full local checkout in this execution environment, so no fresh full-repo pytest claim is made.

The authoritative final release gate remains a real short-drama run on the user's Windows machine using the local acceptance procedure.

## 11. Next safe implementation step

With P2 production functionality implemented, the next code phase is **P3 — 02 拉片 structured Draft UI**. P3 should consume the existing Breakdown read API and the new P2 background task endpoint; it must not duplicate ASR/OCR/VLM/Fusion logic in the frontend.
