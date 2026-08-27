# AI Drama Studio — Project State

> **Last synchronized:** 2026-08-27 22:05 +09:00  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Branch:** `main`  
> **Architecture:** Reference Video V2  
> **FastAPI app version:** `2.4.1`  
> **Formal Character runtime:** Character V10.1  
> **Breakdown-first phase:** P2 IN PROGRESS / P2.1 + P2.2 COMPLETE / P2.3 NEXT

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
PROJECT_STATE + CURRENT_IMPLEMENTATION_MANIFEST + current code/tests
= CURRENT

BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN
= accepted TARGET + phase status

BREAKDOWN_DRAFT_DATA_CONTRACT
= frozen P1 semantic/data contract consumed by later phases

BREAKDOWN_P2_SIDECAR_CONTRACT
= P2 Provider/raw-Evidence sidecar contract + implemented subphase status
```

Do not mark P2.3+ as implemented because ASR now exists. Do not mark P2 complete until OCR/VLM/Fusion/real-video closure are complete.

## 2. Accepted Breakdown-first product direction

The accepted target remains:

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

Important distinction after P2.2:

```text
P1 implemented
= the anonymous Draft data/runtime/history contract exists

P2.1 implemented
= exact ShotRevision provider input + unified raw Evidence contract + immutable local sidecar persistence exist

P2.2 implemented
= formal local ASR Provider can generate anonymous ASR_SEGMENT + ASR_WORD Evidence with source microsecond timing

P2.3–P2.5 not implemented
= OCR/VLM providers and fusion into complete P1 Draft rows are still absent

P3 not implemented
= 02 拉片 does not yet expose the final structured Draft workbench
```

`transvlm_runtime_v51.py` remains a Qwen3-VL-based transition-detection/caching route. It must not be described as the P2 semantic Breakdown engine.

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

The target meaning of `02 拉片` is broader than Shot segmentation, but the current UI has not yet reached that P3 target.

## 4. Current Shot / Reference Video V2 baseline

Formal media chain:

```text
engine/app/main.py
→ engine/app/media_v2.py
→ studio_v2.Project / Episode / Shot
→ shot_revision_v2.ShotRevision / ShotRevisionItem
→ Reference Clip / thumbnail / keyframes
```

Current behavior includes:

```text
FFprobe authoritative timing
FFmpeg preprocess/proxy
integer microseconds
TransNetV2 Shot boundaries
per-Shot Reference Clip
ShotRevision history
manual boundary edit
split
merge
auto rerun
restore
```

Shot ID is not permanent across all revisions. Historical semantic data therefore anchors to `ShotRevision` / `ShotRevisionItem`, not only Current `v2_shots.id`.

## 5. Breakdown P1 — COMPLETE

P1 was implemented in the formal V2 data domain:

```text
engine.app.studio_v2.Base
+ data_v2/studio_v2.sqlite3
```

It does not use the historical `core.database/app.db` / `shot_workbench.py` data domain.

### 5.1 P1 production modules

```text
engine/app/breakdown_models_v1.py
engine/app/breakdown_service_v1.py
engine/app/breakdown_validator_v1.py
engine/app/breakdown_serializer_v1.py
engine/app/breakdown_routes_v1.py
engine/app/shot_revision_v2.py      # P1.6 STALE integration
```

### 5.2 P1 ADD-only tables

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

Resolution/fill-back tables remain later-phase concerns; P1 does not introduce Final Asset IDs into anonymous Draft entities.

### 5.3 P1 semantic separation

```text
LocalSubject / 人物A / 人物B
!= Character

SceneSegmentDraft
!= Final Scene

DraftPropHint
!= Final Prop

Breakdown Evidence
!= Final Asset / Binding truth
```

Draft is semantic evidence/search context. It cannot bypass Character V10.1 identity gates or directly write `ShotCharacterBinding`.

### 5.4 Historical anchors

```text
BreakdownRun.source_shot_revision_id
→ ShotRevision

ShotSemanticDraft.source_shot_revision_item_id
→ ShotRevisionItem

