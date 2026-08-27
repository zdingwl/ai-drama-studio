# Character V10.1 — Capture-first Identity + Shot Binding Recovery

> **Status:** IMPLEMENTED / NEEDS WINDOWS REAL-VIDEO REGRESSION  
> **Formal runtime profile:** `character-v10.1-capture-first-model-classification`  
> **Formal asset profile:** `f05-assets-v10.1-person-evidence-model-classification`  
> **Formal resolver:** `person-evidence-model-classifier-v10.1`

## 1. Why V10.1 exists

V10 solved the structural error of treating detection fragments as Character assets by moving to capture-first Person Evidence and model classification.

V10.1 adds two corrections:

1. **Risky-view identity creation:** strong `CONTAMINATED` / substantial `PARTIAL` Person crops are allowed to propose a new identity under stricter cross-Shot confirmation instead of being permanently excluded by image-condition labels.
2. **Shot-level known-identity recovery:** when the global resolver already knows a Character, an individually ambiguous Track can still be attached to that known identity when repeated observations across the Track produce one unique, stable winner.

The second correction specifically targets the user-visible failure:

```text
Character asset page identifies person correctly
but a Shot still shows “待解析人物” / wrong Character binding
```

## 2. Formal pipeline

```text
Shot / Reference Clip
↓
YOLOX detects every person
↓
one detected person → one explicit isolated Person Instance crop
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
↓
write final A/B/C identity assignment back to Person Evidence manifest
↓
persist classified gallery / CharacterCandidate / CharacterTrack
↓
V10/V10.1 Final Gate
↓
Character + ShotCharacterBinding
```

## 3. Capture-first rule

Image condition is evidence metadata, not identity cardinality.

Supported Person Evidence classes:

```text
CLEAN
OCCLUDED
CONTAMINATED
PARTIAL
```

Rules:

- `CLEAN` / `OCCLUDED`: normal seed candidates when quality is sufficient.
- strong `CONTAMINATED`: may seed a new identity under stricter confirmation.
- substantial detector-backed `PARTIAL`: may seed under stricter confirmation when visible area/quality is sufficient.
- weak/tiny/low-score `PARTIAL`: save/classify/attach only; never creates a new Character.
- multi-person frames must be split into isolated Person Instance crops; whole-frame identity input is forbidden.

## 4. Identity model contract

YoutuReID is the primary identity model signal because it is designed for front/side/back person matching.

Supporting channels remain separate:

```text
person_reid       primary
clothing_upper    support
clothing_lower    support
body_hist         support
body_structure    support
face              optional support / hard conflict
```

There is no demographic inference and no opaque “total person embedding” that hides the reason for a match.

High-quality Face disagreement is a hard negative. Face agreement is useful support but Face is **not required** to define a person.

## 5. New-identity confirmation

A formal V10/V10.1 identity must have at least:

```text
>= 3 independent Shots
>= 3 model-usable Person Images
stable cross-Shot Person-ReID support
unique class
same-sample cannot-link preserved
no high-quality Face hard conflict
```

Risky seed groups use stricter Person-ReID confirmation than normal groups.

This means one strong crop or one Track is never enough to create a Final Character.

## 6. Shot-level known-identity Track recovery

### 6.1 Problem

Single Person Evidence classification is intentionally conservative. A short Shot may contain several observations that are each only “ambiguous” but are all consistently closest to the same already-confirmed identity.

Without a Track-level second pass, the global person list can be correct while that Shot remains unbound.

### 6.2 Formal recovery rule

For each `UNRESOLVED` Track:

```text
compare every usable observation
against every already-RESOLVED identity gallery
↓
aggregate best support by independent gallery Shot
↓
require repeated Track evidence
↓
require one unique winner
↓
attach Track to that existing identity
```

Current guardrails in `character_shot_binding_v101.py`:

```text
MIN_TRACK_OBSERVATIONS = 3
MIN_SUPPORTING_OBSERVATIONS = 2
NORMAL_TRACK_MEDIAN = 0.74
RISKY_TRACK_MEDIAN = 0.79
STRONG_TRACK_MEDIAN = 0.84
WINNER_MARGIN >= 0.07
```

Important behavior:

