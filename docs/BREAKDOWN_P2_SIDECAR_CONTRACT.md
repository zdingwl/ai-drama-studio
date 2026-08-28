# AI Drama Studio — Breakdown P2 Evidence / Fusion / Production Contract

> **Status:** **P2 IMPLEMENTATION COMPLETE / REAL-VIDEO ACCEPTANCE PENDING**  
> **Contract date:** 2026-08-27  
> **Last synchronized:** 2026-08-28 10:17 +08:00  
> **Parent:** `docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md`  
> **P1 schema:** `breakdown-draft-v1`  
> **P2 sidecar schema:** `breakdown-p2-evidence-v1`  
> **P2 production profile:** `breakdown-p2-full-v1`  
> **P2 acceptance schema:** `breakdown-p2-acceptance-v1`

## 0. P2 purpose

P2 does not create a second Breakdown database schema. It turns real multimodal observations into the already-frozen P1 anonymous Draft contract:

```text
Current frozen ShotRevision
+ exact ShotRevisionItems / Reference Clips / keyframes
+ Episode audio
        ↓
ASR / OCR / VLM Provider Adapters
        ↓
validated immutable raw Evidence sidecars
        ↓
deterministic Fusion
        ↓
P1 SceneSegmentDraft / ShotSemanticDraft / LocalSubject / TimelineEvent / DraftPropHint
        ↓
precise BreakdownEvidenceLink provenance
        ↓
P1 validator
        ↓
BreakdownRun READY / READY_WITH_WARNINGS
```

Core rule:

> Raw model Evidence and fused anonymous Draft must remain separate and traceable.

## 1. P2 subphases

```text
P2.1 unified Provider/Evidence + immutable sidecar                COMPLETE
P2.2 ASR Provider + segment/word timing                           COMPLETE
P2.3 OCR Observation Provider                                     COMPLETE
P2.4 anonymous Shot VLM semantics                                 COMPLETE
P2.5 deterministic ASR/OCR/VLM Fusion → P1 Draft/publish         COMPLETE
P2.6 production orchestration/background API                     COMPLETE
P2.6 runtime preflight/Windows runner                             COMPLETE
P2.6 real-video acceptance report/scoring/comparison tooling     COMPLETE
P2.6 real-video acceptance execution                             PENDING
```

Implementation completion and real-video acceptance are different facts. Code may be complete while a real Windows GPU sample run is still pending.

## 2. Provider input contract

Every Provider starts from an already-created `PROCESSING BreakdownRun` and its frozen source revision:

```text
BreakdownRun
→ project_id
→ episode_id
→ source_shot_revision_id

source ShotRevision
→ exact ShotRevisionItems
→ reference_clip_path
→ thumbnail_path
→ keyframes_json
→ start_us / end_us / duration_us

Episode Preprocess
→ audio_path

Project
→ source_language
```

Providers are forbidden from reconstructing historical input by reading Current `v2_shots` and guessing old Shots.

### 2.1 Run state / STALE

Provider/Fusion active writes only target `PROCESSING` Runs. If the Episode Current ShotRevision changes, the Run becomes STALE and must not be published as Current.

Long-running work rechecks revision status around model execution/persistence boundaries. Historical sidecars/Draft are never deleted just because a new revision exists.

## 3. Unified Provider contract

```python
class BreakdownP2Provider(Protocol):
    component: str

    def analyze(self, context: P2RunContext) -> P2ProviderResult:
        ...
```

Formal components:

```text
ASR
OCR
VLM
```

Formal Result fields:

```text
component
provider
model
status
evidence[]
metadata
warnings
```

Allowed statuses:

```text
READY
NO_EVIDENCE
NOT_CONFIGURED
NOT_AVAILABLE
FAILED
```

Rule:

```text
READY      → at least one consumable Evidence
non-READY  → no consumable Evidence
```

## 4. Raw Evidence contract

Formal `P2EvidenceRecord`:

```text
source_type
source_id
source_start_us
source_end_us
shot_revision_item_id
text
language
confidence
payload
```

Supported source types:

```text
ASR_SEGMENT
ASR_WORD
OCR_OBSERVATION
VLM_OUTPUT
FRAME
AUDIO_RANGE
RULE
```

Component source permissions:

```text
ASR → ASR_SEGMENT / ASR_WORD / AUDIO_RANGE / RULE
OCR → OCR_OBSERVATION / FRAME / RULE
VLM → VLM_OUTPUT / FRAME / AUDIO_RANGE / RULE
```

## 5. Time contract

Formal production time is integer microseconds.

When an Evidence record is Shot-bound, its absolute source range must fit inside the exact historical `ShotRevisionItem`.

### 5.1 ASR

