---
name: ai-drama-studio-localized-remake-v1
version: 4.0.0
description: Localized short-drama remake workflow; automatic source understanding + unified Review Center + local MiniMax H3 target generation.
---

# AI Drama Studio — Localized Remake V1

## 0. Recover current truth

Read in this order:

```text
AGENTS.md
→ SKILL.md
→ docs/PRODUCT_REMAKE_ARCHITECTURE_V1.md
→ docs/PROJECT_STATE.md
→ docs/CURRENT_IMPLEMENTATION_MANIFEST.md
→ relevant current code/tests
```

Old P/G/Stage docs remain implementation history. They are not the current product workflow when they conflict with the Localized Remake V1 product definition.

Backup of the repository before this restructuring:

```text
backup/pre-h3-remake-restructure-2026-09-01
37944c693a08c6ff292b08e1f73b1249812cabae
```

## 1. Product goal

Input: an existing short drama.

Output: a new localized drama for the Project target language/region, using the original drama as directing/reference material.

Required behavior:

```text
story/directing/actions/camera may follow source
characters must be replaced/localized
scene may KEEP or LOCALIZE according to project policy
dialogue must become target language
voice must belong to target character
lip movement must follow final target audio
timeline may change for target-language speech duration
final generation engine = local MiniMax H3
```

Do not force target speech into the original duration by unnatural speech acceleration or global slow-motion.

## 2. Product UX rule

> Automatic work is background work, not a page.

The user-facing workflow is:

```text
Project
→ Review Center (only when needed)
→ Output
```

Only errors/uncertainty/conflicts/high-risk decisions require user attention.

## 3. Current V4 UI

Formal entry components:

```text
frontend/src/views/ProjectListV4.vue
frontend/src/views/ProjectStudioV4.vue
```

Main areas:

```text
Project      = locale/policy + episodes + one-click auto processing
Review       = only uncertain items + correction tools
Output       = H3 generation/QC/export surface
```

Legacy Stage 01-06 components are compatibility/advanced tools. Do not add new top-level stages.

## 4. Current automatic source-analysis task

Endpoint/task:

```text
POST /api/projects/{project_id}/tasks/auto-remake-prepare
AUTO_REMAKE_PREP_V1
```

Current chain:

```text
preprocess when needed
→ Shot detection / Reference Clips when needed
→ Breakdown ASR/OCR/Qwen3-VL/Fusion when needed
→ Character V10.1 + Scene/Prop extraction
→ Final Asset application under existing safety gates
→ ReviewIssue sync
```

Current ReviewIssue types:

```text
SHOT_BOUNDARY
CHARACTER_IDENTITY
ASSET_BINDING
```

## 5. Project remake policy

Stored separately from legacy Project schema to avoid ALTER TABLE migration risk:

```text
ProjectRemakePolicy
scene_policy = AUTO | KEEP | LOCALIZE
character_policy = LOCALIZE
generation_engine = MINIMAX_H3_LOCAL
```

## 6. Review Center contract

`ReviewIssue` is the single attention queue, not domain truth.

```text
project_id
episode_id
shot_id
source_key
issue_type
severity
status
reason
ai_suggestion
editable_payload
resolution
```

Corrections still write to authoritative domain models:

```text
ShotRevision / Shot
Final Character/Scene/Prop + Shot bindings
future TargetDialogue
future RemakeTimeline
future GenerationSegment
```

## 7. Existing internal capabilities to preserve

Keep using accepted internals unless deliberately migrated:

```text
Source PTS
ShotRevision
Reference Clip
TransVLM shot runtime/cache
Faster-Whisper
RapidOCR
Qwen3-VL Breakdown
Window Context / Exact Shot
Scene Timeline
Character V10.1
AssetRevision + Final bindings
Localization source/revision safety
BackgroundTask
```

Do not weaken Character identity gates just to eliminate unresolved items. Uncertainty is handled by Review Center.

## 8. Next implementation order

```text
R2 SourceDramaSnapshot
R4 TargetCharacter + SceneLocalizationMapping
R5 automatic localization + TTS
R6 Dialogue Timing Engine + RemakeTimeline
R7 H3RuntimeManager (local MiniMax H3)
R8 H3ContextCompiler + GenerationSegment
R9 H3 QC + retry
R10 Lip Sync + subtitle/audio/assembly/export
R11 legacy cleanup
```

Key rule:

```text
Shot != GenerationSegment
```

## 9. Future H3 input contract

The target compiler should produce H3-ready conditions from:

```text
source Reference Video
Target Character references
Target Scene references if localized
Target Dialogue audio
action/performance facts
camera/composition constraints
target duration
```

Preferred generation use:

```text
Ref2VA = main remake
FL2VA  = extension / bridge / repair
```

## 10. Dialogue timing contract

Required flow:

```text
source dialogue
→ translation/localization
→ TTS
→ actual speech duration
→ timing strategy
→ RemakeTimeline
```

Preferred automatic strategies:

```text
KEEP
REWRITE_SHORTER
TRIM
CARRY_OVER_REACTION
EXTEND
REGENERATE_EXTENSION
HUMAN_REVIEW
```

## 11. Git discipline

```text
main is the active development branch
backup/pre-h3-remake-restructure-2026-09-01 is rollback-only
all commits include [skip ci]
hosted GitHub Actions are not acceptance evidence
```
