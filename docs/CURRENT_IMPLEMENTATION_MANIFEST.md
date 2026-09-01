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

No new top-level page for automatic work.

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
```

## Persistent remake tables

```text
v2_project_remake_policies
v2_review_issues
v2_target_characters
v2_scene_localization_mappings
v2_target_voice_profiles
v2_target_dialogues
```

## R2 SourceDramaSnapshot V1

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

Spec: `docs/SOURCE_DRAMA_SNAPSHOT_V1.md`.

## R4 Target Localization V1

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
```

Test:

```text
engine/tests/v2/test_target_localization_v1.py
```

Core rules:

```text
Source Character != TargetCharacter
same Final Scene across episodes -> one canonical target scene mapping
KEEP -> automatic KEEP
LOCALIZE -> target description required
AUTO -> Qwen decision, low confidence -> REVIEW
```

Spec: `docs/TARGET_LOCALIZATION_V1.md`.

## R5 TargetDialogue + Local Qwen3-TTS V1

```text
IMPLEMENTED ON MAIN
LOCAL ACCEPTANCE PENDING
```

Implementation:

```text
engine/app/local_qwen_text_v1.py
engine/app/target_dialogue_contract_v1.py
engine/app/target_dialogue_v1.py
engine/app/target_dialogue_pipeline_v1.py
engine/app/target_dialogue_routes_v1.py
engine/app/qwen3_tts_runtime_v1.py
scripts/qwen3_tts_worker_v1.py
frontend/src/components/TargetLocalizationReviewV1.vue
frontend/src/api/remake.ts
frontend/src/types/remake.ts
frontend/src/views/ProjectStudioV4.vue
```

Tests:

```text
engine/tests/v2/test_target_dialogue_v1.py
engine/tests/v2/test_target_dialogue_routes_v1.py
engine/tests/v2/test_qwen3_tts_runtime_v1.py
```

### TargetDialogue authority

```text
SourceDramaSnapshot.source dialogue
→ target-only translated_text
→ localized_text
→ final_text
```

Source ASR/OCR is never overwritten.

Automatic localization uses the existing local Qwen OpenAI-compatible service.

Confidence threshold V1:

```text
0.74
```

Known speaker + unsafe target text produces:

```text
LOCALIZATION ReviewIssue
```

Speaker/TargetCharacter ambiguity is not duplicated as LOCALIZATION.

### Review Center behavior

These issue types require authoritative domain edits and are excluded from generic “mark resolved” actions:

```text
TARGET_CHARACTER
SCENE_LOCALIZATION
LOCALIZATION
```

Target dialogue edit:

```text
writes TargetDialogue
sets MANUAL + READY
invalidates old TTS audio
resolves LOCALIZATION issue
```

### Target voice runtime

Runtime profile:

```text
QWEN3_TTS_VOICE_DESIGN_CLONE_V1
```

Workflow:

```text
TargetCharacter
→ VoiceDesign reference WAV
→ Qwen3-TTS Base voice-clone prompt
→ reuse same target-character voice across lines
```

Worker is isolated from the main Studio Python environment.

```text
scripts/qwen3_tts_worker_v1.py
http://127.0.0.1:7861 by default
```

Main client:

```text
engine/app/qwen3_tts_runtime_v1.py
AI_DRAMA_TTS_BASE_URL
```

Worker absence or unsupported speech language is runtime capability state; it does not create content ReviewIssues.

### Real speech duration

READY audio records:

```text
audio_path
speech_duration_us
tts_runtime_profile
audio_input_signature
```

WAV duration is read from actual frame count/sample rate.

### Item-local continuation

`target_dialogue_pipeline_v1` materializes every READY line even if other lines are still REVIEW.

### Freshness

```text
SourceDramaSnapshot fingerprint / source dialogue anchors
TargetCharacter current definition
TargetVoiceProfile target_character_signature
voice_fingerprint
audio_input_signature
```

TargetCharacter change:

```text
AI dialogue -> regenerate
manual dialogue -> reopen review
voice reference -> regenerate
old dialogue WAV -> invalidate
```

GET/audio APIs fail closed on stale target-character dependencies.

### R5 APIs

```text
GET  /api/tts/runtime-status
POST /api/projects/{project_id}/target-dialogue/generate
POST /api/projects/{project_id}/target-dialogue/generate-text
POST /api/projects/{project_id}/target-dialogue/materialize-audio
GET  /api/projects/{project_id}/target-dialogue
PATCH /api/target-dialogues/{id}
GET   /api/target-dialogues/{id}/audio
```

Spec: `docs/TARGET_DIALOGUE_TTS_V1.md`.

## ReviewIssue types currently emitted

```text
SHOT_BOUNDARY
CHARACTER_IDENTITY
ASSET_BINDING
SPEAKER
TARGET_CHARACTER
SCENE_LOCALIZATION
LOCALIZATION
```

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
ASR/OCR source text = immutable
TargetDialogue != source Dialogue
ReviewIssue != domain truth
same-Shot people cannot be merged by downstream hints
SourceDramaSnapshot contains no target truth
```

## Current missing frontier

```text
R6 Dialogue Timing Engine + RemakeTimeline
R7 MiniMax H3 RuntimeManager
R8 H3 ContextCompiler + GenerationSegment
R9 H3 QC / retry
R10 Lip Sync + subtitle/audio/assembly/export
R11 legacy cleanup
```

Mandatory rule:

```text
Shot != GenerationSegment
```

## Local acceptance

No repository edit is FINAL PASS by itself.

R5 commands:

```text
python -m pytest engine/tests/v2/test_target_dialogue_v1.py -q
python -m pytest engine/tests/v2/test_target_dialogue_routes_v1.py -q
python -m pytest engine/tests/v2/test_qwen3_tts_runtime_v1.py -q

cd frontend
npm run typecheck
npm run build
```

Then run a real project with local Qwen/Qwen3-TTS and inspect actual WAVs / `speech_duration_us`.

Hosted GitHub Actions are not acceptance evidence.
