# AI Drama Studio — Current Implementation Manifest

> Last synchronized: **2026-09-01 +08:00**

## Baseline

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Product: Localized Remake V1
Generation target: local MiniMax H3
FastAPI app: 2.7.0
Character runtime: V10.1
Formal UI: ProjectListV4 + ProjectStudioV4
```

Rollback:

```text
backup/pre-h3-remake-restructure-2026-09-01
37944c693a08c6ff292b08e1f73b1249812cabae
```

## User surface

```text
Project
Review Center
Output
```

No new top-level page should be added for automatic work.

## Automatic pipeline currently implemented

```text
AUTO_REMAKE_PREP_V1

Preprocess
→ Shot Detection / Reference Clips
→ ASR / OCR / Qwen3-VL Breakdown / Fusion
→ Character V10.1 / Scene / Prop
→ Final Asset
→ Source ReviewIssues
→ SourceDramaSnapshot
→ Speaker ReviewIssues
→ TargetCharacter / SceneLocalizationMapping
→ Target ReviewIssues
```

## Persistent remake tables

```text
v2_project_remake_policies
v2_review_issues
v2_target_characters
v2_scene_localization_mappings
```

## R2 SourceDramaSnapshot V1

Status:

```text
IMPLEMENTED ON MAIN
LOCAL ACCEPTANCE PENDING
```

Implementation:

```text
engine/app/source_drama_snapshot_contract_v1.py
engine/app/source_drama_snapshot_v1.py
engine/app/source_drama_snapshot_routes_v1.py
engine/app/source_drama_review_issue_sync_v1.py
```

APIs:

```text
GET /api/episodes/{episode_id}/source-drama-snapshot
GET /api/projects/{project_id}/source-drama-snapshot
```

Source-only deterministic facade with `source_fingerprint`; not another source DB.

Spec: `docs/SOURCE_DRAMA_SNAPSHOT_V1.md`.

## R4 Target Localization V1

Status:

```text
IMPLEMENTED ON MAIN
LOCAL ACCEPTANCE PENDING
```

Implementation:

```text
engine/app/target_localization_contract_v1.py
engine/app/target_localization_v1.py
engine/app/target_localization_routes_v1.py
frontend/src/components/TargetLocalizationReviewV1.vue
frontend/src/api/remake.ts
frontend/src/types/remake.ts
frontend/src/views/ProjectStudioV4.vue
```

Test:

```text
engine/tests/v2/test_target_localization_v1.py
```

### TargetCharacter

```text
(project_id, source_character_id) -> one TargetCharacter
```

Target fields:

```text
target_name
appearance_profile
generation_prompt
reference_assets
confidence
status
```

Source Character is never rewritten.

### SceneLocalizationMapping

Safe Final Scene identity is canonical across episodes:

```text
Final Scene SCENE_X -> ASSET:SCENE_X -> one target mapping
```

Anonymous scene without Final Scene uses its SourceDramaSnapshot scene key.

This prevents the same source location from receiving different target designs across episodes.

### Model/runtime

R4 reuses the configured local Qwen3-VL OpenAI-compatible endpoint for text planning.

```text
AI_DRAMA_VLM_BASE_URL
AI_DRAMA_VLM_MODEL
AI_DRAMA_VLM_API_KEY
```

No new model server was introduced.

### Policy behavior

```text
KEEP     -> automatic KEEP, no model decision required
LOCALIZE -> all canonical scenes need target descriptions
AUTO     -> model chooses KEEP / LOCALIZE; low confidence -> REVIEW
```

Automatic confidence threshold in V1:

```text
0.72
```

### APIs

```text
POST   /api/projects/{project_id}/target-localization/generate
GET    /api/projects/{project_id}/target-localization
PATCH  /api/target-characters/{id}
DELETE /api/target-characters/{id}
PATCH  /api/scene-localization-mappings/{id}
DELETE /api/scene-localization-mappings/{id}
```

Spec: `docs/TARGET_LOCALIZATION_V1.md`.

## ReviewIssue types currently emitted

```text
SHOT_BOUNDARY
CHARACTER_IDENTITY
ASSET_BINDING
SPEAKER
TARGET_CHARACTER
SCENE_LOCALIZATION
```

Review Center writes corrections into authoritative domain rows, not into ReviewIssue as replacement truth.

## Freshness protection

Target bundle is fail-closed when any of these are stale:

```text
source_fingerprint
local Character signature
canonical Scene signature
Project scene policy
TargetCharacter language/region
```

Manual target decisions survive ordinary reruns only while their local source signature remains unchanged.

## Source internals retained

```text
FFmpeg / FFprobe
Source PTS
ShotRevision
TransVLM runtime/cache
Reference Clips
Faster-Whisper
RapidOCR
Qwen3-VL Breakdown
Window / Exact Shot
P2-E6 Fusion
G2 Scene Timeline
Character V10.1
Final Asset + Shot bindings
AssetRevision
P5/P6 compatibility while required
BackgroundTask
```

## Semantic invariants

```text
LocalSubject != Character
ASR speaker != Character
Source Character != TargetCharacter
Source Scene != target scene decision
ASR/OCR source text is immutable
same-Shot people cannot be merged by downstream hints
SourceDramaSnapshot contains no target truth
```

## Current missing frontier

```text
R5 TargetDialogue + TTS/Voice
R6 Dialogue Timing Engine + RemakeTimeline
R7 MiniMax H3 RuntimeManager
R8 H3 ContextCompiler + GenerationSegment
R9 H3 QC / retry
R10 Lip Sync + subtitle/audio/assembly/export
R11 legacy cleanup
```

## Local acceptance

Not claimed from repository edits alone.

The assistant attempted to clone current main into the execution container for tests, but the container had no external DNS access to GitHub. Therefore no pytest/npm pass is claimed from this environment.

Use the commands in:

```text
docs/SOURCE_DRAMA_SNAPSHOT_V1.md
docs/TARGET_LOCALIZATION_V1.md
```

Hosted GitHub Actions are not acceptance evidence.
