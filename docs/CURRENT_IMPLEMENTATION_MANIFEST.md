# AI Drama Studio — Current Implementation Manifest

> Purpose: compact code-aligned manifest for new conversations.  
> Last synchronized: **2026-08-27 15:52 +08:00**

## Repository baseline

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Architecture: Reference Video V2
FastAPI app version: 2.4.1
```

## Formal Character baseline

```text
Character version: V10.1
Runtime profile: character-v10.1-capture-first-model-classification
Asset profile: f05-assets-v10.1-person-evidence-model-classification
Resolver: person-evidence-model-classifier-v10.1
Shot assignment version: v10.1-shot-character-assignment-1
Shot assignment source: V10_1_SHOT_CHARACTER_ASSIGNMENT
Primary identity model: YoutuReID Person Re-identification
Face role: optional identity support / known-identity Shot presence / high-quality conflict
Final identity gate: confirmed formal RESOLVED identity only
```

## Executable Character wiring

```text
content_analysis_v2
→ character_visual_v2.analyze_characters
→ character_runtime_v6.analyze_characters
→ character_observation_v10.detect_observations
→ save pre-classification Person Evidence
→ character_tracking_v10.build_tracks
→ character_identity_v101.resolve_global_identities
→ character_shot_assignment_v101.assign_shot_characters
   # independent Shot × known-Character decision from ALL original Track/Observations
→ character_evidence_store_v10.update_person_evidence_classification
→ character_persistence_v6.persist_results_v6
→ asset_final_gate_v10.apply_analysis_to_assets
→ asset_final_gate_v9 materializer consumes explicit shot_presence_assignments
→ Character / ShotCharacterBinding
→ asset_workspace_character_v101
```

The formal runtime no longer calls:

```text
character_shot_binding_v101.recover_unresolved_tracks
character_shot_presence_v101.recover_fragmented_shot_presence
```

Those modules remain only for historical compatibility/tests.

## Semantic layers

```text
Observation / Person Evidence / CharacterTrack
= visual evidence

CharacterCandidate / Identity Class
= project-level person identity

Shot Character Assignment
= known Character presence in one Shot

Character / ShotCharacterBinding
= editable Final asset / binding
```

Track ownership is no longer the Final Shot-binding source.

## New identity confirmation

Formal identity creation remains fail-closed:

```text
>=3 independent Shots
>=3 model-usable Person Images
stable cross-Shot Person-ReID class
unique identity result
same-sample cannot-link preserved
no high-quality Face hard conflict
```

Shot assignment runs only after identities are RESOLVED and can never create a new Character.

## Explicit Shot Character Assignment

Formal module:

```text
engine/app/character_shot_assignment_v101.py
```

Inputs:

```text
all original Tracks / Observations
+ all already-RESOLVED identity galleries
```

Outputs on each RESOLVED Candidate:

```text
shot_assignment_version
shot_assignment_source
shot_assignment_policy
shot_presence_assignments[]
shot_presence_shot_ids
shot_presence_count
shot_presence_recovered_count
```

Assignment modes:

```text
DIRECT_IDENTITY
FACE_STRONG
FACE_REPEATED
BODY_REID
```

Current Face gates:

```text
FACE_PAIR_MIN_SCORE = 0.72
FACE_SUPPORTED = 0.36
FACE_STRONG = 0.50
FACE_WINNER_MARGIN = 0.08
MIN_FACE_REPEAT_OBSERVATIONS = 2
MIN_FACE_REPEAT_TIMESTAMPS = 2
MIN_FACE_REPEAT_MEDIAN = 0.40
```

Current body/ReID gates:

```text
REID_STRONG = 0.84
REID_SUPPORTED = 0.74
RISKY_REID_SUPPORTED = 0.80
RISKY_APPEARANCE_CHANNELS = 2
REID_WINNER_MARGIN = 0.07
MIN_BODY_SUPPORT_OBSERVATIONS = 3
MIN_BODY_SUPPORT_TIMESTAMPS = 3
MIN_BODY_MEDIAN = 0.76
```

Same-sample cannot-link is used as a Shot occupancy constraint. A simultaneous different Person Instance cannot be assigned to a Character already occupying its cannot-link counterpart. This is important for two-person Shots.

Ambiguous winner, insufficient repetition or repeated high-quality Face conflict remains unassigned. The engine never moves Track ownership to manufacture a binding.

## Final Character / Shot binding contract

Identity cardinality gate stays unchanged:

```text
identity_status == RESOLVED
formal resolver allow-list
confirmed_gallery_shots >= 3
confirmed_gallery_images >= 3
final_asset_eligible is not false
```

For current Runs containing `shot_assignment_version`:

```text
ShotCharacterBinding
= explicit shot_presence_assignments only
```

An explicit empty assignment list does **not** fall back to Candidate Track membership.

Historical persisted Runs without `shot_assignment_version` keep the old Track-derived fallback so old projects remain readable.

## Asset Workspace contract

```text
evidence_by_shot.characters
= RESOLVED Character Shot presence

