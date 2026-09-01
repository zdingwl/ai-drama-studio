# SourceDramaSnapshot V1

Status: **IMPLEMENTED ON MAIN / LOCAL TEST ACCEPTANCE PENDING**  
Date: 2026-09-01

## Purpose

`SourceDramaSnapshot` is the single product-facing read model for everything the system has safely understood about the source drama and needs for localized remake.

Downstream remake modules must consume this contract instead of directly depending on G2/P5/P6/P7 names.

```text
accepted internal source truth
  Scene Timeline
  Character bridge / Final Character
  Final Scene / Prop bindings
  ShotRevision / Reference Video
        ↓
SourceDramaSnapshot V1
        ↓
TargetCharacter
SceneLocalizationMapping
TargetDialogue
Dialogue Timing Engine
RemakeTimeline
H3 ContextCompiler
GenerationSegment
```

## Important boundary

`SourceDramaSnapshot` is a deterministic **current read snapshot**, not a new duplicate source-of-truth database.

It does not rewrite or own:

- Shot;
- ShotRevision;
- Breakdown facts;
- Final Character / Scene / Prop;
- source ASR dialogue;
- source OCR text.

It composes the current safe versions and exposes one stable contract.

Downstream persisted models must store the `source_fingerprint`. If source facts, ShotRevision, BreakdownRun or Final Asset projection changes, the current fingerprint changes and downstream work can be marked stale/rebuilt.

## No target-side data

The Contract uses `extra="forbid"` and intentionally does **not** contain:

- target language copy;
- localized dialogue;
- target character;
- target scene;
- TTS audio;
- target duration;
- timing strategy;
- H3 prompt/output.

Those belong to downstream remake models.

## Episode snapshot

Endpoint:

```text
GET /api/episodes/{episode_id}/source-drama-snapshot
```

Schema:

```text
source-drama-snapshot-v1
```

Top-level anchors:

```text
project_id
episode_id
episode_title
episode_order
source_language
source_breakdown_run_id
source_shot_revision_id
source_asset_revision_id
source_fingerprint
```

Main hierarchy:

```text
Episode
└─ Scene
   ├─ scene_key
   ├─ source timing
   ├─ title / story summary / environment
   ├─ Final Scene when safely available
   ├─ Scene-local people
   │  ├─ person_key
   │  ├─ P* ref
   │  ├─ appearance
   │  └─ Final Character when safely resolved
   └─ Shot
      ├─ shot_key
      ├─ current source Shot id when available
      ├─ ShotRevisionItem id
      ├─ source timing
      ├─ thumbnail
      ├─ Reference Video
      ├─ visual description
      ├─ people
      ├─ action / performance
      ├─ source dialogue + speaker person keys
      ├─ observed props
      ├─ Final Props
      ├─ cinematography
      └─ source OCR text
```

## Stable keys

Keys are intentionally anchored to current immutable source versions.

```text
scene_key
= episode_id + BreakdownRun + Scene ordinal

shot_key
= episode_id + ShotRevision + Shot ordinal

person_key
= scene_key + Scene-local P* ref

dialogue_key
= shot_key + dialogue ordinal

text_key
= shot_key + OCR ordinal
```

When a relevant upstream source version changes, keys/fingerprint change rather than silently pretending the old downstream plan still matches.

## Project snapshot

Endpoint:

```text
GET /api/projects/{project_id}/source-drama-snapshot
```

Schema:

```text
source-drama-project-snapshot-v1
```

The Project snapshot aggregates Episodes in project order and exposes a deduplicated catalog of safely resolved source Characters.

```text
Project
├─ source_fingerprint
├─ characters[]
└─ episodes[]
```

The project endpoint fails closed when any Episode does not yet have a current consumable source snapshot. It does not silently return a half-project and let later generation proceed with missing Episodes.

## Status and warnings

Possible status:

```text
READY
READY_WITH_WARNINGS
```

Examples of warnings:

- Scene-local person not safely resolved to Final Character;
- missing ShotRevisionItem mapping;
- missing Reference Video;
- current underlying P6 identity/asset warning.

Warnings do not rewrite source truth.

## Human review integration

`AUTO_REMAKE_PREP_V1` now finishes by composing the project SourceDramaSnapshot.

After composition it checks dialogue speaker usability:

```text
source dialogue with no safe speaker
or one ASR segment associated with multiple speakers
→ ReviewIssue(type=SPEAKER)
```

Normal dialogue produces no page or user task.

Current source-understanding ReviewIssue producers therefore include:

```text
SHOT_BOUNDARY
CHARACTER_IDENTITY
ASSET_BINDING
SPEAKER
```

## Implementation

```text
engine/app/source_drama_snapshot_contract_v1.py
engine/app/source_drama_snapshot_v1.py
engine/app/source_drama_snapshot_routes_v1.py
engine/app/source_drama_review_issue_sync_v1.py
```

Integrated into:

```text
engine/app/auto_remake_prepare_v1.py
engine/app/main.py
```

Tests added:

```text
engine/tests/v2/test_source_drama_snapshot_v1.py
engine/tests/v2/test_source_drama_snapshot_routes_v1.py
```

## Acceptance boundary

Code is implemented on `main`, but do not call it FINAL PASS until local project tests are run in the actual Windows environment.

Minimum local checks:

```text
python -m pytest engine/tests/v2/test_source_drama_snapshot_v1.py -q
python -m pytest engine/tests/v2/test_source_drama_snapshot_routes_v1.py -q
python -m pytest engine/tests/v2/test_remake_foundation_v1.py -q
```

Then run one real Episode/Project through `AUTO_REMAKE_PREP_V1` and inspect:

```text
GET /api/projects/{project_id}/source-drama-snapshot
```

Required real acceptance:

- every expected Episode present;
- every source Shot has correct timing;
- Reference Video opens and matches Shot;
- resolved source Characters are correct;
- unresolved people remain unresolved instead of false identity;
- source dialogue text is unchanged;
- speaker links are reasonable or create `SPEAKER` ReviewIssue;
- Scene / Prop final overlays only appear when current bindings support them;
- repeated read without upstream changes produces the same fingerprint.
