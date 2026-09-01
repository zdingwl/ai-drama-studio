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
→ Dialogue Timing / RemakeTimeline
→ GenerationSegment
→ H3 Context Compiler
→ target reference assets
→ GenerationAttempt / local MiniMax H3
→ H3 QC / retry
→ lip sync / subtitles / audio / episode assembly
→ localized short drama
```

Hard rules:

```text
characters = always localized/replaced
scene = AUTO | KEEP | LOCALIZE
dialogue = target language
voice = target-character voice
lip = final target audio
target timeline may differ from source timeline
Shot != GenerationSegment
source ASR/OCR/Shot truth is immutable downstream
```

## 2. Rollback points

R7/R8 work started after:

```text
branch = backup/pre-r7-20260901
commit = 8abf420262255f464cb08a0aa783a36dd1c13d66
```

Earlier restructure rollback remains:

```text
branch = backup/pre-h3-remake-restructure-2026-09-01
commit = 37944c693a08c6ff292b08e1f73b1249812cabae
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

Automatic processing must stay in background tasks. Only uncertainty, conflict, high-risk edits or repeated generation failure belong in Review Center.

## 4. Automatic preparation chain

```text
AUTO_REMAKE_PREP_V1
POST /api/projects/{project_id}/tasks/auto-remake-prepare
```

Current chain:

```text
Preprocess
→ Shot detection / Reference Clips
→ ASR + OCR + Qwen3-VL Breakdown / Fusion
→ Character V10.1 + Scene + Prop
→ Final Asset / source ReviewIssues
→ SourceDramaSnapshot
→ Speaker ReviewIssues
→ TargetCharacter + SceneLocalizationMapping
→ target ReviewIssues
→ TargetDialogue localization
→ READY-line Qwen3-TTS
→ RemakeTimeline
→ GenerationSegment compile
```

H3 generation is a separate heavy background task so source understanding/localization can finish even when H3 GPU runtime is offline.

## 5. Implemented stages

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
| R9 H3 QC/retry/selection | Next | not yet authoritative |
| R10 Lip sync/assembly/export | Not implemented | — |

Repository implementation does **not** mean the user's local GPU/model environment has passed real-model acceptance.

## 6. R6 Timing rules

`RemakeTimeline` consumes real TargetDialogue `speech_duration_us`. It never rewrites source Shot boundaries or source ASR.

Current strategies include:

```text
KEEP
TRIM
CARRY_OVER_REACTION
EXTEND
HUMAN_REVIEW
WAITING_AUDIO
```

Extreme timing ambiguity produces `DIALOGUE_TIMING` ReviewIssue.

## 7. R7 GenerationSegment

Compiler boundary:

```text
SourceDramaSnapshot
+ TargetLocalization
+ TargetDialogue
+ RemakeTimeline
        ↓
GenerationSegment
```

Important constraints:

```text
H3 render = 4..15 seconds
>15-second target shot = balanced multi-segment split
<4-second target segment = render >=4 seconds + exact post trim
Ref2VA visual reference = 2..15 seconds
source reference too short / extension outside source action = FL2VA
```

Freshness:

```text
source_fingerprint
+ target_dialogue_fingerprint
+ target_localization_fingerprint
+ remake_timeline_fingerprint
→ GenerationSegment input_fingerprint
```

Any authoritative upstream edit makes an old segment stale.

APIs:

```text
POST /api/projects/{project_id}/generation-segments/compile
GET  /api/projects/{project_id}/generation-segments
GET  /api/h3/runtime
```

## 8. R8 H3 Context Compiler

Implementation:

```text
engine/app/h3_context_contract_v1.py
engine/app/h3_context_compiler_v1.py
engine/app/h3_reference_assets_v1.py
```

The compiler does not perform another story-understanding pass. It converts current product truth into executable H3 input.

### Ref2VA context

```text
TargetCharacter current reference image(s)
+ optional LOCALIZE Scene reference image
+ silent source Reference Video
+ aligned target TTS audio timeline when dialogue exists
+ compact H3 Context-IR-style prompt
```

Critical safety/correctness rule:

```text
source Reference Clip may contain source audio for analysis/review
↓
R8 creates a new visual-only derivative with `-an`
↓
source-language soundtrack is never supplied to Ref2VA
```

Target TTS is mixed separately at exact segment offsets as 32 kHz stereo audio.

### FL2VA context

```text
continuation segment
→ previous current successful GenerationAttempt final frame
→ frame_index = 0
→ FL2VA continuation

no keyframe
→ FL2VA endpoint / t2va task
```

