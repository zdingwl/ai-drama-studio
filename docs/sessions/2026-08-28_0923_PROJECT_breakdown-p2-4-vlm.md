# Session Handoff — Breakdown P2.4 VLM Anonymous Shot Semantics Provider

> Date: 2026-08-28 09:23 +08:00  
> Repository: `zdingwl/ai-drama-studio`  
> Branch: `main`  
> Scope: **P2.4 only**

## 1. Current phase state

```text
P0  planning/contracts                         COMPLETE
P1  Draft data/runtime/history/compatibility   COMPLETE
P2  ASR/OCR/VLM anonymous Evidence/Draft       IN PROGRESS
  P2.1 Provider/raw Evidence sidecar            COMPLETE
  P2.2 ASR Provider                            COMPLETE
  P2.3 OCR Observation Provider                COMPLETE
  P2.4 VLM anonymous Shot semantics            COMPLETE
  P2.5 Fusion → complete P1 Draft              NEXT
  P2.6 real-video benchmark/closure            PLANNED
```

P2.4 completion means the formal anonymous **visual semantic raw-Evidence producer** exists. It does **not** mean ASR/OCR/VLM Fusion, complete anonymous Draft, structured 02 拉片 UI, speaker identity mapping, Final Asset resolution or Final Breakdown are complete.

## 2. User continuity requirement

This P2.4 work continued directly from merged PR #11 / P2.3 OCR closure.

**Do not redo or replace the existing OCR implementation.**

P2.3 remains the formal RapidOCR/PP-OCRv6 Observation Provider. P2.4 only read the OCR code/tests as Contract reference and added a separate VLM Provider.

## 3. Files introduced/changed by P2.4

Production:

```text
engine/app/breakdown_p2_vlm_v1.py
scripts/run_breakdown_vlm_qwen3.py
scripts/setup_breakdown_vlm_runtime.ps1
```

Tests/CI:

```text
engine/tests/v2/test_breakdown_p2_vlm_v1.py
.github/workflows/v2-ci.yml
```

Synchronized docs:

```text
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
docs/BREAKDOWN_P2_SIDECAR_CONTRACT.md
docs/sessions/2026-08-28_0923_PROJECT_breakdown-p2-4-vlm.md
```

P2.4 did not modify:

```text
engine/app/breakdown_p2_ocr_v1.py
engine/tests/v2/test_breakdown_p2_ocr_v1.py
Character V10.1 identity/assignment/final-gate implementation
```

## 4. Formal VLM baseline

```text
Provider class: Qwen3VLSemanticProvider
component: VLM
provider: qwen3-vl
model: Qwen/Qwen3-VL-4B-Instruct
semantic schema: breakdown-p2-vlm-shot-semantics-v1
default device: cuda
video fps request: 2.0
max_new_tokens: 1536
max_pixels: 524288
```

Configuration:

```text
AI_DRAMA_P2_VLM_MODEL
AI_DRAMA_P2_VLM_MODEL_PATH
AI_DRAMA_P2_VLM_PYTHON
AI_DRAMA_P2_VLM_RUNNER
AI_DRAMA_P2_VLM_DEVICE
AI_DRAMA_P2_VLM_FPS
AI_DRAMA_P2_VLM_MAX_NEW_TOKENS
AI_DRAMA_P2_VLM_MAX_PIXELS
AI_DRAMA_P2_VLM_FFMPEG_BIN
```

## 5. Runtime architecture

P2.4 intentionally does not install the Qwen3-VL Torch/Transformers stack into the formal main Python 3.11 environment.

It reuses the already isolated TransVLM Python 3.12/CUDA **runtime environment only**:

```text
main Python 3.11
→ breakdown_p2_vlm_v1.py
→ isolated subprocess
→ .runtime/TransVLM/inference/.venv
→ scripts/run_breakdown_vlm_qwen3.py
→ .runtime/TransVLM/inference/pretrained/Qwen3-VL-4B-Instruct
```

Important separation:

```text
HeyGenAI/TransVLM-Qwen3-VL-4B-Instruct
= transition-detection task checkpoint
!= P2.4 Breakdown semantic checkpoint
```

P2.4 uses the separate base `Qwen/Qwen3-VL-4B-Instruct` checkpoint for content semantics.

The runner loads the model once, then processes exact historical Reference Clips sequentially. Model download is setup-only; production inference uses offline Hugging Face/Transformers settings.

## 6. Input contract

P2.4 consumes the exact historical source frozen by the `PROCESSING BreakdownRun`:

```text
BreakdownRun.source_shot_revision_id
→ exact ShotRevision
→ exact ShotRevisionItems
→ each ShotRevisionItem.reference_clip_path
```

It does not rediscover input from Current `v2_shots`, and it does not rely on a single thumbnail as the content source.

Only existing historical Reference Clips are sent to the isolated runner.

## 7. Modality separation

P2.4 Prompt explicitly limits VLM responsibility to visually supported semantics:

```text
scene hints
shot summary / visual description
shot type / camera motion / composition hint
anonymous subjects
visible appearance / activity / screen position / visibility
visual speaking-state hint
VISUAL / ACTION events
plot-relevant prop hints
```

It explicitly does not ask the VLM to transcribe:

```text
dialogue
subtitles
signage
phone screens
documents
```

Those remain P2.2 ASR / P2.3 OCR responsibilities.

`LIKELY_SPEAKING` is only a visual hint and is not speaker identity or Character truth.

## 8. Anonymous semantic whitelist

Per usable Shot, the adapter produces a normalized `VLM_OUTPUT` payload with only:

