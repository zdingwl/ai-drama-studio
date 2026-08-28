# AI Drama Studio — Current Implementation Manifest

> Purpose: compact **code-aligned CURRENT manifest** for new conversations.  
> Last synchronized: **2026-08-28**

## Repository baseline

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Architecture: Reference Video V2
FastAPI app version: 2.4.1
Formal Character runtime: Character V10.1
Breakdown-first infrastructure: P1 COMPLETE
Breakdown semantic inference: P2 IN PROGRESS / P2.1-P2.5 COMPLETE / P2.6 NEXT
```

## Current vs Target — do not merge them

Executable CURRENT truth:

```text
docs/PROJECT_STATE.md
+ docs/CURRENT_IMPLEMENTATION_MANIFEST.md
+ current code/tests
```

Accepted target/contracts:

```text
docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
docs/BREAKDOWN_DRAFT_DATA_CONTRACT.md
docs/BREAKDOWN_P2_SIDECAR_CONTRACT.md
```

Target flow remains:

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

Current implementation has completed P1 and P2.1–P2.5. The Draft contract, raw sidecar, ASR, OCR, anonymous Shot-level VLM semantics and deterministic multimodal Fusion into complete P1 Draft rows now exist. This still does **not** mean real-model quality closure, structured 02 拉片 UI, speaker identity mapping, asset resolution or Final Breakdown are implemented.

```text
P1 storage/lifecycle/validator/read API/history/STALE = IMPLEMENTED
P2.1 Provider/raw Evidence sidecar                  = IMPLEMENTED
P2.2 ASR segment + word timing                     = IMPLEMENTED
P2.3 OCR Observation Provider                      = IMPLEMENTED
P2.4 VLM anonymous Shot semantics                  = IMPLEMENTED
P2.5 ASR/OCR/VLM → complete Draft fusion           = IMPLEMENTED
P2.6 real-video benchmark/closure                  = NOT IMPLEMENTED / NEXT
P3 structured 02 拉片 UI                           = NOT IMPLEMENTED
P4+ Draft-guided assets/fill-back/renderers         = NOT IMPLEMENTED
```

## Current Shot / media wiring

```text
engine/app/main.py
→ engine/app/media_v2.py
→ studio_v2.Project / Episode / Shot
→ shot_revision_v2.ShotRevision / ShotRevisionItem
→ Reference Clip / thumbnail / keyframes
```

Current media facts: FFprobe authoritative timing, integer microseconds, FFmpeg preprocess/proxy, TransNetV2 Shot boundaries, per-Shot Reference Clip, ShotRevision history, manual edit/split/merge/auto-rerun/restore.

Historical semantic data anchors to `ShotRevision / ShotRevisionItem`; Current `Shot.id` is not a permanent cross-revision historical anchor.

`transvlm_runtime_v51.py` remains the Qwen3-VL **transition-detection** route. It is not the P2.4 semantic provider. P2.4 only reuses that route's isolated Python/CUDA environment and uses a separate base `Qwen/Qwen3-VL-4B-Instruct` checkpoint.

## Breakdown P1 — executable infrastructure

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

ADD-only P1 tables:

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

Mandatory semantic separation:

```text
LocalSubject / 人物A / 人物B != Character
SceneSegmentDraft             != Final Scene
DraftPropHint                 != Final Prop
Breakdown Evidence            != Final Asset / Binding truth
```

Run states:

```text
PROCESSING / READY / READY_WITH_WARNINGS / FAILED / STALE
```

`publish_breakdown_run()` uses the real fail-closed P1 validator. Any operation that changes Current ShotRevision marks active Breakdown Runs from older revisions STALE in the same DB transaction. Historical Run/Draft/Revision/Reference Clips remain readable.

## Breakdown P2.1 — Provider / raw Evidence sidecar

Formal module/contract:

```text
engine/app/breakdown_p2_sidecar_v1.py
docs/BREAKDOWN_P2_SIDECAR_CONTRACT.md
schema = breakdown-p2-evidence-v1
```

Frozen input:

```text
BreakdownRun.source_shot_revision_id
→ exact ShotRevision
→ exact ShotRevisionItems
→ Reference Clip / thumbnail / keyframes
+ Episode preprocess audio
+ Project source_language
```

Unified components:

```text
ASR / OCR / VLM
```

Unified raw Evidence:

```text
ASR_SEGMENT
ASR_WORD
OCR_OBSERVATION
VLM_OUTPUT
FRAME
AUDIO_RANGE
RULE
```

Raw Evidence persists as immutable SHA-256 sidecars under the Run workspace. Writes are atomic/idempotent, provenance is non-secret, Final Asset/Binding ID leakage is rejected recursively, and STALE/current-revision checks run before/after long inference and persistence.

## Breakdown P2.2 — executable ASR Provider

```text
engine/app/breakdown_p2_asr_v1.py
engine/tests/v2/test_breakdown_p2_asr_v1.py
faster-whisper==1.2.1
FasterWhisperASRProvider
model = large-v3
beam_size = 5
vad_filter = true
word_timestamps = true
```

Outputs only `ASR_SEGMENT + ASR_WORD` with Episode source integer microseconds. P2.2 deliberately keeps `shot_revision_item_id = NULL` because dialogue can cross Shot boundaries; P2.5 performs exact splitting/assignment.

No `studio_v2.Dialogue`, no speaker→Character mapping, no Final Assets/Bindings.

## Breakdown P2.3 — executable OCR Observation Provider

```text
engine/app/breakdown_p2_ocr_v1.py
engine/tests/v2/test_breakdown_p2_ocr_v1.py
rapidocr==3.9.2
RapidOCROCRProvider
PP-OCRv6 small
ONNX Runtime
default device = cpu
```

P2.3 consumes exact historical Reference Clips and samples multiple deterministic frames. Every valid `OCR_OBSERVATION` binds the exact historical `ShotRevisionItem`, keeps source microsecond point time, text/confidence, polygon/bbox/normalized geometry and sample provenance.

Repeated text is not deduped in OCR. P2.5 owns temporal stitching/duration inference. OCR does not create TimelineEvent or Final Scene/Prop.

## Breakdown P2.4 — executable VLM anonymous Shot semantics Provider

Formal implementation:

```text
engine/app/breakdown_p2_vlm_v1.py
engine/tests/v2/test_breakdown_p2_vlm_v1.py
scripts/run_breakdown_vlm_qwen3.py
scripts/setup_breakdown_vlm_runtime.ps1
```

Formal baseline:

```text
Qwen3VLSemanticProvider
provider = qwen3-vl
model = Qwen/Qwen3-VL-4B-Instruct
license = Apache-2.0
semantic schema = breakdown-p2-vlm-shot-semantics-v1
default device = cuda
video fps request = 2.0
max_new_tokens = 1536
max_pixels = 524288
```

Configuration:

```text
AI_DRAMA_P2_VLM_MODEL
AI_DRAMA_P2_VLM_MODEL_PATH
AI_DRAMA_P2_VLM_PYTHON
AI_DRAMA_P2_VLM_RUNNER
AI_DRAMA_P2_VLM_DEVICE          # auto/cpu/cuda
AI_DRAMA_P2_VLM_FPS
AI_DRAMA_P2_VLM_MAX_NEW_TOKENS
AI_DRAMA_P2_VLM_MAX_PIXELS
AI_DRAMA_P2_VLM_FFMPEG_BIN
```

Runtime architecture:

```text
main Python 3.11 app
→ P2.4 Provider
→ isolated .runtime/TransVLM/inference Python 3.12 runtime
→ scripts/run_breakdown_vlm_qwen3.py
→ separate base Qwen3-VL-4B-Instruct checkpoint
→ sequential exact historical Reference Clips
→ normalized VLM_OUTPUT
→ P2.1 immutable sidecar
```

The existing TransVLM transition-finetuned checkpoint is **not** reused for content semantics.

Per Shot, P2.4 whitelists only anonymous visual semantics:

```text
scene hints
shot summary / visual description / shot type / camera motion / composition
subject_A / subject_B ... appearance + activity + visual speaking_state
VISUAL / ACTION normalized-ratio events
plot-relevant prop hints
```

The prompt explicitly avoids dialogue/subtitle/sign/phone/document transcription. Those remain ASR/OCR responsibilities. It never asks for real names/global identities. The adapter drops arbitrary model keys before sidecar validation, so attempted `character_id / scene_id / prop_id` fields do not persist.

P2.4 uses `confidence = NULL`; generative output is not treated as calibrated probability. Provider metadata records `confidence_policy = provider-output-unscored`.

Failure policy:

```text
all historical Reference Clips missing → NOT_AVAILABLE
isolated runtime/checkpoint missing → NOT_AVAILABLE
provider subprocess failure → FAILED
partial Shot failures with usable semantics → READY + warnings
all Shot semantics failed/unusable → FAILED
```

P2.4 does not write `SceneSegmentDraft`, `ShotSemanticDraft`, `LocalSubject`, `TimelineEvent`, `DraftPropHint`, Dialogue, Character, Scene, Prop, AssetRevision or Final Bindings.

## Breakdown P2.5 — executable deterministic multimodal Fusion

Formal implementation:

```text
engine/app/breakdown_p2_fusion_v1.py
engine/tests/v2/test_breakdown_p2_fusion_v1.py
profile = breakdown-p2-fusion-v1
```

P2.5 consumes already persisted ASR/OCR/VLM sidecars; it never reruns Providers implicitly. It verifies the local artifact URI, SHA-256 fingerprint, sidecar schema, Run/Project/Episode/source ShotRevision/component identity and registered Provider metadata before Fusion.

Component policy:

```text
VLM READY required
ASR/OCR NO_EVIDENCE or NOT_AVAILABLE allowed with warnings
FAILED / NOT_CONFIGURED component blocks Fusion
STALE/non-current source revision blocks Fusion
```

Fusion behavior:

```text
SceneSegmentDraft:
  consecutive exact ShotRevisionItems only
  conservative adjacent merge on exact normalized scene signature

