# AI Drama Studio — Current Implementation Manifest

> Last synchronized: **2026-09-01 +08:00**

## Baseline

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Product: Localized Remake V1
Final video target: local MiniMax H3
Target speech runtime: local Qwen3-TTS
Character runtime: Character V10.1
Formal UI: ProjectListV4 + ProjectStudioV4
```

Rollback points:

```text
backup/pre-r9-20260901
backup/pre-r7-20260901
backup/pre-h3-remake-restructure-2026-09-01
```

## User surface

```text
Project
Review Center
Output
```

Automatic internals do not create new top-level product pages.

## Automatic preparation chain

```text
AUTO_REMAKE_PREP_V1

Preprocess
→ Shot Detection / Reference Clips
→ ASR / OCR / Qwen3-VL Breakdown / Fusion
→ Character V10.1 / Scene / Prop
→ Final Asset
→ SourceDramaSnapshot
→ TargetCharacter / SceneLocalizationMapping
→ TargetDialogue / Qwen3-TTS
→ RemakeTimeline
→ GenerationSegment
```

Heavy H3 execution remains separate:

```text
POST /api/projects/{project_id}/tasks/h3-generate-ready
```

R9 changes that task from raw generation into:

```text
prepare target references
→ H3 GenerationAttempt
→ structural QC
→ semantic Qwen3-VL QC
→ automatic retry when safe
→ GenerationSelection / Selected Output
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
v2_generation_attempts
v2_generation_quality_checks
v2_generation_selections
```

## R2 SourceDramaSnapshot

```text
engine/app/source_drama_snapshot_contract_v1.py
engine/app/source_drama_snapshot_v1.py
engine/app/source_drama_snapshot_routes_v1.py
engine/app/source_drama_review_issue_sync_v1.py
```

Downstream source-fact boundary with deterministic `source_fingerprint`.

## R4 Target localization

```text
engine/app/target_localization_contract_v1.py
engine/app/target_localization_v1.py
engine/app/target_localization_routes_v1.py
frontend/src/components/TargetLocalizationReviewV1.vue
```

```text
Source Character != TargetCharacter
Source Scene != target scene decision
```

## R5 TargetDialogue + local Qwen3-TTS

```text
engine/app/target_dialogue_contract_v1.py
engine/app/target_dialogue_v1.py
engine/app/target_dialogue_pipeline_v1.py
engine/app/target_dialogue_routes_v1.py
engine/app/qwen3_tts_runtime_v1.py
scripts/qwen3_tts_worker_v1.py
```

READY audio stores real `speech_duration_us`; source ASR/OCR remains immutable.

## R6 RemakeTimeline

```text
engine/app/remake_timeline_contract_v1.py
engine/app/remake_timeline_v1.py
engine/app/remake_timeline_routes_v1.py
```

Persistent table:

```text
v2_remake_timelines
```

Consumes real target speech duration and plans target timing without rewriting source facts.

## R7 GenerationSegment + H3 provider

GenerationSegment:

```text
engine/app/generation_segment_contract_v1.py
engine/app/generation_segment_v1.py
engine/app/generation_segment_routes_v1.py
```

Provider boundary:

```text
engine/app/h3_runtime_v1.py
engine/app/video_generation_provider_v1.py
engine/app/minimax_h3_provider_v1.py
```

```text
business
→ VideoGenerationProvider
→ MiniMaxH3Provider
→ H3RuntimeManager
→ local SGLang
```

H3 sizing:

```text
4..15 seconds
>15-second target shot -> multiple GenerationSegments
<4-second target -> exact post-trim after H3
```

## R8 H3 Context / references / GenerationAttempt

```text
engine/app/h3_context_contract_v1.py
engine/app/h3_context_compiler_v1.py
engine/app/h3_reference_assets_v1.py
engine/app/generation_attempt_v1.py
engine/app/h3_generation_routes_v1.py
```

Persistent table:

```text
v2_generation_attempts
```

Ref2VA receives:

```text
current TargetCharacter image reference(s)
+ optional LOCALIZE Scene reference
+ silent source directing/reference video
+ exact target-dialogue audio timeline
```

Source soundtrack is removed from the H3 reference derivative. Target TTS is supplied separately.

GenerationAttempt lifecycle:

```text
PLANNED → SUBMITTED → RUNNING → SUCCEEDED | FAILED
upstream changed → STALE
```

`SUCCEEDED` only means the provider returned a usable technical file. R9 decides whether that file becomes product-current output.

## R9 H3 QC / automatic retry / selected output

### Contracts / persistence

```text
engine/app/h3_qc_contract_v1.py
engine/app/h3_qc_core_v1.py
engine/app/generation_selection_v1.py
```

Persistent tables:

```text
v2_generation_quality_checks
v2_generation_selections
```

Authority rule:

```text
GenerationAttempt = immutable execution history
GenerationQualityCheck = QC result for an Attempt
GenerationSelection = current usable output pointer for one GenerationSegment
```

Downstream final-video work must consume `GenerationSelection`, not merely the latest `SUCCEEDED` Attempt.

### Structural hard gate

```text
ffprobe video stream / real duration / size / fps
+ full ffmpeg video decode
+ target-duration tolerance
```

Corrupt or wrong-duration output cannot be manually selected.

### Semantic Qwen3-VL QC

```text
engine/app/h3_qc_core_v1.py
```

Generated frames are compared with:

```text
TargetCharacter references
TargetScene reference/description
source Reference Video samples for action/blocking/camera only
Selected Output continuity frame when applicable
```

Scored dimensions:

```text
visual_integrity
target_character_consistency
scene_consistency
action_camera_consistency
continuity_consistency
confidence
source_actor_leak
obvious_visual_artifact
```

Source actor leakage and obvious generation corruption force RETRY.

Qwen3-VL unavailable/failing is `WAITING_MODEL`, not a fake human content issue.

### Retry executor

```text
engine/app/h3_retry_execution_v1.py
engine/app/h3_qc_orchestrator_v1.py
engine/app/h3_qc_v1.py
```

Each retry:

```text
uses a different deterministic seed
+ appends the previous QC retry_instruction to H3 prompt
+ preserves current authoritative segment fingerprint
```

For FL2VA continuation, retries use the **previous GenerationSelection output** as first frame. A technically SUCCEEDED but unselected bad output is never propagated forward.

Automatic attempt limit:

```text
AI_DRAMA_H3_QC_MAX_ATTEMPTS
```

default `3`, clamp `1..5`.

### H3_QC ReviewIssue

`H3_QC` is included in `DOMAIN_EDITED_ISSUE_TYPES`.

```text
generic Ignore / Resolve = forbidden
Adopt version -> GenerationSelection
Retry -> new H3 Attempt + QC
```

Only repeated/ambiguous quality failure enters Review Center.

### R9 APIs

```text
GET  /api/projects/{project_id}/h3-quality
POST /api/generation-attempts/{attempt_id}/quality-check
POST /api/generation-attempts/{attempt_id}/select
GET  /api/generation-segments/{segment_id}/selected-video?project_id=...
POST /api/projects/{project_id}/generation-segments/{segment_id}/tasks/h3-qc-retry
```

## R9 frontend

```text
frontend/src/components/H3OutputV1.vue
frontend/src/components/H3QcReviewV1.vue
frontend/src/views/ProjectStudioV4.vue
frontend/src/api/remake.ts
frontend/src/types/remake.ts
```

Output page now shows only Selected Output as current usable video.

Review Center exposes H3-specific actions only:

```text
采用这个版本
再生成一次
```

No separate H3/QC top-level page was added.

Frontend toolchain compatibility was stabilized during R9 acceptance:

```text
frontend/package.json / package-lock.json -> TypeScript 6.0.3 line for vue-tsc compatibility
frontend/.node-version -> 22.18.0 for current Babel/Vite engine requirements
```

Formal `frontend-v2` CI now passes `npm ci` followed by `vue-tsc --noEmit && vite build`.

## Main application wiring

Formal H3 router tree imports R9 QC/selection models before `init_database()` runs:

```text
generation_segment_router
h3_generation_router
  └─ h3_qc_router
