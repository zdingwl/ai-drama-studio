# AI Drama Studio — Project State

> **Last synchronized:** 2026-08-28 09:18 +08:00  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Branch:** `main`  
> **Architecture:** Reference Video V2  
> **FastAPI app version:** `2.4.1`  
> **Formal Character runtime:** Character V10.1  
> **Breakdown-first phase:** P2 IN PROGRESS / P2.1 + P2.2 + P2.3 + P2.4 COMPLETE / P2.5 NEXT

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

Do not mark P2.5+ as implemented because ASR/OCR/VLM raw Evidence now exists. Do not mark P2 complete until Fusion and real-video closure are complete.

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

Current distinction after P2.4:

```text
P1 implemented
= anonymous Draft data/runtime/history contract exists

P2.1 implemented
= exact ShotRevision provider input + unified raw Evidence contract + immutable sidecar exists

P2.2 implemented
= formal local ASR Provider emits ASR_SEGMENT + ASR_WORD with source microsecond timing

P2.3 implemented
= formal local OCR Provider samples exact historical Reference Clips and emits shot-bound OCR_OBSERVATION

P2.4 implemented
= formal local Qwen3-VL Provider analyzes exact historical Reference Clips and emits strict anonymous shot-bound VLM_OUTPUT semantic JSON

P2.5 not implemented
= ASR/OCR/VLM Fusion into complete P1 Draft is absent

P3 not implemented
= 02 拉片 does not yet expose final structured Draft workbench
```

`transvlm_runtime_v51.py` remains the transition-detection/caching route using a transition-finetuned checkpoint. P2.4 is a separate semantic provider using the base `Qwen/Qwen3-VL-4B-Instruct` checkpoint; only the isolated Python/CUDA runtime environment is reused.

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

P1/P2.1/P2.2/P2.3/P2.4 do not change Character thresholds, same-sample cannot-link, Face hard conflict, identity creation gates or explicit Shot assignment. New V10.1 Final bindings remain explicit `shot_presence_assignments` only; historical Runs without assignment version retain compatibility fallback.

## 7. Current Scene / Prop reality

Existing asset-side boundaries remain:

```text
SceneCandidate / ShotSceneEvidence
PropCandidate / ShotPropEvidence
```

Current Scene logic is still lightweight, not target semantic Scene resolver. Prop remains fail-closed when reliable detection is not configured. P1 SceneSegmentDraft/DraftPropHint and P2 OCR/VLM semantics are anonymous Evidence layers, not Final Scene/Prop truth.

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

Outputs only anonymous `ASR_SEGMENT + ASR_WORD`, converted to Episode source integer microseconds. Dialogue can cross cuts, so P2.2 intentionally keeps `shot_revision_item_id = NULL`; P2.5 performs exact Shot assignment/splitting.

P2.2 does not write `studio_v2.Dialogue`, does not map speaker→Character, and does not publish BreakdownRun.

### 8.3 P2.3 formal OCR Observation Provider — IMPLEMENTED

Formal module: `engine/app/breakdown_p2_ocr_v1.py`.

```text
rapidocr==3.9.2
PP-OCRv6 small
ONNX Runtime
default device: cpu
config: AI_DRAMA_P2_OCR_*
sample_interval_us = 500000
max_frames_per_shot = 12
text_score = 0.5
```

P2.3 samples deterministic frames across every exact historical Reference Clip. Every valid text becomes `OCR_OBSERVATION` with exact `shot_revision_item_id`, source microsecond point time, confidence, polygon/bbox/normalized geometry and frame provenance.

Repeated text remains repeated raw Evidence. P2.5 owns temporal dedupe/stitching/duration inference. P2.3 does not create TimelineEvent or Final Scene/Prop.

### 8.4 P2.4 formal VLM anonymous Shot semantics Provider — IMPLEMENTED

Formal implementation:

```text
engine/app/breakdown_p2_vlm_v1.py
scripts/run_breakdown_vlm_qwen3.py
scripts/setup_breakdown_vlm_runtime.ps1
engine/tests/v2/test_breakdown_p2_vlm_v1.py
```

Formal baseline:

```text
provider: qwen3-vl
model: Qwen/Qwen3-VL-4B-Instruct
license: Apache-2.0
semantic schema: breakdown-p2-vlm-shot-semantics-v1
default device: cuda
video sampling request: 2 fps
max_new_tokens: 1536
max_pixels: 524288
config: AI_DRAMA_P2_VLM_*
```

Runtime rule:

```text
reuse isolated .runtime/TransVLM/inference Python/CUDA environment
!= reuse TransVLM transition checkpoint

P2.4 checkpoint:
.runtime/TransVLM/inference/pretrained/Qwen3-VL-4B-Instruct
```

Production loads the base Qwen3-VL model once per provider subprocess and analyzes exact historical Reference Clips sequentially. Model download is setup-only; production inference sets Hugging Face/Transformers offline mode.