ShotSemanticDraft:
  exactly one per historical ShotRevisionItem
  exact Shot/time/ordinal snapshot

LocalSubject:
  Segment-scoped anonymous only
  exact normalized appearance may link across Shots
  same-Shot duplicate appearance creates a Segment-level cannot-link for that appearance
  ambiguous occurrences fall back to shot-local keys
  VLM subject labels never become Character identity

TimelineEvent:
  VLM VISUAL/ACTION ratio → exact Shot source microseconds
  ASR segment → exact Shot intersection; ASR_WORD timing preferred for split text/time
  OCR repeated observations → conservative text/time/geometry stitching

DraftPropHint:
  VLM plot-relevant hint → Segment-scoped hint + Shot occurrence

BreakdownEvidenceLink:
  created only after real Draft owners exist
  preserves source IDs/URIs back to immutable sidecars
```

The complete Draft graph is validated by the existing P1 validator and published through `publish_breakdown_run()`. P2.5 does not create Final Character/Scene/Prop, AssetRevision or Final Shot Bindings.

## Formal Character V10.1 baseline — unchanged

```text
Character version: V10.1
Runtime profile: character-v10.1-capture-first-model-classification
Asset profile: f05-assets-v10.1-person-evidence-model-classification
Resolver: person-evidence-model-classifier-v10.1
Shot assignment version: v10.1-shot-character-assignment-1
Shot assignment source: V10_1_SHOT_CHARACTER_ASSIGNMENT
Primary identity model: YoutuReID
Face role: optional support / known presence / hard conflict
```

P1/P2.1/P2.2/P2.3/P2.4/P2.5 do **not** change Character thresholds, same-sample cannot-link, Face hard-conflict behavior, identity creation gates, explicit Shot assignment or Final Character Gate.

For current V10.1 Runs with `shot_assignment_version`:

```text
ShotCharacterBinding = explicit shot_presence_assignments only
```

Historical Runs without that field retain compatibility fallback.

## Current Scene / Prop / Dialogue reality

```text
SceneCandidate / ShotSceneEvidence
PropCandidate / ShotPropEvidence
```

Current Scene candidate generation remains lightweight and current Prop can remain fail-closed/`NOT_CONFIGURED`. P2 VLM/Fusion scene/prop hints are semantic search hints, not Final assets.

`studio_v2.Dialogue` and historical F05 ASR/Speaker helpers remain compatibility code. Historical direct Speaker→CharacterCandidate is not the P2 target path.

## Current key Breakdown modules

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
```

