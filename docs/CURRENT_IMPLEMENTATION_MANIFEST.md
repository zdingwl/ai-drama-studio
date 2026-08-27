# AI Drama Studio — Current Implementation Manifest

> Purpose: compact **code-aligned CURRENT manifest** for new conversations.  
> Last synchronized: **2026-08-27 23:10 +09:00**

## Repository baseline

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Architecture: Reference Video V2
FastAPI app version: 2.4.1
Formal Character runtime: Character V10.1
Breakdown-first infrastructure: P1 COMPLETE
Breakdown semantic inference: P2 IN PROGRESS / P2.1 + P2.2 + P2.3 COMPLETE / P2.4 NEXT
```

## Current vs Target — do not merge them

Executable CURRENT truth comes from:

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

Target product flow remains:

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

Current implementation has completed P1 and P2.1–P2.3. This means the anonymous Draft contract, unified raw Provider/Evidence sidecar, local ASR segment/word Evidence producer, and local OCR Observation producer exist. It does **not** mean VLM semantics, ASR/OCR/VLM Fusion into complete Draft rows, speaker identity mapping, structured 02 拉片 UI, asset resolution or final Breakdown are implemented.

```text
P1 storage/lifecycle/validator/read API/history/STALE = IMPLEMENTED
P2.1 Provider/raw Evidence sidecar                  = IMPLEMENTED
P2.2 ASR segment + word timing                     = IMPLEMENTED
P2.3 OCR Observation Provider                      = IMPLEMENTED
P2.4 VLM anonymous semantics                       = NOT IMPLEMENTED
P2.5 ASR/OCR/VLM → complete Draft fusion           = NOT IMPLEMENTED
P2.6 real-video benchmark/closure                  = NOT IMPLEMENTED
P3 structured 02 拉片 UI                           = NOT IMPLEMENTED
P4+ Draft-guided assets/fill-back/renderers         = NOT IMPLEMENTED
```

## Current Shot / media wiring

Formal current chain:

```text
engine/app/main.py
→ engine/app/media_v2.py
→ studio_v2.Project / Episode / Shot
→ shot_revision_v2.ShotRevision / ShotRevisionItem
→ Reference Clip / thumbnail / keyframes
```

Current media facts include FFprobe authoritative timing, integer microseconds, FFmpeg preprocess/proxy, TransNetV2 Shot boundaries, per-Shot Reference Clip, ShotRevision history, manual edit/split/merge/auto-rerun/restore.

Historical semantic data must anchor to `ShotRevision` / `ShotRevisionItem`, because Current `Shot.id` is not a permanent cross-revision historical anchor.

`transvlm_runtime_v51.py` remains a Qwen3-VL transition-detection/caching route and is **not** the P2.4 semantic Breakdown VLM provider.

## Breakdown P1 — executable infrastructure

Formal modules:

```text
engine/app/breakdown_models_v1.py
engine/app/breakdown_service_v1.py
engine/app/breakdown_validator_v1.py
engine/app/breakdown_serializer_v1.py
engine/app/breakdown_routes_v1.py
engine/app/shot_revision_v2.py      # P1.6 automatic STALE integration
```

Formal data domain:

```text
engine.app.studio_v2.Base
+ data_v2/studio_v2.sqlite3
```

P1 does not reconnect to historical `core.database/app.db` / `shot_workbench.py`.

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

Semantic separation remains mandatory:

```text
LocalSubject / 人物A / 人物B != Character
SceneSegmentDraft             != Final Scene
DraftPropHint                 != Final Prop
Breakdown Evidence            != Final Asset / Binding truth
```

Historical anchors:

```text
BreakdownRun.source_shot_revision_id
→ ShotRevision

ShotSemanticDraft.source_shot_revision_item_id
→ ShotRevisionItem

