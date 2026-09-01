# AI Drama Studio — Current Implementation Manifest

> Last synchronized: **2026-09-01 +08:00**

## Baseline

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Product: Localized Remake V1
Final video target: local MiniMax H3
Target speech runtime: local Qwen3-TTS
Character runtime: Character V10.1
Formal UI: ProjectListV4 + ProjectStudioV4
```

R7/R8 rollback:

```text
backup/pre-r7-20260901
8abf420262255f464cb08a0aa783a36dd1c13d66
```

## User surface

```text
Project
Review Center
Output
```

Automatic internals do not create new top-level product pages.

## Current automatic preparation chain

```text
AUTO_REMAKE_PREP_V1

Preprocess
→ Shot Detection / Reference Clips
→ ASR / OCR / Qwen3-VL Breakdown / Fusion
→ Character V10.1 / Scene / Prop
→ Final Asset / Source ReviewIssues
→ SourceDramaSnapshot
→ TargetCharacter / SceneLocalizationMapping
→ TargetDialogue / Qwen3-TTS
→ RemakeTimeline
→ GenerationSegment
```

H3 rendering is a separate heavy background task:

```text
POST /api/projects/{project_id}/tasks/h3-generate-ready
```

## Persistent remake tables

```text
v2_project_remake_policies
v2_review_issues
v2_target_characters
v2_scene_localization_mappings
v2_target_voice_profiles
v2_target_dialogues
v2_remake_timelines
v2_generation_segments
v2_generation_attempts
```

## R2 SourceDramaSnapshot

Implementation:

```text
engine/app/source_drama_snapshot_contract_v1.py
engine/app/source_drama_snapshot_v1.py
engine/app/source_drama_snapshot_routes_v1.py
engine/app/source_drama_review_issue_sync_v1.py
```

Downstream source-fact boundary with deterministic `source_fingerprint`.

## R4 Target localization

Implementation:

```text
engine/app/target_localization_contract_v1.py
engine/app/target_localization_v1.py
engine/app/target_localization_routes_v1.py
frontend/src/components/TargetLocalizationReviewV1.vue
```

Core invariant:

```text
Source Character != TargetCharacter
Source Scene != target scene decision
```

## R5 TargetDialogue + local Qwen3-TTS

Implementation:

```text
engine/app/target_dialogue_contract_v1.py
engine/app/target_dialogue_v1.py
engine/app/target_dialogue_pipeline_v1.py
engine/app/target_dialogue_routes_v1.py
engine/app/qwen3_tts_runtime_v1.py
scripts/qwen3_tts_worker_v1.py
```

READY dialogue audio persists real `speech_duration_us`. Source ASR/OCR is immutable.

## R6 RemakeTimeline

Implementation:

```text
engine/app/remake_timeline_contract_v1.py
engine/app/remake_timeline_v1.py
engine/app/remake_timeline_routes_v1.py
```

Persistent table:

```text
v2_remake_timelines
```

Consumes real target speech duration and plans target timing without rewriting source facts.

## R7 GenerationSegment

Implementation:

```text
engine/app/generation_segment_contract_v1.py
engine/app/generation_segment_v1.py
engine/app/generation_segment_routes_v1.py
```

Persistent table:

```text
v2_generation_segments
```

Compile boundary:

```text
SourceDramaSnapshot
+ TargetLocalization
+ TargetDialogue
+ RemakeTimeline
→ GenerationSegment
```

Rules:

```text
Shot != GenerationSegment
H3 render = 4..15 seconds
>15-second target shot = multiple segments
<4-second target = planned post trim
Ref2VA visual reference = 2..15 seconds
```

Routes are explicitly under `/api`.

## R7 H3 Runtime / Provider

Implementation:

```text
engine/app/h3_runtime_v1.py
engine/app/video_generation_provider_v1.py
engine/app/minimax_h3_provider_v1.py
```

Dependency direction:

```text
business
→ VideoGenerationProvider
→ MiniMaxH3Provider
→ H3RuntimeManager
→ local SGLang
```

Defaults:

```text
FL2VA  http://127.0.0.1:30010
Ref2VA http://127.0.0.1:30011
model  MiniMaxAI/MiniMax-H3
```

Current SGLang request adapter supplies:

```text
model
prompt
seconds
task = t2va | fl2va | ref2va
conditions
target
num_outputs_per_prompt
num_inference_steps
flow_shift
audio_flow_shift
seed
```

FL2VA condition addressing supports `frame_index=0|-1`; video/audio reference seek supports `start_time_seconds`.

## R8 H3 Context Compiler

Implementation:

```text
engine/app/h3_context_contract_v1.py
engine/app/h3_context_compiler_v1.py
engine/app/h3_reference_assets_v1.py
```

Responsibilities:

```text
internal Studio reference URL
→ local filesystem path
→ stable SHA256-tracked H3 condition
```

Ref2VA context:

```text
current TargetCharacter reference image(s)
+ optional localized Scene reference image
+ silent source directing/reference video
+ exact target-dialogue audio timeline when present
+ Context-IR-style prompt
```

Important: source Reference Clips may retain source audio for analysis/review, but the H3 compiler creates a new `-an` visual-only reference so source-language audio cannot leak into Ref2VA.

Target TTS reference is separately mixed to exact segment offsets as 32 kHz stereo.

FL2VA continuation uses the previous current successful output final frame with `frame_index=0`.

## R8 automatic target reference assets

Implementation:

```text
engine/app/h3_reference_assets_v1.py
```

TargetCharacter:

```text
current target definition
→ FL2VA endpoint in t2va mode
→ 4-second casting reference clip
→ reusable stills
```

LOCALIZE Scene:

```text
target scene definition
→ FL2VA endpoint in t2va mode
→ empty environment clip
→ reusable scene still
```

Reference assets are fingerprinted runtime assets and are not user-facing pages.

## R8 GenerationAttempt

Implementation:

```text
engine/app/generation_attempt_v1.py
engine/app/h3_generation_routes_v1.py
```

Persistent table:

```text
v2_generation_attempts
```

Lifecycle:

```text
PLANNED → SUBMITTED → RUNNING → SUCCEEDED | FAILED
upstream changed → STALE
```

One attempt stores:

```text
GenerationSegment input fingerprint
H3 context fingerprint
provider / mode
immutable request payload
external H3 job id / provider status
final output path
error / timestamps
```

Execution performs real provider submit, poll and download. For a target segment shorter than H3's minimum render duration, the downloaded H3 output is precisely trimmed back to `post_trim_duration_us` before it becomes the current successful output.

Studio restart fails orphaned local executor attempts instead of leaving permanent false-running rows.

APIs:

```text
POST /api/projects/{project_id}/generation-segments/{segment_id}/h3-context/compile
POST /api/projects/{project_id}/tasks/h3-generate-ready
GET  /api/projects/{project_id}/generation-attempts
GET  /api/generation-attempts/{attempt_id}/video
```

## Main application wiring

`engine/app/main.py` now imports/registers:

```text
generation_segment_router
h3_generation_router
GenerationAttempt startup recovery
```

This guarantees `v2_generation_attempts` is registered before `init_database()` runs.

## Isolated acceptance

Tests:

```text
engine/tests/v2/test_generation_segment_v1.py
engine/tests/v2/test_h3_r8_v1.py
```

Jobs:

```text
r7-generation-segments
r8-h3-generation
```

R8 acceptance covers:

```text
current SGLang request body / task selection
FL2VA frame_index addressing
silent Ref2VA source-video materialization
target-language dialogue tags
exact post-trim of quantized H3 output
FastAPI R7/R8 route registration
```

On 2026-09-01 the isolated R7 and R8 jobs passed.

## Acceptance boundary

```text
CODE / ISOLATED REPOSITORY ACCEPTANCE = PASS
LOCAL H3 GPU / REAL PROJECT ACCEPTANCE = PENDING
```

Real acceptance still requires the user's actual local H3 runtimes and a real prepared Project.

Known unrelated repository debt remains outside R8:

```text
frontend package manifest / lock drift -> npm ci failure
historical Character / Breakdown stale expectations
full lightweight backend CI missing some heavy runtime dependencies
```

## Current frontier

```text
R9 H3 QC / automatic retry / selected output = NEXT
R10 Lip Sync + subtitle/audio/assembly/export
R11 legacy cleanup
```

R9 should inspect generated outputs, retry automatically where safe, and send only repeated/ambiguous failure to Review Center.