## Current validation state

```text
P1.1-P1.7                                            = IMPLEMENTED
P2.1 Provider/raw Evidence sidecar                   = IMPLEMENTED
P2.2 ASR segment/word Evidence Provider              = IMPLEMENTED
P2.3 OCR Observation Provider                        = IMPLEMENTED
P2.4 VLM anonymous Shot semantics                    = IMPLEMENTED
P2.5 Fusion → P1 Draft publish                       = IMPLEMENTED
P2.6 real-video benchmark/Windows real-model closure = NOT IMPLEMENTED / NEXT
P3 structured 02 拉片 UI                             = NOT IMPLEMENTED
P4 Draft-guided Scene/Prop evidence                  = NOT IMPLEMENTED
P5 Draft ↔ Character safe integration                = NOT IMPLEMENTED
P6 Final fill-back/renderers                         = NOT IMPLEMENTED
P7 downstream remake integration                     = NOT IMPLEMENTED

Character V10.1 global identity                      = IMPLEMENTED
Independent Shot × known-Character assignment        = IMPLEMENTED
Final Gate explicit assignment consumption           = IMPLEMENTED
Historical old-Run fallback                          = PRESERVED
Whole repository CI                                  = NOT GREEN
```

## Verification reality at P2.5 close

P2.4 implementation head `4872333e4833eb421850509d860e11f58b1687a0` had:

```text
Ubuntu backend compile: PASS
FastAPI import/version: PASS (AI Drama Studio 2.4.1)
Ubuntu full pytest: 28 failed, 243 passed, 1 skipped
Windows Breakdown P2 provider suite: 37/37 PASS
Frontend build: existing vue-tsc / TypeScript compatibility failure
```

P2.5 initial test head `942f9f524d0ccd1f11c911d60b9b148b18d9396d` had:

```text
Ubuntu full pytest: 29 failed, 248 passed, 1 skipped
P2.5 focused tests: 5 passed / 1 failed
```

The sole new failure was same-Shot identical-appearance anonymous subjects being merged. The correction ending at `b59309d305a15dfa80e9a6af0f961f93fcac5bf9` adds a conservative Segment-level cannot-link for any appearance signature that co-occurs on multiple subjects in one Shot. A local pure-logic check confirms normal same-appearance cross-Shot linking still shares one key while the same-Shot collision yields distinct shot-local keys.

Per user instruction, no fresh GitHub Actions rerun was performed after the fix because CI quota is unavailable. Do **not** claim a new hosted 6/6 P2.5 run. Existing 28 backend failures remain known legacy/runtime/environment categories: lightweight CI missing `cv2`/`trackers`, FFmpeg assumptions, obsolete V6-era assertions and historical Final Gate/workspace expectations.

Do not claim the whole repository is green. Do not claim fake-runner/contract acceptance proves real short-drama Qwen3-VL/ASR/OCR quality.

## Accepted Target phase pointer

```text
P0 planning/contracts                            = COMPLETE
P1 Draft data/runtime contract + compatibility   = COMPLETE
P2 ASR/OCR/VLM anonymous Draft sidecar/Fusion    = IN PROGRESS
  P2.1 Provider/raw Evidence sidecar              = COMPLETE
  P2.2 ASR + segment/word timing                 = COMPLETE
  P2.3 OCR Observation Provider                  = COMPLETE
  P2.4 VLM anonymous Shot semantics              = COMPLETE
  P2.5 Fusion / P1 Draft publish                 = COMPLETE
  P2.6 real-video/Windows/docs closure            = NEXT
P3 02 拉片 structured Draft UI                   = PLANNED
P4 Draft-guided Scene / Prop evidence            = PLANNED
P5 Draft ↔ Character safe integration            = PLANNED
P6 Final fill-back + renderers                    = PLANNED
P7 downstream remake integration                 = PLANNED
```

## Required new-conversation checks

Before new Breakdown work:

```text
1. verify current main SHA
2. read PROJECT_STATE + this manifest
3. read BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN
4. read BREAKDOWN_DRAFT_DATA_CONTRACT
5. read BREAKDOWN_P2_SIDECAR_CONTRACT
6. read latest Breakdown session handoff
7. read actual P2 sidecar/ASR/OCR/VLM/Fusion code + focused tests
```

The next safe implementation step is **P2.6 real short-drama / real-model benchmark + Windows/local-GPU closure**, not P3 and not asset resolution.