```text
scene:
  location_hint
  interior_exterior = INT|EXT|MIXED|UNKNOWN
  time_of_day
  environment_description

shot:
  summary
  visual_description
  shot_type_hint
  camera_motion_hint
  narrative_function_hint
  composition_hint

subjects:
  subject_A / subject_B / ...
  appearance_summary
  activity_summary
  screen_position
  visibility = FULL|PARTIAL|OCCLUDED|UNKNOWN
  speaking_state = LIKELY_SPEAKING|NOT_SPEAKING|UNKNOWN

events:
  VISUAL|ACTION
  start_ratio/end_ratio in 0..1
  content
  anonymous subject labels

props:
  plot-relevant label
  LOW|MEDIUM|HIGH importance
  narrative reason
  anonymous subject labels
```

Unknown model fields are dropped before P2.1 validation. Attempted Final business IDs therefore do not persist, and the P2.1 recursive Final-ID guard remains a second fail-closed layer.

## 9. Timing and confidence

Each valid output is bound to the exact historical `ShotRevisionItem`:

```text
VLM_OUTPUT.source_start_us = ShotRevisionItem.start_us
VLM_OUTPUT.source_end_us   = ShotRevisionItem.end_us
shot_revision_item_id      = exact historical item id
```

This means the VLM output describes that Shot as a whole. It does not mean each internal action lasts the entire Shot.

Internal event ratios remain soft Shot-relative hints:

```text
start_ratio / end_ratio
```

P2.5 Fusion converts these against the exact Shot source interval and reconciles them with ASR/OCR.

VLM generative output is not treated as calibrated probability:

```text
VLM_OUTPUT.confidence = NULL
metadata.confidence_policy = provider-output-unscored
```

## 10. Status/failure behavior

```text
all historical Reference Clips missing → NOT_AVAILABLE
isolated Python/runner/checkpoint missing → NOT_AVAILABLE
whole provider/subprocess failure → FAILED
partial Shot failure + usable semantics → READY with warnings
all Shot semantics failed/unusable → FAILED
valid semantic output(s) → READY
```

Non-secret error type may be recorded; uncontrolled exception text/stdout/stderr is not copied into provenance.

## 11. Protected boundaries

P2.4 does not write:

```text
SceneSegmentDraft
ShotSemanticDraft
LocalSubject
ShotLocalSubject
TimelineEvent
TimelineEventSubject
DraftPropHint
DraftPropOccurrence
BreakdownEvidenceLink
studio_v2.Dialogue
Character
Scene
Prop
AssetRevision
ShotCharacterBinding
ShotSceneBinding
ShotPropBinding
```

It does not modify Character V10.1 thresholds, same-sample cannot-link, Face hard conflict, explicit Shot assignment or Final Character Gate.

## 12. Focused acceptance

Six P2.4 focused tests cover:

```text
exact historical ShotRevisionItem/source-time anchoring
anonymous normalized semantics
Final-ID / arbitrary-field whitelist protection
missing Reference Clips → NOT_AVAILABLE before inference
partial invalid Shot output → READY + warning with valid evidence preserved
all invalid/failed output → FAILED
real Run sidecar persistence/provenance with no Final Asset writes
```

The focused tests use an injected fake inference runner. CI does not download the 4B checkpoint and does not require a GPU.

Implementation-head acceptance at commit:

```text
4872333e4833eb421850509d860e11f58b1687a0
```

Results:

```text
Ubuntu backend compile: PASS
FastAPI import/version: PASS (AI Drama Studio 2.4.1)
Ubuntu full pytest: 28 failed, 243 passed, 1 skipped
Windows Breakdown P2 provider suite: 37/37 PASS
Frontend build: existing vue-tsc / TypeScript failure
```

The six pass-count increase over P2.3 is exactly the six P2.4 VLM focused tests. The known 28 backend failure categories remained unchanged; no new P2.4 backend failure category was introduced.

Do not claim the whole repository is green.

## 13. Real-model acceptance debt intentionally preserved for P2.6

P2.4 contract/runtime acceptance does **not** prove `Qwen3-VL-4B-Instruct`, 2fps or current max-pixel settings are optimal for real short-drama footage.

P2.6 must benchmark real material for:

```text
subject count/visibility/action accuracy
scene/location/environment semantics
plot-relevant prop hint precision/recall
short vs long Shot behavior
2fps / resolution sensitivity
Chinese and multilingual description quality
VRAM / throughput / model-load cost
Windows GPU stability
checkpoint cache/offline readiness
comparison with other suitably licensed VLM candidates if needed
```

## 14. Next safe subphase

Proceed to:

```text
P2.5 — ASR/OCR/VLM Fusion → complete P1 anonymous Draft → validator/publish
```

Before P2.5 coding, read current `main`, `PROJECT_STATE`, `CURRENT_IMPLEMENTATION_MANIFEST`, `BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN`, `BREAKDOWN_DRAFT_DATA_CONTRACT`, `BREAKDOWN_P2_SIDECAR_CONTRACT`, this handoff, and actual P2.1/P2.2/P2.3/P2.4 code/tests.

P2.5 must:

```text
load existing immutable sidecars without implicit model rerun
validate artifact/source-revision ownership
split cross-Shot ASR by exact source-time boundaries
stitch/dedupe OCR observations only at Fusion time
map VLM normalized event ratios through exact Shot intervals
produce complete P1 Draft rows for every source ShotRevisionItem
create precise BreakdownEvidenceLink provenance
run the real P1 validator
publish READY / READY_WITH_WARNINGS only on valid output
```

P2.5 must remain anonymous and must not jump ahead into Character/Scene/Prop Final Asset resolution or Final Shot Binding writes.
