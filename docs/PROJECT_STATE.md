# AI Drama Studio — Project State

> Last synchronized: 2026-09-01 +08:00  
> Repository: `zdingwl/ai-drama-studio`  
> Branch: `main`  
> Product architecture: **Localized Remake V1**  
> Final video target: **local MiniMax H3**  
> Target speech runtime V1: **local Qwen3-TTS**  
> Formal Character runtime: **Character V10.1**

## 1. Product truth

```text
source short drama
→ automatic source understanding
→ SourceDramaSnapshot
→ TargetCharacter + SceneLocalizationMapping
→ TargetDialogue + target-character voice + real TTS duration
→ Dialogue Timing / RemakeTimeline
→ GenerationSegment
→ H3 Context Compiler
→ local MiniMax H3
→ lip sync / QC / episode assembly
→ localized short drama
```

Rules:

```text
characters = always localized/replaced
scene = AUTO | KEEP | LOCALIZE
dialogue = target language
voice = new target-character voice
lip = final target audio
target timeline may differ from source timeline
Shot != GenerationSegment
```

## 2. Current rollback points

R7 entry backup:

```text
branch = backup/pre-r7-20260901
commit = 8abf420262255f464cb08a0aa783a36dd1c13d66
```

Earlier remake restructure backup remains preserved:

```text
branch = backup/pre-h3-remake-restructure-2026-09-01
commit = 37944c693a08c6ff292b08e1f73b1249812cabae
```

Rollback branches are not active development branches.

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

Current automatic chain on `main`:

```text
Preprocess when needed
→ Shot detection / Reference Clips
→ Breakdown ASR + OCR + Qwen3-VL + Fusion
→ Character V10.1 / Scene / Prop
→ Final Asset application
→ source ReviewIssue sync
→ SourceDramaSnapshot
→ Speaker ReviewIssue sync
→ TargetCharacter + SceneLocalizationMapping
→ target localization ReviewIssues
→ TargetDialogue translation/localization
→ READY-line Qwen3-TTS materialization when local worker is available
→ Dialogue Timing / RemakeTimeline
→ GenerationSegment compile
```

A remaining review item does not discard unrelated READY facts. H3 submission must still fail closed for a segment whose status is `REVIEW` or `WAITING_AUDIO`.

## 5. R2 SourceDramaSnapshot

```text
IMPLEMENTED ON MAIN
LOCAL / REAL PROJECT ACCEPTANCE PENDING
```

APIs:

```text
GET /api/episodes/{episode_id}/source-drama-snapshot
GET /api/projects/{project_id}/source-drama-snapshot
```

It is deterministic source-only current read truth with `source_fingerprint`.

Spec: `docs/SOURCE_DRAMA_SNAPSHOT_V1.md`.

## 6. R4 Target localization

```text
IMPLEMENTED ON MAIN
LOCAL / REAL PROJECT ACCEPTANCE PENDING
```

Persistent data:

```text
v2_target_characters
v2_scene_localization_mappings
```

TargetCharacter and source Character are separate truth domains. Same Final Scene across episodes shares one canonical target mapping.

## 7. R5 TargetDialogue + Qwen3-TTS

```text
IMPLEMENTED ON MAIN
LOCAL MODEL ACCEPTANCE PENDING
```

Persistent target-only data:

```text
v2_target_voice_profiles
v2_target_dialogues
```

Source ASR text is never overwritten. READY target WAV stores real `speech_duration_us`; downstream timing never substitutes character-count duration when real audio is available.

Runtime isolation:

```text
scripts/qwen3_tts_worker_v1.py
engine/app/qwen3_tts_runtime_v1.py
```

If the worker is unavailable, target text remains persisted and audio stays runtime-pending rather than becoming fake content truth.

## 8. R6 Dialogue Timing / RemakeTimeline

```text
IMPLEMENTED ON MAIN
LOCAL / REAL PROJECT ACCEPTANCE PENDING
```

Implementation:

```text
engine/app/remake_timeline_contract_v1.py
engine/app/remake_timeline_v1.py
engine/app/remake_timeline_routes_v1.py
```

Persistent data:

```text
v2_remake_timelines
```

The engine consumes SourceDramaSnapshot + TargetDialogue real audio duration and plans a target timeline without mutating source Shot boundaries or source ASR.

Current strategies include:

```text
KEEP
TRIM
CARRY_OVER_REACTION
EXTEND
HUMAN_REVIEW
WAITING_AUDIO
```

Extreme timing choices produce `DIALOGUE_TIMING` ReviewIssue.

## 9. R7 GenerationSegment + local H3 Runtime

