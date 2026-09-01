# AI Drama Studio — Project State

> Last synchronized: 2026-09-01 +08:00  
> Repository: `zdingwl/ai-drama-studio`  
> Branch: `main`  
> Product architecture: **Localized Remake V1**  
> Generation target: **local MiniMax H3**  
> FastAPI app version: `2.7.0`  
> Formal Character runtime: Character V10.1

## 1. Product truth

```text
source short drama
→ automatic source understanding
→ SourceDramaSnapshot
→ TargetCharacter + SceneLocalizationMapping
→ target dialogue + TTS
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
voice = target character voice
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
→ Shot detection / Reference Clips when needed
→ Breakdown ASR + OCR + Qwen3-VL + Fusion
→ Character V10.1 / Scene / Prop
→ Final Asset application
→ source ReviewIssue sync
→ SourceDramaSnapshot
→ Speaker ReviewIssue sync
→ TargetCharacter + SceneLocalizationMapping
→ target localization ReviewIssue sync
```

## 5. R2 SourceDramaSnapshot

Status:

```text
IMPLEMENTED ON MAIN
LOCAL TEST / REAL PROJECT ACCEPTANCE PENDING
```

APIs:

```text
GET /api/episodes/{episode_id}/source-drama-snapshot
GET /api/projects/{project_id}/source-drama-snapshot
```

It is a deterministic source-only read facade and carries `source_fingerprint`. It does not persist another copy of source truth and forbids target-side data.

Detailed contract: `docs/SOURCE_DRAMA_SNAPSHOT_V1.md`.

## 6. R4 Target localization

Status:

```text
IMPLEMENTED ON MAIN
LOCAL TEST / REAL PROJECT ACCEPTANCE PENDING
```

Persistent target-side data:

```text
v2_target_characters
v2_scene_localization_mappings
```

Authority direction:

```text
SourceDramaSnapshot + ProjectRemakePolicy
→ target-localization-v1
```

### TargetCharacter

Exactly one target character per resolved source Character per Project.

Stores stable target-region identity design:

```text
target_name
appearance_profile
generation_prompt
reference_assets
confidence
READY / REVIEW
AI / MANUAL
```

Source and target Character are never the same row.

### SceneLocalizationMapping

Repeated occurrences of the same Final Scene use one canonical mapping:

```text
Final Scene id = SCENE_123
→ canonical mapping key = ASSET:SCENE_123
```

This keeps the same home/office/hospital visually consistent across episodes.

Anonymous scenes without a Final Scene remain occurrence-local.

Project policy:

```text
KEEP     -> automatic KEEP
LOCALIZE -> requires a usable target scene description
AUTO     -> generic spaces prefer KEEP; meaningful regional conflicts may LOCALIZE
```

Local Qwen3-VL OpenAI-compatible service is reused for target-side planning; no second model server was added.

APIs:

```text
POST   /api/projects/{project_id}/target-localization/generate
GET    /api/projects/{project_id}/target-localization
PATCH  /api/target-characters/{id}
DELETE /api/target-characters/{id}
PATCH  /api/scene-localization-mappings/{id}
DELETE /api/scene-localization-mappings/{id}
```

Detailed contract: `docs/TARGET_LOCALIZATION_V1.md`.

## 7. Current ReviewIssue producers

```text
SHOT_BOUNDARY
CHARACTER_IDENTITY
ASSET_BINDING
SPEAKER
TARGET_CHARACTER
SCENE_LOCALIZATION
```

`TARGET_CHARACTER` and `SCENE_LOCALIZATION` are edited directly in Review Center. The old ordinary-user manual localization draft surface is no longer shown in ProjectStudioV4.

## 8. Freshness rules

```text
source_fingerprint change -> target localization must be recomposed/revalidated
local source-character signature change -> manual target character becomes REVIEW
canonical source-scene signature change -> manual scene decision becomes REVIEW
Project scene policy change -> old SceneLocalizationMapping is stale
Project target locale mismatch -> old TargetCharacter bundle is stale
```

No stale target plan may silently appear READY.

## 9. Preserved source invariants

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
same-Shot observations = hard cannot-link
ASR source dialogue = immutable source truth
OCR source text = immutable source truth
SourceDramaSnapshot target-side data = forbidden
TargetCharacter != Source Character
Target scene decision never rewrites Source Scene
```

Character V10.1 remains fail-closed; ambiguity is handled in Review Center.

## 10. Existing source internals retained

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
P5/P6 compatibility layers while required
BackgroundTask / progress
```

## 11. Next frontier

R2 and R4 are implemented. Next order:

```text
R5 automatic TargetDialogue + TTS/Voice contract/runtime
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

## 12. Acceptance boundary

Repository implementation is not equivalent to local acceptance.

The current environment could not clone GitHub from the container because external DNS was unavailable, so targeted pytest/npm execution has **not** been claimed.

Minimum R2/R4 local checks are documented in:

```text
docs/SOURCE_DRAMA_SNAPSHOT_V1.md
docs/TARGET_LOCALIZATION_V1.md
```

## 13. Git workflow

```text
main = active development
backup/pre-h3-remake-restructure-2026-09-01 = rollback-only
all commits = [skip ci]
hosted GitHub Actions = not acceptance evidence
```
