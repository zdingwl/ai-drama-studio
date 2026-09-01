# R5 — TargetDialogue + Local Qwen3-TTS V1

> Status: **IMPLEMENTED ON `main` / local acceptance pending**  
> Product rule: target dialogue/TTS is automatic background work; only unsafe text becomes Review Center work.

## 1. Purpose

R5 turns immutable source dialogue from `SourceDramaSnapshot` into target-side dialogue and real speech timing material.

```text
SourceDramaSnapshot.source_dialogue
+ TargetCharacter
+ Project target_language / target_region
        ↓
translation
        ↓
regional localization
        ↓
TargetDialogue.final_text
        ↓
TargetVoiceProfile
        ↓
local Qwen3-TTS
        ↓
WAV + speech_duration_us
```

R5 does **not** change Shot duration. Timing changes belong to R6.

## 2. Source/target separation

Source dialogue remains immutable:

```text
source_text
source_start_us
source_end_us
source speaker anchors
```

R5 stores target-only truth in new tables:

```text
v2_target_voice_profiles
v2_target_dialogues
```

It never writes translated/localized text back into source ASR or `SourceDramaSnapshot`.

## 3. TargetDialogue

One current source dialogue anchor maps to one target dialogue row per Project.

Important fields:

```text
source_dialogue_key
source_dialogue_signature
source_fingerprint
source_text
source_character_id

target_character_id
target_voice_profile_id
translated_text
localized_text
final_text
translation_confidence
status = READY | REVIEW

audio_status
 audio_input_signature
 audio_path
 speech_duration_us
 tts_runtime_profile
```

`final_text` is the text R6/H3/Lip Sync must consume.

## 4. Automatic localization

R5 reuses the already configured local Qwen OpenAI-compatible endpoint used by the existing Qwen3-VL workflow.

Input context includes:

```text
source dialogue
source speaker → TargetCharacter
scene story summary
Shot visual description
Project source language
Project target language
Project target region
source-name → target-name mapping
```

The model returns:

```text
translated_text = faithful translation
localized_text  = natural target-market wording
final_text      = current recommended performance line
confidence      = 0..1
```

R5 must not shorten a line merely to fit the source Shot. R6 owns duration optimization.

## 5. Review rule

A normal high-confidence line never becomes a page/card.

`LOCALIZATION` ReviewIssue is created only when:

```text
speaker/TargetCharacter is already known
AND
translation/localization cannot be accepted safely
```

Speaker/Character ambiguity remains owned by upstream `SPEAKER` / `TARGET_CHARACTER` issues and is not duplicated as a localization issue.

In Review Center the user edits the authoritative TargetDialogue fields. The UI does not allow a `LOCALIZATION` problem to be closed by merely clicking “resolved”.

Manual dialogue edit:

```text
writes TargetDialogue
sets decision_source = MANUAL
sets status = READY
invalidates old audio
resolves the matching LOCALIZATION issue
```

## 6. TargetVoiceProfile

One READY TargetCharacter gets one stable target voice profile.

Runtime profile:

```text
QWEN3_TTS_VOICE_DESIGN_CLONE_V1
```

Workflow:

```text
TargetCharacter stable persona
        ↓
Qwen3-TTS VoiceDesign
        ↓
short target-character reference WAV
        ↓
Qwen3-TTS Base create_voice_clone_prompt
        ↓
reuse the same target voice for every line
```

This intentionally creates a new localized character voice rather than cloning the source actor.

## 7. Local Qwen3-TTS worker

Worker:

```text
scripts/qwen3_tts_worker_v1.py
```

Main-process client:

```text
engine/app/qwen3_tts_runtime_v1.py
```

Default local endpoint:

```text
http://127.0.0.1:7861
```

Main app environment override:

```text
AI_DRAMA_TTS_BASE_URL=http://127.0.0.1:7861
```

Worker environment:

```text
AI_DRAMA_QWEN3_TTS_VOICE_DESIGN_MODEL_PATH=<local Qwen3-TTS-12Hz-1.7B-VoiceDesign directory>
AI_DRAMA_QWEN3_TTS_BASE_MODEL_PATH=<local Qwen3-TTS-12Hz-1.7B-Base directory>
AI_DRAMA_QWEN3_TTS_DEVICE=cuda:0
AI_DRAMA_QWEN3_TTS_DTYPE=bfloat16
AI_DRAMA_QWEN3_TTS_ATTN=flash_attention_2
AI_DRAMA_QWEN3_TTS_HOST=127.0.0.1
AI_DRAMA_QWEN3_TTS_PORT=7861
```

