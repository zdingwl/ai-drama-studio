# AI Drama Studio — Project State

> Last synchronized: 2026-09-01 +08:00  
> Repository: `zdingwl/ai-drama-studio`  
> Branch: `main`  
> Product architecture: **Localized Remake V1**  
> Generation target: **local MiniMax H3**  
> FastAPI app version: `2.6.0`  
> Formal Character runtime: Character V10.1

## 1. Current product truth

AI Drama Studio receives a source short drama, understands the story/directing structure, then remakes a localized drama for the Project target language and region.

```text
source drama
→ automatic source understanding
→ SourceDramaSnapshot
→ localized characters / scenes / dialogue
→ target-language TTS and timing plan
→ local MiniMax H3 remake
→ lip sync / QC / episode assembly
→ exported localized drama
```

Product rules:

```text
characters = always localized/replaced
scene = AUTO | KEEP | LOCALIZE
dialogue = target language
voice = target character voice
lip movement = final target audio
target timeline may differ from source timeline
```

## 2. Backup / rollback point

Before restructuring, `main` was frozen exactly to:

```text
branch = backup/pre-h3-remake-restructure-2026-09-01
commit = 37944c693a08c6ff292b08e1f73b1249812cabae
```

The backup branch is rollback-only.

## 3. Current formal UI

Normal users use:

```text
Project
Review Center
Output
```

Formal frontend:

```text
frontend/src/views/ProjectListV4.vue
frontend/src/views/ProjectStudioV4.vue
```

Legacy Stage 01-06 screens remain compatibility/advanced tools only.

## 4. Current automatic source-understanding task

```text
AUTO_REMAKE_PREP_V1
POST /api/projects/{project_id}/tasks/auto-remake-prepare
```

Current executable chain:

```text
Preprocess when needed
→ Shot detection / frame-exact Reference Clips when needed
→ Breakdown ASR + OCR + Qwen3-VL + Fusion when needed
→ Character V10.1 / Scene / Prop extraction
→ Final Asset application under existing gates
→ Shot / Character / Asset ReviewIssue sync
→ SourceDramaSnapshot composition
→ Speaker ReviewIssue sync
```

A successful task now returns a SourceDramaSnapshot summary including its `source_fingerprint`.

## 5. SourceDramaSnapshot V1

Status:

```text
IMPLEMENTED ON MAIN
LOCAL TEST / REAL EPISODE ACCEPTANCE PENDING
```

Purpose:

```text
G2 / P5 / P6 / current Final Asset internals
                ↓
      SourceDramaSnapshot V1
                ↓
all future remake modules
```

It is a deterministic current read model, not a second source-of-truth database.

Episode API:

```text
GET /api/episodes/{episode_id}/source-drama-snapshot
```

Project API:

```text
GET /api/projects/{project_id}/source-drama-snapshot
```

It exposes only source facts needed downstream:

```text
Episode / Scene / Shot
source timing
ShotRevision anchors
Reference Video
source people + safe Final Character resolution
Final Scene / Prop overlays when supported
action / performance
source dialogue + speaker person keys
OCR
cinematography
source fingerprint
```

It explicitly forbids target-side fields such as target dialogue, TargetCharacter, TTS, target duration or H3 output.

Detailed contract: `docs/SOURCE_DRAMA_SNAPSHOT_V1.md`.

## 6. Current unified ReviewIssue producers

```text
SHOT_BOUNDARY
CHARACTER_IDENTITY
ASSET_BINDING
SPEAKER
```

Normal high-confidence source understanding remains automatic and does not become a separate page.

## 7. Current persistent remake data

### ProjectRemakePolicy

```text
v2_project_remake_policies
scene_policy = AUTO | KEEP | LOCALIZE
character_policy = LOCALIZE
generation_engine = MINIMAX_H3_LOCAL
```

### ReviewIssue

```text
v2_review_issues
```

ReviewIssue records only attention/resolution state. Authoritative fixes remain in Shot/Asset/Dialogue/etc. domain models.

## 8. Existing accepted internals remain valid

Keep using:

```text
FFmpeg / FFprobe
Source PTS authority
ShotRevision / manual Shot edits
current TransVLM runtime/cache
frame-exact Reference Clips
Faster-Whisper ASR
RapidOCR
Qwen3-VL Breakdown
Window Context / Exact Shot
Scene Timeline structured facts
Character V10.1 Person Evidence / tracking / ReID
Final Character/Scene/Prop + Shot bindings
AssetRevision
P5/P6 compatibility safety layers while still depended upon
BackgroundTask / progress
```

Accepted Breakdown regression reference remains:

```text
Run = BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
Episode = EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
ShotRevision = SHOTREV_1462ac6d9f3948b994fc9bc575fee3a0
Shots = 30
Scenes = 2
LocalSubjects = 4
same-Shot conflicts = 0
```

## 9. Hard semantic invariants

```text
Shot = smallest visual evidence/location unit
Exact-Shot visible fact > Window Context
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
same-Shot observations = hard cannot-link
ASR source dialogue = immutable source truth
OCR source text = immutable source truth
translated/localized/final copy != source truth
SourceDramaSnapshot target-side fields = forbidden
```

Character V10.1 remains fail-closed. Ambiguity goes to Review Center; do not lower identity safety gates to reduce unresolved counts.

## 10. Next development frontier

R2 SourceDramaSnapshot is now implemented. Next order:

```text
R4 TargetCharacter + SceneLocalizationMapping
R5 automatic target dialogue + TTS
R6 Dialogue Timing Engine + RemakeTimeline
R7 local MiniMax H3 RuntimeManager
R8 H3 ContextCompiler + GenerationSegment
R9 automatic H3 QC / retry
R10 Lip Sync + subtitle/audio/episode assembly/export
R11 legacy cleanup after dependency migration
```

Critical rule:

```text
Shot != GenerationSegment
```

## 11. Acceptance status

The repository-side implementation is complete for R2, but this environment cannot run the user's Windows/CUDA/local model stack. Do **not** mark R2 FINAL PASS until local tests and a real Project snapshot are checked.

Minimum local checks are documented in `docs/SOURCE_DRAMA_SNAPSHOT_V1.md`.

## 12. Repository workflow

```text
main = active development branch
backup/pre-h3-remake-restructure-2026-09-01 = rollback-only
code/doc changes = direct main unless user asks for another branch/PR
all commits = [skip ci]
hosted GitHub Actions = not acceptance evidence
```