ASR keeps Episode source absolute time and leaves `shot_revision_item_id = NULL` because speech can cross a video cut.

Fusion performs exact Shot assignment/splitting. If word timestamps exist, they are authoritative for split content/timing; segment-text overlap fallback is warning-bearing degradation only.

### 5.2 OCR

OCR observations are exact sampled-frame point observations:

```text
source_start_us = sampled frame source time
source_end_us   = source_start_us + 1µs
shot_revision_item_id = exact historical item
```

A single OCR frame must not pretend to define subtitle duration. Temporal duration may only be inferred during Fusion from repeated text/time/geometry observations.

### 5.3 VLM

One main `VLM_OUTPUT` may explain one usable historical Shot:

```text
source_start_us = ShotRevisionItem.start_us
source_end_us   = ShotRevisionItem.end_us
shot_revision_item_id = exact historical item
```

Internal `events[].start_ratio/end_ratio` are normalized Shot-relative hints. Fusion maps them to exact source microseconds using that Shot's frozen source interval.

## 6. Confidence contract

```text
0 <= confidence <= 1
or NULL
```

Examples:

```text
ASR_WORD.confidence = provider word probability when available
OCR_OBSERVATION.confidence = recognition score
VLM_OUTPUT.confidence = NULL
```

Generative VLM text is not treated as calibrated probability. VLM provenance records:

```text
confidence_policy = provider-output-unscored
```

Fusion does not invent a fake shared probability to make heterogeneous model outputs look comparable.

## 7. Anonymous / Final-ID boundary

Raw P2 Evidence and fused Draft may not contain Final business identity fields such as:

```text
character_id
scene_id
prop_id
asset_revision_id
speaker_character_id
shot_character_binding_id
shot_scene_binding_id
shot_prop_binding_id
```

P2.4 normalizes VLM output through a strict anonymous whitelist before P2.1 recursive Final-ID validation.

Semantic mapping rules:

```text
subject_A / 人物A / LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
```

## 8. Immutable sidecar persistence

Provider output is persisted under the Run workspace:

```text
workspace/<project>/episodes/<episode>/breakdown/<run>/evidence/
  asr/<sha256>.json
  ocr/<sha256>.json
  vlm/<sha256>.json
```

Fingerprint = SHA-256 of normalized serialized JSON. Writes use temp-file → atomic replace → final. Identical normalized output reuses the same artifact path; different output does not overwrite history.

`BreakdownRun.component_status_json` stores a compact component/provenance summary, not full model output.

## 9. EvidenceLink timing

Provider stages P2.1–P2.4 do not invent fake Run-level links because no Draft owner exists yet.

P2.5 creates `BreakdownEvidenceLink` only after Draft owners exist:

```text
SHOT_DRAFT
SCENE_SEGMENT
LOCAL_SUBJECT
TIMELINE_EVENT
PROP_HINT
```

Each owner links only to Evidence actually consumed for that owner. Bulk-linking every sidecar record to every Draft entity is forbidden.

## 10. ASR Provider baseline

Formal module:

```text
engine/app/breakdown_p2_asr_v1.py
FasterWhisperASRProvider
faster-whisper==1.2.1
default model = large-v3
beam_size = 5
vad_filter = true
word_timestamps = true
```

Outputs:

```text
ASR_SEGMENT
ASR_WORD
```

Device contract supports auto/cpu/cuda. Auto-selected CUDA load failure may visibly fall back to CPU; explicitly requested CUDA failure must fail closed.

P2 ASR does not write `studio_v2.Dialogue` and never maps a speaker directly to Character.

## 11. OCR Provider baseline — frozen

Formal module:

```text
engine/app/breakdown_p2_ocr_v1.py
RapidOCROCRProvider
rapidocr==3.9.2
PP-OCRv6 small
ONNX Runtime
default device = cpu
```

Default sampling:

```text
sample_interval_us = 500000
max_frames_per_shot = 12
text_score = 0.5
```

Every valid `OCR_OBSERVATION` keeps:

```text
exact historical ShotRevisionItem
source point time
text
recognition confidence
polygon/bbox/normalized geometry
frame sample provenance
```

Repeated frame text remains raw Evidence. P2.5 Fusion owns text/time/geometry stitching and duration inference.

Do not redo this OCR implementation without a concrete regression requiring a minimal fix.

## 12. VLM Provider baseline

Formal implementation:

```text
engine/app/breakdown_p2_vlm_v1.py
scripts/run_breakdown_vlm_qwen3.py
scripts/setup_breakdown_vlm_runtime.ps1
Qwen3VLSemanticProvider
provider = qwen3-vl
model = Qwen/Qwen3-VL-4B-Instruct
semantic schema = breakdown-p2-vlm-shot-semantics-v1
default device = cuda
video fps request = 2.0
max_new_tokens = 1536
max_pixels = 524288
```

