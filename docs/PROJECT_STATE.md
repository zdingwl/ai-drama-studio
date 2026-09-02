# AI Drama Studio — Project State

> Last synchronized: 2026-09-02 +08:00  
> Repository: `zdingwl/ai-drama-studio`  
> Branch: `main`  
> Product architecture: **Localized Remake V1**  
> Final video target: **local MiniMax H3**  
> Target speech runtime: **local Qwen3-TTS**  
> Lip-sync runtime: **local LatentSync 1.6**  
> Formal Character runtime: **Character V10.1**

## 1. Product truth

```text
source short drama
→ source understanding / Reference Clips
→ SourceDramaSnapshot
→ TargetCharacter + SceneLocalizationMapping
→ TargetDialogue + target-character voice + real TTS duration
→ RemakeTimeline
→ GenerationSegment
→ H3 Context Compiler
→ target reference assets
→ GenerationAttempt / local MiniMax H3
→ structural + semantic H3 QC
→ automatic retry
→ GenerationSelection / Selected Output
→ target-speaker lip sync
→ final target dialogue audio + subtitles
→ EpisodeOutput assembly / export
→ localized short drama
```

Hard rules:

```text
characters = always replaced/localized
scene = AUTO | KEEP | LOCALIZE
dialogue = target language
voice = target-character voice
target timeline may differ from source timeline
Shot != GenerationSegment
GenerationAttempt != selected usable output
only GenerationSelection may enter R10
multi-face lip sync must identify the target speaker first
source ASR/OCR/Shot truth is immutable downstream
```

## 2. Rollback points

```text
backup/pre-r9-20260901
backup/pre-r7-20260901
backup/pre-h3-remake-restructure-2026-09-01
```

Rollback branches are read-only recovery points. `main` is active development.

## 3. Formal user surface

```text
Project
Review Center
Output
```

Formal UI:

```text
frontend/src/views/ProjectListV4.vue
frontend/src/views/ProjectStudioV4.vue
```

Automatic work stays in background tasks. Only uncertainty/conflict/high-risk decisions/repeated failure belong in Review Center.

`Output` now prioritizes final Episode video. H3/PostProduction segment details are advanced diagnostics rather than the normal user workflow.

## 4. Automatic preparation and heavy-task boundaries

Preparation:

```text
POST /api/projects/{project_id}/tasks/auto-remake-prepare

Preprocess
→ Shot detection / Reference Clips
→ ASR + OCR + Qwen3-VL Breakdown / Fusion
→ Character V10.1 + Scene + Prop
→ Final Asset / source ReviewIssues
→ SourceDramaSnapshot
→ TargetCharacter + SceneLocalizationMapping
→ TargetDialogue localization
→ READY-line Qwen3-TTS
→ RemakeTimeline
→ GenerationSegment compile
```

H3 generation/QC:

```text
POST /api/projects/{project_id}/tasks/h3-generate-ready

prepare target references
→ GenerationAttempt
→ structural QC
→ Qwen3-VL semantic QC
→ automatic retry
→ GenerationSelection / Selected Output
```

R10 postproduction:

```text
POST /api/projects/{project_id}/tasks/postproduction

Selected Output
→ final target-dialogue audio
→ LatentSync
→ PostProductionSegment
→ SRT
→ media normalization
→ EpisodeOutput assembly
→ MP4 + SRT
```

## 5. Current stage table

| Stage | State | Persistent authority |
|---|---|---|
| R2 SourceDramaSnapshot | Implemented | source read model / fingerprint |
| R4 Target localization | Implemented | `v2_target_characters`, `v2_scene_localization_mappings` |
| R5 TargetDialogue + TTS | Implemented | `v2_target_voice_profiles`, `v2_target_dialogues` |
| R6 Dialogue Timing | Implemented | `v2_remake_timelines` |
| R7 GenerationSegment | Implemented | `v2_generation_segments` |
| R7 H3 Runtime/Provider | Implemented | isolated local SGLang adapter |
| R8 H3 Context Compiler | Implemented | deterministic materialized context |
| R8 GenerationAttempt | Implemented | `v2_generation_attempts` |
| R9 H3 QC | Implemented | `v2_generation_quality_checks` |
| R9 Selected Output | Implemented | `v2_generation_selections` |
| R10 PostProductionSegment | Implemented | `v2_postproduction_segments` |
| R10 EpisodeOutput | Implemented | `v2_episode_outputs` |
| R10.1 ambience/BGM/SFX mix | Next | not yet authoritative |

Repository implementation does **not** mean the user's local GPU/model environment has passed real-project acceptance.

## 6. R6/R7 timing and segment rules

`RemakeTimeline` consumes real TargetDialogue `speech_duration_us`; source Shot boundaries and source ASR are never rewritten.

```text
KEEP
TRIM
CARRY_OVER_REACTION
EXTEND
HUMAN_REVIEW
WAITING_AUDIO
```

GenerationSegment boundary:

```text
SourceDramaSnapshot
+ TargetLocalization
+ TargetDialogue
+ RemakeTimeline
→ GenerationSegment
```

H3 constraints:

```text
render = 4..15 seconds
>15-second target shot = balanced multi-segment split
<4-second target = H3 render >=4 seconds + exact FFmpeg post-trim
Ref2VA visual reference = 2..15 seconds
```

Any authoritative upstream fingerprint change makes old segment/attempt/QC/selection/postproduction/output stale or invalid.

## 7. R8 H3 execution

Core implementation:

```text
engine/app/h3_context_contract_v1.py
engine/app/h3_context_compiler_v1.py
engine/app/h3_reference_assets_v1.py
engine/app/generation_attempt_v1.py
engine/app/h3_generation_routes_v1.py
```

Ref2VA receives current TargetCharacter references, optional LOCALIZE Scene reference, a visual-only source Reference Video and exact target-dialogue audio condition. Source-language soundtrack is not sent as H3 reference audio.

## 8. R9 H3 QC / automatic retry / selection

Persistent tables:

```text
v2_generation_quality_checks
v2_generation_selections
```

Structural hard gate:

```text
ffprobe video stream / duration / dimensions / fps
+ full ffmpeg video decode
+ exact target-duration tolerance
```

Semantic Qwen3-VL QC evaluates:

```text
visual integrity
source actor leakage
target character consistency
scene consistency
Ref2VA action/camera consistency
FL2VA continuity consistency
```

Rules:

```text
QC PASS -> auto GenerationSelection
QC RETRY -> different seed + QC correction prompt
Qwen unavailable -> WAITING_MODEL, not human issue
ambiguous/repeated failure -> H3_QC ReviewIssue
H3_QC cannot be generic ignored/resolved
```

## 9. R10 lip sync / subtitles / assembly / export

Core implementation:

```text
engine/app/postproduction_contract_v1.py
engine/app/postproduction_lipsync_v1.py
engine/app/postproduction_v1.py
engine/app/postproduction_review_v1.py
engine/app/postproduction_routes_v1.py
engine/app/speaker_face_locator_v1.py
engine/app/latentsync_provider_v1.py
engine/app/episode_output_contract_v1.py
engine/app/episode_output_v1.py
scripts/latentsync_worker_v1.py
frontend/src/components/LipSyncReviewV1.vue
frontend/src/components/FinalOutputV1.vue
```

Persistent tables:

```text
v2_postproduction_segments
v2_episode_outputs
```

R10 consumes **GenerationSelection only**.

Lip-sync policy:

```text
off-screen dialogue -> keep target audio, skip lip sync
single visible target speaker -> LatentSync full segment
multi-face visible speaker -> SFace target-speaker localization -> ROI LatentSync
locator/model unavailable -> waiting/model state
identity ambiguity -> LIP_SYNC_QC
```

`LIP_SYNC_QC` is domain-edited. Generic Ignore/Resolve is blocked; retry re-enters real target-face localization/postproduction.

Audio/timeline rules:

```text
cross-segment dialogue trims already-played audio instead of replaying sentence start
subtitles use the target RemakeTimeline
one dialogue spanning multiple GenerationSegments appears once in SRT
EpisodeOutput only uses SUCCEEDED PostProductionSegments
segment media is normalized before concat
```

Final output endpoints provide MP4 and SRT.

Current limitation: R10 has final target dialogue audio but does not yet own a dedicated ambience/BGM/SFX mix layer.

## 10. ReviewIssue families

```text
SHOT_BOUNDARY
CHARACTER_IDENTITY
ASSET_BINDING
SPEAKER
TARGET_CHARACTER
SCENE_LOCALIZATION
LOCALIZATION
DIALOGUE_TIMING
H3_QC
LIP_SYNC_QC
```

`ReviewIssue` is attention state, not authoritative business truth.

## 11. Repository acceptance

Dedicated jobs:

```text
r7-generation-segments
r8-h3-generation
r9-h3-qc
r10-postproduction
frontend-v2
```

Latest verified R10 line:

```text
r7-generation-segments = PASS
r8-h3-generation       = PASS
r9-h3-qc                = PASS
r10-postproduction      = PASS
frontend-v2             = PASS
```

R10 acceptance includes:

```text
single-speaker lip-sync planning
multi-face compile without sync model work
unique target-face ROI localization
ambiguity -> REVIEW fail-closed
cross-segment audio trimming
off-screen dialogue behavior
LIP_SYNC_QC domain-edit protection
R10 route registration
UTF-8 target-timeline SRT
subtitle deduplication
FFmpeg media normalization + concat
EpisodeOutput route/table registration
```

The general lightweight `backend-v2` and older Breakdown jobs still contain historical dependency/contract debt. R10 media tests skip explicitly when FFmpeg is absent there; the dedicated `r10-postproduction` job installs FFmpeg and performs the real media acceptance.

## 12. Local acceptance still required

Real end-to-end acceptance requires the user's actual machine:

```text
1. start FL2VA / Ref2VA H3 runtime
2. start local Qwen3-VL QC service
3. start local Qwen3-TTS runtime
4. start LatentSync 1.6 runtime
5. run a real prepared Project through H3 -> QC -> Selected Output -> R10
6. inspect target identity, scene, action/camera, duration and lip sync
7. verify multi-person dialogue targets the correct face
8. verify final Episode MP4/SRT playback and timing
9. force H3_QC and LIP_SYNC_QC ambiguous cases and verify Review Center recovery
```

Current factual state:

```text
R7/R8/R9/R10 CODE + ISOLATED REPOSITORY ACCEPTANCE = PASS
FRONTEND BUILD ACCEPTANCE = PASS
LOCAL H3 / QWEN / LATENTSYNC / REAL PROJECT ACCEPTANCE = PENDING
```

## 13. Next frontier

```text
R10.1 ambience / BGM / SFX mix layer
→ preserve or reconstruct non-dialogue sound without leaking source dialogue
→ deterministic mix policy around target dialogue
→ loudness/peak control
→ keep postproduction/episode assembly idempotent

then
→ real local GPU end-to-end acceptance
→ R11 legacy cleanup
```