ShotSemanticDraft.source_shot_id_snapshot
= historical snapshot only
```

This is why an old Breakdown remains readable after Current Shots are replaced.

### 5.5 Run lifecycle + validator

Implemented Run states:

```text
PROCESSING
READY
READY_WITH_WARNINGS
FAILED
STALE
```

Rules:

```text
Run starts from Episode Current ShotRevision
READY requires the real P1 validator
validation failure → FAILED and old Current remains
successful publish atomically switches Current Breakdown
historical Runs remain readable
```

Validator is fail-closed and checks ShotRevision/ShotRevisionItem coverage, segment ordering/timing, local-subject ownership, timeline timing, prop ownership, evidence links, confidence ranges and Final-Asset leakage.

### 5.6 Read-only history/API

Implemented read behavior:

```text
list Episode Breakdown Runs
get Episode Current Breakdown
get Breakdown by Run ID
serialize historical ShotRevisionItem provenance
open historical Reference Clip
```

Read-only access to an old/pre-P1 project does not silently create a BASELINE ShotRevision or BreakdownRun.

### 5.7 P1.6 automatic STALE

Any action that creates a new Current ShotRevision automatically marks active Breakdown Runs from older revisions `STALE`:

```text
auto rerun
manual boundary edit
split
merge
record_manual_revision
restore
```

ShotRevision switch + Breakdown STALE happen in the same database transaction.

STALE does **not** delete:

```text
old BreakdownRun / Draft rows
old ShotRevision / ShotRevisionItem
old Reference Clip
```

No heuristic migration by ordinal/time is performed.

## 6. P1.7 compatibility acceptance

P1.7 closes P1 with a durable Windows compatibility gate in `.github/workflows/v2-ci.yml`:

```text
job: breakdown-p1-windows
runner: windows-latest
```

Acceptance covers:

```text
fresh empty SQLite database
idempotent init_database()
ADD-only P1 table creation
pre-P1 historical V2 Project/Episode/Shot database
Windows paths with spaces/Chinese text
legacy Reference Clip readability
read-only Breakdown access with no hidden writes
full focused P1 lifecycle/validator/history/STALE regression
```

Verified P1 baseline:

```text
Windows focused P1 suite: 32/32 PASS
Ubuntu full pytest at P1 close: 28 failed, 219 passed, 1 skipped
Backend compile: PASS
FastAPI import/version: PASS
```

The 28 Ubuntu failures are the same existing legacy/runtime/environment categories. The whole repository is still **not globally green**.

Frontend continues to have the existing `vue-tsc` / TypeScript package compatibility build failure.

## 7. Formal Character V10.1 baseline — unchanged by Breakdown P1/P2

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

Formal pipeline:

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

Breakdown P1/P2.1/P2.2 did not change Character thresholds, same-sample cannot-link, Face hard-conflict behavior, identity creation gates or explicit Shot assignment.

Formal Final binding for new V10.1 Runs remains:

```text
ShotCharacterBinding
= explicit shot_presence_assignments only
```

Historical Runs without `shot_assignment_version` retain the old compatibility fallback.

For detailed Character behavior read `docs/ASSET_CHARACTER_RECOGNITION_V10_1.md` and `docs/CURRENT_IMPLEMENTATION_MANIFEST.md`.

## 8. Current Scene / Prop reality

Existing asset-side data boundaries remain:

```text
SceneCandidate / ShotSceneEvidence
PropCandidate / ShotPropEvidence
```

Current Scene candidate logic remains lightweight and is not the target semantic Scene resolver.

Current Prop path remains fail-closed; without reliable configured detection it may be `NOT_CONFIGURED`.

P1 `SceneSegmentDraft` / `DraftPropHint` are separate anonymous semantic layers and do not mean P4 is implemented.

## 9. Breakdown P2 — IN PROGRESS

Formal sidecar contract:

```text
docs/BREAKDOWN_P2_SIDECAR_CONTRACT.md
schema: breakdown-p2-evidence-v1
```

### 9.1 P2.1 unified Provider / raw Evidence sidecar — IMPLEMENTED

Formal module:

```text
engine/app/breakdown_p2_sidecar_v1.py
```

P2.1 recovers a `PROCESSING BreakdownRun` into an exact immutable provider context:

```text
BreakdownRun.source_shot_revision_id
→ exact ShotRevision
→ exact ShotRevisionItems
→ Reference Clip / thumbnail / keyframes
+ Episode preprocess audio
+ Project source_language
```

It defines one synchronous local Provider boundary for ASR/OCR/VLM and validates/persists raw Evidence as fingerprinted immutable JSON sidecars. Final Asset/Binding IDs are rejected recursively, and a STALE/non-current Run cannot continue active writes.

Raw Evidence remains separate from future fused Draft rows:

```text
workspace/<project>/episodes/<episode>/breakdown/<run>/evidence/<component>/<sha256>.json
```

P2.1 does not create fake Run-level `BreakdownEvidenceLink`; P2.5 Fusion will link actual Draft owner rows to consumed raw Evidence.

### 9.2 P2.2 formal ASR Provider — IMPLEMENTED

Formal module:

```text
engine/app/breakdown_p2_asr_v1.py
```

Current provider baseline:

```text
faster-whisper==1.2.1
default model: large-v3
config: AI_DRAMA_P2_ASR_MODEL / DEVICE / COMPUTE_TYPE / MODEL_CACHE
beam_size=5
vad_filter=true
word_timestamps=true
```

P2.2 outputs only anonymous raw Evidence:

```text
ASR_SEGMENT
ASR_WORD
```

Timing is converted to Episode source integer microseconds. `ASR_WORD` can retain provider word probability as confidence. Source/detected language, device/compute type, duration and segment/word counts are preserved as non-secret provenance metadata.

Crucial boundary:

```text
P2.2 ASR Evidence shot_revision_item_id = NULL
```

This is deliberate: dialogue can cross a Shot cut. P2.5 Fusion will split/assign by exact source time and ShotRevisionItem; P2.2 does not use an “overlap-max Shot” heuristic and does not write `studio_v2.Dialogue`.

Device behavior:

```text
auto → detect CTranslate2 CUDA
CUDA available → try cuda/float16
only auto mode may visibly fall back to cpu/int8 on CUDA load failure
explicit cuda failure → FAILED, no silent CPU fallback
missing audio → NOT_AVAILABLE
no speech → NO_EVIDENCE
model/transcription failure → FAILED
```

The provider loads lazily and caches the loaded model per provider instance. Focused CI uses an injected fake Whisper model, so CI does not download `large-v3` weights.

P2.2 does **not** implement speaker diarization or speaker→LocalSubject/Character mapping.

### 9.3 P2.3–P2.5 — NOT IMPLEMENTED YET

Still missing from the formal Breakdown path:

```text
P2.3 OCR Observation Provider
P2.4 VLM anonymous Shot semantics Provider
P2.5 ASR/OCR/VLM Fusion → complete P1 Draft → validator/publish
```

Historical `content_analysis_v2.py` ASR/Speaker helpers remain compatibility code. In particular, direct Speaker → CharacterCandidate mapping is not the P2 identity path; P2 speaker semantics stay anonymous until later resolution.

Qwen3-ASR + ForcedAligner remains a P2.6 real-material benchmark candidate. P2.2 contract tests do not claim `large-v3` is already proven best on the project’s real short-drama corpus.

## 10. Current implementation status

```text
01 剧集管理: IMPLEMENTED

