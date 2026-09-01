# AI Drama Studio — Project State

> Last synchronized: 2026-09-01 +08:00  
> Repository: `zdingwl/ai-drama-studio`  
> Branch: `main`  
> Product architecture: **Localized Remake V1**  
> Final video target: **local MiniMax H3**  
> Target speech runtime: **local Qwen3-TTS**  
> Formal Character runtime: **Character V10.1**

## 1. Product truth

```text
source short drama
→ source understanding / Reference Clips
→ SourceDramaSnapshot
→ TargetCharacter + SceneLocalizationMapping
→ TargetDialogue + target-character voice + real TTS duration
→ RemakeTimeline
→ GenerationSegment
→ H3 Context Compiler
→ target reference assets
→ GenerationAttempt / local MiniMax H3
→ structural + semantic H3 QC
→ automatic retry
→ GenerationSelection / Selected Output
→ lip sync / subtitles / audio / episode assembly
→ localized short drama
```

Hard rules:

```text
characters = always replaced/localized
scene = AUTO | KEEP | LOCALIZE
dialogue = target language
voice = target-character voice
target timeline may differ from source timeline
Shot != GenerationSegment
GenerationAttempt != selected usable output
source ASR/OCR/Shot truth is immutable downstream
```

## 2. Rollback points

R9 entry backup:

```text
branch = backup/pre-r9-20260901
```

Earlier recovery points remain:

```text
backup/pre-r7-20260901
backup/pre-h3-remake-restructure-2026-09-01
```

Rollback branches are read-only recovery points. `main` is active development.

## 3. Formal user surface

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

Automatic work stays in background tasks. Only uncertainty/conflict/high-risk decisions/repeated generation failure belong in Review Center.

## 4. Automatic preparation chain

```text
AUTO_REMAKE_PREP_V1
POST /api/projects/{project_id}/tasks/auto-remake-prepare
```

Current preparation chain:

```text
Preprocess
→ Shot detection / Reference Clips
→ ASR + OCR + Qwen3-VL Breakdown / Fusion
→ Character V10.1 + Scene + Prop
→ Final Asset / source ReviewIssues
→ SourceDramaSnapshot
→ TargetCharacter + SceneLocalizationMapping
→ TargetDialogue localization
→ READY-line Qwen3-TTS
→ RemakeTimeline
→ GenerationSegment compile
```

H3 is intentionally separate:

```text
POST /api/projects/{project_id}/tasks/h3-generate-ready
```

That task now performs generation **and R9 QC/automatic retry**, and only produces downstream-current output after `GenerationSelection` is written.

## 5. Current stage table

| Stage | State | Persistent authority |
|---|---|---|
| R2 SourceDramaSnapshot | Implemented | source read model / fingerprint |
| R4 Target localization | Implemented | `v2_target_characters`, `v2_scene_localization_mappings` |
| R5 TargetDialogue + TTS | Implemented | `v2_target_voice_profiles`, `v2_target_dialogues` |
| R6 Dialogue Timing | Implemented | `v2_remake_timelines` |
| R7 GenerationSegment | Implemented | `v2_generation_segments` |
| R7 H3 Runtime/Provider | Implemented | isolated local SGLang adapter |
| R8 H3 Context Compiler | Implemented | deterministic materialized context |
| R8 GenerationAttempt | Implemented | `v2_generation_attempts` |
| R9 H3 QC | Implemented | `v2_generation_quality_checks` |
| R9 Selected Output | Implemented | `v2_generation_selections` |
| R10 Lip sync/assembly/export | Next | — |

Repository implementation does **not** mean the user's local GPU/model environment has passed real-project acceptance.

## 6. R6/R7 timing and segment rules

`RemakeTimeline` consumes real TargetDialogue `speech_duration_us`; source Shot boundaries and source ASR are never rewritten.

```text
KEEP
TRIM
CARRY_OVER_REACTION
EXTEND
HUMAN_REVIEW
WAITING_AUDIO
```

GenerationSegment boundary:

```text
SourceDramaSnapshot
+ TargetLocalization
+ TargetDialogue
+ RemakeTimeline
→ GenerationSegment
```

H3 constraints:

```text
render = 4..15 seconds
>15-second target shot = balanced multi-segment split
<4-second target = H3 render >=4 seconds + exact FFmpeg post-trim
Ref2VA visual reference = 2..15 seconds
```

Any authoritative upstream fingerprint change makes old segment/attempt/QC/selection stale or invalid.

## 7. R8 H3 execution

Core implementation:

```text
engine/app/h3_context_contract_v1.py
engine/app/h3_context_compiler_v1.py
engine/app/h3_reference_assets_v1.py
engine/app/generation_attempt_v1.py
engine/app/h3_generation_routes_v1.py
```

Ref2VA input:

```text
TargetCharacter reference image(s)
+ optional LOCALIZE Scene reference
+ visual-only source Reference Video (`-an`)
+ exact target-dialogue TTS audio condition when dialogue exists
+ compact deterministic prompt
```

Source-language soundtrack is never passed into Ref2VA. Target TTS is mixed separately as aligned 32 kHz stereo audio.

GenerationAttempt lifecycle:

```text
PLANNED → SUBMITTED → RUNNING → SUCCEEDED | FAILED
upstream changed → STALE
```

