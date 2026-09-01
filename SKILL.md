---
name: ai-drama-studio-localized-remake-v1
version: 4.2.0
description: Localized short-drama remake workflow; SourceDramaSnapshot + TargetCharacter/Scene localization + Review Center + local MiniMax H3 target generation.
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
→ TTS + real speech duration
→ timing-adjusted remake timeline
→ local MiniMax H3
→ lip sync / QC / assembly/export
```

Source drama is a directing/reference template. Characters must change. Target dialogue must not be unnaturally forced into source duration.

## 2. UX rule

> Automatic work is background work, not a page.

User flow:

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
→ Character V10.1 / Scene / Prop
→ Final Asset
→ source ReviewIssues
→ SourceDramaSnapshot
→ Speaker ReviewIssues
→ TargetCharacter / SceneLocalizationMapping
→ target ReviewIssues
```

Current ReviewIssue types:

```text
SHOT_BOUNDARY
CHARACTER_IDENTITY
ASSET_BINDING
SPEAKER
TARGET_CHARACTER
SCENE_LOCALIZATION
```

## 4. R2 SourceDramaSnapshot

Implemented on main; local acceptance pending.

```text
GET /api/episodes/{episode_id}/source-drama-snapshot
GET /api/projects/{project_id}/source-drama-snapshot
```

It is source-only deterministic current read truth with stable source keys and `source_fingerprint`. It is not another source database.

Target-side data is forbidden.

## 5. R4 Target localization

Implemented on main; local acceptance pending.

### TargetCharacter

```text
Source Character
→ one TargetCharacter per Project
```

TargetCharacter stores:

```text
target_name
appearance_profile
generation_prompt
future reference_assets
confidence
READY / REVIEW
AI / MANUAL
```

Source Character and TargetCharacter are separate rows and separate truth domains.

### SceneLocalizationMapping

Safe Final Scene identity is project-global:

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

R4 reuses the current local Qwen3-VL OpenAI-compatible service. Do not add a second planning model service without need.

Target rows are stale if source fingerprint/local signatures, target locale or Project scene policy no longer match.

## 6. Review Center

ReviewIssue is attention state only. Corrections write to authoritative rows:

```text
ShotRevision / source assets
TargetCharacter
SceneLocalizationMapping
future TargetDialogue
future RemakeTimeline
future GenerationSegment
```

Target character/scene review is embedded directly in Review Center; no separate localization asset page.

## 7. Source invariants

```text
LocalSubject != Character
ASR speaker != Character
Source Character != TargetCharacter
Source Scene != target scene decision
same-Shot person observations = hard cannot-link
ASR/OCR source text = immutable
SourceDramaSnapshot = source-only
```

Do not weaken Character V10.1 safety gates to reduce ReviewIssues.

## 8. Next implementation order

```text
R2 SourceDramaSnapshot                        = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
R4 TargetCharacter + SceneLocalizationMapping = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
R5 TargetDialogue + TTS/Voice                 = NEXT
R6 Dialogue Timing Engine + RemakeTimeline
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

## 9. H3 target input

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

## 10. Dialogue timing

```text
source dialogue
→ target translation/localization
→ TTS
→ real target speech duration
→ KEEP / REWRITE_SHORTER / TRIM / CARRY_OVER_REACTION / EXTEND / REGENERATE_EXTENSION / HUMAN_REVIEW
→ RemakeTimeline
```

## 11. Git / acceptance

```text
main = active development
backup branch = rollback-only
all commits = [skip ci]
hosted GitHub Actions != acceptance evidence
```

Repository edits are not FINAL PASS. R2/R4 local checks are documented in their spec files.
