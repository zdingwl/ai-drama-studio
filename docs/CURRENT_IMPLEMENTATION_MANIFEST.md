# AI Drama Studio — Current Implementation Manifest

> Last synchronized: **2026-09-02 +08:00**

## Baseline

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Product: Localized Remake V1
Final video target: local MiniMax H3
Target speech runtime: local Qwen3-TTS
Lip-sync runtime: local LatentSync 1.6
Background-audio runtime: local audio-separator worker
Character runtime: Character V10.1
Formal UI: ProjectListV4 + ProjectStudioV4
```

Rollback points:

```text
backup/pre-r9-20260901
backup/pre-r7-20260901
backup/pre-h3-remake-restructure-2026-09-01
```

## User surface

```text
Project
Review Center
Output
```

Automatic internals do not create new top-level product pages. `Output` prioritizes final Episode MP4/SRT; H3/PostProduction internals are advanced diagnostics.

## Automatic preparation chain

```text
AUTO_REMAKE_PREP_V1

Preprocess
→ Shot Detection / Reference Clips
→ ASR / OCR / Qwen3-VL Breakdown / Fusion
→ Character V10.1 / Scene / Prop
→ Final Asset
→ SourceDramaSnapshot
→ TargetCharacter / SceneLocalizationMapping
→ TargetDialogue / Qwen3-TTS
→ RemakeTimeline
→ GenerationSegment
```

Heavy H3 execution:

```text
POST /api/projects/{project_id}/tasks/h3-generate-ready

prepare target references
→ H3 GenerationAttempt
→ structural QC
→ semantic Qwen3-VL QC
→ automatic retry when safe
→ GenerationSelection / Selected Output
```

Heavy R10/R10.1 postproduction:

```text
POST /api/projects/{project_id}/tasks/postproduction

