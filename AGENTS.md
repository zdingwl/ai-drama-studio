# AI Drama Studio — Agent Entry Rules

Current product architecture: **Localized Remake V1 + local MiniMax H3**.

Current rollback points:

```text
backup/pre-r9-20260901
backup/pre-r7-20260901
backup/pre-h3-remake-restructure-2026-09-01
```

Rollback branches are recovery-only. `main` is active development.

## 1. Highest product definition

Input an existing short drama, understand its story/directing structure, then remake a localized drama for the Project target language/region.

```text
source story / shots / actions / camera / Reference Video
→ localized characters
→ KEEP / LOCALIZE target scenes
→ target-language dialogue + target-character voice
→ real target speech duration
→ timing-adjusted RemakeTimeline
→ GenerationSegment
→ H3 Context Compiler
→ local MiniMax H3 GenerationAttempt
→ H3 structural + semantic QC
→ automatic retry
→ GenerationSelection / Selected Output
→ lip sync / assembly / export
```

Hard product rules:

```text
characters must be replaced
scene policy = AUTO | KEEP | LOCALIZE
source Reference Video = directing/performance reference, not source-person identity truth
target speech must not be unnaturally forced into source timing
Shot != GenerationSegment
GenerationAttempt != usable output
only Selected Output may flow into downstream final-video work
source ASR/OCR/Shot facts remain immutable downstream
```

**UX rule:** automatic work is background work, not a page. Only uncertainty/conflict/high-risk/repeated failure enters Review Center.

## 2. Formal user surface

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

Do not create top-level pages for GenerationSegment, H3 Context, target references, retries, QC or internal evidence.

## 3. Automatic preparation workflow

```text
AUTO_REMAKE_PREP_V1

Project/Episodes
→ preprocess
→ Shot / Reference Clip
→ ASR / OCR / Qwen3-VL Breakdown / Fusion
→ Character V10.1 / Scene / Prop
→ Final Asset
→ SourceDramaSnapshot
→ TargetCharacter / SceneLocalizationMapping
→ TargetDialogue
→ READY-line local Qwen3-TTS
→ RemakeTimeline
→ GenerationSegment
```

H3 generation/QC is a separate heavy background task so preparation can finish while H3 runtime is offline:

```text
POST /api/projects/{project_id}/tasks/h3-generate-ready
```

That task now means:

```text
prepare target references
→ generate H3 attempt
→ structural QC
→ Qwen3-VL semantic QC
→ PASS -> Selected Output
→ RETRY -> new seed + QC correction prompt
→ repeated/ambiguous failure -> Review Center
```

## 4. Authority boundaries

### Source truth

`SourceDramaSnapshot` is the only downstream source-fact interface.

### Target/remake truth

Persistent target/remake authority includes:

```text
TargetCharacter
SceneLocalizationMapping
TargetDialogue
TargetVoiceProfile
RemakeTimeline
GenerationSegment
GenerationAttempt
GenerationQualityCheck
GenerationSelection
```

`ReviewIssue` is attention state, not domain truth.

### H3 provider boundary

```text
business code
→ VideoGenerationProvider
→ MiniMaxH3Provider
→ H3RuntimeManager
→ local SGLang
```

Never call SGLang directly from remake business services.

## 5. H3 execution rules

R8 H3 execution is implemented.

Ref2VA:

```text
source Reference Clip -> visual-only derivative (`-an`)
target TTS -> separate aligned 32 kHz stereo audio condition
target character identity -> current target reference image(s)
LOCALIZE scene -> current target scene reference image when available
```

Never send source-language soundtrack as Ref2VA reference audio.

H3 sizing:

```text
4..15 seconds
<4-second target -> H3 render >=4 -> exact FFmpeg post-trim
>15-second target shot -> multiple GenerationSegments
```

## 6. R9 H3 QC / retry / selection rules

R9 is implemented on `main`.

A technically successful H3 download is **not** final truth.

```text
GenerationAttempt(SUCCEEDED)
→ ffprobe structure + duration
→ full ffmpeg video decode
→ Qwen3-VL semantic QC
→ PASS
→ GenerationSelection
```

Semantic QC compares generated samples with:

```text
TargetCharacter references
TargetScene reference/description
source Reference Video for action/blocking/camera only
previous Selected Output for FL2VA continuity
```

It checks at minimum:

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
Qwen3-VL unavailable -> WAITING_MODEL, not human content issue
QC retry -> change seed + append concrete QC correction prompt
automatic attempts default max = 3 (`AI_DRAMA_H3_QC_MAX_ATTEMPTS`, clamp 1..5)
repeated/ambiguous content failure -> H3_QC ReviewIssue
H3_QC cannot be generic ignored/resolved
human may select a structurally valid successful version
hard decode/duration failure cannot be manually bypassed
FL2VA retry continuity must use previous Selected Output, never merely latest SUCCEEDED attempt
```

## 7. Current ReviewIssue families

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
```

Future product-level producer:

```text
LIP_SYNC_QC
```

Do not create human ReviewIssues for infrastructure-only states such as H3/TTS/Qwen service offline.

## 8. Existing internals to preserve

```text
FFmpeg / FFprobe
Source PTS
ShotRevision + manual Shot edits
Reference Clips
Faster-Whisper
RapidOCR
Qwen3-VL Breakdown
Scene Timeline
Character V10.1
Final Character/Scene/Prop + bindings
AssetRevision
SourceDramaSnapshot
BackgroundTask / progress
Target localization / dialogue / TTS
RemakeTimeline
GenerationSegment
GenerationAttempt
GenerationQualityCheck
GenerationSelection
```

Do not weaken accepted Character identity gates merely to reduce ReviewIssues.

## 9. Development frontier

```text
R2 SourceDramaSnapshot                        = IMPLEMENTED
R4 TargetCharacter + SceneLocalizationMapping = IMPLEMENTED
R5 TargetDialogue + local Qwen3-TTS           = IMPLEMENTED
R6 Dialogue Timing + RemakeTimeline            = IMPLEMENTED
R7 GenerationSegment + H3 Runtime/Provider     = IMPLEMENTED
R8 H3 Context + GenerationAttempt              = IMPLEMENTED / ISOLATED CI PASS / LOCAL GPU PENDING
R9 H3 QC / automatic retry / selected output  = IMPLEMENTED / ISOLATED CI PASS / LOCAL REAL-PROJECT PENDING
R10 Lip Sync + subtitle/audio/assembly/export  = NEXT
R11 legacy cleanup
```

Do not return to old Stage 05/R6/R8 planning unless debugging a regression.

## 10. Acceptance discipline

Repository CI acceptance and local model acceptance are different facts.

Current isolated jobs:

```text
r7-generation-segments
r8-h3-generation
r9-h3-qc
```

Do not claim local H3/Qwen QC PASS until a real Project is generated and inspected on the user's actual GPU/runtime machine.

Frontend build acceptance uses the real repository lockfile and current Node version; do not dismiss a frontend failure as unrelated without reading its concrete CI cause.

## 11. Recovery order

```text
1. AGENTS.md
2. SKILL.md
3. docs/PRODUCT_REMAKE_ARCHITECTURE_V1.md
4. docs/PROJECT_STATE.md
5. docs/CURRENT_IMPLEMENTATION_MANIFEST.md
6. current R2/R4/R5/R6/R7/R8/R9 code/tests
7. old P/G docs only for compatibility maintenance
```

## 12. Git discipline

```text
main = active development
backup branches = rollback-only
minimal changes on current architecture
code/docs -> main unless user explicitly requests another branch
```
