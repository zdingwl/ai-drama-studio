# AI Drama Studio — Current Implementation Manifest

> Purpose: compact **code-aligned CURRENT manifest**.  
> Last synchronized: **2026-08-28 10:17 +08:00**

## Repository baseline

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Architecture: Reference Video V2
FastAPI app version: 2.4.1
Formal Character runtime: Character V10.1
Breakdown P1: COMPLETE
Breakdown P2: IMPLEMENTATION CODE COMPLETE / REAL-VIDEO ACCEPTANCE PENDING
Next code phase: P3 structured 02 拉片 UI
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

Data domain:

```text
engine.app.studio_v2.Base
+ data_v2/studio_v2.sqlite3
```

P1 lifecycle:

```text
PROCESSING / READY / READY_WITH_WARNINGS / FAILED / STALE
```

P1 validator is fail closed; successful publish atomically switches Current; historical Runs remain readable.

## P2 current executable chain

Formal full production entry:

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

### P2.1 Evidence sidecar

```text
engine/app/breakdown_p2_sidecar_v1.py
schema = breakdown-p2-evidence-v1
```

Exact frozen ShotRevision context, unified Provider Result/Evidence validation, recursive Final-ID leak guard, fingerprinted immutable JSON sidecars and STALE race protection.

### P2.2 ASR

```text
engine/app/breakdown_p2_asr_v1.py
FasterWhisperASRProvider
faster-whisper==1.2.1
model = large-v3
word_timestamps = true
```

Produces `ASR_SEGMENT + ASR_WORD` in Episode source microseconds. Speaker identity is not mapped to Character.

### P2.3 OCR — frozen baseline

```text
engine/app/breakdown_p2_ocr_v1.py
RapidOCROCRProvider
rapidocr==3.9.2
PP-OCRv6 small
ONNX Runtime
default CPU
```

Exact historical Reference Clip multi-frame observations, source point time, text/confidence/polygon/bbox. Repeated observations are preserved until Fusion. Do not redo OCR without a concrete regression.

### P2.4 VLM

```text
engine/app/breakdown_p2_vlm_v1.py
scripts/run_breakdown_vlm_qwen3.py
scripts/setup_breakdown_vlm_runtime.ps1
Qwen3VLSemanticProvider
model = Qwen/Qwen3-VL-4B-Instruct
```

Uses a separate base content-semantic checkpoint inside the existing isolated TransVLM Python/CUDA environment. Emits strict anonymous scene/shot/subject/action/prop semantics; no dialogue/OCR transcription role and no Final identity role.

### P2.5 Fusion

```text
engine/app/breakdown_p2_fusion_v1.py
```

```text
immutable sidecar verification
ASR word-timing cross-Shot split
OCR temporal stitching/dedupe
VLM ratios → source microseconds
conservative SceneSegmentDraft grouping
full ShotSemanticDraft coverage
anonymous LocalSubject / ShotLocalSubject
TimelineEvent / participant rows
DraftPropHint / occurrences
precise BreakdownEvidenceLink
P1 validator/publish
```

Same-Shot duplicate appearance is an anonymous cannot-link signal: when two simultaneous subjects share the same normalized appearance summary, that appearance cannot be used to merge them across Shots within the segment.

### P2.6 production / acceptance tooling

```text
engine/app/breakdown_p2_acceptance_v1.py
scripts/run_breakdown_p2.py
scripts/run_breakdown_p2_windows.ps1
scripts/p2_acceptance_review_template.json
docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md
```

Formal APIs:

```text
POST /api/episodes/{episode_id}/tasks/breakdown
POST /api/projects/{project_id}/tasks/breakdown-batch
GET  /api/breakdown/p2/runtime-preflight
POST /api/breakdown-runs/{run_id}/p2-acceptance
```

Batch execution is sequential by `Episode.sort_order` and reuses the existing persistent BackgroundTask infrastructure.

Acceptance states:

```text
STRUCTURAL_FAIL
NEEDS_HUMAN_REVIEW
NEEDS_TUNING
PASS
```

`PASS` requires structural success + explicit real-video human review with every required dimension >=4/5 + no blocking issue. Machine checks alone cannot self-certify quality.

## P2 status discipline

Implemented now:

```text
P2.1 sidecar                          IMPLEMENTED
P2.2 ASR                              IMPLEMENTED
P2.3 OCR                              IMPLEMENTED
P2.4 VLM                              IMPLEMENTED
P2.5 Fusion                           IMPLEMENTED
P2.6 production orchestrator          IMPLEMENTED
P2.6 background API / batch           IMPLEMENTED
P2.6 CLI / Windows runner             IMPLEMENTED
P2.6 runtime preflight                IMPLEMENTED
P2.6 acceptance report/comparison     IMPLEMENTED
```

Not executed in this development environment:

```text
real short-drama sample inference
user Windows GPU end-to-end run
human-scored acceptance PASS
```

Reason: the repository contains no real short-drama video sample and this execution environment is not the user's Windows GPU machine. Therefore the correct status is **implementation complete / acceptance execution pending**, not “real-video quality accepted”.

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

Current V10.1 Final ShotCharacterBinding for new Runs comes from explicit `shot_presence_assignments`, not Candidate Track ownership. P2 does not change these rules.

## Current Scene / Prop boundary

P2 scene/prop output is semantic hint only. Existing SceneCandidate/ShotSceneEvidence and PropCandidate/ShotPropEvidence remain asset-side evidence. Draft-guided asset extraction begins in P4.

## Important modules

```text
engine/app/breakdown_models_v1.py
engine/app/breakdown_service_v1.py
engine/app/breakdown_validator_v1.py
engine/app/breakdown_serializer_v1.py
engine/app/breakdown_routes_v1.py
engine/app/breakdown_p2_sidecar_v1.py
engine/app/breakdown_p2_asr_v1.py
engine/app/breakdown_p2_ocr_v1.py
engine/app/breakdown_p2_vlm_v1.py
engine/app/breakdown_p2_fusion_v1.py
engine/app/breakdown_p2_pipeline_v1.py
engine/app/breakdown_p2_acceptance_v1.py
```

## Validation reality

User explicitly requested no GitHub hosted CI usage because quota is unavailable. No new Actions run/check is part of P2.6 closure.

New P2.6 Python sources/tests received local syntax compilation during development. No fresh full-repository pytest result is claimed because this environment does not have a repository checkout. Historical CI results must remain labeled historical.

## Phase pointer

```text
P0 COMPLETE
P1 COMPLETE
P2 IMPLEMENTATION CODE COMPLETE
P2 real-video acceptance execution PENDING
P3 structured 02 拉片 UI NEXT
P4 Draft-guided Scene/Prop PLANNED
P5 Draft ↔ Character safe integration PLANNED
P6 Final fill-back/renderers PLANNED
P7 remake integration PLANNED
```

Next implementation work should consume the P2 APIs/Draft in P3 rather than duplicate model logic.
