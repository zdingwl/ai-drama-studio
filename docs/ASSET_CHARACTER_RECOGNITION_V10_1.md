# Character V10.1 — Capture-first Identity + Two-pass Shot Presence Recovery

> **Status:** IMPLEMENTED / NEEDS WINDOWS REAL-VIDEO + UI REGRESSION  
> **Formal runtime profile:** `character-v10.1-capture-first-model-classification`  
> **Formal asset profile:** `f05-assets-v10.1-person-evidence-model-classification`  
> **Formal resolver:** `person-evidence-model-classifier-v10.1`  
> **Last synchronized:** 2026-08-27 14:59 +08:00

## 1. Why V10.1 exists

V10 moved Character extraction away from detection/Track cardinality and toward capture-first Person Evidence + project-level identity classification.

V10.1 adds three corrections:

1. strong risky views may propose a new identity only under stricter multi-Shot confirmation;
2. one unresolved Track with repeated support may attach to an already-confirmed identity;
3. several short unresolved fragments / close-up Face evidence inside one Shot may recover presence of an already-confirmed identity.

Real material showed the key failure mode:

```text
Global Character classes are correct
but some Shot rows still miss a visible known Character
```

Observed priority rows included `SHOT 0002 / 0004 / 0006 / 0007 / 0009`. Later reruns improved `0006/0007`; the remaining close-up/two-person cases continue to guide local validation.

## 2. Formal pipeline

```text
Shot / Reference Clip
↓
YOLOX Person Detection + safe YuNet Face fallback
↓
one detected person → one isolated Person Instance
↓
YoutuReID
+ clothing_upper / clothing_lower
+ body_hist / body_structure
+ optional SFace
↓
persist model-usable Person Evidence
↓
Mature MOT
↓
resolve_global_identities(tracks)
↓
RESOLVED identities + UNRESOLVED evidence
↓
recover_unresolved_tracks(candidates)
  Pass 1
↓
recover_fragmented_shot_presence(candidates)
  Pass 2
↓
write identity assignment back to Person Evidence
↓
persist CharacterCandidate / CharacterTrack / classified Gallery
↓
V10/V10.1 Final Gate
↓
Character + ShotCharacterBinding
↓
Asset Workspace V10.1 adapter
```

## 3. Capture-first identity contract

Image condition is evidence metadata, not Character cardinality.

```text
CLEAN
OCCLUDED
CONTAMINATED
PARTIAL
```

YoutuReID remains the primary identity model channel. Clothing/body support remains separate and explainable. Face is optional support and a high-quality conflict signal.

A formal new identity requires:

```text
>=3 independent Shots
>=3 model-usable Person Images
stable cross-Shot Person-ReID support
unique identity class
same-sample cannot-link preserved
no high-quality Face hard conflict
```

Weak/tiny partial evidence cannot manufacture a Character.

## 4. Pass 1 — repeated unresolved Track → known identity

Formal module:

```text
engine/app/character_shot_binding_v101.py
```

Source:

```text
V10_1_TRACK_KNOWN_IDENTITY_RECOVERY
```

Current guardrails:

```text
MIN_TRACK_OBSERVATIONS = 3
MIN_SUPPORTING_OBSERVATIONS = 2
NORMAL_TRACK_MEDIAN = 0.74
RISKY_TRACK_MEDIAN = 0.79
STRONG_TRACK_MEDIAN = 0.84
WINNER_MARGIN >= 0.07
```

Rules:

- compare repeated usable observations against all already-RESOLVED identity galleries;
- aggregate support across independent gallery Shots;
- require one unique winner;
- same-sample cannot-link hard rejects;
- high-quality Face conflict hard rejects;
- attach the whole Track only to an existing identity;
- never create a new Character.

## 5. Pass 2 — fragmented same-Shot known presence

Formal module:

```text
engine/app/character_shot_presence_v101.py
```

Source:

```text
V10_1_SHOT_FRAGMENT_AGGREGATION
```

### 5.1 Body/side/back path

```text
REID_STRONG = 0.84
REID_SUPPORTED = 0.74
RISKY_REID_SUPPORTED = 0.80
RISKY_APPEARANCE_CHANNELS = 2
MIN_SHOT_SUPPORT_OBSERVATIONS = 3
MIN_SHOT_SUPPORT_TIMESTAMPS = 3
MIN_SHOT_MEDIAN = 0.76
WINNER_MARGIN = 0.075
```

Several short fragments may jointly prove one already-known Character is present. One weak fragment cannot be promoted just to fill a binding.

### 5.2 Known-Face close-up path

After real-video regression the known-Face presence logic is:

```text
FACE_SUPPORTED = 0.40
FACE_STRONG = 0.50
FACE_PAIR_MIN_SCORE = 0.76
```

Moderate Face support requires:

```text
>=2 supported observations in the current Shot
>=2 distinct current-Shot timestamps
positive support from >=2 independent confirmed Gallery Shots
unique Character winner
```

