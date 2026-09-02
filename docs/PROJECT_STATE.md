# AI Drama Studio — Project State

> Last synchronized: 2026-09-02 +08:00  
> Repository: `zdingwl/ai-drama-studio`  
> Branch: `main`  
> Product architecture: **Localized Remake V1**  
> Final video target: **local MiniMax H3**  
> Target speech runtime: **local Qwen3-TTS**  
> Lip-sync runtime: **local LatentSync 1.6**  
> Background-audio runtime: **local audio-separator worker**  
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
→ final target dialogue + safe non-dialogue background audio + subtitles
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
raw source audio must never be mixed into target output
source-derived background must pass separation + source-dialogue suppression
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

`Output` prioritizes final Episode video. H3/PostProduction segment details are advanced diagnostics rather than the normal user workflow.

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

R10/R10.1 postproduction:

```text
POST /api/projects/{project_id}/tasks/postproduction

Selected Output
→ final target-dialogue audio
→ target-speaker LatentSync
→ PostProductionSegment
→ safe source-background enhancement when available
→ SRT
→ media normalization
→ EpisodeOutput assembly
→ MP4 + SRT
```

Background enhancement is best-effort quality work. If its worker/model is unavailable, the valid target-dialogue-only R10 result continues to Episode assembly.

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
| R10.1 safe ambience/BGM/SFX reuse mix | Implemented / isolated CI pass | PostProductionSegment derivative output + Shot cache |
| Local runtime stack checker | Implemented / Windows tooling CI pass | read-only acceptance tooling |
| Real-project resumable acceptance runner | Implemented / Windows tooling CI pass | public production APIs only |

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

## 10. R10.1 safe background audio

Implementation:

```text
engine/app/background_audio_provider_v1.py
engine/app/audio_separator_provider_v1.py
engine/app/background_audio_v1.py
engine/app/postproduction_audio_mix_v1.py
scripts/audio_separator_worker_v1.py
scripts/requirements_audio_separator_v1.txt
engine/tests/v2/test_background_audio_r10_1_v1.py
```

Provider boundary:

```text
PostProduction
→ BackgroundAudioProvider
→ AUDIO_SEPARATOR_LOCAL_V1
→ dedicated audio-separator worker
```

The main backend does not import the heavy separator/model stack.

Safety flow:

```text
source Episode/Shot audio
→ extract exact source Shot
→ separate Instrumental stem
→ use SourceDramaSnapshot source-dialogue windows
→ hard-mute those windows again with configurable padding
→ cache safe Shot background by source/profile fingerprint
→ map corresponding source window to each target GenerationSegment
→ atempo conform to target duration
→ conservative gain + target-dialogue duck + limiter
→ replace only the R10 output audio
```

The system never uses "raw source audio at lower volume" as a fallback.

```text
separator READY + safe stem -> SOURCE_BACKGROUND_SAFE
separator offline/failure   -> TARGET_DIALOGUE_ONLY_FALLBACK
```

Fallback remains a valid final result and does not create a human ReviewIssue.

The default worker model is configurable; the current default is `UVR-MDX-NET-Inst_HQ_5.onnx`. `audio-separator` is pinned in the dedicated worker requirements, not in the main engine requirements.

R10.1 currently **reuses** safely separated source ambience/music/SFX. It does not yet generate replacement BGM/SFX; that should only be added if real-project quality acceptance proves source separation insufficient.

## 11. ReviewIssue families

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

`ReviewIssue` is attention state, not authoritative business truth. Audio-separator/model infrastructure failures do not become ReviewIssues.

## 12. Repository acceptance

Dedicated jobs:

```text
r7-generation-segments
r8-h3-generation
r9-h3-qc
r10-postproduction
frontend-v2
Real Project Acceptance Orchestrator
```

Latest verified production/tooling lines:

```text
r7-generation-segments             = PASS
r8-h3-generation                   = PASS
r9-h3-qc                            = PASS
r10-postproduction                  = PASS
frontend-v2                         = PASS
Real Project Acceptance Orchestrator = PASS
```