ShotSemanticDraft.source_shot_id_snapshot
= historical snapshot only
```

Run states:

```text
PROCESSING
READY
READY_WITH_WARNINGS
FAILED
STALE
```

`publish_breakdown_run()` calls the real fail-closed P1 validator. Validation checks revision/item coverage, segment order/timing, anonymous subject ownership, timeline timing/participants, prop ownership, EvidenceLink ownership, confidence and Final-Asset leakage.

Every operation that creates/switches a Current ShotRevision automatically marks active Breakdown Runs from older revisions STALE in the same database transaction. Historical Run/Draft/Revision/Reference Clip data remains readable and is never heuristic-migrated by ordinal/time.

Durable P1 Windows compatibility gate remains `breakdown-p1-windows`.

## Breakdown P2.1 — Provider / raw Evidence sidecar

Formal contract/module:

```text
docs/BREAKDOWN_P2_SIDECAR_CONTRACT.md
engine/app/breakdown_p2_sidecar_v1.py
schema: breakdown-p2-evidence-v1
```

Provider context is frozen to the exact P1 Run source:

```text
BreakdownRun.source_shot_revision_id
→ exact ShotRevision
→ exact ShotRevisionItems
→ Reference Clip / thumbnail / keyframes
+ Episode preprocess audio
+ Project source_language
```

Unified local components:

```text
ASR
OCR
VLM
```

Unified raw Evidence types:

```text
ASR_SEGMENT
ASR_WORD
OCR_OBSERVATION
VLM_OUTPUT
FRAME
AUDIO_RANGE
RULE
```

Raw Evidence persists as immutable fingerprinted sidecars:

```text
workspace/<project>/episodes/<episode>/breakdown/<run>/evidence/
  asr/<sha256>.json
  ocr/<sha256>.json
  vlm/<sha256>.json
