# AI Drama Studio — Current Implementation Manifest

> Purpose: code-aligned executable CURRENT manifest.  
> Last synchronized: **2026-09-01 +08:00**

## Repository baseline

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Product architecture: Localized Remake V1
Generation target: local MiniMax H3
FastAPI app version: 2.6.0
Formal Character runtime: Character V10.1
Formal ordinary-user UI: ProjectListV4 + ProjectStudioV4
```

Rollback snapshot:

```text
backup/pre-h3-remake-restructure-2026-09-01
37944c693a08c6ff292b08e1f73b1249812cabae
```

Executable CURRENT = `AGENTS.md + SKILL.md + PRODUCT_REMAKE_ARCHITECTURE_V1 + PROJECT_STATE + SOURCE_DRAMA_SNAPSHOT_V1 + this manifest + current code/tests`.

## Current product surface

```text
Project
Review Center
Output
```

Legacy Stage 01-06 screens are compatibility/advanced surfaces only.

## Current remake foundation

### ProjectRemakePolicy

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

Implementation:

```text
engine/app/remake_policy_v1.py
engine/app/remake_routes_v1.py
frontend/src/api/remake.ts
frontend/src/types/remake.ts
```

### Unified ReviewIssue

Persistence:

```text
v2_review_issues
```

Implementation:

```text
engine/app/review_issue_v1.py
engine/app/review_issue_routes_v1.py
engine/app/review_issue_sync_v1.py
engine/app/character_review_issue_sync_v1.py
engine/app/source_drama_review_issue_sync_v1.py
```

Current automatic issue types:

```text
SHOT_BOUNDARY
CHARACTER_IDENTITY
ASSET_BINDING
SPEAKER
```

### One-click automatic source analysis

Task/API:

```text
AUTO_REMAKE_PREP_V1
POST /api/projects/{project_id}/tasks/auto-remake-prepare
```

Implementation:

```text
engine/app/auto_remake_prepare_v1.py
engine/app/auto_remake_routes_v1.py
```

Current chain:

```text
Preprocess when needed
→ Shot detection / Reference Clips when needed
→ Breakdown ASR/OCR/Qwen3-VL/Fusion when needed
→ Character V10.1 / Scene / Prop extraction
→ Final Asset application
→ Shot / Character / Asset ReviewIssue sync
→ project SourceDramaSnapshot composition
→ Speaker ReviewIssue sync
```

The completed task result includes SourceDramaSnapshot schema/status/fingerprint/counts.

## SourceDramaSnapshot V1

Status:

```text
IMPLEMENTED ON MAIN
LOCAL TEST / REAL PROJECT ACCEPTANCE PENDING
```

Implementation:

```text
engine/app/source_drama_snapshot_contract_v1.py
engine/app/source_drama_snapshot_v1.py
engine/app/source_drama_snapshot_routes_v1.py
engine/app/source_drama_review_issue_sync_v1.py
```

Tests:

```text
engine/tests/v2/test_source_drama_snapshot_v1.py
engine/tests/v2/test_source_drama_snapshot_routes_v1.py
```

APIs:

```text
GET /api/episodes/{episode_id}/source-drama-snapshot
GET /api/projects/{project_id}/source-drama-snapshot
```

Schema versions:

```text
source-drama-snapshot-v1
source-drama-project-snapshot-v1
```

Authority direction:

```text
current safe source internals
→ deterministic SourceDramaSnapshot
→ future remake models
```

The contract carries source-only Episode/Scene/Shot structure, source timing, ShotRevision/Reference Video anchors, safe Character/Scene/Prop overlays, action/performance, verbatim source dialogue, speaker person keys, OCR and cinematography.

Target-side fields are forbidden.

The Snapshot is a current deterministic read facade, not a duplicate persistent source-of-truth table. Downstream persisted models must anchor the `source_fingerprint`.

Detailed spec: `docs/SOURCE_DRAMA_SNAPSHOT_V1.md`.

## V4 frontend

Formal router:

```text
frontend/src/views/ProjectListV4.vue
frontend/src/views/ProjectStudioV4.vue
frontend/src/router/index.ts
```

The SourceDramaSnapshot is an automatic internal artifact/status boundary, not a separate product page.

## Existing internals retained

The following remain production/accepted implementation building blocks:

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
P5/P6 compatibility layers while still depended upon
P7 localization revision safety while legacy localization UI remains
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
SourceDramaSnapshot target-side data = forbidden
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

Previously frozen G1/G2/P5 internals stay protected unless a concrete regression or deliberate remake-contract migration requires change.

## Not yet implemented

R2 SourceDramaSnapshot is no longer in the missing list.

Current frontier:

```text
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

## Acceptance boundary

Repository implementation for R2 is complete, but local execution evidence is still required.

Minimum commands:

```text
python -m pytest engine/tests/v2/test_source_drama_snapshot_v1.py -q
python -m pytest engine/tests/v2/test_source_drama_snapshot_routes_v1.py -q
python -m pytest engine/tests/v2/test_remake_foundation_v1.py -q
```

Then run a real Project through `AUTO_REMAKE_PREP_V1` and inspect the project snapshot.

Hosted GitHub Actions are not acceptance evidence.

## Git discipline

```text
main = active development
backup branch = rollback-only
all commits include [skip ci]
```