- fewer than 3 usable observations → no recovery;
- same-sample cannot-link → hard reject;
- high-quality Face conflict → hard reject;
- no unique winner → no recovery;
- repeated weaker ReID support must also have enough independent clothing/body support;
- repeated very strong ReID may stand alone;
- recovery attaches the **whole Track**, not just one crop.

### 6.3 Non-negotiable invariant

Track recovery **never creates a new identity**.

It can only answer:

> “This unresolved Track belongs to one Character that was already independently confirmed.”

If there is no confirmed identity, the pass does nothing.

## 7. Persistence after recovery

After one Track is recovered:

```text
candidate.tracks += recovered_track
→ candidate embeddings/gallery refreshed
→ v10_metadata.track_recovery_* updated
→ unresolved candidate keeps only remaining tracks
```

Metadata includes:

```text
track_recovery_count
track_recovery_shot_ids
track_recovery_scores
track_recovery_policy
```

Then `content_analysis_v2` persists the new Candidate/Track membership. The Final Asset materializer creates `ShotCharacterBinding` by iterating those persisted Character Tracks.

Therefore the recovery step must occur **before** Candidate/Track persistence and before Final materialization.

## 8. Final Gate

Formal V10/V10.1 Final Character materialization is fail-closed:

```text
identity_status == RESOLVED
+ resolver in formal allow-list
+ confirmed_gallery_shots >= 3
+ confirmed_gallery_images >= 3
+ final_asset_eligible is not false
```

V10.1 adds `person-evidence-model-classifier-v10.1` to the formal resolver allow-list through:

```text
engine/app/asset_final_gate_v10.py
```

Face visibility is not required for formal V10/V10.1 candidates.

## 9. Formal code map

```text
engine/app/character_visual_v2.py
  compatibility facade that currently points to V10.1

engine/app/character_runtime_v6.py
  formal V10.1 runtime entry; filename retained for import compatibility

engine/app/character_observation_v10.py
  Person Instance detection / crop capture

engine/app/character_person_evidence_v10.py
  evidence/seed eligibility policy

engine/app/character_person_features_v9.py
  separated Person feature channels

engine/app/character_tracking_v10.py
  temporal Track building

engine/app/character_identity_v10.py
  V10 classifier base/helpers

engine/app/character_identity_v101.py
  formal V10.1 identity resolver

engine/app/character_shot_binding_v101.py
  post-confirmation known-identity Track recovery

engine/app/character_gallery_v10.py
  classified gallery selection/persistence

engine/app/character_evidence_store_v10.py
  capture-first evidence store and classification writeback

engine/app/asset_final_gate_v10.py
  formal Final Character gate
```

## 10. Required regression cases

The following cases must remain locked:

```text
1. multi-person frame → independent Person Instances
2. same-sample different persons → cannot-link
3. weak partial fragments → evidence only
4. strong risky views across >=3 Shots → may form one identity
5. Face absent → confirmed identity can still pass formal gate
6. high-quality Face conflict → never merge
7. unresolved Track with repeated unique support → attach to confirmed identity
8. ambiguous winner → stays unresolved
9. cannot-link conflict during recovery → stays unresolved
10. recovery never creates a new Character
11. recovered Track changes persisted Shot membership
12. Final Gate still requires formal resolver + >=3 Shots/images
```

## 11. Current validation status

Implementation and targeted regression tests exist, but the entire repository CI is not currently green because of legacy/environment failures unrelated to this single feature, including missing `cv2`/`trackers` in the lightweight runner, old V6 assertions, FFmpeg assumptions, and frontend TypeScript/vue-tsc compatibility.

Do not mark Character V10.1 `STABLE/FROZEN` until the user reruns asset extraction on real Windows short-drama material and verifies both:

```text
Final Character count
and
ShotCharacterBinding accuracy
```

## 12. Local acceptance procedure

After pulling the latest code:

```text
1. verify F05 models/runtime
2. rerun asset extraction (old Run will not auto-rebind)
3. compare Character list to real cast in the sample
4. inspect previously incorrect Shot bindings
5. if a known person is still missing from a Shot, inspect Person Evidence + track_recovery_* metadata
6. tune only if the failure is reproducible on real media
```
