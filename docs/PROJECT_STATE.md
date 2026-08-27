# AI Drama Studio — Project State

> **Last synchronized:** 2026-08-27 21:48 +08:00  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Branch:** `main`  
> **Architecture:** Reference Video V2  
> **FastAPI app version:** `2.4.1`  
> **Formal Character runtime:** Character V10.1  
> **Breakdown-first phase:** P2 IN PROGRESS / P2.1 + P2.2 + P2.3 COMPLETE / P2.4 NEXT

## 1. Current-state source of truth

This file describes what the repository actually runs now. Older V1–V10/F06 plans are historical unless explicitly referenced here.

New-conversation recovery order:

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/CURRENT_IMPLEMENTATION_MANIFEST.md
→ docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
→ docs/BREAKDOWN_DRAFT_DATA_CONTRACT.md
→ docs/BREAKDOWN_P2_SIDECAR_CONTRACT.md
→ docs/ASSET_CHARACTER_RECOGNITION_V10_1.md    # when Character is involved
→ latest docs/sessions/* Breakdown handoff
→ current code/tests
```

Source-of-truth split:

```text
PROJECT_STATE + CURRENT_IMPLEMENTATION_MANIFEST + current code/tests = CURRENT
BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN = accepted TARGET + phase status
BREAKDOWN_DRAFT_DATA_CONTRACT = frozen P1 semantic/data contract
BREAKDOWN_P2_SIDECAR_CONTRACT = P2 Provider/raw-Evidence contract + implemented subphase status
```

Do not mark P2.4+ as implemented because ASR/OCR now exist. Do not mark P2 complete until VLM/Fusion/real-video closure are complete.

## 2. Accepted Breakdown-first product direction

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

Current distinction after P2.3:

```text
P1 implemented
= anonymous Draft data/runtime/history contract exists

P2.1 implemented
= exact ShotRevision provider input + unified raw Evidence contract + immutable sidecar exists

P2.2 implemented
= formal local ASR Provider emits ASR_SEGMENT + ASR_WORD with source microsecond timing

P2.3 implemented
= formal local OCR Provider samples exact historical Reference Clips and emits shot-bound OCR_OBSERVATION with text/confidence/geometry/source timing

P2.4–P2.5 not implemented
= VLM semantic Provider and ASR/OCR/VLM Fusion into complete P1 Draft are absent

P3 not implemented
= 02 拉片 does not yet expose final structured Draft workbench
```

`transvlm_runtime_v51.py` remains a Qwen3-VL transition-detection/caching route. It is not the P2.4 semantic Breakdown VLM engine.

## 3. Product workspaces

```text
01 剧集管理
02 拉片
03 资产
04 内容剧本
05 重制设计
06 生成 / 导出
```

Shot + Revision-owned Reference Clip remains the core production unit. Heavy media/model work remains sequential by default.

## 4. Current Shot / Reference Video V2 baseline

Formal media chain:

```text
engine/app/main.py
→ engine/app/media_v2.py
→ studio_v2.Project / Episode / Shot
→ shot_revision_v2.ShotRevision / ShotRevisionItem
→ Reference Clip / thumbnail / keyframes
```

Current behavior:

```text
FFprobe authoritative timing
FFmpeg preprocess/proxy
integer microseconds
TransNetV2 Shot boundaries
per-Shot Reference Clip
ShotRevision history
manual boundary edit / split / merge / auto rerun / restore
```

Shot ID is not permanent across revisions. Historical semantic data anchors to `ShotRevision / ShotRevisionItem`, not only Current `v2_shots.id`.

## 5. Breakdown P1 — COMPLETE

P1 uses formal V2 data domain:

```text
engine.app.studio_v2.Base
+ data_v2/studio_v2.sqlite3
```

Production modules:

```text
engine/app/breakdown_models_v1.py
engine/app/breakdown_service_v1.py
engine/app/breakdown_validator_v1.py
engine/app/breakdown_serializer_v1.py
engine/app/breakdown_routes_v1.py
engine/app/shot_revision_v2.py
```

ADD-only tables:

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

Semantic separation remains mandatory:

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
Breakdown Evidence != Final Asset / Binding truth
```

Historical anchors:

```text
BreakdownRun.source_shot_revision_id → ShotRevision
ShotSemanticDraft.source_shot_revision_item_id → ShotRevisionItem
ShotSemanticDraft.source_shot_id_snapshot = historical snapshot only
```

Run states:

```text
PROCESSING / READY / READY_WITH_WARNINGS / FAILED / STALE
```

READY requires the real P1 validator. Failed Runs never replace old Current. Successful publish atomically switches Current Breakdown. Historical Runs remain readable.

Any new Current ShotRevision automatically marks active old-revision Breakdown Runs STALE in the same DB transaction. STALE never deletes historical Draft/Revision/Reference Clips and no ordinal/time heuristic migrates old Draft.

P1 Windows compatibility gate remains durable and covers fresh/pre-P1 DBs, Unicode/space paths, idempotent ADD-only init, legacy Reference Clip readability, lifecycle/validator/history/STALE.

## 6. Formal Character V10.1 baseline — unchanged by Breakdown P1/P2

```text
Runtime profile: character-v10.1-capture-first-model-classification
Asset profile: f05-assets-v10.1-person-evidence-model-classification
Resolver: person-evidence-model-classifier-v10.1
Shot assignment version: v10.1-shot-character-assignment-1
Shot assignment source: V10_1_SHOT_CHARACTER_ASSIGNMENT
```

Models:

```text
YOLOX Person Detection
YoutuReID Person Re-identification
YuNet Face Detection
SFace Face embedding/support
```

Formal chain:

```text
Reference Clip / Shot
→ Person observations / Person Evidence
→ mature MOT
→ project-level Global Identity
→ RESOLVED / UNRESOLVED
→ explicit Shot × known-Character Assignment
→ Final Character Gate
→ Character + ShotCharacterBinding
```

P1/P2.1/P2.2/P2.3 did not change Character thresholds, same-sample cannot-link, Face hard conflict, identity creation gates or explicit Shot assignment. New V10.1 Final bindings remain explicit `shot_presence_assignments` only; historical Runs without assignment version retain compatibility fallback.

## 7. Current Scene / Prop reality

Existing asset-side boundaries remain:

```text
SceneCandidate / ShotSceneEvidence
PropCandidate / ShotPropEvidence
```

Current Scene logic is still lightweight, not target semantic Scene resolver. Prop remains fail-closed when reliable detector/VLM is not configured. P1 SceneSegmentDraft/DraftPropHint and P2 OCR text are anonymous evidence layers, not Final Scene/Prop.

## 8. Breakdown P2 — IN PROGRESS

Formal contract:

```text
docs/BREAKDOWN_P2_SIDECAR_CONTRACT.md
schema: breakdown-p2-evidence-v1
```

### 8.1 P2.1 Provider/raw Evidence sidecar — IMPLEMENTED

`engine/app/breakdown_p2_sidecar_v1.py` recovers a `PROCESSING BreakdownRun` into exact immutable Provider context:

```text
BreakdownRun.source_shot_revision_id
→ exact ShotRevision
→ exact ShotRevisionItems
→ Reference Clip / thumbnail / keyframes
+ Episode preprocess audio
+ Project source_language
```

ASR/OCR/VLM share one synchronous local Provider boundary. Provider results are validated and persisted as fingerprinted immutable JSON under:

```text
workspace/<project>/episodes/<episode>/breakdown/<run>/evidence/<component>/<sha256>.json
```

Final Asset/Binding IDs are rejected recursively. STALE/non-current Runs cannot continue active writes. P2.1 does not create fake Run-level BreakdownEvidenceLink; P2.5 will link actual Draft owners.

### 8.2 P2.2 formal ASR Provider — IMPLEMENTED

Formal module: `engine/app/breakdown_p2_asr_v1.py`.

```text
provider: faster-whisper==1.2.1
default model: large-v3
beam_size=5
vad_filter=true
word_timestamps=true
config: AI_DRAMA_P2_ASR_*
```

Outputs only anonymous `ASR_SEGMENT + ASR_WORD`, converted to Episode source integer microseconds.

Crucial boundary:

```text
P2.2 ASR Evidence shot_revision_item_id = NULL
```

Dialogue can cross cuts, so P2.5 Fusion splits/assigns against exact ShotRevisionItem. P2.2 does not write `studio_v2.Dialogue`, does not diarize speaker→Character, and does not publish BreakdownRun.

Device policy: auto CTranslate2 CUDA detection; only auto-selected CUDA may visibly fall back CPU; explicit cuda failure is FAILED. Missing audio → NOT_AVAILABLE; no speech → NO_EVIDENCE.

### 8.3 P2.3 formal OCR Observation Provider — IMPLEMENTED

Formal module: `engine/app/breakdown_p2_ocr_v1.py`.

Current baseline:

```text
rapidocr==3.9.2
PP-OCRv6 small
ONNX Runtime
OpenCV Reference Clip frame decoding
default device: cpu
config: AI_DRAMA_P2_OCR_*
```

P2.3 deliberately does **not** rely on only the middle thumbnail. For every exact historical ShotRevisionItem it samples deterministic frames across the whole historical Reference Clip, with configurable interval and max-frame cap.

Default sampling:

```text
sample_interval_us = 500000
max_frames_per_shot = 12
text_score = 0.5
```

Every valid OCR text becomes `OCR_OBSERVATION` with:

```text
exact shot_revision_item_id
Episode source integer-microsecond point time
text
recognition confidence
polygon_px / bbox_px / polygon_norm
frame dimensions + sample provenance
```

The 1µs interval represents a sampled frame point, not subtitle duration. Repeated subtitle/text observations across frames remain raw; P2.5 Fusion performs temporal dedupe/stitching/duration inference.

Status/device behavior:

```text
no historical Reference Clip → NOT_AVAILABLE
RapidOCR/OpenCV missing → NOT_AVAILABLE
engine init failure → FAILED
partial frame failures → warnings + continue
all frames unanalyzable → FAILED
frames analyzed but no text → NO_EVIDENCE
valid observations → READY

default cpu
auto may use CUDAExecutionProvider
auto-selected CUDA init failure → visible CPU fallback
explicit cuda unavailable/failure → FAILED, no silent fallback
```

P2.3 does not create TimelineEvent, does not materialize Scene/Prop from OCR text, and writes no Final Asset/Binding.

### 8.4 P2.4–P2.5 — NOT IMPLEMENTED

Still missing:

```text
P2.4 VLM anonymous Shot semantics Provider
P2.5 ASR/OCR/VLM Fusion → complete P1 Draft → validator/publish
```

Historical ASR/Speaker helpers remain compatibility code; direct Speaker → CharacterCandidate is not the P2 identity path.

`large-v3` and RapidOCR PP-OCRv6 small are current stable baselines, not real-material accuracy winners. P2.6 must benchmark actual short-drama quality, speed, VRAM and alternatives.

## 9. Current implementation status

```text
01 剧集管理: IMPLEMENTED

02 拉片 infrastructure:
  preprocess: IMPLEMENTED
  Shot detection/timing: IMPLEMENTED
  Shot + Reference Clip: IMPLEMENTED
  ShotRevision/manual edit/history: IMPLEMENTED

  P1 anonymous Draft data/runtime/history: IMPLEMENTED
  P1 validator/read API/STALE/Windows compatibility: IMPLEMENTED

  P2.1 Provider/raw Evidence sidecar: IMPLEMENTED
  P2.2 ASR Provider + segment/word timing: IMPLEMENTED
  P2.3 OCR Observation Provider: IMPLEMENTED
  P2.4 VLM anonymous semantics Provider: NOT IMPLEMENTED
  P2.5 Fusion → complete anonymous Draft publish: NOT IMPLEMENTED
  P2.6 real-video benchmark/closure: NOT IMPLEMENTED
  P3 structured Draft UI: NOT IMPLEMENTED
  Final standard/international Breakdown renderer: NOT IMPLEMENTED

03 资产:
  Character V10.1 Global Identity: IMPLEMENTED
  explicit Shot × known-Character Assignment: IMPLEMENTED
  Final Gate explicit assignment consumption: IMPLEMENTED
  historical old-Run fallback: PRESERVED
  Draft-guided Character integration: NOT IMPLEMENTED
  target semantic Scene resolver: NOT IMPLEMENTED
  targeted Prop evidence pipeline: NOT IMPLEMENTED
  separate Windows real-video Character SHOT 0001–0009 acceptance: pending

04 内容剧本: PLANNED / partial compatibility code exists
05 重制设计: PLANNED
06 生成 / 导出: PLANNED
```

## 10. Phase status / next safe step

```text
P0 planning/contracts                            = COMPLETE
P1 Draft data/runtime contract + compatibility   = COMPLETE
P2 ASR/OCR/VLM anonymous Draft sidecar           = IN PROGRESS
  P2.1 Provider/Evidence sidecar                  = COMPLETE
  P2.2 ASR Provider + segment/word timing         = COMPLETE
  P2.3 OCR Observation Provider                   = COMPLETE
  P2.4 VLM anonymous semantics                    = NEXT
  P2.5 Fusion / P1 Draft publish                  = PLANNED
  P2.6 real-video/Windows/docs closure            = PLANNED
P3 02 拉片 structured Draft UI                   = PLANNED
P4 Draft-guided Scene / Prop evidence            = PLANNED
P5 Draft ↔ Character safe integration            = PLANNED
P6 Final fill-back + renderers                    = PLANNED
P7 downstream remake integration                 = PLANNED
```

**Do not start P3/P4/P5 while pretending P2 already exists.** P2 consumes the P1 Contract rather than inventing a parallel semantic Draft schema.

P2 remains forbidden from writing:

```text
Character
Scene
Prop
ShotCharacterBinding
ShotSceneBinding
ShotPropBinding
AssetRevision
```

## 11. Current CI reality

P2.3 implementation acceptance:

```text
Ubuntu backend compile: PASS
FastAPI import/version: PASS (2.4.1)
Ubuntu full pytest: 28 failed, 237 passed, 1 skipped
Windows Breakdown P2 provider suite: 31/31 PASS
Windows Breakdown P1 regression gate: PASS
Frontend: existing vue-tsc / TypeScript build failure
```

The 7 additional Ubuntu passes over P2.2 are exactly the seven new P2.3 OCR focused tests. The same historical 28 backend failure categories remain; no new OCR failure category was introduced.

Known historical categories include missing lightweight-CI `cv2`, missing `trackers`, FFmpeg assumptions, obsolete V6-era assertions and historical Final Gate/workspace expectations.

Do not claim the whole repository is green. Do not claim contract/fake-provider tests are real-video OCR accuracy acceptance.

## 12. Documentation / phase-completion rule

A Breakdown phase is complete only when these agree:

```text
PROJECT_STATE.md
CURRENT_IMPLEMENTATION_MANIFEST.md
BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
BREAKDOWN_DRAFT_DATA_CONTRACT.md where applicable
BREAKDOWN_P2_SIDECAR_CONTRACT.md for P2
current code/tests
latest session handoff
```

For the next conversation, verify `main` SHA before relying on a handoff commit SHA.

P1 is closed. P2.1–P2.3 are complete. The next safe implementation step is **P2.4 VLM anonymous Shot semantics Provider**.