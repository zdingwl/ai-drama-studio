---
name: ai-drama-studio-localized-remake-v1
version: 4.3.0
description: Localized short-drama remake workflow; SourceDramaSnapshot + target assets + TargetDialogue/Qwen3-TTS + Review Center + local MiniMax H3.
---

# AI Drama Studio — Localized Remake V1

## 0. Read current truth

```text
AGENTS.md
→ SKILL.md
→ docs/PRODUCT_REMAKE_ARCHITECTURE_V1.md
→ docs/PROJECT_STATE.md
→ docs/CURRENT_IMPLEMENTATION_MANIFEST.md
→ docs/SOURCE_DRAMA_SNAPSHOT_V1.md
→ docs/TARGET_LOCALIZATION_V1.md
→ docs/TARGET_DIALOGUE_TTS_V1.md
→ relevant current code/tests
```

Rollback:

```text
backup/pre-h3-remake-restructure-2026-09-01
37944c693a08c6ff292b08e1f73b1249812cabae
```

## 1. Goal

```text
source short drama
→ understand source story/shots/actions/camera/dialogue
→ replace characters for target region
→ KEEP / LOCALIZE scenes
→ translate/localize dialogue
→ target-character TTS + real speech duration
→ timing-adjusted remake timeline
→ local MiniMax H3
→ lip sync / QC / assembly/export
```

Source drama is a directing/reference template. Characters must change. Target dialogue must not be unnaturally forced into source duration.

## 2. UX rule

> Automatic work is background work, not a page.

```text
Project
→ Review Center only when needed
→ Output
```

Formal UI: `ProjectListV4` + `ProjectStudioV4`.

## 3. Current one-click pipeline

```text
AUTO_REMAKE_PREP_V1

preprocess
→ Shot / Reference Clips
→ ASR / OCR / Qwen3-VL Breakdown / Fusion
→ Character V10.1 + Scene/Prop extraction
→ Final Asset
→ source ReviewIssues
→ SourceDramaSnapshot
→ Speaker ReviewIssues
→ TargetCharacter / SceneLocalizationMapping
→ target ReviewIssues
→ TargetDialogue translation/localization
→ READY-line local Qwen3-TTS when available
```

Current ReviewIssue types:

```text
SHOT_BOUNDARY
CHARACTER_IDENTITY
ASSET_BINDING
SPEAKER
TARGET_CHARACTER
SCENE_LOCALIZATION
LOCALIZATION
```

## 4. R2 SourceDramaSnapshot

Implemented on main; local acceptance pending.

```text
GET /api/episodes/{episode_id}/source-drama-snapshot
GET /api/projects/{project_id}/source-drama-snapshot
```

Source-only deterministic current read truth with stable source keys and `source_fingerprint`.

## 5. R4 Target localization

Implemented on main; local acceptance pending.

### TargetCharacter

```text
Source Character
→ one TargetCharacter per Project
```

Stores target-region name, stable appearance profile, generation prompt and future reference assets.

### SceneLocalizationMapping

```text
Final Scene SCENE_X
→ canonical ASSET:SCENE_X
→ one KEEP / LOCALIZE mapping across episodes
```

Anonymous source scenes remain occurrence-local.

Policy:

```text
KEEP     -> KEEP automatically
LOCALIZE -> target scene description required
AUTO     -> Qwen KEEP/LOCALIZE; low confidence -> REVIEW
```

## 6. R5 TargetDialogue + local Qwen3-TTS

Implemented on main; local acceptance pending.

### TargetDialogue

```text
source dialogue
+ READY TargetCharacter
+ scene / Shot context
+ target locale
→ translated_text
→ localized_text
→ final_text
```

`final_text` is the downstream dialogue authority. Source ASR text remains immutable.

Low-confidence target text with a known target speaker creates `LOCALIZATION` ReviewIssue.

### Target voice

Runtime profile:

```text
QWEN3_TTS_VOICE_DESIGN_CLONE_V1
```

```text
TargetCharacter
→ Qwen3-TTS VoiceDesign reference WAV
→ Base VoiceClone reusable prompt
→ same character voice across all lines
```

Worker:

```text
scripts/qwen3_tts_worker_v1.py
```

Main runtime client:

```text
engine/app/qwen3_tts_runtime_v1.py
```

Actual WAV duration is stored in:

```text
speech_duration_us
```

R6 must use this real duration.

One uncertain dialogue must not block audio for other READY dialogue rows.

If TargetCharacter changes, manual target dialogue is reopened and old target voice/audio is invalidated.

Spec: `docs/TARGET_DIALOGUE_TTS_V1.md`.

## 7. Review Center

ReviewIssue is attention state only.

These types must be fixed through real domain editors, not generic “mark resolved” buttons:

```text
TARGET_CHARACTER
SCENE_LOCALIZATION
LOCALIZATION
```

Authoritative writes go to:

```text
TargetCharacter
SceneLocalizationMapping
TargetDialogue
```

## 8. Source invariants

```text
LocalSubject != Character
ASR speaker != Character
Source Character != TargetCharacter
Source Scene != target Scene decision
Source Dialogue != TargetDialogue
same-Shot person observations = hard cannot-link
ASR/OCR source text = immutable
SourceDramaSnapshot = source-only
```

Do not weaken Character V10.1 safety gates to reduce ReviewIssues.

## 9. Next implementation order

```text
R2 SourceDramaSnapshot                        = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
R4 TargetCharacter + SceneLocalizationMapping = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
R5 TargetDialogue + local Qwen3-TTS           = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
R6 Dialogue Timing Engine + RemakeTimeline     = NEXT
R7 H3RuntimeManager (local MiniMax H3)
R8 H3ContextCompiler + GenerationSegment
R9 H3 QC + retry
R10 Lip Sync + subtitle/audio/assembly/export
R11 legacy cleanup
```

Mandatory rule:

```text
Shot != GenerationSegment
```

## 10. R6 input boundary

R6 consumes current READY R5 facts:

```text
TargetDialogue.final_text
TargetDialogue.audio_path
TargetDialogue.speech_duration_us
TargetDialogue.target_character_id
source dialogue timing
SourceDramaSnapshot Shot / Reference Video / action / camera context
```

R6 strategies:

```text
KEEP
REWRITE_SHORTER
TRIM
CARRY_OVER_REACTION
EXTEND
REGENERATE_EXTENSION
HUMAN_REVIEW
```

## 11. H3 target input

```text
Source Reference Video
+ TargetCharacter reference assets
+ target scene references when localized
+ TargetDialogue final audio
+ action/performance
+ camera/composition
+ planned target duration
```

```text
Ref2VA = main remake
FL2VA  = extension / bridge / repair
```

## 12. Git / acceptance

```text
main = active development
backup branch = rollback-only
all commits = [skip ci]
hosted GitHub Actions != acceptance evidence
```

Repository edits are not FINAL PASS. R2/R4/R5 local checks are documented in their spec files.
