# AI Drama Studio — Project State

> Last synchronized: 2026-09-01 +08:00  
> Repository: `zdingwl/ai-drama-studio`  
> Branch: `main`  
> Product architecture: **Localized Remake V1**  
> Final video target: **local MiniMax H3**  
> Target speech runtime V1: **local Qwen3-TTS**  
> Formal Character runtime: Character V10.1

## 1. Product truth

```text
source short drama
→ automatic source understanding
→ SourceDramaSnapshot
→ TargetCharacter + SceneLocalizationMapping
→ TargetDialogue + target-character voice + real TTS duration
→ Dialogue Timing / RemakeTimeline
→ local MiniMax H3
→ lip sync / QC / episode assembly
→ localized short drama
```

Rules:

```text
characters = always localized/replaced
scene = AUTO | KEEP | LOCALIZE
dialogue = target language
voice = new target-character voice
lip = final target audio
target timeline may differ from source timeline
```

## 2. Rollback point

```text
branch = backup/pre-h3-remake-restructure-2026-09-01
commit = 37944c693a08c6ff292b08e1f73b1249812cabae
```

Rollback branch remains untouched.

## 3. Formal user workflow

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

Automatic internals do not become product pages.

## 4. One-click automatic task

```text
AUTO_REMAKE_PREP_V1
POST /api/projects/{project_id}/tasks/auto-remake-prepare
```

Current chain:

```text
Preprocess when needed
→ Shot detection / Reference Clips
→ Breakdown ASR + OCR + Qwen3-VL + Fusion
→ Character V10.1 / Scene / Prop
→ Final Asset application
→ source ReviewIssue sync
→ SourceDramaSnapshot
→ Speaker ReviewIssue sync
→ TargetCharacter + SceneLocalizationMapping
→ target localization ReviewIssues
→ TargetDialogue translation/localization
→ READY-line Qwen3-TTS materialization when local worker is available
```

A remaining review item does not block unrelated READY dialogue audio.

## 5. R2 SourceDramaSnapshot

```text
IMPLEMENTED ON MAIN
LOCAL TEST / REAL PROJECT ACCEPTANCE PENDING
```

APIs:

```text
GET /api/episodes/{episode_id}/source-drama-snapshot
GET /api/projects/{project_id}/source-drama-snapshot
```

It is deterministic source-only current read truth with `source_fingerprint`.

Spec: `docs/SOURCE_DRAMA_SNAPSHOT_V1.md`.

## 6. R4 Target localization

```text
IMPLEMENTED ON MAIN
LOCAL TEST / REAL PROJECT ACCEPTANCE PENDING
```

Persistent data:

```text
v2_target_characters
v2_scene_localization_mappings
```

Same Final Scene across episodes shares one canonical target mapping.

```text
Final Scene SCENE_X
→ ASSET:SCENE_X
→ one KEEP / LOCALIZE plan
```

TargetCharacter and source Character are separate truth domains.

Spec: `docs/TARGET_LOCALIZATION_V1.md`.

## 7. R5 TargetDialogue + TTS

```text
IMPLEMENTED ON MAIN
LOCAL TEST / REAL PROJECT + LOCAL MODEL ACCEPTANCE PENDING
```

Persistent target-only data:

```text
v2_target_voice_profiles
v2_target_dialogues
```

Source ASR text is never overwritten.

### TargetDialogue

```text
source dialogue
+ TargetCharacter
+ scene/Shot story context
+ target language / region
        ↓
translated_text
localized_text
final_text
```

Only unsafe target text produces `LOCALIZATION` ReviewIssue.

User correction writes the real TargetDialogue row and invalidates old audio; `LOCALIZATION` cannot be closed from the generic ReviewIssue buttons.

### TargetVoiceProfile

Default V1 runtime:

```text
QWEN3_TTS_VOICE_DESIGN_CLONE_V1
```

Per TargetCharacter:

