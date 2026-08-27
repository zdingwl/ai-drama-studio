# Character V10.1 — Capture-first Identity + Two-pass Shot Presence Recovery

> **Status:** IMPLEMENTED / NEEDS NEXT WINDOWS REAL-VIDEO REGRESSION  
> **Formal runtime profile:** `character-v10.1-capture-first-model-classification`  
> **Formal asset profile:** `f05-assets-v10.1-person-evidence-model-classification`  
> **Formal resolver:** `person-evidence-model-classifier-v10.1`  
> **Last synchronized:** 2026-08-27 14:25 +08:00

## 1. Scope

Character V10.1 keeps identity creation and Shot presence as separate problems.

```text
Person Evidence / Track
→ cross-Shot identity classification
→ RESOLVED Character identities
→ known-identity Shot-presence recovery
→ Final Character + ShotCharacterBinding
```

It solves three classes of issues:

1. strong contaminated/substantial partial views may participate in new identity confirmation under stricter rules;
2. one unresolved Track with repeated evidence may attach to an existing Character;
3. several short fragments or close-up Face observations in one Shot may recover presence of an already-confirmed Character.

None of the Shot recovery paths can create a new Character.

## 2. Formal pipeline

```text
Shot / Reference Clip
↓
YOLOX Person Detection + YuNet Face fallback
↓
isolated Person Instance observations
↓
YoutuReID person embedding
+ clothing_upper / clothing_lower
+ body_hist / body_structure
+ optional SFace
↓
Mature MOT
↓
character_identity_v101.resolve_global_identities
↓
RESOLVED + UNRESOLVED
↓
Pass 1: character_shot_binding_v101.recover_unresolved_tracks
↓
Pass 2: character_shot_presence_v101.recover_fragmented_shot_presence
↓
persist exact Track recovery provenance
↓
Final Gate
↓
Character + ShotCharacterBinding
```

## 3. New identity contract

New Character creation still requires:

```text
>=3 independent Shots
>=3 model-usable Person Images
stable Person-ReID consistency
unique identity result
same-sample cannot-link preserved
no high-quality Face hard conflict
```

YoutuReID remains the primary identity signal. Face is optional support and may block a merge when high-quality evidence strongly disagrees.

Weak/tiny partials remain attach-only.

## 4. Pass 1 — repeated Track recovery

Module:

```text
engine/app/character_shot_binding_v101.py
```

Source:

```text
V10_1_TRACK_KNOWN_IDENTITY_RECOVERY
```

Rule:

```text
one UNRESOLVED Track
→ compare repeated observations against all RESOLVED galleries
→ require >=3 usable observations
→ require repeated support
→ require unique winner + margin
→ cannot-link / strong Face conflict fail closed
→ attach entire Track to that existing identity
```

Current thresholds:

```text
MIN_TRACK_OBSERVATIONS = 3
MIN_SUPPORTING_OBSERVATIONS = 2
NORMAL_TRACK_MEDIAN = 0.74
RISKY_TRACK_MEDIAN = 0.79
STRONG_TRACK_MEDIAN = 0.84
WINNER_MARGIN >= 0.07
```

## 5. Pass 2 — same-Shot presence recovery

Module:

```text
engine/app/character_shot_presence_v101.py
```

Source:

```text
V10_1_SHOT_FRAGMENT_AGGREGATION
```

Pass 2 handles two related cases:

```text
A. body/side/back person split into several short Tracks
B. close-up / edge / two-person view where Face is clear but synthetic-body ReID is weak
```

### 5.1 Body/side/back path

```text
REID_STRONG = 0.84
REID_SUPPORTED = 0.74
RISKY_REID_SUPPORTED = 0.80
RISKY_APPEARANCE_CHANNELS = 2
WINNER_MARGIN = 0.075

MIN_SHOT_SUPPORT_OBSERVATIONS = 3
MIN_SHOT_SUPPORT_TIMESTAMPS = 3
MIN_SHOT_MEDIAN = 0.76
```

A single weak body fragment never gets promoted just to fill a Shot.

### 5.2 Known-Face close-up path

The first real-video fragment patch improved body/partial rows but the next user rerun showed:

```text
SHOT 0006 old woman close-up → corrected
SHOT 0007 young woman partial/body → corrected
SHOT 0002 young woman clear face close-up → still unbound
SHOT 0004 old + young → young woman still missing
```

This narrows the remaining failure to the known-Face presence branch.

The previous code used:

```text
FACE_STRONG = 0.52
```

and allowed one bad high-quality Gallery Face comparison to hard-veto the candidate. That behavior was too brittle for expression, viewpoint and crop variation.

Current known-Face rules:

```text
FACE_SUPPORTED = 0.40
FACE_STRONG = 0.50
FACE_PAIR_MIN_SCORE = 0.76
MIN_FACE_SUPPORT_OBSERVATIONS = 2
MIN_FACE_SUPPORT_TIMESTAMPS = 2
MIN_FACE_GROUP_SCORE = 0.84
STRONG_FACE_PRESENCE_SCORE = 0.89
```