Qwen3-TTS should run in an isolated Python environment instead of being installed into the main Studio/H3 environment.

Current project-language dropdown is within the worker V1 language set:

```text
Chinese
English
Japanese
Korean
Spanish
Portuguese
French
German
```

Runtime helpers also support Russian and Italian.

Unsupported target language is an infrastructure/runtime capability state, not a human content ReviewIssue.

## 8. Real speech duration

Generated dialogue audio is PCM WAV. R5 reads the real frame count/sample rate and stores:

```text
speech_duration_us
```

Example:

```text
source speaking interval = 1.20s
target Qwen3-TTS WAV      = 1.57s
```

R5 only records the fact. R6 decides how to adapt the remake timeline.

## 9. Item-local progress

One uncertain line must not block all READY lines.

Product coordinator:

```text
engine/app/target_dialogue_pipeline_v1.py
```

Behavior:

```text
translate/localize all possible lines
→ create ReviewIssue only for unsafe items
→ still synthesize every READY line
```

## 10. Freshness

R5 is anchored to:

```text
SourceDramaSnapshot.source_fingerprint
source_dialogue_signature
TargetCharacter definition
TargetVoiceProfile.target_character_signature
voice_fingerprint
audio_input_signature
```

If source facts change, source anchors become stale.

If TargetCharacter changes:

```text
AI target lines -> regenerate automatically
manual target lines -> reopen for LOCALIZATION review
old voice reference -> invalidate/regenerate
old dialogue WAV -> invalidate/regenerate
```

The GET/audio APIs fail closed when persisted target dialogue depends on an older TargetCharacter definition.

## 11. APIs

```text
GET  /api/tts/runtime-status

POST /api/projects/{project_id}/target-dialogue/generate
POST /api/projects/{project_id}/target-dialogue/generate-text
POST /api/projects/{project_id}/target-dialogue/materialize-audio
GET  /api/projects/{project_id}/target-dialogue

PATCH /api/target-dialogues/{target_dialogue_id}
GET   /api/target-dialogues/{target_dialogue_id}/audio
```

## 12. One-click pipeline

`AUTO_REMAKE_PREP_V1` now continues through R5:

```text
SourceDramaSnapshot
→ TargetCharacter / SceneLocalizationMapping
→ TargetDialogue text
→ READY-line Qwen3-TTS materialization when worker is ready
```

TTS worker absence does not erase or fail completed target text. Audio remains pending/not configured.

## 13. Tests

Run locally:

```text
python -m pytest engine/tests/v2/test_target_dialogue_v1.py -q
python -m pytest engine/tests/v2/test_target_dialogue_routes_v1.py -q
python -m pytest engine/tests/v2/test_qwen3_tts_runtime_v1.py -q
```

Also rerun upstream contracts:

```text
python -m pytest engine/tests/v2/test_remake_foundation_v1.py -q
python -m pytest engine/tests/v2/test_source_drama_snapshot_v1.py -q
python -m pytest engine/tests/v2/test_target_localization_v1.py -q
```

Frontend:

```text
cd frontend
npm run typecheck
npm run build
```

Then run a real Project through `AUTO_REMAKE_PREP_V1` and verify:

```text
TargetDialogue count matches current source dialogue count
high-confidence lines do not create LOCALIZATION issues
manual edits invalidate old audio
same TargetCharacter reuses one TargetVoiceProfile
READY WAV files exist
speech_duration_us matches real WAV duration
```

Do not mark R5 FINAL PASS until local Windows/CUDA/model acceptance is completed.

## 14. R6 handoff

R6 must consume only current READY R5 facts:

```text
TargetDialogue.final_text
TargetDialogue.audio_path
TargetDialogue.speech_duration_us
TargetDialogue.target_character_id
source_start_us / source_end_us
Shot/Reference Video from SourceDramaSnapshot
```

R6 owns:

```text
KEEP
REWRITE_SHORTER
TRIM
CARRY_OVER_REACTION
EXTEND
REGENERATE_EXTENSION
HUMAN_REVIEW
```