Target language is read from current target localization truth and used in H3 dialogue tags; it is not inferred from the compact character context.

Internal Studio URLs such as `/api/shots/.../reference` are always resolved to real local files before SGLang submission.

## 9. R8 target reference assets

Text-only TargetCharacter definitions are automatically materialized into deterministic H3 casting references before Ref2VA generation:

```text
TargetCharacter
→ FL2VA endpoint in text-to-video mode
→ 4-second neutral casting clip
→ reusable current reference stills
```

LOCALIZE scenes can similarly receive an empty target-region environment reference image.

These are automatic runtime assets, not user-facing pages. Their signatures depend on current target truth, so target edits invalidate old references naturally.

## 10. R8 GenerationAttempt

Implementation:

```text
engine/app/generation_attempt_v1.py
engine/app/h3_generation_routes_v1.py
```

Persistent table:

```text
v2_generation_attempts
```

One row = one immutable execution attempt for one current GenerationSegment context.

Lifecycle:

```text
PLANNED
→ SUBMITTED
→ RUNNING
→ SUCCEEDED | FAILED

upstream changed during/after generation
→ STALE
```

Execution:

```text
compile H3 context
→ submit through VideoGenerationProvider
→ poll local SGLang job
→ download raw H3 output
→ if H3 minimum render > target duration, exact FFmpeg post-trim
→ persist current final output
```

A Studio process restart marks local executor attempts left in `PLANNED/SUBMITTED/RUNNING` as failed instead of leaving a permanent false-running state.

APIs:

```text
POST /api/projects/{project_id}/generation-segments/{segment_id}/h3-context/compile
POST /api/projects/{project_id}/tasks/h3-generate-ready
GET  /api/projects/{project_id}/generation-attempts
GET  /api/generation-attempts/{attempt_id}/video
```

The batch task runs READY GenerationSegments sequentially and reuses a current successful output instead of regenerating it.

## 11. H3 runtime boundary

```text
business code
→ VideoGenerationProvider
→ MiniMaxH3Provider
→ H3RuntimeManager
→ local SGLang H3
```

Default endpoints:

```text
FL2VA  http://127.0.0.1:30010
Ref2VA http://127.0.0.1:30011
```

Current runtime request profile follows the SGLang async `/v1/videos` contract and supplies `model`, `seconds`, `task`, `conditions`, target resolution/aspect, inference settings and seed.

The main Studio FastAPI process never loads the H3 weights.

## 12. Current ReviewIssue families

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

`ReviewIssue` is attention state, not authoritative business truth.

## 13. Repository acceptance

Dedicated isolated jobs:

```text
r7-generation-segments
r8-h3-generation
```

Commands:

```text
python -m pytest -q engine/tests/v2/test_generation_segment_v1.py
python -m pytest -q engine/tests/v2/test_h3_r8_v1.py engine/tests/v2/test_generation_segment_v1.py
```

On 2026-09-01 both isolated R7 and R8 jobs passed, including FastAPI R8 route import.

Known unrelated repository debt remains outside this acceptance boundary:

```text
frontend package.json/package-lock dependency drift -> npm ci failure
historical Character/Breakdown tests with stale version expectations
lightweight full-suite CI missing some heavy runtime dependencies
```

Do not claim those failures prove R7/R8 failed, and do not claim isolated repository PASS proves the local H3 model itself works.

## 14. Local acceptance still required

Real H3 acceptance must run on the user's actual GPU/model machine:

```text
1. start FL2VA SGLang runtime
2. start Ref2VA SGLang runtime when plan needs reference generation
3. GET /api/h3/runtime
4. run a prepared real Project through GenerationSegment
5. POST /api/projects/{project_id}/tasks/h3-generate-ready
6. inspect real target-character references and H3 outputs
7. verify target identity, source action/camera transfer, target-language audio timing and exact final segment duration
```

Until this is performed, R8 state is:

```text
CODE / ISOLATED REPOSITORY ACCEPTANCE = PASS
LOCAL H3 GPU / REAL PROJECT ACCEPTANCE = PENDING
```

## 15. Next frontier

```text
R9 H3 QC
→ automatic quality metrics
→ retry policy
→ selected attempt/output
→ repeated failure -> Review Center

R10 Lip Sync
→ enforce final target TTS
→ subtitle / ambience / BGM / SFX policy
→ episode assembly
→ preview / export

R11 legacy cleanup
```