Semantics:

```text
moderate Face similarity
→ must repeat on >=2 current-Shot observations
→ must occur at >=2 distinct current-Shot timestamps
→ each observation must be supported by Face evidence from >=2 independent confirmed Gallery Shots

very strong Face similarity
→ one observation may confirm presence of an already-known Character
```

Face-supported candidates are ranked before synthetic-body ReID when a close-up/face-fallback observation has both. This prevents a synthetic body crop around a face from incorrectly outranking the actual Face identity.

### 5.3 Face conflict rule

Same-sample cannot-link remains immediate hard rejection.

High-quality Face conflict is now aggregated across Gallery Shots:

```text
one bad/noisy Gallery Face crop
→ does NOT veto the identity by itself

consistent Face conflict across >=2 independent Gallery Shots
AND no supported positive Face match
→ hard reject
```

This preserves fail-closed safety while avoiding false negatives from one poor profile/expression crop.

## 6. Why this does not loosen Character identity

The Face presence path only runs after `RESOLVED` identities already exist.

It answers:

> Is this already-confirmed person present in this Shot?

It does not answer:

> Is this a brand-new person?

Therefore:

```text
FACE_SUPPORTED / FACE_STRONG
never change new-identity confirmation cardinality
never bypass >=3 independent Shots
never create a Final Character from a close-up alone
```

## 7. Recovery provenance

Pass 1 Track evidence includes:

```text
source
target_candidate_id
shot_id
score
observation_count
policy
```

Pass 2 additionally includes:

```text
support_count
face_support_count
strong_face_support
```

Persisted at:

```text
CharacterTrack.evidence_json.identity_recovery
```

Candidate summaries keep `track_recovery_*` and `shot_fragment_recovery_*` metadata.

## 8. Shot confidence

Project-level identity confidence and Shot presence confidence are separate.

```text
direct identity-assigned Track in Shot
→ ShotCharacterBinding.confidence = candidate identity confidence fallback

recovered-only Track(s)
→ ShotCharacterBinding.confidence = strongest validated recovery score
```

One Character produces at most one Final binding per Shot even if several fragments were recovered.

## 9. Final Gate

Final Character materialization remains fail-closed:

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

## 10. Workspace evidence

```text
evidence_by_shot.characters
= RESOLVED Character evidence only

evidence_by_shot.character_diagnostics
= UNRESOLVED diagnostics only
```

The workspace adapter reads the actual recovery source from the Track. Unresolved diagnostics never become Final suggestions.

## 11. Character Gallery labels

Gallery `shot_id` values are UUID ids. Display labels resolve the real `v2_shots.ordinal`; UUID suffixes are never interpreted as Shot numbers.

## 12. Formal code map

```text
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
engine/app/asset_final_gate_v10.py
engine/app/asset_final_gate_v9.py
engine/app/asset_workspace_character_v101.py
```

## 13. Required regression cases

Current focused cases include:

```text
1. global identity still requires >=3 independent Shots/images
2. same-sample persons remain cannot-link
3. weak partials cannot seed Character
4. repeated unresolved Track can attach to known Character
5. ambiguous Pass-1 Track stays unresolved
6. three body singleton fragments can recover one known Character
7. one weak body fragment stays unresolved
8. one very strong Face can confirm known presence
9. repeated moderate Face below old 0.52 threshold can recover known presence
10. one moderate Face observation stays unresolved
11. Face-supported identity outranks synthetic-body ReID in close-up fallback
12. same-sample fragments cannot fake repeated support
13. recovered-only Shot uses recovery confidence
14. workspace exposes actual Pass-1/Pass-2 source
15. Final Gate remains unchanged
```

## 14. Validation reality

The whole repository CI is not green. Before the latest known-Face patch, the backend full-test summary was:

```text
28 failed, 176 passed, 1 skipped
```

Existing failures are still repository-level legacy/runtime/environment categories. The newest Face-focused tests were added after that summary; their workflow may still be pending when this document is read.

Do not mark V10.1 `STABLE/FROZEN` until real Windows footage confirms Shot binding accuracy.

## 15. Next local acceptance

A new asset extraction Run is required.

```text
SHOT 0002 → should bind 人物002
SHOT 0004 → should bind 人物001 + 人物002
SHOT 0006 → should remain 人物001
SHOT 0007 → should remain 人物002
SHOT 0009 → verify every actually visible known Character
```

If 0002/0004 still miss, inspect:

```text
YuNet Face observations
face_score
SFace similarity support
CharacterTrack.evidence_json.identity_recovery.face_support_count
winner margin against other resolved identities
```

Do not lower body/ReID thresholds again unless evidence proves the remaining failure is body-based.
