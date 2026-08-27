# Session Handoff — Character Evidence vs Final Binding Compare

> Date: 2026-08-27 15:00 +08:00  
> Branch: `main`  
> Scope: 03 资产 / Character V10.1 diagnostic visualization

## User-visible problem

The Character Gallery and the Asset library appeared inconsistent:

- Character Gallery showed many isolated person crops and repeated Shot labels;
- Asset library showed one whole-Shot thumbnail per Final binding;
- it was visually unclear whether a Shot was truly missing from AI identity evidence or merely omitted from the bounded Gallery representative subset.

This ambiguity also made remaining Shot binding misses harder to diagnose.

## Architecture decision

Keep three layers separate:

```text
CharacterTrack Shot membership
= exhaustive immutable AI identity evidence

V10 Gallery
= bounded/diversified strong identity representative subset

ShotCharacterBinding
= editable Final binding
```

A Shot omitted from the bounded Gallery must never be interpreted as “AI did not identify this Character in the Shot”.

## Implemented backend

### `engine/app/character_gallery_routes_v10.py`

Now `GET /api/content-analysis/characters/{candidate_id}/gallery` exposes:

```text
evidence_shot_count
evidence_shots[]
gallery_image_count
image_count
images[]
```

`evidence_shots[]` is derived from all persisted `CharacterTrack` rows for the Candidate and contains:

```text
shot_id
shot_ordinal
episode_id
episode_order
track_count
sample_count
recovered_track_count
recovery_sources
```

The `images[]` visual layer covers every Evidence Shot:

- true bounded Gallery crops use `source_kind = gallery`;
- if an Evidence Shot was omitted from the bounded Gallery, one persisted Track representative crop is exposed with `source_kind = track_representative`.

On-demand crop route:

```text
GET /api/content-analysis/characters/{candidate_id}/evidence-shot/{shot_id}
```

It uses persisted `representative_source_us`, `bbox_json`, Shot start time and Reference Clip. It does not reclassify identity or mutate Evidence.

Relevant commits:

```text
3e85e2533e5ba7d48cc3cd2a09a5baf5971e88a7  api: expose exhaustive Character evidence Shots
8787b662d4987d35acfd914e6b4135a06852de92  api: provide per-Shot Character evidence crops
```

## Implemented frontend

### Shared API/types

`frontend/src/api/client.ts`
- added `getCharacterGallery(candidateId)`.

`frontend/src/types/studio.ts`
- added Character Gallery image/payload/evidence-Shot types;
- added `source_kind` and exhaustive evidence-Shot metadata.

Relevant commits:

```text
25ce3c030200df9fb9923f235fbbf8ec92536158  types: add Character Gallery comparison payload
61b9e0c1a84955b74610a7ead4969462fd69209f  api: expose Character Gallery reads
aa5620d79e6970a17466eb51a113437f6d781106  types: distinguish Gallery crops from evidence Shots
ff5e89c8b0b55c33120380875c055ce6eebc4a92  types: mark Gallery versus Track evidence crops
```

### Character Gallery

`frontend/src/components/CharacterPersonGalleryV10.vue`

Current UI:

```text
人物001
N Evidence Shots · M Gallery 代表图 · K 张可视证据图

SHOT xxxx
[Gallery crop] [Gallery crop] [Track 代表图 if needed]
```

The view loads every `source_candidate_id` for a Final Character, not only the first Candidate.

Relevant commits:

```text
21b62b1deeec0144ae9d5e2b4c24d26051bbf456  ui: group Character Gallery evidence by Shot
bbb7c9d901218d420bd8f8c847c41817099a2ba2  ui: make Character Evidence Shot coverage explicit
```

### Asset library comparison

`frontend/src/components/AssetReviewMatrixV4.vue`

Character asset detail now displays:

```text
Final Binding Shots
Evidence Shots
人物 crop
不一致 Shots
```

Each Shot card shows:

```text
top: whole-Shot thumbnail / context
bottom: Person Evidence crop(s)
status:
  Evidence + Final
  AI ONLY
  FINAL ONLY
```

`AI ONLY` is the direct signal for likely binding recall misses.

Merged Characters load all `source_candidate_ids`.

Style is in `frontend/src/asset-review-matrix-v4.css`.

Relevant commits:

```text
815b4ab5deb6cef97f995a247a6996aba598b69d  ui: compare Character Evidence and Final Shot bindings
a69fc0b31d8f6a6b1fbbf00f69ef1c61a9a2bb4d  style: distinguish Character Evidence from Final bindings
```

## Regression test

Added:

```text
engine/tests/v2/test_character_gallery_routes_v10.py
```

The test intentionally seeds:

```text
3 persisted CharacterTrack Evidence Shots
1 bounded Gallery manifest Shot
```

and asserts:

```text
evidence_shot_count == 3
gallery_image_count == 1
visual images cover all 3 Shots
Gallery Shot uses source_kind=gallery
omitted Shots use source_kind=track_representative
recovery source summary survives
```

Commit:

```text
bfed1b1d69559a282d877b08b126bcabd91f9e69  test: distinguish exhaustive evidence Shots from Gallery subset
```

## CI reality

Latest checked backend run after the test:

```text
28 failed, 179 passed, 1 skipped
```

The new Gallery/Evidence route test is not among failures. `Compile V2 backend` and `Import FastAPI app` pass.

Existing failures remain the known repository-wide categories:

```text
cv2 absent in lightweight CI
trackers absent in lightweight CI
FFmpeg absent / media assumptions
obsolete V6-era assertions / semantics
```

Frontend still fails before project type checking in the existing `vue-tsc` / TypeScript incompatibility:

```text
Package subpath './lib/tsc' is not defined by "exports" in typescript/package.json
```

Do not claim whole CI is green.

## Documents synchronized

```text
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/ASSET_CHARACTER_RECOGNITION_V10_1.md
this handoff
```

## Immediate next local validation

```text
1. git pull
2. restart backend + frontend
3. open Character Gallery; verify Evidence Shots vs Gallery representative counts
4. open 03资产 → 资产库 → 人物
5. verify each compare card has whole-Shot context on top and Person crop below
6. inspect AI ONLY cards first — these are likely missing Final Shot bindings
7. inspect FINAL ONLY cards separately — manual/stale/no-Track cases
8. use this diagnostic view to recheck SHOT 0002 / 0004 / 0006 / 0007 / 0009
9. do not lower identity thresholds based only on bounded Gallery counts
```

## Important invariants

```text
Evidence != Final Asset
bounded Gallery != exhaustive Evidence Shot set
Shot thumbnail != Person crop
AI ONLY does not auto-write Final binding
manual Final revisions remain protected
old Analysis Runs remain immutable
```
