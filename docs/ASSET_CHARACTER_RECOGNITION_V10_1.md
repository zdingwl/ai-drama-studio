# Character V10.1 — Capture-first Identity + Two-pass Shot Presence Recovery

> **Status:** IMPLEMENTED / NEEDS WINDOWS REAL-VIDEO REGRESSION  
> **Formal runtime profile:** `character-v10.1-capture-first-model-classification`  
> **Formal asset profile:** `f05-assets-v10.1-person-evidence-model-classification`  
> **Formal resolver:** `person-evidence-model-classifier-v10.1`  
> **Last synchronized:** 2026-08-27 13:38 +08:00

## 1. Why V10.1 exists

V10 solved the structural error of treating detections/Tracks as Character assets by moving to capture-first Person Evidence and project-level model classification.

V10.1 now contains three corrections:

1. **Risky-view identity creation** — strong `CONTAMINATED` / substantial `PARTIAL` Person crops may propose a new identity only under strict cross-Shot confirmation.
2. **Pass-1 known-identity Track recovery** — one unresolved Track with repeated observations may attach to an already-confirmed identity.
3. **Pass-2 fragmented Shot-presence recovery** — several short unresolved Track fragments inside the same Shot may be aggregated to recover presence of an already-confirmed Character.

The third correction was added after real-video regression showed this exact pattern:

```text
Global Character classes are correct
but Shot rows still miss visible known people
```

Observed regression rows included:

```text
SHOT 0002  young woman visible → unbound
SHOT 0004  old + young visible → only old woman bound
SHOT 0006  old woman close-up → unbound
SHOT 0007  young woman partial/body view → unbound
SHOT 0009  two-person view → second known person may be missing
```

This is a Shot-presence recall problem, not evidence that the global identity classes should be loosened.

## 2. Formal pipeline

```text
Shot / Reference Clip
↓
YOLOX detects every person
↓
one detected person → one isolated Person Instance crop
↓
extract separated Person features
  YoutuReID person embedding
  clothing_upper / clothing_lower
  body_hist / body_structure
  optional Face
↓
persist model-usable Person Evidence before identity classification
↓
Mature MOT organizes observations into temporal Tracks
↓
resolve_global_identities(tracks)
↓
RESOLVED identity classes + UNRESOLVED evidence
↓
recover_unresolved_tracks(candidates)
  Pass 1: repeated evidence inside one unresolved Track
↓
recover_fragmented_shot_presence(candidates)
  Pass 2: aggregate remaining short fragments inside one Shot
↓
write final A/B/C identity assignment back to Person Evidence manifest
↓
persist classified Gallery / CharacterCandidate / CharacterTrack
  └ exact identity_recovery provenance stays on recovered Tracks
↓
V10/V10.1 Final Gate
↓
Character + ShotCharacterBinding
↓
Asset Workspace V10.1 adapter
  ├ RESOLVED → evidence_by_shot.characters
  └ UNRESOLVED → evidence_by_shot.character_diagnostics
```

## 3. Capture-first and identity contract

Image condition is evidence metadata, not Character cardinality.

Supported Person Evidence classes:

```text
CLEAN
OCCLUDED
CONTAMINATED
PARTIAL
```

YoutuReID is the primary identity model signal. Supporting channels remain separate:

```text
person_reid       primary
clothing_upper    support
clothing_lower    support
body_hist         support
body_structure    support
face              optional support / high-quality hard conflict
```

Multi-person frames must be split into isolated Person Instances. Whole-frame identity input is forbidden.

A formal new V10/V10.1 identity requires at least:

```text
>= 3 independent Shots
>= 3 model-usable Person Images
stable cross-Shot Person-ReID support
unique identity class
same-sample cannot-link preserved
no high-quality Face hard conflict
```

Risky seed groups use stricter Person-ReID confirmation. Weak/tiny partial fragments remain evidence/attach-only and cannot create a Character.

Face is not required to define a person.

## 4. Pass 1 — known-identity Track recovery

Formal module:

```text
engine/app/character_shot_binding_v101.py
```

For each unresolved Track:

```text
compare every usable observation
against every already-RESOLVED identity Gallery
↓
aggregate support across independent Gallery Shots
↓
require repeated Track evidence
↓
require one unique winner
↓
attach whole Track to that existing identity
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

Hard rules:

- fewer than 3 usable observations → no Pass-1 recovery;
- same-sample cannot-link → reject;
- high-quality Face conflict → reject;
- ambiguous winner → unresolved;
- repeated weaker ReID requires appearance support;
- repeated very strong ReID may stand alone;
- recovery never creates a new identity.

Pass-1 source:

```text
V10_1_TRACK_KNOWN_IDENTITY_RECOVERY
```

## 5. Why Pass 2 is necessary

MOT and conservative per-observation classification can split one visually-present person into several short Track fragments.

Example:

```text
SHOT 0007
fragment A = 1 useful observation
fragment B = 1 useful observation
fragment C = 1 useful observation
```

Each fragment individually fails Pass 1 because it has fewer than 3 observations, even if all three independently point to the same known Character.

Lowering `MIN_TRACK_OBSERVATIONS` globally would increase false binding. The correct unit for this failure is therefore:

```text
known Character presence inside one Shot
```

rather than a weaker new-identity rule.

## 6. Pass 2 — fragmented Shot-presence recovery

Formal module:

```text
engine/app/character_shot_presence_v101.py
```

Formal source:

```text
V10_1_SHOT_FRAGMENT_AGGREGATION
```

Flow:

```text
remaining unresolved short Track fragments
↓
compare each usable observation with every confirmed identity Gallery
↓
Person-ReID primary
+ clothing/body support
+ optional high-quality Face positive support
↓
require a unique known-Character winner for each fragment
↓
group mutually-compatible fragments by (Shot, Character)
↓
aggregate support across independent Shot timestamps
↓
recover only if the Shot-level group is strong enough
↓
attach those fragments to the already-RESOLVED Character
```

Current thresholds:

```text
REID_STRONG = 0.84
REID_SUPPORTED = 0.74
RISKY_REID_SUPPORTED = 0.80
RISKY_APPEARANCE_CHANNELS = 2
FACE_STRONG = 0.52
FACE_POSITIVE_MIN_SCORE = 0.76
WINNER_MARGIN = 0.075

body-only recovery:
MIN_SHOT_SUPPORT_OBSERVATIONS = 3
MIN_SHOT_SUPPORT_TIMESTAMPS = 3
MIN_SHOT_MEDIAN = 0.76
```

### 6.1 Body/side/back path

A body-only/side/back recovery still needs repeated evidence across the Shot:

```text
>= 3 supporting observations
>= 3 distinct source timestamps
Shot aggregate median >= 0.76
unique Character winner
```

This keeps one weak fragment from being promoted just to fill a missing binding.

### 6.2 Strong Face positive path

V10.1 Face remains optional, but close-up Shots can have weak body ReID while SFace is very strong.

Pass 2 therefore allows a strong Face match to confirm **presence of an already-known Character** when:

```text
observation Face quality >= 0.76
Gallery Face quality >= 0.76
Face similarity >= 0.52
support exists from >=2 independent Gallery Shots
unique Character winner
no hard Face conflict / cannot-link conflict
```

This does not create a new Character and does not make Face mandatory for side/back/body recovery.

## 7. Cannot-link and hard conflicts

Same-sample cannot-link remains a hard constraint in both passes.

If two fragments represent two different persons visible at the same sampling time, they cannot be counted as repeated evidence for one Character.

High-quality Face disagreement is also fail-closed. A positive ReID/clothing score cannot override a strong contradictory Face pair.

These constraints are especially important for two-person Shots such as SHOT 0004 / 0009.

## 8. Recovery provenance and persistence

Every recovered Track carries exact provenance before persistence.

Pass 1:

```text
track.identity_recovery = {
  source: "V10_1_TRACK_KNOWN_IDENTITY_RECOVERY",
  target_candidate_id,
  shot_id,
  score,
  observation_count,
  policy
}
```

Pass 2 adds:

```text
track.identity_recovery = {
  source: "V10_1_SHOT_FRAGMENT_AGGREGATION",
  target_candidate_id,
  shot_id,
  score,
  observation_count,
  support_count,
  strong_face_support,
  policy
}
```

Persisted location:

```text
CharacterTrack.evidence_json.identity_recovery
```

Candidate summary metadata retains `track_recovery_*`; the second pass also records `shot_fragment_recovery_count` and its policy.

`character_persistence_v6.py` is a compatibility filename; it preserves the formal V10.1 profile and exact Track recovery JSON.

## 9. Identity confidence vs Shot-presence confidence

`CharacterCandidate.confidence` is project-level identity confidence.

Recovery score answers a different question:

> how confidently is this already-known Character present in this Shot?

Final rule:

```text
Shot has a normal/direct identity-assigned Track
→ ShotCharacterBinding.confidence = CharacterCandidate.confidence fallback

Shot contains only recovered Track fragment(s)
→ ShotCharacterBinding.confidence = max(valid recovery scores for that Shot)
```

If several Track fragments of the same Character occur in one Shot, Final materialization still creates one `ShotCharacterBinding`.

No DB schema migration is required.

## 10. Final Gate

Formal V10/V10.1 Final Character materialization remains unchanged and fail-closed:

```text
identity_status == RESOLVED
+ resolver in formal allow-list
+ confirmed_gallery_shots >= 3
+ confirmed_gallery_images >= 3
+ final_asset_eligible is not false
```

Neither recovery pass can upgrade an unconfirmed identity through this Gate.

Face visibility is not required.

Formal entry:

```text
engine/app/asset_final_gate_v10.py
```

Shared V10/V10.1 materializer:

```text
engine/app/asset_final_gate_v9.py
```

## 11. Asset Workspace evidence semantics

Formal API responses are decorated by:

```text
engine/app/asset_workspace_character_v101.py
```

Contract:

```text
evidence_by_shot[shot_id].characters
= RESOLVED Character evidence only