evidence_by_shot.character_diagnostics
= UNRESOLVED visual diagnostics only
```

For explicit-assignment Runs, `asset_workspace_character_v101` follows the assignment map. A RESOLVED Candidate Track absent from that map cannot silently recreate a Shot suggestion.

Gallery/Evidence comparison UI is diagnostic only and is not a binding source.

## Fixed model package

```text
YOLOX person detection
YoutuReID person re-identification
YuNet face detection
SFace face embedding/support
```

## Current key modules

```text
engine/app/main.py
engine/app/content_analysis_v2.py
engine/app/content_models_v2.py
engine/app/character_visual_v2.py
engine/app/character_runtime_v6.py
engine/app/character_observation_v10.py
engine/app/character_person_evidence_v10.py
engine/app/character_person_features_v9.py
engine/app/character_tracking_v10.py
engine/app/character_identity_v10.py
engine/app/character_identity_v101.py
engine/app/character_shot_assignment_v101.py
engine/app/character_persistence_v6.py
engine/app/character_gallery_v10.py
engine/app/character_gallery_routes_v10.py
engine/app/character_evidence_store_v10.py
engine/app/asset_final_gate_v10.py
engine/app/asset_final_gate_v9.py
engine/app/asset_workspace_character_v101.py
engine/app/asset_routes_v3.py
```

Historical compatibility files not in the formal runtime path:

```text
engine/app/character_shot_binding_v101.py
engine/app/character_shot_presence_v101.py
```

Do not infer active algorithm generation from compatibility filenames.

## Current validation state

```text
Global Character identity classification: implemented
Independent Shot × known-Character assignment: implemented
Direct identity Shot presence: implemented
Strong Face known-presence: implemented
Repeated moderate Face known-presence: implemented
Repeated Body/ReID known-presence: implemented
Same-Shot cannot-link occupancy constraints: implemented
No Track ownership mutation in formal binding path: implemented
Final Gate explicit assignment consumption: implemented
Workspace explicit assignment consumption: implemented
Historical old-Run fallback: preserved
Windows real-video SHOT 0001–0009 acceptance: pending
Whole repository CI: not green
```

Latest backend CI after the new binding tests:

```text
28 failed, 187 passed, 1 skipped
```

Backend compile and FastAPI import pass. The explicit Shot assignment tests, explicit Final Gate tests and explicit workspace assignment test are not among failures. Existing failures remain legacy/runtime/environment categories (`cv2`, `trackers`, FFmpeg and obsolete historical assertions).

Frontend CI still has the existing `vue-tsc` / TypeScript package compatibility failure.

## Required new-conversation checks

Before changing Character binding behavior verify:

```text
character_runtime_v6 calls assign_shot_characters(tracks, candidates)
character_runtime_v6 does not call the old Track recovery passes
CharacterCandidate.evidence_json persists shot_assignment_version + shot_presence_assignments
asset_final_gate_v9 treats explicit assignments as authoritative for new Runs
asset_workspace_character_v101 follows explicit assignments for RESOLVED presence
old Runs without shot_assignment_version still use historical fallback
```

## Next Windows acceptance

A fresh Analysis Run is required.

```text
SHOT 0001 → []
SHOT 0002 → [人物002]
SHOT 0003 → [人物001]
SHOT 0004 → [人物001, 人物002]
SHOT 0005 → [人物001]
SHOT 0006 → [人物001]
SHOT 0007 → [人物002]
SHOT 0008 → []
SHOT 0009 → verify all actually visible known Characters
```

If a Shot is still wrong, inspect `shot_presence_assignments` first. Do not return to broad Gallery changes or lower global identity thresholds without evidence.