For target segments shorter than H3's 4-second minimum, the raw H3 file is precisely trimmed to target duration before the Attempt output is published.

## 8. R9 H3 QC / automatic retry / selection

Implementation:

```text
engine/app/h3_qc_contract_v1.py
engine/app/h3_qc_core_v1.py
engine/app/h3_qc_orchestrator_v1.py
engine/app/h3_qc_v1.py
engine/app/h3_retry_execution_v1.py
engine/app/generation_selection_v1.py
engine/app/h3_qc_routes_v1.py
frontend/src/components/H3QcReviewV1.vue
frontend/src/components/H3OutputV1.vue
```

Persistent tables:

```text
v2_generation_quality_checks
v2_generation_selections
```

### Structural hard gate

Each SUCCEEDED Attempt is checked with:

```text
ffprobe video stream / duration / dimensions / fps
+ full ffmpeg video decode
+ exact target-duration tolerance
```

A corrupt or wrong-duration output cannot become Selected Output, even by manual override.

### Semantic QC

The existing local Qwen3-VL service receives sampled frames from the generated video plus current comparison references:

```text
TargetCharacter references
TargetScene reference/description
source Reference Video samples for action/blocking/camera only
previous Selected Output continuity frame when needed
```

It evaluates:

```text
visual integrity
source actor leakage
target character consistency
scene consistency
Ref2VA action/camera consistency
FL2VA continuity consistency
```

Final lip sync is intentionally **not** scored here; it belongs to R10.

### Retry policy

```text
QC PASS -> auto GenerationSelection
QC RETRY -> different seed + concrete QC correction added to H3 prompt
Qwen unavailable -> WAITING_MODEL, no human content ReviewIssue
low-confidence/ambiguous semantic result -> H3_QC ReviewIssue
repeated retry failure -> H3_QC ReviewIssue
```

Automatic attempt cap defaults to 3 and can be configured with:

```text
AI_DRAMA_H3_QC_MAX_ATTEMPTS
```

clamped to 1..5.

FL2VA retry continuity uses the **previous Selected Output**, never merely the latest technically SUCCEEDED Attempt.

### Human fallback

`H3_QC` is a domain-edited ReviewIssue. Generic ignore/resolve is blocked.

The Review Center allows only meaningful actions:

```text
采用这个版本 -> writes GenerationSelection
再生成一次 -> background H3 retry + QC
```

Manual selection may override semantic uncertainty only when the output has passed structural hard checks.

## 9. R9 APIs

```text
GET  /api/projects/{project_id}/h3-quality
POST /api/generation-attempts/{attempt_id}/quality-check
POST /api/generation-attempts/{attempt_id}/select
GET  /api/generation-segments/{segment_id}/selected-video?project_id=...
POST /api/projects/{project_id}/generation-segments/{segment_id}/tasks/h3-qc-retry
```

Existing H3 entry remains:

```text
POST /api/projects/{project_id}/tasks/h3-generate-ready
```

but its product semantics are now **generate + QC + auto retry + select**, not raw generation only.

## 10. ReviewIssue families

```text
SHOT_BOUNDARY
CHARACTER_IDENTITY
ASSET_BINDING
SPEAKER
TARGET_CHARACTER
SCENE_LOCALIZATION
LOCALIZATION
DIALOGUE_TIMING
H3_QC
```

`ReviewIssue` is attention state, not authoritative business truth.

## 11. Repository acceptance

Dedicated isolated jobs:

```text
r7-generation-segments
r8-h3-generation
r9-h3-qc
frontend-v2
```

R9 acceptance covers:

```text
QC pass thresholds
source actor leakage -> RETRY
low QC confidence -> REVIEW
structural exact-duration + full-decode gate
retry seed changes + QC correction prompt
H3_QC domain-edit protection
FastAPI R9 route registration
R8/R7 regression checks
```

On 2026-09-01:

```text
r7-generation-segments = PASS
r8-h3-generation       = PASS
r9-h3-qc                = PASS
frontend-v2             = PASS (npm ci + vue-tsc + vite build)
```

Frontend toolchain was stabilized by regenerating `package-lock.json` with TypeScript 6.0.3 compatibility for `vue-tsc` and keeping `.node-version` at 22.18.0 for the current Babel/Vite engine requirements.

Historical full-suite backend/older Breakdown debt remains separate from the R7/R8/R9 isolated acceptance boundary.

## 12. Local acceptance still required

Real end-to-end H3/R9 acceptance requires the user's actual machine:

```text
1. start FL2VA and required Ref2VA runtime
2. start local Qwen3-VL QC service
3. run a real prepared Project
4. generate target references and H3 attempts
5. verify automatic QC/retries
6. inspect Selected Output identity, scene, action/camera and duration
7. force at least one bad/ambiguous case and verify H3_QC Review Center flow
```

Current factual state:

```text
R7/R8/R9 CODE + REPOSITORY ACCEPTANCE = PASS
FRONTEND BUILD ACCEPTANCE = PASS
LOCAL H3 GPU / QWEN QC / REAL PROJECT ACCEPTANCE = PENDING
```

## 13. Next frontier

```text
R10 Lip Sync
→ enforce final target TTS mouth sync on Selected Output
→ subtitle policy
→ ambience / BGM / SFX / target voice mix
→ episode assembly
→ preview / export

R11 legacy cleanup
```