evidence_by_shot[shot_id].character_diagnostics
= UNRESOLVED Track/person diagnostics only
```

A recovered front/side/back/body Track remains visible with `face_visible=false`.

The adapter reads the **actual source from each Track recovery record**. Therefore Pass-2 evidence reports:

```text
V10_1_SHOT_FRAGMENT_AGGREGATION
```

rather than being mislabeled as Pass 1.

UNRESOLVED diagnostics have no Final asset id and no Final-binding confidence.

## 12. Character Gallery Shot labels

While reviewing the same real-video screenshots, a separate UI defect was identified: Gallery cards were deriving a fake Shot number from the trailing digits of the UUID-based `shot_id`.

That is invalid because `studio_v2.new_id()` produces UUID ids.

Current behavior:

```text
character_gallery_routes_v10.py
→ resolve immutable shot_id against v2_shots
→ return shot_ordinal / episode_id / episode_order

CharacterPersonGalleryV10.vue
→ render SHOT #### from shot_ordinal
```

This is display-only and does not affect identity/binding logic.

## 13. Formal code map

```text
engine/app/character_visual_v2.py
  compatibility facade → current V10.1 runtime

engine/app/character_runtime_v6.py
  formal V10.1 runtime; executes both recovery passes

engine/app/character_observation_v10.py
  Person Instance detection / crop capture

engine/app/character_person_evidence_v10.py
  evidence/seed eligibility

engine/app/character_person_features_v9.py
  separated Person feature channels

engine/app/character_tracking_v10.py
  temporal MOT organization

engine/app/character_identity_v101.py
  formal global identity classifier

engine/app/character_shot_binding_v101.py
  Pass-1 known-identity Track recovery

engine/app/character_shot_presence_v101.py
  Pass-2 fragmented same-Shot known-presence aggregation

engine/app/character_persistence_v6.py
  persistence bridge / identity_recovery storage

engine/app/character_gallery_v10.py
  classified Person Gallery persistence

engine/app/character_gallery_routes_v10.py
  Gallery API + real Shot ordinal resolution

engine/app/asset_final_gate_v10.py
  formal Final Character Gate entry

engine/app/asset_final_gate_v9.py
  shared materializer + Shot-presence confidence

engine/app/asset_workspace_character_v101.py
  resolved Shot evidence / unresolved diagnostics adapter

frontend/src/components/CharacterPersonGalleryV10.vue
  classified Person Gallery UI with real Shot ordinals
```

## 14. Required regression cases

The following must remain locked:

```text
1. multi-person frame → independent Person Instances
2. same-sample different persons → cannot-link
3. weak partial fragments → evidence only
4. strong risky views across >=3 Shots → may form one identity
5. Face absent → confirmed identity can still pass formal gate
6. high-quality Face conflict → never merge
7. unresolved Track with repeated unique support → Pass-1 attach to confirmed identity
8. Pass-1 recovery persists source/target/Shot/score
9. Pass-1 ambiguous winner → unresolved
10. Pass-1 cannot-link conflict → unresolved
11. recovery never creates a new Character
12. three singleton fragments in one Shot → Pass-2 may recover one known Character
13. one strong high-quality Face fragment → may confirm presence of existing Character
14. one weak body fragment → stays unresolved
15. same-sample cannot-link fragments → cannot be counted as duplicate support
16. recovered-only Shot binding → uses recovery confidence
17. normal/direct Shot → uses identity-confidence fallback
18. mixed direct + recovered fragments → direct assignment wins confidence semantics
19. face_visible=false recovered Track → visible as RESOLVED Shot evidence
20. UNRESOLVED Track → character_diagnostics only
21. workspace reports actual Pass-1/Pass-2 recovery source
22. Gallery displays real v2_shots.ordinal, never UUID suffix
23. Final Gate still requires formal resolver + >=3 Shots/images
```

## 15. Validation status

Implementation exists, but the whole repository CI is not green because of existing legacy/environment failures.

After adding Pass 2, the backend full-test summary reached:

```text
28 failed, 176 passed, 1 skipped
```

The new fragment-presence focused test file was not among the failures. Backend compile and FastAPI import passed. Existing failures still include missing/full runtime assumptions (`cv2`, trackers, FFmpeg/media) and legacy assertions. Frontend build remains blocked by the existing `vue-tsc` / TypeScript compatibility issue.

Do not mark Character V10.1 `STABLE/FROZEN` until real Windows footage verifies both Final Character count and ShotCharacterBinding accuracy.

## 16. Local acceptance procedure

After pulling latest `main`:

```text
1. restart backend/frontend as needed
2. rerun asset extraction — old Run will not auto-rebind
3. verify Final Character count stays correct
4. recheck SHOT 0002 / 0004 / 0006 / 0007 / 0009
5. inspect CharacterTrack.evidence_json.identity_recovery for recovered Shots
6. expect new fragment cases to use source V10_1_SHOT_FRAGMENT_AGGREGATION
7. if 0002/0006 still miss, inspect Face detection, face_score and SFace evidence before threshold changes
8. if 0004/0009 miss the second person, verify YOLOX captured a separate Person Instance
9. if 0007 misses, inspect support_count / timestamps / winner margin before tuning
10. only tune thresholds after the failure is reproducible and its stage is known
```
