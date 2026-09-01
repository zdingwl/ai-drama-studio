# Target Localization V1

Status: **IMPLEMENTED ON MAIN / LOCAL TEST + REAL PROJECT ACCEPTANCE PENDING**  
Date: 2026-09-01

## Purpose

R4 converts the current `SourceDramaSnapshot` into target-side character and scene decisions for the Project target language/region.

```text
SourceDramaSnapshot
+ ProjectRemakePolicy
        ↓
TargetCharacter
+ SceneLocalizationMapping
        ↓
future TargetDialogue / TTS / RemakeTimeline / H3 ContextCompiler
```

This is target-side data only. It never edits source Character, Scene, Shot, ASR, OCR or SourceDramaSnapshot truth.

## Product behavior

There is no separate Target Character page or Scene Localization page.

The normal flow remains:

```text
Project
→ automatic processing
→ Review Center only for uncertain target people/scenes
→ Output
```

High-confidence target plans are accepted automatically.

## Persistence

### TargetCharacter

Table:

```text
v2_target_characters
```

Identity:

```text
(project_id, source_character_id) = one target character
```

Important fields:

```text
source_character_id
source_character_signature
source_fingerprint
target_language
target_region
target_name
appearance_profile
generation_prompt
confidence
status = READY | REVIEW
decision_source = AI | MANUAL
reference_assets
```

Characters are always localized/replaced. The source character only supplies narrative role and stable appearance context. The target character must be a new target-region person, not a copy of the original actor identity/face.

A manual target-character decision is preserved across automatic reruns while the local source-character signature remains unchanged. If the source character facts change, the row becomes `REVIEW` instead of being silently reused.

## Scene localization consistency

Table:

```text
v2_scene_localization_mappings
```

The mapping is project-global when a safe Final Scene exists.

```text
Final Scene SCENE_123
appears in Episode 1 Scene 2
appears in Episode 3 Scene 1
appears in Episode 8 Scene 4
        ↓
one canonical key:
ASSET:SCENE_123
        ↓
one KEEP / LOCALIZE decision
        ↓
one target scene design
```

This prevents the same home/office/hospital from becoming visually different between episodes.

When no Final Scene exists, the anonymous SourceDramaSnapshot `scene_key` is used and the mapping remains occurrence-local.

Fields include:

```text
scene_key
source_scene_id
source_scene_signature
source_fingerprint
project_policy = AUTO | KEEP | LOCALIZE
decision = KEEP | LOCALIZE | REVIEW
decision_source = PROJECT_POLICY | AI | MANUAL
target_label
target_description
confidence
status
```

## Scene policy rules

### KEEP

```text
all source scenes -> KEEP
```

No AI call is required merely to decide whether to replace a scene.

### LOCALIZE

```text
all source scenes -> LOCALIZE
```

The system still needs a usable target scene description. If the local model cannot produce one safely, the mapping enters Review Center rather than inventing a scene.

### AUTO

Default decision guidance:

```text
generic bedroom / living room / office / hotel with no regional conflict -> prefer KEEP
obvious source-region signage / currency / institutional design / architecture / commercial branding / school / hospital / police context -> consider LOCALIZE
uncertain -> REVIEW
```

`AUTO_CONFIDENCE_MIN = 0.72` in V1.

## Local model reuse

R4 does not introduce another model server.

It reuses the configured local Qwen3-VL OpenAI-compatible service:

```text
AI_DRAMA_VLM_BASE_URL
AI_DRAMA_VLM_MODEL
AI_DRAMA_VLM_API_KEY
```

The model receives SourceDramaSnapshot-derived text context only for R4 planning.

If the model is unavailable:

- KEEP scene policy still resolves scenes automatically;
- TargetCharacter becomes `REVIEW`;
- AUTO/LOCALIZE scenes that cannot be safely completed become `REVIEW`.

## ReviewIssue

New issue types:

```text
TARGET_CHARACTER
SCENE_LOCALIZATION
```

`TARGET_CHARACTER` is blocking because H3 cannot maintain a stable replacement person without a target identity design.

`SCENE_LOCALIZATION` is review-level until later generation planning determines it blocks a required localized scene.

The Review Center edits the actual `TargetCharacter` / `SceneLocalizationMapping` row. ReviewIssue itself remains attention state only.

The user can:

- edit and confirm a target character;
- choose KEEP or LOCALIZE for an uncertain scene;
- edit target scene label/description;
- delete a proposal and regenerate it.

## Freshness / stale protection

Every row records the project SourceDramaSnapshot `source_fingerprint`.

The bundle rejects rows whose fingerprint no longer matches the current source snapshot.

It also rejects:

- target characters for the wrong target language/region;
- scene mappings generated under an old Project scene policy;
- target-character local signatures that no longer match the current source Character context;
- scene local signatures that no longer match the current canonical source Scene context.

This prevents old target plans from silently continuing after source edits.

## APIs

```text
POST   /api/projects/{project_id}/target-localization/generate
GET    /api/projects/{project_id}/target-localization
PATCH  /api/target-characters/{target_character_id}
DELETE /api/target-characters/{target_character_id}
PATCH  /api/scene-localization-mappings/{mapping_id}
DELETE /api/scene-localization-mappings/{mapping_id}
```

## Automatic task integration

`AUTO_REMAKE_PREP_V1` now ends with:

```text
SourceDramaSnapshot
→ Speaker ReviewIssue sync
→ TargetCharacter / SceneLocalizationMapping generation
→ Target localization ReviewIssue sync
```

The task result includes target-character, scene-mapping and review counts.

## Main implementation

```text
engine/app/target_localization_contract_v1.py
engine/app/target_localization_v1.py
engine/app/target_localization_routes_v1.py
frontend/src/components/TargetLocalizationReviewV1.vue
frontend/src/api/remake.ts
frontend/src/types/remake.ts
frontend/src/views/ProjectStudioV4.vue
```

Tests:

```text
engine/tests/v2/test_target_localization_v1.py
```

## Local acceptance

Minimum non-GPU checks:

```text
python -m pytest engine/tests/v2/test_target_localization_v1.py -q
python -m pytest engine/tests/v2/test_source_drama_snapshot_v1.py -q
python -m pytest engine/tests/v2/test_source_drama_snapshot_routes_v1.py -q
python -m pytest engine/tests/v2/test_source_drama_review_issue_sync_v1.py -q
python -m pytest engine/tests/v2/test_remake_foundation_v1.py -q

cd frontend
npm run typecheck
npm run build
```

Then run a real project through the automatic flow and verify:

1. every resolved source Character has exactly one TargetCharacter;
2. repeated occurrences of the same Final Scene have one canonical mapping;
3. KEEP/AUTO/LOCALIZE behave according to Project policy;
4. only uncertain target rows appear in Review Center;
5. manual changes survive ordinary reruns while local source signatures are unchanged;
6. source/policy changes make stale target plans fail closed.

Do not mark R4 FINAL PASS until local execution and a real Project are checked.