Every usable Shot produces exactly one shot-bound `VLM_OUTPUT` over the historical Shot source interval. The payload is normalized through a strict anonymous whitelist:

```text
scene:
  location_hint / INT|EXT|MIXED|UNKNOWN / time_of_day / environment_description

shot:
  summary / visual_description / shot_type_hint / camera_motion_hint
  narrative_function_hint / composition_hint

subjects:
  subject_A / subject_B / ...
  appearance_summary / activity_summary / screen_position
  FULL|PARTIAL|OCCLUDED|UNKNOWN
  LIKELY_SPEAKING|NOT_SPEAKING|UNKNOWN

events:
  VISUAL|ACTION
  start_ratio / end_ratio
  anonymous subject labels

props:
  plot-relevant label hint
  LOW|MEDIUM|HIGH
  narrative reason
  anonymous subject labels
```

P2.4 deliberately does **not** ask the VLM to transcribe dialogue/subtitles/signs/phone text; P2.2 ASR and P2.3 OCR remain authoritative raw sources for those modalities. `speaking_state` is only a visual hint.

The adapter drops unknown model keys before persistence, including any attempted `character_id / scene_id / prop_id` or arbitrary raw model fields. The P2.1 recursive Final-ID guard remains a second fail-closed boundary.

Generative VLM confidence is not treated as calibrated probability; `VLM_OUTPUT.confidence = NULL` and provenance records `confidence_policy = provider-output-unscored`.

Status behavior:

```text
no historical Reference Clips → NOT_AVAILABLE
isolated runtime/checkpoint missing → NOT_AVAILABLE
provider process failure → FAILED
partial per-Shot failure + usable outputs → READY with warnings
all Shot outputs unusable/failed → FAILED
```

P2.4 does not create `SceneSegmentDraft`, `ShotSemanticDraft`, `LocalSubject`, `TimelineEvent`, `DraftPropHint`, Character, Scene, Prop, AssetRevision or Final Bindings. These boundaries remain for P2.5+.

### 8.5 P2.5 — NEXT / NOT IMPLEMENTED

Still missing:

```text
P2.5 load immutable ASR/OCR/VLM sidecars
→ align ASR across exact ShotRevisionItem boundaries
→ OCR temporal stitching/deduping
→ VLM + ASR + OCR evidence fusion
→ SceneSegmentDraft / ShotSemanticDraft / LocalSubject / TimelineEvent / DraftPropHint
→ BreakdownEvidenceLink provenance
→ P1 validator
→ publish READY / READY_WITH_WARNINGS
```

P2.5 must not create Final Character/Scene/Prop or Final Shot Bindings. Historical ASR/Speaker helpers remain compatibility code; direct Speaker → CharacterCandidate is not the P2 identity path.

P2.6 still owns real short-drama benchmark/Windows real-model quality closure. Contract/fake-runner CI is not proof that Qwen3-VL-4B, faster-whisper large-v3 or PP-OCRv6 small is the permanent quality winner.

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
  P2.4 VLM anonymous semantics Provider: IMPLEMENTED
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
```

## 10. Phase status / next safe step

```text
P0 planning/contracts                            = COMPLETE
P1 Draft data/runtime contract + compatibility   = COMPLETE
P2 ASR/OCR/VLM anonymous Draft sidecar           = IN PROGRESS
  P2.1 Provider/Evidence sidecar                  = COMPLETE
  P2.2 ASR Provider + segment/word timing         = COMPLETE
  P2.3 OCR Observation Provider                   = COMPLETE
  P2.4 VLM anonymous Shot semantics               = COMPLETE
  P2.5 Fusion / P1 Draft publish                  = NEXT
  P2.6 real-video/Windows/docs closure            = PLANNED
P3 02 拉片 structured Draft UI                   = PLANNED
P4 Draft-guided Scene / Prop evidence            = PLANNED
P5 Draft ↔ Character safe integration            = PLANNED
P6 Final fill-back + renderers                    = PLANNED
P7 downstream remake integration                 = PLANNED
```

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

P2.4 implementation acceptance at commit `4872333e4833eb421850509d860e11f58b1687a0`:

```text
Ubuntu backend compile: PASS
FastAPI import/version: PASS (2.4.1)
Ubuntu full pytest: 28 failed, 243 passed, 1 skipped
Windows Breakdown P2 provider suite: 37/37 PASS
Frontend: existing vue-tsc / TypeScript build failure
```

The six additional Ubuntu passes over P2.3 are exactly the six new P2.4 VLM focused tests. The same historical 28 backend failure categories remain; no new P2.4 backend failure category was introduced.

Known historical categories include missing lightweight-CI `cv2`, missing `trackers`, FFmpeg assumptions, obsolete V6-era assertions and historical Final Gate/workspace expectations.

Do not claim the whole repository is green. Do not claim contract/fake-provider tests are real-video VLM quality acceptance.

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

P1 is closed. P2.1–P2.4 are complete. The next safe implementation step is **P2.5 ASR/OCR/VLM Fusion → complete P1 Draft → validator/publish**.