The Windows acceptance-tooling job compiles and parses both the resumable real-project runner and the unified runtime-stack checker, then runs their contract tests. It does not install H3/Qwen/LatentSync/audio-separator model environments and therefore does not replace local GPU/model acceptance.

R10/R10.1 acceptance includes:

```text
single-speaker lip-sync planning
multi-face compile without sync model work
unique target-face ROI localization
ambiguity -> REVIEW fail-closed
cross-segment target-dialogue audio trimming
off-screen dialogue behavior
LIP_SYNC_QC domain-edit protection
UTF-8 target-timeline SRT
subtitle deduplication
FFmpeg media normalization + concat
EpisodeOutput route/table registration
source-dialogue suppression window conversion/merge
real FFmpeg hard mute of residual source dialogue
safe background + target-dialogue mix duration/channel contract
split target segments map to the corresponding source-Shot audio window
background runtime offline -> safe target-dialogue-only fallback
main process imports audio-separator worker lazily without model stack
background runtime route registration
```

The dedicated R10 job installs FFmpeg but deliberately does not install the heavy `audio-separator` model environment; Provider/Worker behavior is isolated and the real model runtime remains a local acceptance item.

The general lightweight `backend-v2` and older Breakdown jobs still contain historical dependency/contract debt. They do not redefine R10.1 isolated acceptance unless a new change directly causes their failure.

## 13. Local acceptance tooling

Unified read-only Runtime check:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check_local_remake_runtime_stack.ps1
```

It checks the complete desired local acceptance stack:

```text
Backend
H3 FL2VA
H3 Ref2VA
Qwen3-VL
Qwen3-TTS
LatentSync
Audio Separator
```

It never installs models, starts services or modifies project data. A Qwen3-VL `/models` response that exposes a canonical/absolute model path rather than the configured alias is diagnostic only and does not create a false blocker.

Resumable real-project acceptance:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_real_project_acceptance_v1.ps1 `
  -ProjectId PROJECT_... `
  -Run
```

The runner calls public production APIs only, resumes from current product truth, stops on genuine ReviewIssues and never auto-resolves/ignores domain truth. Machine completion is only `READY_FOR_MANUAL_ACCEPTANCE`; human watch/listen acceptance remains mandatory.

## 14. Local acceptance still required

Real end-to-end acceptance requires the user's actual machine:

```text
1. start FL2VA / Ref2VA H3 runtime
2. start local Qwen3-VL QC service
3. start local Qwen3-TTS runtime
4. start LatentSync 1.6 runtime
5. start audio-separator R10.1 worker and prepare its model
6. run check_local_remake_runtime_stack.ps1 and require every runtime READY
7. run a real Project through H3 -> QC -> Selected Output -> R10/R10.1
8. inspect target identity, scene, action/camera, duration and lip sync
9. verify multi-person dialogue targets the correct face
10. listen specifically for any residual source-language dialogue
11. compare SOURCE_BACKGROUND_SAFE vs TARGET_DIALOGUE_ONLY_FALLBACK on real episodes
12. verify final Episode MP4/SRT playback and timing
13. force H3_QC and LIP_SYNC_QC ambiguous cases and verify Review Center recovery
```

Current factual state:

```text
R7/R8/R9/R10/R10.1 CODE + ISOLATED REPOSITORY ACCEPTANCE = PASS
FRONTEND BUILD ACCEPTANCE = PASS
WINDOWS LOCAL ACCEPTANCE TOOLING = PASS
LOCAL H3 / QWEN / LATENTSYNC / AUDIO-SEPARATOR / REAL PROJECT ACCEPTANCE = PENDING
```

## 15. Next frontier

The next meaningful product milestone is **local real-project end-to-end acceptance**.

```text
real H3 generation
→ real R9 QC/retry
→ real LatentSync
→ real audio-separator background enhancement
→ listen/watch final Episode output
→ tune only evidence-backed thresholds/gain/model choices
```

After the real workflow is stable:

```text
R11 legacy cleanup
```

Do not add another speculative BGM/SFX generation subsystem before real-project R10.1 acceptance shows it is necessary.
