---
name: ai-drama-studio-localized-remake-v1
version: 5.0.0
description: Localized short-drama remake workflow through local MiniMax H3, QC, lip sync, safe background audio and Episode export.
---

# AI Drama Studio — Localized Remake V1

## 0. Read current truth

```text
AGENTS.md
→ SKILL.md
→ docs/PRODUCT_REMAKE_ARCHITECTURE_V1.md
→ docs/PROJECT_STATE.md
→ docs/CURRENT_IMPLEMENTATION_MANIFEST.md
→ relevant current code/tests
```

Rollback branches are recovery-only. `main` is active development.

## 1. Goal

```text
source short drama
→ understand source story / shots / actions / camera / dialogue
→ SourceDramaSnapshot
→ localized characters + target scene decisions
→ localized target dialogue + stable target-character voice
→ real target speech duration
→ RemakeTimeline
→ GenerationSegment
→ local MiniMax H3
→ structural + semantic QC / automatic retry
→ GenerationSelection
→ target-speaker lip sync
→ safe non-dialogue background audio
→ subtitles / Episode assembly / export
```

Source drama is a directing/reference template. Characters must change. Target dialogue must not be unnaturally forced into source duration.

## 2. Product and UX rules

```text
characters = always replaced/localized
scene policy = AUTO | KEEP | LOCALIZE
source Reference Video = directing/action/camera reference, not source-person identity truth
Shot != GenerationSegment
GenerationAttempt != usable output
only GenerationSelection may enter final-video work
raw source audio must never be mixed into target output
SourceDramaSnapshot is the only downstream source-fact boundary
```

Automatic work is background work, not a page.

Formal user surface:

```text
Project
Review Center
Output
```

Formal UI:

```text
ProjectListV4
ProjectStudioV4
```

Do not add top-level pages for internal generation/QC/lip-sync/audio-separation stages.

## 3. Automatic preparation

```text
AUTO_REMAKE_PREP_V1

preprocess
→ Shot / Reference Clips
→ ASR / OCR / Qwen3-VL Breakdown / Fusion
→ Character V10.1 + Scene / Prop extraction
→ Final Asset
→ source ReviewIssues
→ SourceDramaSnapshot
→ TargetCharacter / SceneLocalizationMapping
→ TargetDialogue localization
→ READY-line local Qwen3-TTS
→ RemakeTimeline
→ GenerationSegment
```

H3 and final postproduction remain separate heavy tasks so preparation can finish while local model runtimes are offline.

## 4. Current authority chain

### Source truth

```text
SourceDramaSnapshot
```

Source ASR/OCR/Shot timing and source dialogue are immutable downstream.

### Target/remake truth

```text
TargetCharacter
SceneLocalizationMapping
TargetVoiceProfile
TargetDialogue
RemakeTimeline
GenerationSegment
GenerationAttempt
GenerationQualityCheck
GenerationSelection
PostProductionSegment
EpisodeOutput
```

`ReviewIssue` is attention state only, not a second truth database.

## 5. R5 TargetDialogue + local Qwen3-TTS

Runtime profile:

```text
QWEN3_TTS_VOICE_DESIGN_CLONE_V1
```

```text
TargetCharacter
→ VoiceDesign reference
→ reusable character voice
→ TargetDialogue final WAV
→ real speech_duration_us
```

`TargetDialogue.final_text` is the target dialogue authority. Source text remains immutable.

## 6. R6 RemakeTimeline

Implemented.

Consumes real target TTS duration and plans target time without rewriting source Shot/ASR truth.

Strategies include:

```text
KEEP
TRIM
CARRY_OVER_REACTION
EXTEND
HUMAN_REVIEW
WAITING_AUDIO
```

Do not solve target-language timing by globally slowing video or unnaturally accelerating speech.

## 7. R7 GenerationSegment + H3 provider

Implemented.

Mandatory rule:

```text
Shot != GenerationSegment
```

H3 sizing:

```text
4..15 seconds
<4-second target -> render >=4 then exact post-trim
>15-second target -> split into multiple GenerationSegments
```

Provider boundary:

```text
business
→ VideoGenerationProvider
→ MiniMaxH3Provider
→ H3RuntimeManager
→ local SGLang
```

## 8. R8 H3 Context + GenerationAttempt

Implemented.

Ref2VA receives:

```text
silent source Reference Video
+ current TargetCharacter references
+ optional LOCALIZE Scene reference
+ exact target-dialogue audio condition
+ compact action/camera constraints
```

Never pass source-language soundtrack as H3 reference audio.

`GenerationAttempt(SUCCEEDED)` means only that a technical output file exists.

## 9. R9 H3 QC / retry / selection

Implemented with isolated CI acceptance.

```text
GenerationAttempt
→ ffprobe + full ffmpeg decode + exact-duration gate
→ Qwen3-VL semantic QC
→ PASS -> GenerationSelection
→ RETRY -> new seed + QC correction prompt
→ ambiguous/repeated failure -> H3_QC
```

Semantic QC checks target identity, source-actor leakage, scene consistency, action/camera consistency, continuity and visual integrity.

`H3_QC` cannot be generically ignored/resolved. Human action must select a structurally valid version or retry.

## 10. R10 Lip Sync / subtitle / EpisodeOutput

Implemented with isolated CI acceptance.

```text
GenerationSelection
→ final target dialogue audio
→ target-speaker lip sync
→ PostProductionSegment
→ target-timeline SRT
→ normalized media
→ EpisodeOutput
→ MP4 + SRT
```

Lip-sync rules:

```text
off-screen dialogue -> keep target audio, skip mouth edit
single visible target speaker -> full-segment LatentSync
multiple visible faces -> resolve target speaker identity -> ROI LatentSync
identity ambiguity -> LIP_SYNC_QC
runtime/model unavailable -> waiting state, not human issue
```

`LIP_SYNC_QC` cannot be generically ignored/resolved.

## 11. R10.1 safe background audio

Implemented with isolated CI acceptance.

Hard invariant:

```text
raw source audio is never mixed into target output
```

Provider boundary:

```text
PostProduction
→ BackgroundAudioProvider
→ AUDIO_SEPARATOR_LOCAL_V1
→ dedicated audio-separator worker
```

Safe flow:

```text
source Shot audio
→ Instrumental/background separation
→ SourceDramaSnapshot source-dialogue windows
→ second hard-mute pass with padding
→ cache by source/profile fingerprint
→ map corresponding source window to target GenerationSegment
→ atempo conform to target duration
→ conservative gain + target-dialogue duck + limiter
→ final mixed PostProduction output
```

If the separator runtime/model fails:

```text
TARGET_DIALOGUE_ONLY_FALLBACK
```

The existing target-dialogue-only R10 video remains valid; Episode assembly continues and no ReviewIssue is created.

## 12. Review Center

Current issue families:

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

Infrastructure-only failures such as H3/TTS/Qwen/LatentSync/audio-separator offline must not become human ReviewIssues.

## 13. Current stage state

```text
R2 SourceDramaSnapshot                        = IMPLEMENTED
R4 TargetCharacter + SceneLocalizationMapping = IMPLEMENTED
R5 TargetDialogue + local Qwen3-TTS           = IMPLEMENTED
R6 Dialogue Timing + RemakeTimeline            = IMPLEMENTED
R7 GenerationSegment + H3 Runtime/Provider     = IMPLEMENTED
R8 H3 Context + GenerationAttempt              = IMPLEMENTED / ISOLATED CI PASS
R9 H3 QC / automatic retry / selection        = IMPLEMENTED / ISOLATED CI PASS
R10 Lip Sync + subtitle / assembly / export    = IMPLEMENTED / ISOLATED CI PASS
R10.1 safe ambience/BGM/SFX reuse              = IMPLEMENTED / ISOLATED CI PASS
R11 legacy cleanup                            = LATER
```

The next meaningful milestone is real local end-to-end acceptance on the actual model/GPU machine.

## 14. Acceptance discipline

Repository acceptance and real local model acceptance are separate facts.

Dedicated repository jobs:

```text
r7-generation-segments
r8-h3-generation
r9-h3-qc
r10-postproduction
frontend-v2
```

Latest verified R10.1 line passes all five jobs above. Historical `backend-v2` / old Breakdown failures remain legacy/dependency debt unless a current change directly causes them.

Do **not** claim local H3/Qwen3-TTS/Qwen3-VL/LatentSync/audio-separator PASS until a real Project has run through the actual local runtimes and its final video/audio has been inspected.

## 15. Git discipline

```text
main = active development
backup branches = rollback-only
minimal changes on current architecture
code/docs -> main unless the user explicitly requests another branch
```