```

Properties include normalized SHA-256 fingerprinting, atomic `.tmp → os.replace`, idempotent same-result reuse, no overwrite of different results, non-secret BreakdownRun component provenance, fail-closed Final Asset/Binding leakage checks and STALE/current-revision checks before/after inference and persistence.

P2.1 introduced no Final Asset/Binding writes and no parallel semantic Draft schema.

## Breakdown P2.2 — executable ASR Provider

Formal module/tests/dependency:

```text
engine/app/breakdown_p2_asr_v1.py
engine/tests/v2/test_breakdown_p2_asr_v1.py
engine/requirements.txt → faster-whisper==1.2.1
```

Formal baseline:

```text
FasterWhisperASRProvider
provider = faster-whisper
default model = large-v3
beam_size = 5
vad_filter = true
word_timestamps = true
```

Configuration:

```text
AI_DRAMA_P2_ASR_MODEL
AI_DRAMA_P2_ASR_DEVICE        # auto/cpu/cuda
AI_DRAMA_P2_ASR_COMPUTE_TYPE
AI_DRAMA_P2_ASR_MODEL_CACHE
```

Outputs only:

```text
ASR_SEGMENT
ASR_WORD
```

Timing is Episode source integer microseconds. P2.2 deliberately leaves `shot_revision_item_id = NULL`, because dialogue can cross a Shot cut; exact Shot assignment/splitting belongs to P2.5 Fusion.

Auto CUDA may visibly fall back to CPU on CUDA load failure. Explicit CUDA is fail-closed. Missing audio → NOT_AVAILABLE; no speech → NO_EVIDENCE; load/transcription failure → FAILED.

P2.2 does not write `studio_v2.Dialogue`, diarize speakers, map speakers to LocalSubject/Character, publish BreakdownRun or write Final Assets/Bindings.

`large-v3` is the current provider baseline, not a declared real-short-drama accuracy winner. Qwen3-ASR + ForcedAligner and other candidates remain P2.6 benchmark options.

## Breakdown P2.3 — executable OCR Observation Provider

Formal module/tests/dependency:

```text
engine/app/breakdown_p2_ocr_v1.py
engine/tests/v2/test_breakdown_p2_ocr_v1.py
engine/requirements.txt → rapidocr==3.9.2
```

Formal baseline:

```text
RapidOCROCRProvider
provider = rapidocr
OCR version = PP-OCRv6
model type = small
engine = ONNX Runtime
default device = cpu
```

Configuration:

```text
AI_DRAMA_P2_OCR_MODEL_TYPE          # small / medium
AI_DRAMA_P2_OCR_DEVICE              # cpu / auto / cuda
AI_DRAMA_P2_OCR_SAMPLE_INTERVAL_US
AI_DRAMA_P2_OCR_MAX_FRAMES_PER_SHOT
AI_DRAMA_P2_OCR_TEXT_SCORE
AI_DRAMA_P2_OCR_MODEL_CACHE
```

P2.3 consumes each exact historical `ShotRevisionItem.reference_clip_path` and samples multiple deterministic frames across the clip. It does **not** rely on only the middle thumbnail.

Each usable result becomes anonymous:

```text
OCR_OBSERVATION
→ exact shot_revision_item_id
→ Episode source integer microseconds
→ text / source language
→ provider confidence when valid
→ polygon_px / bbox_px / polygon_norm
→ frame dimensions / sample index / frame-relative time
```

OCR Evidence uses a 1µs point interval at the requested sampled source position. A sampled frame is not misrepresented as a subtitle duration. Repeated text across frames remains repeated raw Evidence; temporal dedupe, subtitle persistence/duration inference and cross-frame stitching belong to P2.5 Fusion.

Language routing maps common BCP-47/source languages into RapidOCR PP-OCRv6 recognition profiles while keeping the project source language on Evidence.

Device policy mirrors the P2 fail-closed principle:

```text
default cpu → stability-first
requested auto → CUDA when available, visible CPU fallback allowed on auto-selected CUDA load failure
requested cuda → CUDA unavailable/load failure = FAILED, no silent CPU fallback
missing all historical Reference Clips → NOT_AVAILABLE
no recognized text after usable frame inference → NO_EVIDENCE
no sampled frame can be analyzed → FAILED
```

The production adapter lazy-loads RapidOCR and converts project string config into RapidOCR 3.9.x `EngineType`, `LangDet`, `LangRec`, `ModelType`, `OCRVersion` enums inside the adapter boundary.

P2.3 writes no TimelineEvent, complete Draft row, Dialogue, Character, Scene, Prop, AssetRevision or Final Binding. OCR → semantic events/hints/assets remains later Fusion/resolution work.

Real short-drama OCR accuracy, sampling interval, CPU/GPU tradeoffs and PP-OCRv6 small/medium comparison remain P2.6 benchmark work; focused fake-engine tests are contract/runtime acceptance, not real-video quality proof.

## Formal Character V10.1 baseline — unchanged

```text
Character version: V10.1
Runtime profile: character-v10.1-capture-first-model-classification
Asset profile: f05-assets-v10.1-person-evidence-model-classification
Resolver: person-evidence-model-classifier-v10.1
Shot assignment version: v10.1-shot-character-assignment-1
Shot assignment source: V10_1_SHOT_CHARACTER_ASSIGNMENT
Primary identity model: YoutuReID Person Re-identification
Face role: optional identity support / known-identity Shot presence / high-quality conflict
Final identity gate: confirmed formal RESOLVED identity only
```

P1/P2.1/P2.2/P2.3 do **not** change Character thresholds, same-sample cannot-link, Face hard-conflict behavior, identity creation gates, explicit Shot assignment or Final Character Gate.

Formal current Character chain remains:

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

New identity remains fail-closed around independent-Shot/model-usable Person Evidence, stable Person-ReID identity class, unique result, same-sample cannot-link and no high-quality Face hard conflict. Explicit Shot assignment runs only after identity resolution and cannot create a Character.

For current Runs with `shot_assignment_version`:

```text
ShotCharacterBinding
= explicit shot_presence_assignments only
```

Historical Runs without that field retain the compatibility fallback.

## Current Scene / Prop / Dialogue reality

Existing asset-side boundaries remain:

```text
SceneCandidate / ShotSceneEvidence
PropCandidate / ShotPropEvidence
```

Current Scene candidate generation is still lightweight and is not the target semantic Scene resolver. Current Prop path remains fail-closed and may be `NOT_CONFIGURED` without reliable detection.

`studio_v2.Dialogue` and historical F05 ASR/Speaker helpers still exist for compatibility. Historical direct Speaker → CharacterCandidate mapping is not the P2 target; future speaker semantics stay anonymous until later resolution.

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
```

## Current validation state

