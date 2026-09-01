# AI Drama Studio — Agent Entry Rules

Current product architecture: **Localized Remake V1 + local MiniMax H3**.

Rollback snapshot:

```text
branch: backup/pre-h3-remake-restructure-2026-09-01
commit: 37944c693a08c6ff292b08e1f73b1249812cabae
```

## 1. Highest product definition

Input an existing short drama, understand its story/directing structure, then remake a localized drama for the Project target language/region.

```text
source story / shots / actions / camera / Reference Video
→ localized characters
→ KEEP / LOCALIZE target scenes
→ target-language dialogue + target-character voice
→ real target speech duration
→ timing-adjusted remake timeline
→ local MiniMax H3
→ lip sync / QC / final episode
```

Characters must be replaced. Scene policy is AUTO / KEEP / LOCALIZE. Target speech must not be forced into source timing with unnatural speed/slow-motion.

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

Old Stage/P/G screens are compatibility/advanced only.

## 3. Current automatic workflow

```text
AUTO_REMAKE_PREP_V1

Project/Episodes
→ preprocess
→ Shot / Reference Clip
→ ASR / OCR / Qwen3-VL Breakdown / Fusion
→ Character V10.1 / Scene / Prop
→ Final Asset
→ source ReviewIssues
→ SourceDramaSnapshot
→ Speaker ReviewIssues
→ TargetCharacter / SceneLocalizationMapping
→ target asset ReviewIssues
→ TargetDialogue translation/localization
→ READY-line local Qwen3-TTS when available
```

Current ReviewIssue producers:

```text
SHOT_BOUNDARY
CHARACTER_IDENTITY
ASSET_BINDING
SPEAKER
TARGET_CHARACTER
SCENE_LOCALIZATION
LOCALIZATION
```

Future producers:

```text
DIALOGUE_TIMING
H3_QC
LIP_SYNC_QC
```

## 4. SourceDramaSnapshot boundary

R2 is implemented.

All downstream remake modules consume SourceDramaSnapshot, not direct G2/P5/P6/P7 product names.

```text
GET /api/episodes/{episode_id}/source-drama-snapshot
GET /api/projects/{project_id}/source-drama-snapshot
```

It is deterministic source-only current read truth with `source_fingerprint`, not another source DB.

Spec: `docs/SOURCE_DRAMA_SNAPSHOT_V1.md`.

## 5. Target localization boundary

R4 is implemented.

Persistent target-side models:

```text
TargetCharacter
SceneLocalizationMapping
```

Source and target assets are strictly separate.

Same Final Scene across episodes shares one canonical target scene plan:

```text
Final Scene SCENE_X
→ ASSET:SCENE_X
→ one KEEP / LOCALIZE mapping
```

Project policy:

```text
KEEP     -> automatic KEEP
LOCALIZE -> target description required
AUTO     -> local Qwen KEEP/LOCALIZE; low confidence -> REVIEW
```

Spec: `docs/TARGET_LOCALIZATION_V1.md`.

## 6. TargetDialogue / TTS boundary

R5 is implemented.

Persistent target-only models:

```text
TargetDialogue
TargetVoiceProfile
```

Source ASR text remains immutable.

```text
SourceDramaSnapshot dialogue
+ READY TargetCharacter
+ story/Shot context
+ target locale
→ translated_text
→ localized_text
→ final_text
```

Only text uncertainty with a known target speaker creates `LOCALIZATION` ReviewIssue.

Target voice V1:

```text
QWEN3_TTS_VOICE_DESIGN_CLONE_V1
TargetCharacter
→ VoiceDesign reference WAV
→ Base VoiceClone reusable prompt
→ consistent voice across all lines
```

Worker:

```text
scripts/qwen3_tts_worker_v1.py
```

Main client:

```text
engine/app/qwen3_tts_runtime_v1.py
```

Actual WAV duration is stored as `speech_duration_us`; R6 must use the real value.

TTS worker absence/unsupported language is runtime capability state, not a human content issue.

One review line must not block TTS for unrelated READY lines.

Spec: `docs/TARGET_DIALOGUE_TTS_V1.md`.

## 7. Review Center rules

`ReviewIssue` is attention state, not domain truth.

These current issue types require actual domain editing and must not be resolved by generic buttons:

```text
TARGET_CHARACTER
SCENE_LOCALIZATION
LOCALIZATION
```

Corrections write to:

```text
TargetCharacter
SceneLocalizationMapping
TargetDialogue
```

## 8. Freshness rules

Downstream target data fails closed when stale.

```text
SourceDramaSnapshot fingerprint change
source Character signature change
canonical source Scene signature change
Project scene policy / target locale change
TargetCharacter definition change
```

TargetCharacter change:

```text
AI TargetDialogue -> regenerate
manual TargetDialogue -> reopen LOCALIZATION review
old target voice -> invalidate
old dialogue WAV -> invalidate
```

## 9. Existing internals to preserve

```text
FFmpeg / FFprobe
Source PTS
ShotRevision + manual Shot edits
TransVLM shot runtime/cache
Reference Clip
Faster-Whisper
RapidOCR
Qwen3-VL Breakdown
Window / Exact Shot
Scene Timeline
Character V10.1
Final Character/Scene/Prop + Shot bindings
AssetRevision
P5/P6 compatibility while required by SourceDramaSnapshot
BackgroundTask / progress
```

Do not weaken accepted Character identity gates to reduce ReviewIssues.

## 10. Semantic invariants

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
Source Character != TargetCharacter
Source Scene != target Scene decision
Source Dialogue != TargetDialogue
same-Shot observations = hard cannot-link
ASR/OCR source text = immutable
SourceDramaSnapshot contains no target truth
ReviewIssue is not domain truth
```

## 11. Development frontier

Do not resume old Stage 05 planning.

```text
R2 SourceDramaSnapshot                        = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
R4 TargetCharacter + SceneLocalizationMapping = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
R5 TargetDialogue + local Qwen3-TTS           = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
R6 Dialogue Timing Engine + RemakeTimeline     = NEXT
R7 local MiniMax H3 RuntimeManager
R8 H3 ContextCompiler + GenerationSegment
R9 H3 QC / retry
R10 Lip Sync + subtitle/audio/assembly/export
R11 legacy cleanup
```

`Shot != GenerationSegment` remains mandatory.

## 12. Recovery order

```text
1. AGENTS.md
2. SKILL.md
3. docs/PRODUCT_REMAKE_ARCHITECTURE_V1.md
4. docs/PROJECT_STATE.md
5. docs/CURRENT_IMPLEMENTATION_MANIFEST.md
6. docs/SOURCE_DRAMA_SNAPSHOT_V1.md
7. docs/TARGET_LOCALIZATION_V1.md
8. docs/TARGET_DIALOGUE_TTS_V1.md
9. relevant current code/tests
10. old P/G docs only for internal maintenance
```

## 13. Git discipline

```text
main = active development
backup branch = rollback-only
code/docs -> main directly unless user explicitly asks otherwise
all commits -> [skip ci]
hosted GitHub Actions != acceptance evidence
```
