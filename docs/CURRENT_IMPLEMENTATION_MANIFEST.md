# AI Drama Studio — Current Implementation Manifest

> Purpose: code-aligned executable CURRENT manifest.  
> Last synchronized: **2026-09-01 +08:00**

## Repository baseline

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Product architecture: Localized Remake V1
Generation target: local MiniMax H3
FastAPI app version: 2.5.0
Formal Character runtime: Character V10.1
Formal ordinary-user UI: ProjectListV4 + ProjectStudioV4
```

Rollback snapshot:

```text
backup/pre-h3-remake-restructure-2026-09-01
37944c693a08c6ff292b08e1f73b1249812cabae
```

Executable CURRENT = `AGENTS.md + SKILL.md + PRODUCT_REMAKE_ARCHITECTURE_V1 + PROJECT_STATE + this manifest + current code/tests`.

## Current product surface

```text
Project
Review Center
Output
```

Legacy 01-06 Stage screens remain compatibility/advanced surfaces only.

## New current implementation

### ProjectRemakePolicy

Files:

```text
engine/app/remake_policy_v1.py
engine/app/remake_routes_v1.py
frontend/src/api/remake.ts
frontend/src/types/remake.ts
```

Persistence:

```text
v2_project_remake_policies
```

Contract:

```text
scene_policy = AUTO | KEEP | LOCALIZE
character_policy = LOCALIZE
generation_engine = MINIMAX_H3_LOCAL
```

### Unified ReviewIssue

Files:

```text
engine/app/review_issue_v1.py
engine/app/review_issue_routes_v1.py
engine/app/review_issue_sync_v1.py
engine/app/character_review_issue_sync_v1.py
```

Persistence:

```text
v2_review_issues
```

Current automatic issue types:

```text
SHOT_BOUNDARY
CHARACTER_IDENTITY
ASSET_BINDING
```

### One-click automatic source analysis

Files:

```text
engine/app/auto_remake_prepare_v1.py
engine/app/auto_remake_routes_v1.py
```

Task/API:

```text
AUTO_REMAKE_PREP_V1
POST /api/projects/{project_id}/tasks/auto-remake-prepare
```

Current chain:

```text
Preprocess when needed
→ Shot detection / Reference Clips when needed
→ Breakdown ASR/OCR/Qwen3-VL/Fusion when needed
→ Character V10.1 / Scene / Prop extraction
→ Final Asset application
→ ReviewIssue synchronization
```

### V4 frontend

Files:

```text
frontend/src/views/ProjectListV4.vue
frontend/src/views/ProjectStudioV4.vue
frontend/src/router/index.ts
```

The router now points the normal user to V4.

## Existing internals retained

The following remain production/accepted implementation building blocks and are not removed by the product restructure:

```text
FFmpeg / FFprobe
Source PTS
ShotRevision
current TransVLM shot runtime/cache
frame-exact Reference Clips
Faster-Whisper
RapidOCR
Qwen3-VL Breakdown
Window Context / Exact Shot
P2-E6 Fusion
G2 Scene Timeline structured facts
Character V10.1
Final Asset + Shot bindings
AssetRevision
P5/P6/P7 safety/read layers where still depended upon
BackgroundTask / progress
```

## Preserved semantic invariants

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
same-Shot observations = hard cannot-link
ASR source dialogue = immutable source truth
OCR source text = immutable source truth
translated/localized/final copy != source truth
```

Character identity remains fail-closed. Review Center is the product solution for ambiguity.

## Existing accepted regression reference

```text
Breakdown Run = BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
Episode = EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
ShotRevision = SHOTREV_1462ac6d9f3948b994fc9bc575fee3a0
Shots = 30
Scenes = 2
LocalSubjects = 4
same-Shot conflicts = 0
```

Previously frozen G1/G2/P5 internals remain protected unless a concrete regression or deliberate remake-contract migration requires change.

## Not yet implemented

The product restructure does **not** claim the complete remake chain is already executable.

Missing/current frontier:

```text
SourceDramaSnapshot remake-facing facade
TargetCharacter
SceneLocalizationMapping
automatic target dialogue translation/localization
TTS / Voice runtime
Dialogue Timing Engine
RemakeTimeline
GenerationSegment
local MiniMax H3 RuntimeManager
H3 ContextCompiler
H3 generation service/versioning
H3 automatic QC/retry
Lip Sync
subtitle/audio mix
final Episode assembly/export
```

## Development order

```text
R2 SourceDramaSnapshot
R4 TargetCharacter + SceneLocalizationMapping
R5 target dialogue + TTS
R6 Dialogue Timing Engine + RemakeTimeline
R7 MiniMax H3 local runtime
R8 H3 ContextCompiler + GenerationSegment
R9 QC / retry
R10 Lip Sync + assembly / export
R11 legacy cleanup
```

Do not resume the old Stage 05 implementation plan.

## Git discipline

```text
main = active development
backup branch = rollback-only
all commits include [skip ci]
hosted GitHub Actions are not acceptance evidence
```