Runtime:

```text
main Python 3.11 app
→ isolated .runtime/TransVLM/inference Python/CUDA environment
→ separate base Qwen3-VL-4B-Instruct content checkpoint
```

The transition-finetuned TransVLM checkpoint is not used as the content-semantic model.

VLM responsibility whitelist:

```text
scene location/interior/time/environment hints
shot summary/visual description/type/camera/composition/narrative hint
anonymous subject labels + appearance/activity/screen position/visibility/visual speaking state
VISUAL/ACTION events + normalized ratios
plot-relevant prop hints
```

VLM deliberately does not own dialogue/subtitle/sign/phone/document transcription; those are ASR/OCR responsibilities.

## 13. Deterministic Fusion contract

Formal module:

```text
engine/app/breakdown_p2_fusion_v1.py
profile = breakdown-p2-fusion-v1
```

Fusion never implicitly reruns ASR/OCR/VLM. It requires the Run's already-registered ASR/OCR/VLM sidecars and validates:

```text
file URI
SHA-256 fingerprint
sidecar schema
run/project/episode IDs
source ShotRevision
component/provider/model/status/evidence_count
P2 provider result contract
```

All three sidecars are required. ASR/OCR may be degraded (`NO_EVIDENCE / NOT_AVAILABLE`) with warnings; VLM must be READY.

### 13.1 Scene segments

Consecutive exact VLM scene signatures:

```text
location_hint + interior_exterior + time_of_day
```

may group into one SceneSegmentDraft. Missing/unknown location is conservative and does not trigger speculative merge.

### 13.2 Shot Draft coverage

Every frozen source ShotRevisionItem must receive exactly one ShotSemanticDraft with exact source bounds/snapshot. Missing per-Shot VLM semantics yields a conservative blank semantic Draft + warning rather than silently removing the Shot.

### 13.3 Anonymous LocalSubject grouping

Normal cross-Shot grouping is conservative semantic grouping, not identity resolution.

If an exact normalized appearance appears for >=2 simultaneous subjects in any Shot within the segment:

```text
appearance is ambiguous
→ appearance cannot be used as cross-Shot merge key in that segment
→ fall back to shot-local anonymous keys
```

This acts as a Draft-level cannot-link. The system prefers extra anonymous subjects over a false identity merge.

### 13.4 ASR events

Cross-cut ASR segments are intersected against exact frozen Shot boundaries. When word records exist, exact per-Shot text/timing is reconstructed from the word timestamps. Segment-text fallback is warning-bearing degradation only.

### 13.5 OCR events

Fusion groups OCR observations only when normalized text, temporal gap and geometry are compatible. Repeated observations may infer a duration through the last observation + sample interval clipped to Shot end. A single observation remains a 1µs point event.

### 13.6 VLM events

Normalized VLM ratios map to exact Shot source microseconds, clipped to valid positive intervals. VISUAL/ACTION participants reference only declared anonymous LocalSubjects in that Shot.

### 13.7 Props

Plot-relevant VLM prop hints become segment-scoped DraftPropHint with per-Shot DraftPropOccurrence. They remain hints, never Final Prop assets.

### 13.8 Publish

Fusion writes the Draft graph transactionally, records exact Evidence provenance, then calls the real P1 validator/publish gate. Validator hard error fails the Run. STALE state is preserved and never overwritten by generic failure closure.

## 14. Full P2 production orchestration

Formal module:

```text
engine/app/breakdown_p2_pipeline_v1.py
profile = breakdown-p2-full-v1
provider order = ASR → OCR → VLM
```

Purpose: there is one production path instead of separate callers inventing their own provider order/lifecycle.

Single Episode:

```text
create fresh frozen PROCESSING BreakdownRun
→ ASR Provider through P2.1 sidecar boundary
→ OCR Provider through P2.1 sidecar boundary
→ VLM Provider through P2.1 sidecar boundary
→ P2.5 Fusion
→ P1 validator/publish
```

Continuation policy:

```text
ASR READY / NO_EVIDENCE / NOT_AVAILABLE allowed
OCR READY / NO_EVIDENCE / NOT_AVAILABLE allowed
VLM READY required
FAILED / NOT_CONFIGURED fail closed
```

Pipeline failure provenance stored in immutable Run metadata uses only safe error type, not uncontrolled Provider exception text.

## 15. Background execution contract

Formal APIs:

```text
POST /api/episodes/{episode_id}/tasks/breakdown
POST /api/projects/{project_id}/tasks/breakdown-batch
```

