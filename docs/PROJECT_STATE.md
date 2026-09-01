# AI Drama Studio — Project State

> Last synchronized: 2026-09-01 +08:00  
> Repository: `zdingwl/ai-drama-studio`  
> Branch: `main`  
> Product architecture: **Localized Remake V1**  
> Generation target: **local MiniMax H3**  
> FastAPI app version: `2.5.0`  
> Formal Character runtime: Character V10.1

## 1. Current product truth

AI Drama Studio is a localized short-drama remake system.

```text
source short drama
→ automatic source understanding
→ localized characters/scenes/dialogue
→ target-language TTS and timing plan
→ local MiniMax H3 remake
→ lip sync / QC / episode assembly
→ exported localized drama
```

Source drama is used as story/directing/action/camera/Reference Video guidance.

Current product rules:

```text
characters = always localized/replaced
scene = AUTO | KEEP | LOCALIZE
dialogue = target language
voice = target character voice
lip movement = final target audio
target timeline may differ from source timeline
```

## 2. Backup / rollback point

Before the 2026-09-01 product restructuring, `main` was backed up exactly to:

```text
branch = backup/pre-h3-remake-restructure-2026-09-01
commit = 37944c693a08c6ff292b08e1f73b1249812cabae
```

Do not modify that backup branch unless the user explicitly asks.

## 3. Current formal UI

The main router now uses:

```text
frontend/src/views/ProjectListV4.vue
frontend/src/views/ProjectStudioV4.vue
```

Ordinary-user workflow:

```text
Project
Review Center
Output
```

Old Stage 01-06 screens are compatibility/advanced tools only and no longer define product architecture.

## 4. Current automatic task

```text
AUTO_REMAKE_PREP_V1
POST /api/projects/{project_id}/tasks/auto-remake-prepare
```

Current executable automatic scope:

```text
Preprocess when needed
→ Shot detection / Reference Clips when needed
→ Breakdown ASR + OCR + Qwen3-VL + Fusion when needed
→ Character V10.1 / Scene / Prop extraction
→ Final Asset application under existing safety gates
→ unified ReviewIssue sync
```

Current ReviewIssue producers:

```text
SHOT_BOUNDARY
CHARACTER_IDENTITY
ASSET_BINDING
```

The system does not require separate user pages for these automatic stages.

## 5. Current new persistent data

### ProjectRemakePolicy

```text
v2_project_remake_policies
scene_policy = AUTO | KEEP | LOCALIZE
character_policy = LOCALIZE
generation_engine = MINIMAX_H3_LOCAL
```

This lives in a separate one-to-one table so existing local databases do not require ALTER TABLE migration.

### ReviewIssue

```text
v2_review_issues
```

Unified human-attention queue. ReviewIssue records attention/resolution state and does not replace authoritative Shot/Character/Scene/Prop/Dialogue/Generation data.

## 6. Existing accepted internals remain valid

The restructuring changes product workflow, not the accepted low-level truth rules.

Keep using:

```text
Source PTS authority
ShotRevision / manual Shot edits
current TransVLM shot runtime/cache
frame-exact Reference Clips
Faster-Whisper ASR
RapidOCR
Qwen3-VL Breakdown
Window Context / Exact Shot
Scene Timeline structured facts
Character V10.1 Person Evidence / tracking / ReID
Final Character/Scene/Prop + Shot bindings
AssetRevision
P7 immutable localization source/revision safety where useful
BackgroundTask / progress
```

Existing accepted Breakdown reference remains useful regression evidence:

```text
Run = BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
Episode = EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
ShotRevision = SHOTREV_1462ac6d9f3948b994fc9bc575fee3a0
Shots = 30
Scenes = 2
LocalSubjects = 4
same-Shot conflicts = 0
```

## 7. Hard semantic invariants

```text
Shot = smallest visual evidence/location unit
Exact-Shot visible fact > Window Context
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
subject_A/B = Shot-local labels only
same-Shot observations = hard cannot-link
ASR source dialogue = immutable source truth
OCR source text = immutable source truth
translated/localized/final copy != source truth
```

Character V10.1 identity safety stays fail-closed. Do not weaken same-sample cannot-link, identity ambiguity rules, explicit Shot assignment, or Final Gate merely to reduce unresolved counts. Uncertainty belongs in Review Center.

## 8. Legacy P/G layers

G1/G2/P5/P6/P7 are no longer product navigation stages.

They may remain internal implementation layers until migrated into simpler remake-facing read models.

Current intended migration:

```text
G1/G2/P5/P6/P7 internal outputs
→ SourceDramaSnapshot
→ Target localization/remake models
```

Do not continue the old Stage 05 plan.

## 9. Next development frontier

```text
R2 SourceDramaSnapshot facade
R4 TargetCharacter + SceneLocalizationMapping
R5 automatic target dialogue + TTS
R6 Dialogue Timing Engine + RemakeTimeline
R7 local MiniMax H3 RuntimeManager
R8 H3 ContextCompiler + GenerationSegment
R9 automatic H3 QC / retry
R10 Lip Sync + subtitle/audio/episode assembly/export
R11 legacy cleanup only after dependency migration
```

Critical design rule:

```text
Shot != GenerationSegment
```

Shot is the source directing/editing structure. GenerationSegment is the actual H3 generation unit.

## 10. Repository workflow

```text
main = active development branch
backup/pre-h3-remake-restructure-2026-09-01 = rollback-only
code/doc changes = direct main unless user asks for another branch/PR
all commits = [skip ci]
hosted GitHub Actions = not acceptance evidence
```

Detailed current architecture: `docs/PRODUCT_REMAKE_ARCHITECTURE_V1.md`.
