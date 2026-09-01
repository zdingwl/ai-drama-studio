# AI Drama Studio — Agent Entry Rules

Current product architecture: **Localized Remake V1 + local MiniMax H3**.

Current rollback points:

```text
backup/pre-r7-20260901
8abf420262255f464cb08a0aa783a36dd1c13d66

backup/pre-h3-remake-restructure-2026-09-01
37944c693a08c6ff292b08e1f73b1249812cabae
```

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
→ H3 QC / retry
→ lip sync / assembly / export
```

Hard product rules:

```text
characters must be replaced
scene policy = AUTO | KEEP | LOCALIZE
source Reference Video is directing/performance reference, not source-person identity truth
target speech must not be unnaturally forced into source timing
Shot != GenerationSegment
source ASR/OCR/Shot facts remain immutable downstream
```

**UX rule:** automatic work is background work, not a page. Only uncertainty/conflict/high-risk/repeated failure enters Review Center.

## 2. User surface

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

Do not create a top-level page for GenerationSegment, H3 Context, reference generation, retries or internal evidence.

## 3. Current automatic preparation workflow

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

H3 generation remains a separate heavy background task so preparation can finish while the local H3 runtime is offline.

## 4. Authority boundaries

### Source truth

`SourceDramaSnapshot` is the only downstream source-fact interface. Downstream remake modules must not bind directly to historical P/G stage names.

### Target truth

Persistent target authority:

```text
TargetCharacter
SceneLocalizationMapping
TargetDialogue
TargetVoiceProfile
RemakeTimeline
GenerationSegment
GenerationAttempt
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

## 5. R8 H3 execution rules

R8 is implemented on `main`.

```text
GenerationSegment
→ H3 Context Compiler
→ local materialized file:// conditions
→ VideoGenerationProvider
→ GenerationAttempt
```

Ref2VA rules:

```text
source Reference Clip is rematerialized as VIDEO-ONLY (`-an`)
target dialogue audio is a separate aligned 32 kHz stereo condition
target-character identity comes from current target reference assets
LOCALIZE scene may use a current target scene reference image
never feed source-language soundtrack to H3
```

FL2VA continuation:

```text
previous current successful segment output
→ final frame
→ frame_index=0
→ next segment
```

H3 render constraints:

```text
4..15 seconds
<4-second target = render >=4 then exact FFmpeg post-trim
>15-second target shot = multiple GenerationSegments
```

A current upstream fingerprint change makes old segments/attempts stale.

## 6. Current ReviewIssue families

```text
SHOT_BOUNDARY
CHARACTER_IDENTITY
ASSET_BINDING
SPEAKER
TARGET_CHARACTER
SCENE_LOCALIZATION
LOCALIZATION
DIALOGUE_TIMING
```

Future product-level producers:

```text
H3_QC
LIP_SYNC_QC
```

Do not create human ReviewIssues for infrastructure-only states such as H3/TTS service offline.

## 7. Existing internals to preserve

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
```

Do not weaken accepted Character identity gates merely to reduce ReviewIssues.

## 8. Development frontier

```text
R2 SourceDramaSnapshot                        = IMPLEMENTED
R4 TargetCharacter + SceneLocalizationMapping = IMPLEMENTED
R5 TargetDialogue + local Qwen3-TTS           = IMPLEMENTED
R6 Dialogue Timing + RemakeTimeline            = IMPLEMENTED
R7 GenerationSegment + H3 Runtime/Provider     = IMPLEMENTED
R8 H3 Context + GenerationAttempt              = IMPLEMENTED / ISOLATED CI PASS / LOCAL GPU PENDING
R9 H3 QC / automatic retry / selected output  = NEXT
R10 Lip Sync + subtitle/audio/assembly/export
R11 legacy cleanup
```

Do not return to old Stage 05/R6 planning unless debugging a regression.

## 9. Acceptance discipline

Repository CI acceptance and local model acceptance are different facts.

Current isolated jobs:

```text
r7-generation-segments
r8-h3-generation
```

Do not claim local H3 PASS until a real Project is generated on the user's actual H3 GPU runtime and outputs are inspected.

Known unrelated CI debt exists in historical tests and frontend dependency lock drift; do not solve it opportunistically during H3 feature work unless it blocks the current stage.

## 10. Recovery order

```text
1. AGENTS.md
2. SKILL.md
3. docs/PRODUCT_REMAKE_ARCHITECTURE_V1.md
4. docs/PROJECT_STATE.md
5. docs/CURRENT_IMPLEMENTATION_MANIFEST.md
6. current R2/R4/R5/R6/R7/R8 specs/code/tests
7. old P/G docs only for compatibility maintenance
```

## 11. Git discipline

```text
main = active development
backup branches = rollback-only
minimal changes on current architecture
code/docs -> main unless user explicitly requests another branch
```