```text
Breakdown P1.1 ADD-only data model: IMPLEMENTED
Breakdown P1.2 Run lifecycle: IMPLEMENTED
Breakdown P1.3 fail-closed validator: IMPLEMENTED
Breakdown P1.4 read-only serializer/API: IMPLEMENTED
Breakdown P1.5 focused/compatibility tests: IMPLEMENTED
Breakdown P1.6 ShotRevision automatic STALE integration: IMPLEMENTED
Breakdown P1.7 docs + Windows empty/historical compatibility acceptance: IMPLEMENTED

Breakdown P2.1 Provider/raw Evidence sidecar: IMPLEMENTED
Breakdown P2.2 ASR segment/word Evidence Provider: IMPLEMENTED
Breakdown P2.3 OCR Observation Provider: IMPLEMENTED
Breakdown P2.4 VLM anonymous semantics: NOT IMPLEMENTED
Breakdown P2.5 Fusion → P1 Draft publish: NOT IMPLEMENTED
Breakdown P2.6 real-video benchmark/Windows/docs closure: NOT IMPLEMENTED

P3 02 拉片 structured Draft UI: NOT IMPLEMENTED
P4 Draft-guided Scene/Prop evidence: NOT IMPLEMENTED
P5 Draft ↔ Character safe integration: NOT IMPLEMENTED
P6 Final fill-back/renderers: NOT IMPLEMENTED
P7 downstream remake integration: NOT IMPLEMENTED

Character V10.1 global identity classification: IMPLEMENTED
Independent Shot × known-Character assignment: IMPLEMENTED
Final Gate explicit assignment consumption: IMPLEMENTED
Historical old-Run fallback: PRESERVED
Windows real-video SHOT 0001–0009 Character acceptance: separate/pending

Whole repository CI: NOT GREEN
```

## Accepted Target phase pointer

```text
P0 planning/contracts                            = COMPLETE
P1 Draft data/runtime contract + compatibility   = COMPLETE
P2 ASR/OCR/VLM anonymous Draft sidecar           = IN PROGRESS
  P2.1 Provider/raw Evidence sidecar              = COMPLETE
  P2.2 ASR + segment/word timing                 = COMPLETE
  P2.3 OCR Observation Provider                  = COMPLETE
  P2.4 VLM anonymous Shot semantics              = NEXT
  P2.5 Fusion / P1 Draft publish                 = PLANNED
  P2.6 real-video/Windows/docs closure            = PLANNED
P3 02 拉片 structured Draft UI                   = PLANNED
P4 Draft-guided Scene / Prop evidence            = PLANNED
P5 Draft ↔ Character safe integration            = PLANNED
P6 Final fill-back + renderers                    = PLANNED
P7 downstream remake integration                 = PLANNED
```

## CI reality at P2.3 close

```text
Ubuntu backend compile: PASS
FastAPI import/version: PASS (AI Drama Studio 2.4.1)
Ubuntu full pytest: 28 failed, 237 passed, 1 skipped
Windows Breakdown P1 regression gate: PASS
Windows Breakdown P2 provider suite: 31/31 PASS
Frontend build: existing vue-tsc / TypeScript compatibility failure
```

The seven additional passes over P2.2 are exactly the seven P2.3 OCR focused tests. Existing 28 backend failures remain the known legacy/runtime/environment categories such as lightweight-CI missing `cv2`/`trackers`, FFmpeg assumptions, obsolete V6-era assertions and historical Final Gate/workspace expectations.

Do **not** claim the whole repository is green. Do **not** claim `large-v3` ASR or PP-OCRv6 OCR has won a real-video quality benchmark from these CI tests.

## Required new-conversation checks

Before any new Breakdown work:

```text
1. verify main SHA
2. read PROJECT_STATE + this manifest
3. read BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN
4. read BREAKDOWN_DRAFT_DATA_CONTRACT
5. read BREAKDOWN_P2_SIDECAR_CONTRACT
6. read latest Breakdown session handoff
7. verify current code/tests before changing anything
```

For P2 specifically:

```text
consume P1 entities; do not invent a parallel semantic Draft schema
bind Provider input to BreakdownRun.source_shot_revision_id
write only raw anonymous Evidence / later anonymous Draft layers
preserve integer microseconds
preserve immutable READY history
never write Final Character/Scene/Prop/Bindings
keep provider metadata/provenance non-secret
keep Windows compatibility
```

Next safe subphase: **P2.4 VLM anonymous Shot semantics Provider**.

Before changing Character binding behavior, continue to verify formal V10.1 runtime and explicit `shot_presence_assignments`. Do not use P1 Draft prose or P2 raw Evidence to bypass identity or assignment gates.
