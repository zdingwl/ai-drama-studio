# Session Handoff — Breakdown P2.2 ASR Provider

> Date: 2026-08-27  
> Scope: Breakdown-first P2.2 only  
> Branch during implementation: `feat/breakdown-p2-2-asr-provider`

## Current phase

```text
P1 = COMPLETE
P2 = IN PROGRESS
  P2.1 Provider/raw Evidence sidecar = COMPLETE
  P2.2 ASR Provider + segment/word timing = COMPLETE
  P2.3 OCR Observation Provider = NEXT
```

Do not skip to P3/P4/P5. Do not interpret P2.2 as complete Breakdown generation.

## P2.2 formal implementation

New production module:

```text
engine/app/breakdown_p2_asr_v1.py
```

Provider contract:

```text
FasterWhisperASRProvider
component = ASR
provider = faster-whisper
pinned package = faster-whisper==1.2.1
default model = large-v3
```

Environment configuration:

```text
AI_DRAMA_P2_ASR_MODEL
AI_DRAMA_P2_ASR_DEVICE
AI_DRAMA_P2_ASR_COMPUTE_TYPE
AI_DRAMA_P2_ASR_MODEL_CACHE
```

Default inference options:

```text
beam_size = 5
vad_filter = true
word_timestamps = true
```

Formal entry:

```text
run_faster_whisper_asr(run_id)
→ P2.1 run_local_provider()
→ immutable ASR Evidence sidecar
→ BreakdownRun component/provenance metadata
```

## Evidence semantics

P2.2 emits:

```text
ASR_SEGMENT
ASR_WORD
```

All source time is converted to integer microseconds.

Critical rule:

```text
ASR segment/word shot_revision_item_id = NULL
```

Dialogue can cross Shot boundaries. P2.2 deliberately does not choose a largest-overlap Shot. P2.5 Fusion will split/assign raw ASR Evidence against exact ShotRevisionItem source-time boundaries and then create TimelineEvents.

`ASR_WORD.confidence` may store valid provider word probability. Provider diagnostics and source/detected language/device metadata remain provenance only.

P2.2 does not write `studio_v2.Dialogue`.

## Device behavior

```text
auto
→ detect CUDA through CTranslate2
→ CUDA available: try cuda/float16
→ auto-selected CUDA model-load failure: visible warning + cpu/int8 fallback allowed

explicit device=cuda
→ load failure = FAILED
→ no silent CPU fallback

missing audio → NOT_AVAILABLE
no speech → NO_EVIDENCE
load/transcription error → FAILED
```

The model is loaded lazily and cached on the Provider instance.

## Protected boundaries

P2.2 did NOT implement:

```text
speaker diarization
speaker → LocalSubject mapping
speaker → Character mapping
OCR
VLM semantic understanding
TimelineEvent / complete P1 Draft generation
Breakdown publish
```

P2 still may not write:

```text
Character
Scene
Prop
AssetRevision
ShotCharacterBinding
ShotSceneBinding
ShotPropBinding
```

Character V10.1 thresholds, same-sample cannot-link, Face hard conflict, explicit Shot assignment and Final Gate are unchanged.

## Tests / CI

New focused test file:

```text
engine/tests/v2/test_breakdown_p2_asr_v1.py
```

Six P2.2 tests cover:

```text
segment/word timing + zh language normalization
cross-Shot ASR remains unbound
missing audio
no speech
auto CUDA → visible CPU fallback
explicit CUDA failure remains FAILED
sidecar persistence + Unicode/space paths + no Final Asset materialization
```

PR acceptance before status-doc synchronization:

```text
Windows Breakdown P2 provider suite: 24/24 PASS
Windows Breakdown P1 regression gate: PASS
Ubuntu backend compile: PASS
FastAPI import/version: PASS
Ubuntu full pytest: 28 failed, 230 passed, 1 skipped
Frontend: existing vue-tsc / TypeScript build failure
```

The six additional Ubuntu passes over P2.1 are exactly the six P2.2 tests. The historical 28 backend failure categories are unchanged.

CI uses an injected fake Whisper model and does not download `large-v3` weights. Therefore this acceptance proves Provider/contract/runtime behavior, not real short-drama recognition quality.

## Model benchmark boundary

`faster-whisper large-v3` is the current formal P2.2 baseline because faster-whisper is already pinned in the project and supports local segment/word timing with a mature Windows path.

Qwen3-ASR + Qwen3 ForcedAligner remains a P2.6 benchmark candidate. P2.6 must compare real short-drama accuracy/readability, timing quality, speed, VRAM, Windows behavior and licensing/deployment before declaring the best production model.

The P2 Provider contract is intentionally model-swappable; changing the winning ASR provider later must not require a P1 Draft schema rewrite.

## Next safe step

```text
P2.3 — OCR Observation Provider
```

Before P2.3:

```text
1. verify current main SHA
2. read PROJECT_STATE / CURRENT_IMPLEMENTATION_MANIFEST
3. read BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN
4. read BREAKDOWN_DRAFT_DATA_CONTRACT
5. read BREAKDOWN_P2_SIDECAR_CONTRACT
6. read this handoff
7. inspect current code/tests
```

P2.3 should produce shot/frame-grounded `OCR_OBSERVATION` raw Evidence with text, confidence, polygon/box provenance and source microsecond timing; it must not directly create Final Scene/Prop/Binding.