```text
IMPLEMENTED ON MAIN
ISOLATED REPOSITORY ACCEPTANCE ADDED
LOCAL H3 / GPU ACCEPTANCE PENDING
```

### R7.1 GenerationSegment

Implementation:

```text
engine/app/generation_segment_contract_v1.py
engine/app/generation_segment_v1.py
engine/app/generation_segment_routes_v1.py
```

Persistent data:

```text
v2_generation_segments
```

Compiler input boundary:

```text
SourceDramaSnapshot
+ TargetLocalization
+ TargetDialogue
+ RemakeTimeline
        ↓
GenerationSegment
```

GenerationSegment is a deterministic compile result, not a new AI understanding layer.

H3 sizing rules currently enforced:

```text
H3 output = 4..15 seconds
>15-second target shot = balanced multi-segment split
<4-second target segment = render >=4 seconds + planned post trim
Ref2VA reference clip = 2..15 seconds
reference too short or extension outside source action = FL2VA path
```

Freshness chain:

```text
source fingerprint
+ target dialogue fingerprint
+ target localization fingerprint
+ remake timeline fingerprint
        ↓
upstream_fingerprint
        ↓
GenerationSegment input_fingerprint
```

Any authoritative upstream edit makes stale GenerationSegments unreadable until recompiled.

APIs:

```text
POST /api/projects/{project_id}/generation-segments/compile
GET  /api/projects/{project_id}/generation-segments
```

### R7.2 local H3 RuntimeManager

Implementation:

```text
engine/app/h3_runtime_v1.py
```

Default isolated SGLang endpoints:

```text
FL2VA  http://127.0.0.1:30010
Ref2VA http://127.0.0.1:30011
```

Environment overrides:

```text
AI_DRAMA_H3_FL2VA_URL
AI_DRAMA_H3_REF2VA_URL
AI_DRAMA_H3_REQUEST_TIMEOUT
AI_DRAMA_H3_DOWNLOAD_TIMEOUT
```

The FastAPI process does not import/load H3 weights. It performs health check, submit, status poll and atomic output download against the isolated local runtime.

Diagnostic API:

```text
GET /api/h3/runtime
```

### R7.3 provider boundary

Implementation:

```text
engine/app/video_generation_provider_v1.py
engine/app/minimax_h3_provider_v1.py
```

Business rule:

```text
remake/generation business
        ↓
VideoGenerationProvider
        ↓
MiniMaxH3Provider
        ↓
H3RuntimeManager / SGLang
```

No future business service should directly call SGLang or import MiniMax H3 runtime details.

## 10. ReviewIssue producers

Current product issue families include:

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

Target domain edits must modify authoritative rows; ReviewIssue itself is attention state, not business truth.

## 11. Preserved source invariants

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
same-Shot observations = hard cannot-link
ASR source dialogue = immutable
OCR source text = immutable
Source Character != TargetCharacter
Source Scene != target Scene decision
SourceDramaSnapshot contains no target truth
ReviewIssue is attention state, not domain truth
Shot != GenerationSegment
```

Character V10.1 remains fail-closed.

## 12. Next frontier

R6 and the R7 foundation are now on `main`.

Next implementation order:

```text
R8 H3 Context Compiler
→ GenerationAttempt / output persistence
→ real H3 submit / poll / download
→ FL2VA continuation keyframes
→ Ref2VA condition materialization
R9 H3 QC / automatic retry / selected output
R10 Lip Sync + subtitle/audio/episode assembly/export
R11 legacy cleanup
```

R8 must resolve internal source URLs into real local H3 conditions. `GenerationSegment.reference_url` must never be passed blindly as an SGLang file URI.

## 13. Acceptance boundary

Repository implementation is not local GPU/model acceptance.

R7 isolated repository acceptance:

```text
python -m pytest -q engine/tests/v2/test_generation_segment_v1.py
```

Real local acceptance still requires both H3 runtimes and a real prepared Project:

```text
GET /api/h3/runtime
POST /api/projects/{project_id}/generation-segments/compile
GET /api/projects/{project_id}/generation-segments
```

Then verify actual H3 service submission only after R8 Context Compiler / GenerationAttempt is implemented.

The repository currently also contains historical CI debt outside R7 (legacy Character/Breakdown expectations, lightweight CI missing heavy runtime deps, and frontend package manifest/lock drift). Those failures are not used as proof that R7 failed or passed; R7 has its own isolated acceptance job.

## 14. Git workflow

```text
main = active development
backup/pre-r7-20260901 = R7 rollback-only
backup/pre-h3-remake-restructure-2026-09-01 = older rollback-only
```