```text
VoiceDesign
→ stable reference WAV
→ Base VoiceClone reusable prompt
→ same target voice for every line
```

The source actor voice is not cloned as the default remake identity.

### Real speech duration

READY target WAV stores:

```text
audio_path
speech_duration_us
voice_fingerprint
audio_input_signature
```

`R6` must use this real `speech_duration_us`, not an estimated character count.

### Runtime isolation

Worker:

```text
scripts/qwen3_tts_worker_v1.py
```

Main-process client:

```text
engine/app/qwen3_tts_runtime_v1.py
```

Qwen3-TTS runs in a separate local Python environment to avoid dependency conflicts with the main analysis/H3 stack.

If the worker is not ready, target text remains saved and audio is marked `NOT_CONFIGURED`; this is infrastructure state, not a human content issue.

Spec: `docs/TARGET_DIALOGUE_TTS_V1.md`.

## 8. Current ReviewIssue producers

```text
SHOT_BOUNDARY
CHARACTER_IDENTITY
ASSET_BINDING
SPEAKER
TARGET_CHARACTER
SCENE_LOCALIZATION
LOCALIZATION
```

Domain-edited issues:

```text
TARGET_CHARACTER
SCENE_LOCALIZATION
LOCALIZATION
```

These must be resolved by editing their authoritative domain rows in Review Center.

## 9. Freshness rules

```text
SourceDramaSnapshot fingerprint change
→ downstream target rows become stale

source Character local signature change
→ target character may require review

source Scene canonical signature / Project scene policy change
→ target scene mapping becomes stale

TargetCharacter change
→ AI TargetDialogue regenerates
→ manual TargetDialogue reopens for review
→ old target voice reference invalidates
→ old dialogue WAV invalidates
```

GET/audio R5 APIs fail closed when target-character dependencies are stale.

## 10. Preserved source invariants

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
same-Shot observations = hard cannot-link
ASR source dialogue = immutable
OCR source text = immutable
Source Character != TargetCharacter
Source Scene != target Scene decision
SourceDramaSnapshot contains no target truth
ReviewIssue is attention state, not domain truth
```

Character V10.1 remains fail-closed.

## 11. Existing source internals retained

```text
FFmpeg / FFprobe
Source PTS
ShotRevision + manual Shot edits
TransVLM shot runtime/cache
Reference Clips
Faster-Whisper
RapidOCR
Qwen3-VL Breakdown
Window Context / Exact Shot
Scene Timeline
Character V10.1
Final Character/Scene/Prop + Shot bindings
AssetRevision
P5/P6 compatibility while required
BackgroundTask / progress
```

## 12. Next frontier

R2, R4 and R5 are implemented on `main`.

Next order:

```text
R6 Dialogue Timing Engine + RemakeTimeline
R7 local MiniMax H3 RuntimeManager
R8 H3 ContextCompiler + GenerationSegment
R9 H3 QC / retry
R10 Lip Sync + subtitle/audio/episode assembly/export
R11 legacy cleanup
```

Critical rule:

```text
Shot != GenerationSegment
```

## 13. Acceptance boundary

Repository implementation is not local acceptance.

R5 minimum checks:

```text
python -m pytest engine/tests/v2/test_target_dialogue_v1.py -q
python -m pytest engine/tests/v2/test_target_dialogue_routes_v1.py -q
python -m pytest engine/tests/v2/test_qwen3_tts_runtime_v1.py -q

cd frontend
npm run typecheck
npm run build
```

Then run a real Project with local Qwen + Qwen3-TTS worker and verify real target WAV duration.

R2/R4/R5 remain **LOCAL ACCEPTANCE PENDING** until those checks are run in the user's Windows/CUDA/model environment.

## 14. Git workflow

```text
main = active development
backup/pre-h3-remake-restructure-2026-09-01 = rollback-only
all commits = [skip ci]
hosted GitHub Actions = not acceptance evidence
```
