# AI Drama Studio — Current Implementation Manifest

> Purpose: compact code-aligned recovery manifest for new conversations.  
> Last synchronized: **2026-08-27 14:25 +08:00**

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
Primary identity model: YoutuReID Person Re-identification
Face role: optional support / known-identity Shot presence / high-quality conflict
Final Gate: confirmed formal RESOLVED identity only
```

Fixed model package:

```text
YOLOX person detection
YoutuReID person re-identification
YuNet face detection
SFace face embedding/support
```

## Executable Character wiring

```text
content_analysis_v2
→ character_visual_v2.analyze_characters
→ character_runtime_v6.analyze_characters
→ character_observation_v10.detect_observations
→ character_tracking_v10.build_tracks
→ character_identity_v101.resolve_global_identities
→ character_shot_binding_v101.recover_unresolved_tracks
   # Pass 1: repeated evidence inside one unresolved Track
→ character_shot_presence_v101.recover_fragmented_shot_presence
   # Pass 2: same-Shot fragment aggregation + known-Face presence
→ character_evidence_store_v10.update_person_evidence_classification
→ character_persistence_v6.persist_results_v6
→ asset_final_gate_v10.apply_analysis_to_assets
→ Character / ShotCharacterBinding
→ asset_workspace_character_v101
```

## New identity contract

A new formal Character still requires:

```text
>=3 independent Shots
>=3 model-usable Person Images
stable cross-Shot Person-ReID class
unique identity result
same-sample cannot-link preserved
no high-quality Face hard conflict
```

Neither Shot-presence recovery pass may create a new Character.

## Shot-presence Pass 1

Module:

```text
engine/app/character_shot_binding_v101.py
```

Source:

```text
V10_1_TRACK_KNOWN_IDENTITY_RECOVERY
```

Key rules:

```text
>=3 usable observations in one unresolved Track
>=2 supporting observations
NORMAL_TRACK_MEDIAN = 0.74
RISKY_TRACK_MEDIAN = 0.79
STRONG_TRACK_MEDIAN = 0.84
winner margin >= 0.07
cannot-link / Face conflict fail closed
```

## Shot-presence Pass 2

Module:

```text
engine/app/character_shot_presence_v101.py
```

Source:

```text
V10_1_SHOT_FRAGMENT_AGGREGATION
```

Body/side/back path:

```text
REID_STRONG = 0.84
REID_SUPPORTED = 0.74
RISKY_REID_SUPPORTED = 0.80
MIN_SHOT_SUPPORT_OBSERVATIONS = 3
MIN_SHOT_SUPPORT_TIMESTAMPS = 3
MIN_SHOT_MEDIAN = 0.76
WINNER_MARGIN = 0.075
```

Known-Face presence path after the 2026-08-27 second real-video rerun:

```text
FACE_SUPPORTED = 0.40
FACE_STRONG = 0.50
FACE_PAIR_MIN_SCORE = 0.76
moderate Face: >=2 current-Shot observations + >=2 timestamps
Face comparison: supported by >=2 independent confirmed Gallery Shots
one very strong Face may still recover immediately
Face-supported identities are ranked before synthetic-body ReID for close-up fallbacks
hard Face conflict requires consistent conflict across >=2 Gallery Shots with no positive Face support
```

This Face path answers only “does this already-confirmed Character appear in this Shot?”. It does not seed identity and does not make Face mandatory.

## Why the latest patch exists

The first fragment-recovery rerun improved some rows but did not complete binding:

```text
SHOT 0006: old woman close-up became correctly bound
SHOT 0007: young woman partial/body view became correctly bound
SHOT 0002: young woman clear face close-up still unbound
SHOT 0004: old + young visible, young woman still missing
```

That result narrows the remaining defect to the known-Face/close-up presence branch rather than global identity classification or generic body-fragment aggregation.

The old Pass-2 Face positive threshold (`0.52`) was stricter than the project’s earlier real-video SFace experience, and one bad Gallery Face crop could previously veto a whole identity. The current implementation uses repeated moderate Face support plus cross-Gallery consistency instead of blindly lowering body/ReID thresholds.

## Recovery persistence

Recovered Track provenance is stored at:

```text
CharacterTrack.evidence_json.identity_recovery
```

Pass 2 can include:

```text
source
target_candidate_id
shot_id
score
observation_count
support_count
face_support_count
strong_face_support
policy
```

Identity confidence and Shot-presence confidence remain separate. Recovered-only Shot bindings use the strongest validated recovery score.

## Final Character Gate

Formal materialization remains fail-closed:

```text
identity_status == RESOLVED
resolver in formal allow-list
confirmed_gallery_shots >= 3
confirmed_gallery_images >= 3
final_asset_eligible is not false
```

Face visibility is not required.

## Asset Workspace contract

```text
evidence_by_shot.characters
= RESOLVED Character evidence only

evidence_by_shot.character_diagnostics
= UNRESOLVED diagnostics only
```

The workspace reads the actual per-Track recovery source. UNRESOLVED diagnostics never become Final suggestions.

## Character Gallery labels

Gallery `shot_id` is UUID-based. UI labels are resolved from real `v2_shots.ordinal`; UUID suffixes are never treated as Shot numbers.

## Current key modules

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
engine/app/asset_routes_v3.py
frontend/src/components/CharacterPersonGalleryV10.vue
frontend/src/types/studio.ts
```

Compatibility filenames do not imply active algorithm version.

## Validation state

```text
Global Character identity classification: working on current real sample
Pass-1 Track recovery: implemented
Pass-2 body/fragment aggregation: implemented and improved SHOT 0006/0007 in real rerun
Repeated moderate known-Face presence patch: implemented, needs next real rerun
Per-Track recovery provenance: implemented
Final Gate: implemented
Whole repository CI: not green
```

Before the latest Face patch, backend full-test summary was:

```text
28 failed, 176 passed, 1 skipped
```

The existing failures are still repository-level legacy/runtime/environment categories. Do not claim all tests pass. CI for the newest Face patch may still be pending when this manifest is read.

## Next real-video acceptance

A fresh asset extraction is mandatory; old Runs do not auto-rebind.

Priority rows:

```text
SHOT 0002 → should bind 人物002
SHOT 0004 → should bind 人物001 + 人物002
SHOT 0006 → should remain 人物001
SHOT 0007 → should remain 人物002
SHOT 0009 → verify all actually visible known Characters
```

If 0002/0004 still miss after this patch, inspect whether YuNet produced repeated high-quality Face observations and inspect `identity_recovery.face_support_count` before changing any more thresholds.
