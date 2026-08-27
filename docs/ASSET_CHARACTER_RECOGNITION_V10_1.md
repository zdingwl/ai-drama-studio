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
  └ recovered Track receives identity_recovery provenance
↓
write final A/B/C identity assignment back to Person Evidence manifest
↓
persist classified gallery / CharacterCandidate / CharacterTrack
  └ persist identity_recovery JSON on the exact Track
↓
V10/V10.1 Final Gate
↓
Character + ShotCharacterBinding
  └ recovered-only Shot uses Track recovery score as Shot-presence confidence
↓
Asset Workspace V10.1 adapter
  ├ RESOLVED → evidence_by_shot.characters
  └ UNRESOLVED → evidence_by_shot.character_diagnostics
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

## 7. Recovery provenance and persistence

Before a Track is moved into a confirmed Candidate, V10.1 attaches transient Track-level provenance:

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

Then:

```text
candidate.tracks += recovered_track
→ candidate embeddings/gallery refreshed
→ v10_metadata.track_recovery_* updated
→ unresolved candidate keeps only remaining tracks
→ character_persistence_v6 persists the exact Track recovery metadata
```

Persisted Track Evidence:

```text
CharacterTrack.evidence_json.identity_recovery
```

Candidate summary metadata includes:

```text
track_recovery_count
track_recovery_shot_ids
track_recovery_scores
track_recovery_source
track_recovery_policy
```

`character_persistence_v6.py` is a compatibility filename but now preserves an already-formal V9/V10/V10.1 asset profile rather than temporarily downgrading a V10.1 Run to the historical V6 profile.

Recovery must occur **before** Candidate/Track persistence and before Final materialization.

## 8. Identity confidence vs Shot-presence confidence

The project now treats these as different semantics.

`CharacterCandidate.confidence` describes the confirmed identity class at project level.

A V10.1 Track recovery score describes:

> how strongly this already-known Character is present in this particular Shot.

Final binding rule:

```text
Shot has at least one normal/direct identity-assigned Track
→ ShotCharacterBinding.confidence = CharacterCandidate.confidence fallback

Shot contains only V10.1 recovered Track fragment(s)
→ ShotCharacterBinding.confidence = max(valid recovery scores for that Shot)
```

If multiple Track fragments of the same Character appear in one Shot, Final materialization still creates only one `ShotCharacterBinding`.

No DB schema migration was needed. The existing binding `confidence` column is used for Shot-presence confidence, while Track recovery provenance stays inside immutable Track Evidence JSON.

Implementation lives in the shared materializer:

```text
engine/app/asset_final_gate_v9.py
```

The formal V10/V10.1 entry remains:

```text
engine/app/asset_final_gate_v10.py
```

## 9. Final Gate

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

## 10. Asset Workspace evidence semantics

The older `asset_workspace_v3._evidence_by_shot()` implementation filters Character Evidence by `track.face_visible`. That is historical behavior and does not match V10.1.

Formal API responses are therefore decorated by:

```text
engine/app/asset_workspace_character_v101.py
```

Current contract:

```text
evidence_by_shot[shot_id].characters
= RESOLVED Character evidence only

face_visible == false is allowed
front / side / back / body-visible / recovered Track are all valid once identity is confirmed

evidence_by_shot[shot_id].character_diagnostics
= UNRESOLVED Track/person diagnostics only
```

UNRESOLVED diagnostics have:

```text
final_asset_id = null
confidence = null
confidence_source = UNRESOLVED_DIAGNOSTIC
```

They remain available for debugging/future diagnostic UI but no longer appear in the main Shot Character evidence list consumed by the current review table.

This prevents a pending fragment from replacing a correctly confirmed Character in the Shot UI.

## 11. Formal code map

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
  post-confirmation known-identity Track recovery + Track provenance

engine/app/character_persistence_v6.py
  persistence bridge; stores identity_recovery and preserves formal V10/V10.1 profile

engine/app/character_gallery_v10.py
  classified gallery selection/persistence

engine/app/character_evidence_store_v10.py
  capture-first evidence store and classification writeback

engine/app/asset_final_gate_v10.py
  formal Final Character gate entry

engine/app/asset_final_gate_v9.py
  shared V10/V10.1 materializer + Shot-presence confidence aggregation

engine/app/asset_workspace_character_v101.py
  face-optional resolved Shot evidence + unresolved diagnostics split

engine/app/asset_routes_v3.py
  decorates every returned Asset Workspace payload with V10.1 Character evidence semantics
```

## 12. Required regression cases

The following cases must remain locked:

```text
1. multi-person frame → independent Person Instances
2. same-sample different persons → cannot-link
3. weak partial fragments → evidence only
4. strong risky views across >=3 Shots → may form one identity
5. Face absent → confirmed identity can still pass formal gate
6. high-quality Face conflict → never merge
7. unresolved Track with repeated unique support → attach to confirmed identity
8. successful recovery persists source/target/Shot/score provenance on Track
9. ambiguous winner → stays unresolved
10. cannot-link conflict during recovery → stays unresolved
11. recovery never creates a new Character
12. recovered-only Shot binding uses Track recovery confidence
13. normal/direct Shot binding keeps identity-confidence fallback
14. mixed direct + recovered Track fragments prefer direct assignment
15. face_visible=false recovered Track remains visible in RESOLVED Shot evidence
16. UNRESOLVED Track is exposed only as character_diagnostics
17. Final Gate still requires formal resolver + >=3 Shots/images
```

## 13. Current validation status

Implementation and focused regression tests exist, but the entire repository CI is not currently green because of legacy/environment failures unrelated to this single feature. Recent runs continue to show backend compile and FastAPI import succeeding before the full-pytest failure. Known repository-level categories include missing full `cv2`/`trackers`/media runtime, legacy semantic assertions, FFmpeg assumptions, and frontend TypeScript/vue-tsc compatibility.

Do not mark Character V10.1 `STABLE/FROZEN` until real Windows short-drama material verifies both:

```text
Final Character count
and
ShotCharacterBinding accuracy
```

## 14. Local acceptance procedure

After pulling the latest code:

```text
1. verify F05 models/runtime
2. rerun asset extraction (old Run will not auto-rebind or gain identity_recovery metadata)
3. compare Character list to real cast in the sample
4. inspect previously incorrect Shot bindings
5. verify the Shot AI Character line contains only RESOLVED Character evidence
6. if a known person is still missing, inspect CharacterTrack.evidence_json.identity_recovery + candidate track_recovery_* metadata
7. distinguish identity-classification failure from Shot-presence recovery failure before changing thresholds
8. tune only if the failure is reproducible on real media
```