Selected Output
→ final target audio
→ LatentSync / target-face ROI LatentSync
→ PostProductionSegment
→ optional safe source background enhancement
→ SRT
→ normalized media
→ EpisodeOutput
→ MP4 + SRT
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
v2_generation_quality_checks
v2_generation_selections
v2_postproduction_segments
v2_episode_outputs
```

## R2 SourceDramaSnapshot

```text
engine/app/source_drama_snapshot_contract_v1.py
engine/app/source_drama_snapshot_v1.py
engine/app/source_drama_snapshot_routes_v1.py
engine/app/source_drama_review_issue_sync_v1.py
```

Downstream source-fact boundary with deterministic `source_fingerprint`.

## R4 Target localization

```text
engine/app/target_localization_contract_v1.py
engine/app/target_localization_v1.py
engine/app/target_localization_routes_v1.py
frontend/src/components/TargetLocalizationReviewV1.vue
```

```text
Source Character != TargetCharacter
Source Scene != target scene decision
```

## R5 TargetDialogue + local Qwen3-TTS

```text
engine/app/target_dialogue_contract_v1.py
engine/app/target_dialogue_v1.py
engine/app/target_dialogue_pipeline_v1.py
engine/app/target_dialogue_routes_v1.py
engine/app/qwen3_tts_runtime_v1.py
scripts/qwen3_tts_worker_v1.py
```

READY audio stores real `speech_duration_us`; source ASR/OCR remains immutable.

## R6 RemakeTimeline

```text
engine/app/remake_timeline_contract_v1.py
engine/app/remake_timeline_v1.py
engine/app/remake_timeline_routes_v1.py
```

Persistent table: `v2_remake_timelines`.

Consumes real target speech duration and plans target timing without rewriting source facts.

## R7 GenerationSegment + H3 provider

```text
engine/app/generation_segment_contract_v1.py
engine/app/generation_segment_v1.py
engine/app/generation_segment_routes_v1.py
engine/app/h3_runtime_v1.py
engine/app/video_generation_provider_v1.py
engine/app/minimax_h3_provider_v1.py
```

Provider boundary:

```text
business
→ VideoGenerationProvider
→ MiniMaxH3Provider
→ H3RuntimeManager
→ local SGLang
```

H3 sizing:

```text
4..15 seconds
>15-second target shot -> multiple GenerationSegments
<4-second target -> exact post-trim after H3
```

## R8 H3 Context / references / GenerationAttempt

```text
engine/app/h3_context_contract_v1.py
engine/app/h3_context_compiler_v1.py
engine/app/h3_reference_assets_v1.py
engine/app/generation_attempt_v1.py
engine/app/h3_generation_routes_v1.py
```

Persistent table: `v2_generation_attempts`.

Ref2VA receives current TargetCharacter references, optional LOCALIZE Scene reference, silent source directing/reference video and exact target-dialogue audio timeline. Source soundtrack is removed from the reference derivative.

`GenerationAttempt(SUCCEEDED)` only means the provider returned a usable technical file. R9 decides whether it becomes product-current output.

## R9 H3 QC / automatic retry / selected output

```text
engine/app/h3_qc_contract_v1.py
engine/app/h3_qc_core_v1.py
engine/app/h3_qc_orchestrator_v1.py
engine/app/h3_qc_v1.py
engine/app/h3_retry_execution_v1.py
engine/app/generation_selection_v1.py
engine/app/h3_qc_routes_v1.py
frontend/src/components/H3QcReviewV1.vue
frontend/src/components/H3OutputV1.vue
```

Persistent tables:

```text
v2_generation_quality_checks
v2_generation_selections
```

Authority rule:

```text
GenerationAttempt = immutable execution history
GenerationQualityCheck = QC result for an Attempt
GenerationSelection = current usable output pointer for one GenerationSegment
```

Downstream R10 consumes `GenerationSelection`, never merely the latest `SUCCEEDED` Attempt.

Structural gate uses ffprobe + full ffmpeg decode + target-duration tolerance. Semantic Qwen3-VL QC checks visual integrity, source actor leakage, target identity, scene, action/camera and FL2VA continuity.

```text
PASS -> GenerationSelection
RETRY -> new seed + QC correction prompt
WAITING_MODEL -> infrastructure wait, not human issue
ambiguous/repeated failure -> H3_QC
```

`H3_QC` is domain-edited; generic Ignore/Resolve is forbidden.

## R10 PostProduction / Lip Sync / EpisodeOutput

### Contracts and persistence

```text
engine/app/postproduction_contract_v1.py
engine/app/postproduction_v1.py
engine/app/episode_output_contract_v1.py
engine/app/episode_output_v1.py
```

Persistent tables:

```text
v2_postproduction_segments
v2_episode_outputs
```

Authority flow:

```text
GenerationSelection
→ PostProductionSegment
→ EpisodeOutput
```

### Lip sync

```text
engine/app/postproduction_lipsync_v1.py
engine/app/speaker_face_locator_v1.py
engine/app/latentsync_provider_v1.py
scripts/latentsync_worker_v1.py
```

Policy:

```text
off-screen dialogue -> target audio only, no mouth edit
single visible target speaker -> LATENTSYNC_FULL_SEGMENT
multi-face target speaker -> locate target identity -> LATENTSYNC_TARGET_FACE_ROI
locator/model unavailable -> waiting/model state
identity ambiguity -> REVIEW_MULTI_FACE + LIP_SYNC_QC
```

Multi-face localization is executed inside the background R10 task, not during read/compile APIs.

`LIP_SYNC_QC` is a domain-edited issue. Generic Ignore/Resolve is forbidden. The dedicated retry action re-enters real localization/postproduction and only closes the issue after successful work.

### Audio and subtitle behavior

TargetDialogue audio is materialized on the target timeline. If one dialogue starts in an earlier GenerationSegment, the later segment trims already-played audio instead of replaying the sentence start.

SRT behavior:

```text
UTF-8
uses target RemakeTimeline timestamps
one dialogue spanning multiple GenerationSegments is deduplicated
```

### Episode assembly

`EpisodeOutput` only uses `SUCCEEDED` PostProductionSegments. Segments are normalized before concat so mixed size/fps/audio-presence inputs do not silently break assembly.

Current output endpoints:

```text
GET /api/projects/{project_id}/outputs
GET /api/episodes/{episode_id}/final-video?project_id=...
GET /api/episodes/{episode_id}/subtitles?project_id=...
```

### R10 frontend

```text
frontend/src/components/FinalOutputV1.vue
frontend/src/components/LipSyncReviewV1.vue
frontend/src/components/H3OutputV1.vue
frontend/src/views/ProjectStudioV4.vue
frontend/src/api/remake.ts
frontend/src/types/remake.ts
```

Normal Output UX:

```text
final Episode result first
→ play final video
→ download MP4
→ download SRT
→ if H3 is pending, start H3 from Output
→ if postproduction is pending, continue finalization from Output
```

H3/PostProduction segment internals stay under advanced diagnostics.

## R10.1 safe background audio enhancement

### Provider and worker

```text
engine/app/background_audio_provider_v1.py
engine/app/audio_separator_provider_v1.py
scripts/audio_separator_worker_v1.py
scripts/requirements_audio_separator_v1.txt
```

Boundary:

```text
postproduction business code
→ BackgroundAudioProvider
→ AUDIO_SEPARATOR_LOCAL_V1
→ localhost audio-separator worker
```

The heavy separation stack is isolated from `engine/requirements.txt`. The dedicated worker requirements pin `audio-separator[gpu]==0.47.0`.

Default separator model:

```text
UVR-MDX-NET-Inst_HQ_5.onnx
```

It is configurable through `AI_DRAMA_BACKGROUND_AUDIO_MODEL`.

### Safety/mix core

```text
engine/app/background_audio_v1.py
engine/app/postproduction_audio_mix_v1.py
```

Safety invariant:

```text
raw source audio is never mixed into target output
```

Flow:

```text
source Episode/Shot audio
→ exact source-Shot WAV
→ separator Instrumental stem
→ SourceDramaSnapshot source-dialogue windows
→ second hard-mute pass with safety padding
→ cache by source/profile fingerprint
→ map the corresponding source window to each target GenerationSegment
→ FFmpeg atempo conform to target duration
→ conservative background gain
→ extra duck during target-dialogue windows
→ limiter
→ remux R10 visual with final mixed audio
```

A Shot split into several target GenerationSegments uses proportional source-Shot windows. Later target segments do not restart the background from source time zero.

Safe fallback:

```text
separator/model unavailable or enhancement failure
→ keep already-valid target-dialogue-only R10 output
→ TARGET_DIALOGUE_ONLY_FALLBACK
→ no ReviewIssue
→ Episode assembly continues
```

Runtime endpoint:

```text
GET /api/background-audio/runtime
```

R10.1 currently reuses safely separated source ambience/music/SFX. It does not introduce a speculative generated-BGM/SFX subsystem.

## Main application wiring

The formal router/model import tree includes generation, R9 QC/selection and R10/R10.1 postproduction/output code. Heavy LatentSync/audio-separator model stacks remain lazy workers outside the main backend process.

## Repository acceptance

Tests include:

```text
engine/tests/v2/test_generation_segment_v1.py
engine/tests/v2/test_h3_r8_v1.py
engine/tests/v2/test_h3_qc_r9_v1.py
engine/tests/v2/test_postproduction_r10_v1.py
engine/tests/v2/test_episode_output_r10_v1.py
engine/tests/v2/test_background_audio_r10_1_v1.py
```

Dedicated jobs:

```text
r7-generation-segments
r8-h3-generation
r9-h3-qc
r10-postproduction
frontend-v2
```

Latest verified R10.1 line:

```text
r7-generation-segments = PASS
r8-h3-generation       = PASS
r9-h3-qc                = PASS
r10-postproduction      = PASS
frontend-v2             = PASS
```

R10.1 CI specifically verifies:

```text
source-dialogue suppression window conversion + merge
real FFmpeg hard mute of residual source dialogue
safe background + target-dialogue mix duration/channel contract
extreme atempo chaining
split target segments map to the corresponding source-Shot audio window
background runtime offline -> safe fallback
R10 success remains usable during fallback
audio-separator worker import is lazy
background runtime route is registered
```

The dedicated R10 job installs FFmpeg and performs real media tests. It deliberately does not install the heavy audio-separator model environment, so model quality/runtime remains a local acceptance fact rather than a fake CI claim.

## Acceptance boundary

```text
R7/R8/R9/R10/R10.1 CODE / ISOLATED REPOSITORY ACCEPTANCE = PASS
FRONTEND BUILD ACCEPTANCE = PASS
LOCAL H3 / QWEN / LATENTSYNC / AUDIO-SEPARATOR / REAL PROJECT ACCEPTANCE = PENDING
```

Historical full-suite backend/older Breakdown failures remain separate legacy/dependency debt unless a current change directly causes them.

## Current frontier

```text
real local end-to-end project acceptance = NEXT
R11 legacy cleanup                      = LATER
```

Do not add a generated BGM/SFX subsystem before real R10.1 listening tests show that safely separated source ambience/music is insufficient.
