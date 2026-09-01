# AI Drama Studio — Current Implementation Manifest

> Last synchronized: **2026-09-01 +08:00**

## Baseline

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Product: Localized Remake V1
Final video target: local MiniMax H3
Target speech runtime V1: local Qwen3-TTS
Character runtime: V10.1
Formal UI: ProjectListV4 + ProjectStudioV4
```

R7 rollback:

```text
backup/pre-r7-20260901
8abf420262255f464cb08a0aa783a36dd1c13d66
```

## User surface

```text
Project
Review Center
Output
```

No new top-level page is created for automatic work.

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
→ TargetDialogue translation/localization
→ READY-line local Qwen3-TTS when worker is available
→ Dialogue Timing / RemakeTimeline
→ GenerationSegment compile
```

## Persistent remake tables

```text
v2_project_remake_policies
v2_review_issues
v2_target_characters
v2_scene_localization_mappings
v2_target_voice_profiles
v2_target_dialogues
v2_remake_timelines
v2_generation_segments
```

## Implemented authority layers

### R2 SourceDramaSnapshot V1

```text
engine/app/source_drama_snapshot_contract_v1.py
engine/app/source_drama_snapshot_v1.py
engine/app/source_drama_snapshot_routes_v1.py
engine/app/source_drama_review_issue_sync_v1.py
```

Source-only current read truth. Source fingerprint changes invalidate downstream target facts.

### R4 Target Localization V1

```text
engine/app/target_localization_contract_v1.py
engine/app/target_localization_v1.py
engine/app/target_localization_routes_v1.py
frontend/src/components/TargetLocalizationReviewV1.vue
```

Core invariants:

```text
Source Character != TargetCharacter
same Final Scene across episodes -> one canonical target mapping
KEEP -> KEEP
LOCALIZE -> localized target description
AUTO -> automatic decision, uncertain result -> REVIEW
```

### R5 TargetDialogue + Qwen3-TTS V1

```text
engine/app/target_dialogue_contract_v1.py
engine/app/target_dialogue_v1.py
engine/app/target_dialogue_pipeline_v1.py
engine/app/target_dialogue_routes_v1.py
engine/app/qwen3_tts_runtime_v1.py
scripts/qwen3_tts_worker_v1.py
```

READY audio persists real `speech_duration_us`. Source ASR/OCR is immutable.

### R6 Dialogue Timing / RemakeTimeline V1

```text
engine/app/remake_timeline_contract_v1.py
engine/app/remake_timeline_v1.py
engine/app/remake_timeline_routes_v1.py
```

Persistent table:

```text
v2_remake_timelines
```

Consumes current source + target dialogue truth and plans the target timeline from real speech duration.

Strategies include:

```text
KEEP
TRIM
CARRY_OVER_REACTION
EXTEND
HUMAN_REVIEW
WAITING_AUDIO
```

Source Shot boundaries and source ASR are never rewritten.

## R7 GenerationSegment + local H3 runtime

```text
IMPLEMENTED ON MAIN
LOCAL H3/GPU ACCEPTANCE PENDING
```

### GenerationSegment compiler

```text
engine/app/generation_segment_contract_v1.py
engine/app/generation_segment_v1.py
engine/app/generation_segment_routes_v1.py
```

Persistent table:

```text
v2_generation_segments
```

Compile boundary:

```text
SourceDramaSnapshot
+ TargetLocalization
+ TargetDialogue
+ RemakeTimeline
        ↓
GenerationSegment
```

Important runtime sizing rules:

```text
H3 render duration: 4..15 seconds
Target shot >15 seconds: split to balanced GenerationSegments
Target segment <4 seconds: render >=4 seconds, keep post-trim target
Ref2VA reference duration: 2..15 seconds
Reference too short / extension beyond source action: FL2VA path
```

GenerationSegment stores source direction context, target scene/characters, target dialogue slices, timing strategy, H3 mode and stable freshness fingerprints.

Freshness:

```text
source_fingerprint
+ target_dialogue_fingerprint
+ target_localization_fingerprint
+ remake_timeline_fingerprint
        ↓
upstream_fingerprint
        ↓
input_fingerprint
```

A stale segment fails closed and must be recompiled.

APIs:

```text
POST /api/projects/{project_id}/generation-segments/compile
GET  /api/projects/{project_id}/generation-segments
```

### H3 RuntimeManager

```text
engine/app/h3_runtime_v1.py
```

Default local endpoints:

```text
FL2VA  http://127.0.0.1:30010
Ref2VA http://127.0.0.1:30011
```

Runtime responsibilities:

```text
health check
request validation
POST /v1/videos
GET /v1/videos/{id}
GET /v1/videos/{id}/content
atomic local download
```

The main FastAPI process does not load H3 weights.

Diagnostic API:

```text
GET /api/h3/runtime
```

### VideoGenerationProvider boundary

```text
engine/app/video_generation_provider_v1.py
engine/app/minimax_h3_provider_v1.py
```

Dependency direction:

```text
business code
→ VideoGenerationProvider
→ MiniMaxH3Provider
→ H3RuntimeManager
→ local SGLang H3
```

Business code must not call provider-specific HTTP/runtime APIs directly.

## R7 tests / CI

Test:

```text
engine/tests/v2/test_generation_segment_v1.py
```

Coverage includes:

```text
4-15 second H3 duration quantization
>15 second segment splitting
FL2VA / Ref2VA condition validation
MiniMaxH3Provider delegation
provider terminal status mapping
```

Dedicated GitHub Actions job:

```text
r7-generation-segments
```

Command:

```text
python -m pytest -q engine/tests/v2/test_generation_segment_v1.py
```

This isolated job exists because the repository's full historical suite currently contains unrelated stale expectations and missing heavy CI runtime dependencies.

## ReviewIssue types currently relevant

```text
SHOT_BOUNDARY
CHARACTER_IDENTITY
ASSET_BINDING
SPEAKER
TARGET_CHARACTER
SCENE_LOCALIZATION
LOCALIZATION
DIALOGUE_TIMING
```

ReviewIssue is attention state, never the authoritative business row.

## Semantic invariants

```text
LocalSubject != Character
ASR speaker != Character
Source Character != TargetCharacter
Source Scene != target scene decision
ASR/OCR source text = immutable
TargetDialogue != source Dialogue
ReviewIssue != domain truth
same-Shot people cannot be merged by downstream hints
SourceDramaSnapshot contains no target truth
Shot != GenerationSegment
```

## Current missing frontier

R7 foundation is implemented. Next:

```text
R8 H3 Context Compiler
→ GenerationAttempt / output persistence
→ materialize Ref2VA video/image/audio conditions
→ materialize FL2VA start/end/continuation keyframes
→ real H3 submit / status poll / output download
R9 H3 QC / automatic retry / selected output
R10 Lip Sync + subtitle/audio/assembly/export
R11 legacy cleanup
```

`GenerationSegment.reference_url` is an internal Studio reference and must be resolved to a real local H3 condition by R8; it must not be forwarded blindly to SGLang.

## Acceptance boundary

Repository implementation is not local H3 acceptance.

R7 repository acceptance:

```text
python -m pytest -q engine/tests/v2/test_generation_segment_v1.py
```

Local model acceptance requires the user's actual H3 environment and will begin only when R8 implements real submission/persistence.