One truly strong Face observation may still confirm **presence of an already-confirmed Character**.

Face-supported identities rank before synthetic-body ReID for face-fallback close-ups. A hard Face veto now requires consistent conflict across >=2 Gallery Shots with no positive Face support; one bad Gallery Face crop is not allowed to veto an otherwise stable identity.

This never makes Face mandatory and never creates a new identity.

## 6. Cannot-link / conflict invariants

Both recovery passes preserve:

```text
same sampling time + spatially distinct people
→ cannot share one identity through recovery

high-quality repeated Face conflict
→ fail closed

ambiguous winner
→ stay unresolved
```

These constraints are especially important for multi-person Shots such as `0004/0009`.

## 7. Recovery provenance and persistence

Every recovered Track receives exact provenance before persistence.

```text
CharacterTrack.evidence_json.identity_recovery
```

Pass 1 records source / target / Shot / score / observation count / policy.

Pass 2 may additionally record:

```text
support_count
face_support_count
strong_face_support
```

Candidate summaries retain `track_recovery_*` and fragment-recovery summary metadata.

## 8. Identity confidence vs Shot-presence confidence

```text
CharacterCandidate.confidence
= project-level identity class confidence

Track recovery score
= confidence this already-known Character is present in this Shot
```

Final rule:

```text
normal/direct identity-assigned Track exists in Shot
→ ShotCharacterBinding.confidence uses candidate identity confidence fallback

Shot contains only recovered Track fragments
→ ShotCharacterBinding.confidence uses strongest validated recovery score
```

Multiple fragments for one Character in one Shot still create exactly one Final binding.

## 9. Final Gate

Formal V10/V10.1 materialization is fail-closed:

```text
identity_status == RESOLVED
resolver in formal allow-list
confirmed_gallery_shots >= 3
confirmed_gallery_images >= 3
final_asset_eligible is not false
```

Face visibility is not required.

Formal entry:

```text
engine/app/asset_final_gate_v10.py
```

## 10. Asset Workspace evidence semantics

Formal workspace responses use:

```text
engine/app/asset_workspace_character_v101.py
```

Contract:

```text
evidence_by_shot[shot_id].characters
= RESOLVED Character evidence only

evidence_by_shot[shot_id].character_diagnostics
= UNRESOLVED diagnostics only
```

UNRESOLVED diagnostics have no Final asset id and do not contaminate the main Character suggestion.

## 11. Critical distinction: exhaustive AI Evidence != bounded Gallery != Final Binding

The latest UI review exposed an important architecture point.

### 11.1 CharacterTrack Shot membership is exhaustive AI identity evidence

Every persisted `CharacterTrack` attached to a RESOLVED Candidate is immutable AI evidence that this Candidate was classified into that Shot.

This is the authoritative Candidate evidence-Shot set.

### 11.2 V10 Gallery is deliberately a representative subset

`character_gallery_v10.select_candidate_gallery()` applies diversity and capacity limits. The Gallery is designed to represent identity well, not enumerate every Shot.

Therefore this is invalid:

```text
Shot not selected into Gallery
⇒ AI did not identify this person in the Shot
```

That inference is now explicitly forbidden.

### 11.3 Final ShotCharacterBinding is a separate editable layer

Final binding may differ from immutable AI evidence because:

- automatic materialization can miss presence;
- a user can manually add/remove bindings;
- a MANUAL/RESTORE Revision may intentionally differ from a newer analysis;
- old Runs remain immutable.

## 12. Character Evidence read API

Formal route:

```text
engine/app/character_gallery_routes_v10.py
```

Endpoint:

```text
GET /api/content-analysis/characters/{candidate_id}/gallery
```

Response separates:

```text
evidence_shot_count
= exhaustive persisted CharacterTrack Shot count

evidence_shots[]
= every Candidate Track Shot
  + real shot_ordinal / episode context
  + track_count / sample_count
  + recovered_track_count / recovery_sources

gallery_image_count
= true bounded Gallery representative image count

images[]
= visual evidence that covers every evidence Shot
```

For a Shot that has CharacterTrack evidence but no bounded Gallery image, the API adds one actual persisted Track representative crop with:

```text
source_kind = track_representative
```

True Gallery crops use:

```text
source_kind = gallery
```

The fallback crop endpoint is:

```text
GET /api/content-analysis/characters/{candidate_id}/evidence-shot/{shot_id}
```

It uses persisted:

```text
CharacterTrack.representative_source_us
CharacterTrack.bbox_json
Shot.reference_clip_path
Shot.start_us
```

to decode the Reference Clip and return the real person crop. It does not re-run identity classification and does not mutate Evidence.

## 13. Evidence-vs-Final diagnostic UI

### Character Gallery

`frontend/src/components/CharacterPersonGalleryV10.vue` now groups by real Shot and shows:

```text
N Evidence Shots
M Gallery 代表图
K 可视证据图
```

`Track 代表图` means AI evidence exists but that Shot was omitted from the bounded identity Gallery subset.