```

Therefore all R8/R9 tables participate in safe `Base.metadata.create_all()` without a schema rewrite.

## Repository acceptance

Tests:

```text
engine/tests/v2/test_generation_segment_v1.py
engine/tests/v2/test_h3_r8_v1.py
engine/tests/v2/test_h3_qc_r9_v1.py
```

Jobs:

```text
r7-generation-segments
r8-h3-generation
r9-h3-qc
frontend-v2
```

R9 acceptance covers:

```text
QC threshold policy
source actor leak retry
low-confidence human review
structural duration/decode gate
retry seed + QC feedback
H3_QC domain-edit protection
FastAPI R9 routes
R8/R7 regression
```

On 2026-09-01:

```text
r7-generation-segments = PASS
r8-h3-generation       = PASS
r9-h3-qc                = PASS
frontend-v2             = PASS
```

## Acceptance boundary

```text
R7/R8/R9 CODE / REPOSITORY ACCEPTANCE = PASS
FRONTEND BUILD ACCEPTANCE = PASS
LOCAL H3 GPU / QWEN QC / REAL PROJECT ACCEPTANCE = PENDING
```

Historical full-suite backend/older Breakdown failures are separate legacy/dependency debt and do not redefine the isolated R7/R8/R9 acceptance result.

## Current frontier

```text
R10 Lip Sync + subtitle/audio/assembly/export = NEXT
R11 legacy cleanup
```

R10 must consume **Selected Output** and final target TTS, not raw GenerationAttempt output.