They reuse the existing persistent BackgroundTask infrastructure.

Batch rule:

```text
Episode.sort_order
→ one episode at a time
→ concurrency = 1
```

A failed Episode is recorded and batch execution continues with later Episodes; aggregate task status becomes `READY_WITH_WARNINGS` when any episode failed or completed with warnings.

## 16. P2.6 runtime preflight

Formal API/CLI:

```text
GET /api/breakdown/p2/runtime-preflight
python scripts/run_breakdown_p2.py preflight --strict
```

Preflight checks local presence only:

```text
main Python
faster-whisper
RapidOCR
OpenCV
FFmpeg/FFprobe
isolated VLM Python/runner/model path
isolated torch/transformers/qwen_vl_utils imports
CUDA when explicitly required
nvidia-smi GPU/VRAM/driver metadata
```

Preflight performs no video inference, no model download and no BreakdownRun mutation.

## 17. Real-video acceptance contract

Formal module:

```text
engine/app/breakdown_p2_acceptance_v1.py
schema = breakdown-p2-acceptance-v1
```

API:

```text
POST /api/breakdown-runs/{run_id}/p2-acceptance
```

HTTP reports are always written into that Run's own workspace acceptance directory; the API does not accept arbitrary server output paths.

CLI may explicitly select an output path for local operator workflows.

### 17.1 Structural checks

At minimum:

```text
Run READY / READY_WITH_WARNINGS
ASR/OCR/VLM component sidecars registered
all sidecar fingerprints are SHA-256-shaped provenance
VLM READY
FUSION READY / READY_WITH_WARNINGS
ShotSemanticDraft count == frozen source ShotRevisionItem count
```

Structural failure → `STRUCTURAL_FAIL`.

### 17.2 Human review

0–5 review keys:

```text
asr_dialogue
asr_timing
ocr_text
vlm_scene
vlm_subjects
vlm_actions
vlm_props
fusion_completeness
fusion_timing
fusion_conflict_handling
```

OCR can be explicitly `not_applicable` only when the reviewed material genuinely has no reviewable text.

Acceptance states:

```text
STRUCTURAL_FAIL
NEEDS_HUMAN_REVIEW
NEEDS_TUNING
PASS
```

PASS requires:

```text
structural checks passed
all required review dimensions scored
minimum required score >= 4.0 / 5.0
no blocking issues
```

Machine metrics cannot automatically self-certify real-video quality.

### 17.3 Comparison

Existing acceptance JSON reports can be ranked without model reruns:

```text
python scripts/run_breakdown_p2.py compare <report-a> <report-b> ...
```

Provider/model/parameter candidates must use separate Runs so Evidence remains traceable.

## 18. Windows local runner

```text
scripts/run_breakdown_p2_windows.ps1
```

Default behavior:

```text
strict runtime preflight
→ full Episode P2 run
→ acceptance report
```

Optional human review template:

```text
scripts/p2_acceptance_review_template.json
```

No GitHub hosted CI is required for this local acceptance flow.

## 19. P2 all-stage forbidden writes

P2 must not create/update:

```text
Character
Scene
Prop
AssetRevision
ShotCharacterBinding
ShotSceneBinding
ShotPropBinding
```

P2 also must not change Character V10.1 identity thresholds, same-sample cannot-link, high-quality Face conflict behavior, explicit Shot Assignment authority or Final Character Gate.

## 20. Stable implementation gate

Implemented artifacts now include:

```text
[x] exact frozen ShotRevision Provider context
[x] unified Provider/Result/Evidence contract
[x] immutable fingerprinted sidecars
[x] ASR segment/word timing
[x] OCR exact historical multi-frame observations
[x] strict anonymous VLM Shot semantics
[x] deterministic Fusion
[x] exact EvidenceLink provenance
[x] real P1 validator/publish
[x] conservative same-Shot anonymous cannot-link
[x] full production ASR→OCR→VLM→Fusion orchestrator
[x] single Episode background task
[x] sequential batch Breakdown task
[x] runtime preflight
[x] Windows local runner
[x] acceptance JSON report and scoring contract
[x] acceptance comparison tool
[x] focused tests for production orchestration and acceptance scoring added
```

Not truthfully checked in this environment:

```text
[ ] real short-drama end-to-end model inference
[ ] user Windows GPU runtime execution
[ ] human-reviewed PASS acceptance report
```

Reason: the repository contains no real short-drama video sample and this development session does not run on the user's Windows GPU host.

Therefore the formal status is:

```text
P2 IMPLEMENTATION CODE = COMPLETE
P2 REAL-VIDEO ACCEPTANCE EXECUTION = PENDING
```

See `docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md` for the exact local acceptance procedure.