### Asset library

`frontend/src/components/AssetReviewMatrixV4.vue` shows, for each Character:

```text
Final Binding Shots
Evidence Shots
人物 crop
不一致 Shots
```

Every Shot comparison card contains:

```text
Shot whole-frame thumbnail
Person Evidence crop(s)
status
```

Statuses are formal diagnostics:

```text
Evidence + Final
= CharacterTrack evidence exists + Final binding exists

AI ONLY
= CharacterTrack evidence exists + Final binding missing
= likely Shot-binding recall defect

FINAL ONLY
= Final binding exists + no CharacterTrack evidence from this Final asset's source Candidate(s)
= manual/stale/special review case
```

Merged Final Characters load all `source_candidate_ids`; the UI never assumes only the first Candidate represents the Final asset.

This comparison is diagnostic only. It does not automatically rewrite Final bindings.

## 14. Character Gallery Shot labels

Human-facing Shot labels always resolve immutable `shot_id` through real `v2_shots.ordinal`. UUID suffixes are never Shot numbers.

## 15. Formal code map

```text
engine/app/character_visual_v2.py
engine/app/character_runtime_v6.py
engine/app/character_observation_v10.py
engine/app/character_person_evidence_v10.py
engine/app/character_person_features_v9.py
engine/app/character_tracking_v10.py
engine/app/character_identity_v101.py
engine/app/character_shot_binding_v101.py
engine/app/character_shot_presence_v101.py
engine/app/character_persistence_v6.py
engine/app/character_gallery_v10.py
engine/app/character_gallery_routes_v10.py
engine/app/character_evidence_store_v10.py
engine/app/asset_final_gate_v10.py
engine/app/asset_final_gate_v9.py
engine/app/asset_workspace_character_v101.py
engine/app/asset_routes_v3.py
frontend/src/api/client.ts
frontend/src/types/studio.ts
frontend/src/components/CharacterPersonGalleryV10.vue
frontend/src/components/AssetReviewMatrixV4.vue
frontend/src/asset-review-matrix-v4.css
```

## 16. Required regression cases

At minimum keep these contracts locked:

```text
1. multi-person frame → independent Person Instances
2. same-sample different people → cannot-link
3. weak partial evidence → cannot create Character
4. strong risky views across >=3 Shots → may form one identity
5. Face absent → confirmed identity may pass Final Gate
6. high-quality Face conflict → never merge
7. repeated unresolved Track → Pass-1 known identity recovery
8. Pass-1 recovery persists exact provenance
9. ambiguous/cannot-link Track → no recovery
10. several singleton fragments → Pass-2 may recover known presence
11. repeated moderate known-Face support → may recover
12. single moderate Face → remains unresolved
13. Face-supported known identity outranks synthetic-body ReID in close-up fallback
14. recovery never creates a Character
15. recovered-only Final binding uses Shot-presence confidence
16. UNRESOLVED → character_diagnostics only
17. real Gallery Shot labels use v2_shots.ordinal
18. Gallery representative subset cannot define exhaustive Evidence Shot cardinality
19. exhaustive Evidence API includes CharacterTrack Shots omitted from bounded Gallery
20. missing Gallery Shot receives a real persisted Track representative crop URL
21. recovered Track summary exposes recovery source in evidence_shots
22. Final Gate still requires formal resolver + >=3 confirmed Shots/images
```

Current focused test for the new distinction:

```text
engine/tests/v2/test_character_gallery_routes_v10.py
```

It seeds three CharacterTrack evidence Shots while the bounded Gallery manifest contains only one Shot, then verifies the API reports all three Evidence Shots and supplies Track-representative visual crops for the two Gallery-omitted Shots.

## 17. Validation status

Latest repository CI after the Evidence-vs-Final work:

```text
28 failed, 179 passed, 1 skipped
```

The new Gallery/Evidence route test is not among failures. Backend compile and FastAPI import pass. Existing failures remain known legacy/runtime/environment categories such as missing `cv2`, missing `trackers`, FFmpeg assumptions and obsolete V6-era assertions.

Frontend CI remains blocked before project type checking by the existing `vue-tsc` / TypeScript package incompatibility (`typescript` does not export `./lib/tsc`).

Do not mark Character V10.1 `STABLE/FROZEN` until the user accepts the real Windows result.

## 18. Local acceptance procedure

```text
1. git pull latest main
2. restart backend/frontend
3. open Character Gallery and verify Shot grouping / counts
4. open 03资产 → 资产库 → 人物
5. verify whole-Shot context and Person crop are visually distinct
6. use AI ONLY rows to locate binding misses
7. use FINAL ONLY rows to locate manual/stale/no-track cases
8. do not interpret bounded Gallery count as exhaustive Shot evidence
9. rerun asset extraction when validating new binding logic; old Runs do not auto-rebind
10. recheck SHOT 0002 / 0004 / 0006 / 0007 / 0009 on the real sample
```