02 拉片 infrastructure:
  preprocess: IMPLEMENTED
  Shot detection/timing: IMPLEMENTED
  Shot + Reference Clip: IMPLEMENTED
  ShotRevision/manual edit/history: IMPLEMENTED

  P1 anonymous Draft data model: IMPLEMENTED
  P1 Run lifecycle: IMPLEMENTED
  P1 validator: IMPLEMENTED
  P1 read-only serializer/API: IMPLEMENTED
  P1 history/reference compatibility: IMPLEMENTED
  P1 automatic ShotRevision → STALE: IMPLEMENTED
  P1 Windows empty/historical compatibility acceptance: IMPLEMENTED

  P2.1 Provider/raw Evidence sidecar contract: IMPLEMENTED
  P2.2 ASR Provider + segment/word timing: IMPLEMENTED
  P2.3 OCR Provider: NOT IMPLEMENTED
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

## 11. Phase status / next safe step

```text
P0 planning/contracts                            = COMPLETE
P1 Draft data/runtime contract + compatibility   = COMPLETE
P2 ASR/OCR/VLM anonymous Draft sidecar           = IN PROGRESS
  P2.1 Provider/Evidence sidecar                  = COMPLETE
  P2.2 ASR Provider + segment/word timing         = COMPLETE
  P2.3 OCR Provider                               = NEXT
  P2.4 VLM anonymous semantics                    = PLANNED
  P2.5 Fusion / P1 Draft publish                  = PLANNED
  P2.6 real-video/Windows/docs closure            = PLANNED
P3 02 拉片 structured Draft UI                   = PLANNED
P4 Draft-guided Scene / Prop evidence            = PLANNED
P5 Draft ↔ Character safe integration            = PLANNED
P6 Final fill-back + renderers                    = PLANNED
P7 downstream remake integration                 = PLANNED
```

**Do not start P3/P4/P5 while pretending P2 already exists.**

P2 consumes the P1 Contract rather than inventing a parallel semantic Draft schema.

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

## 12. Current test / CI reality

Latest P2.2 acceptance before status-only docs synchronization:

```text
Ubuntu backend compile: PASS
FastAPI import/version: PASS (2.4.1)
Ubuntu pytest: 28 failed, 230 passed, 1 skipped
Windows Breakdown P1 gate: PASS (same P1 regression suite)
Windows Breakdown P2 provider gate: 24/24 PASS
Frontend: existing build failure
```

The six additional Ubuntu passes over P2.1 are exactly the six new P2.2 ASR focused tests. The same 28 historical failures remain; no new P2.2 failure category was introduced.

Known backend failure categories include missing lightweight-CI `cv2`, missing `trackers`, FFmpeg assumptions, obsolete V6-era assertions and historical Final Gate/workspace expectations.

Do not claim the whole repository is green. Also do not describe the focused fake-model ASR tests as a real short-drama quality benchmark; that remains P2.6.

## 13. Documentation / phase-completion rule

A Breakdown phase/subphase is complete only when these agree:

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

P1 is closed. P2.1 and P2.2 are complete. The next safe implementation step is **P2.3 OCR Observation Provider**.
