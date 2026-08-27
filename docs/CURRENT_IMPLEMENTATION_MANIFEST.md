# AI Drama Studio — Current Implementation Manifest

> Purpose: give a new conversation one compact, code-aligned manifest before it reads historical Feature documents.
>
> Last synchronized: **2026-08-27 13:35 +08:00**

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
Face role: optional support / high-quality conflict signal
Final Gate: confirmed formal RESOLVED identity only
```

## Executable wiring

```text
content_analysis_v2
→ character_visual_v2.analyze_characters
→ character_runtime_v6.analyze_characters
→ character_observation_v10.detect_observations
→ character_tracking_v10.build_tracks
→ character_identity_v101.resolve_global_identities
→ character_shot_binding_v101.recover_unresolved_tracks
   # Pass 1: one repeatedly-supported unresolved Track
→ character_shot_presence_v101.recover_fragmented_shot_presence
   # Pass 2: aggregate remaining short Track fragments inside one Shot
→ character_evidence_store_v10.update_person_evidence_classification
→ character_persistence_v6.persist_results_v6
   └ persist exact per-Track identity_recovery provenance
→ asset_final_gate_v10.apply_analysis_to_assets
   └ recovered-only Shot uses recovery score as Shot-presence confidence
→ Character / ShotCharacterBinding
→ asset_routes_v3 workspace response
→ asset_workspace_character_v101 decorator
   ├ RESOLVED → evidence_by_shot.characters
   └ UNRESOLVED → evidence_by_shot.character_diagnostics
```

## Identity confirmation

Formal new-identity creation remains unchanged and fail-closed:

```text
>=3 independent Shots
>=3 model-usable Person Images
stable cross-Shot Person-ReID class
unique identity result
same-sample cannot-link preserved
no high-quality Face hard conflict
```

Strong contaminated/substantial partial crops can seed only with stricter confirmation. Weak partial crops are evidence/attach-only.

Neither Shot recovery pass can create a new Character.

## Shot-presence recovery — Pass 1

Module:

```text
engine/app/character_shot_binding_v101.py
```

```text
UNRESOLVED Track
→ compare repeated observations to all RESOLVED identity galleries
→ >=3 usable observations
→ repeated support
→ unique winner + margin
→ cannot-link / Face conflict fail closed
→ attach Track to existing identity only
```

Source:

```text
V10_1_TRACK_KNOWN_IDENTITY_RECOVERY
```

## Shot-presence recovery — Pass 2

Real-video regression showed that one visible person can be fragmented into several 1–2 observation Tracks. Those fragments cannot satisfy Pass 1 individually even when the global Character classes are already correct.

Module:

```text
engine/app/character_shot_presence_v101.py
```

```text
remaining short unresolved Track fragments
→ per-observation comparison to confirmed galleries
→ Person-ReID primary
→ clothing/body support
→ optional strong high-quality Face positive support
→ unique known-Character winner per fragment
→ aggregate mutually-compatible fragments by (Shot, Character)
→ body-only recovery requires >=3 support observations AND >=3 timestamps
→ cannot-link / high-quality Face conflict fail closed
→ attach fragments to existing RESOLVED identity only
```

Source:

```text
V10_1_SHOT_FRAGMENT_AGGREGATION
```

Current key thresholds:

```text
REID_STRONG = 0.84
REID_SUPPORTED = 0.74
RISKY_REID_SUPPORTED = 0.80
FACE_STRONG = 0.52
FACE_POSITIVE_MIN_SCORE = 0.76
WINNER_MARGIN = 0.075
MIN_SHOT_SUPPORT_OBSERVATIONS = 3
MIN_SHOT_SUPPORT_TIMESTAMPS = 3
MIN_SHOT_MEDIAN = 0.76
```

Strong Face may confirm **presence of an already-known Character**. Face remains optional and cannot create a new identity.

## Recovery persistence

Each recovered Track persists its actual source:

```text
CharacterTrack.evidence_json.identity_recovery = {
  source,
  target_candidate_id,
  shot_id,
  score,
  observation_count,
  ...pass-specific diagnostics,
  policy
}
```

Fragment aggregation can additionally record:

```text
support_count
strong_face_support
```

Candidate summaries retain `track_recovery_*`; fragment recovery additionally exposes `shot_fragment_recovery_count` / policy metadata.

## Identity confidence vs Shot presence

```text
normal/direct Track in Shot
→ ShotCharacterBinding.confidence = candidate identity confidence fallback

recovered-only Track(s) in Shot
→ ShotCharacterBinding.confidence = strongest validated recovery score
```

Multiple fragments of one Character in one Shot materialize only one Final binding. No DB migration is required.

## Final Character materialization

Formal V10/V10.1 gate requires:

```text
identity_status == RESOLVED
formal resolver allow-list
confirmed_gallery_shots >= 3
confirmed_gallery_images >= 3
final_asset_eligible is not false
```

Face visibility is not required.

## Asset Workspace Character evidence

```text
evidence_by_shot.characters
= RESOLVED Character evidence only

evidence_by_shot.character_diagnostics
= UNRESOLVED diagnostics only
= no final_asset_id
= no Final-binding confidence
```

The V10.1 adapter now reports the **actual recovery source from the exact Track**. Fragment-recovered evidence therefore reports `V10_1_SHOT_FRAGMENT_AGGREGATION` instead of the older hard-coded Track source.

## Character Gallery labels

Gallery `shot_id` values are UUID-based ids, not ordinal numbers. The previous frontend incorrectly displayed trailing UUID digits as `SHOT ####`.

Current behavior:

```text
character_gallery_routes_v10
→ resolve shot_id against v2_shots
→ return shot_ordinal / episode_id / episode_order
→ CharacterPersonGalleryV10 renders SHOT #### from shot_ordinal
```

This is display-only and does not change identity/binding logic.

## Fixed model package

```text
YOLOX person detection
YoutuReID person re-identification
YuNet face detection
SFace face embedding/support
```

V10.1 reuses the V10 model package.

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
engine/app/character_shot_binding_v101.py
engine/app/character_shot_presence_v101.py
engine/app/character_persistence_v6.py
engine/app/character_gallery_v10.py
engine/app/character_gallery_routes_v10.py
engine/app/character_evidence_store_v10.py
engine/app/asset_final_gate_v10.py
engine/app/asset_final_gate_v9.py
engine/app/asset_workspace_v3.py
engine/app/asset_workspace_character_v101.py
engine/app/asset_routes_v3.py
frontend/src/components/CharacterPersonGalleryV10.vue
frontend/src/types/studio.ts
```

Do not infer the formal algorithm version from compatibility filenames.

## Real-video regression target

2026-08-27 screenshots confirmed global Character classification was correct while Shot-presence recall was insufficient. Priority rows for the next rerun:

```text
SHOT 0002: young woman should bind
SHOT 0004: old woman + young woman should both bind
SHOT 0006: old woman close-up should bind
SHOT 0007: young woman partial/body view should bind
SHOT 0009: verify both visible known Characters
```

Old Runs do not auto-gain new Track recovery metadata or bindings. A fresh asset extraction is mandatory.

## Current validation state

```text
Character V10.1 identity classification: implemented
Risky-view identity creation: implemented
Pass-1 known-identity Track recovery: implemented
Pass-2 fragmented Shot presence recovery: implemented
Optional strong-Face known-presence support: implemented
Per-Track recovery provenance: implemented
Shot-presence confidence separation: implemented
Face-optional workspace evidence: implemented
RESOLVED/UNRESOLVED workspace split: implemented
Real Shot ordinal Gallery label: implemented
V10/V10.1 Final Gate: implemented
Real Windows rerun after fragment recovery: pending
Whole repository CI: not green
```

Latest backend full-test summary after adding the fragment recovery tests was:

```text
28 failed, 176 passed, 1 skipped
```

The new fragment test file was not among failures. Backend compile and FastAPI import passed. Existing failures remain in legacy/runtime/environment categories; frontend build still has the known vue-tsc/TypeScript compatibility failure.

## New-conversation guardrail

Before changing Character logic, verify:

```text
character_runtime_v6 calls both recovery passes in order
character_persistence_v6 persists identity_recovery
asset_final_gate_v10 includes resolver v10.1
asset_workspace_character_v101 reads actual recovery source
Character Gallery uses real v2_shots.ordinal
```

If code differs, reconcile this manifest and `PROJECT_STATE.md` before continuing.

## Current Character documents

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/ASSET_CHARACTER_RECOGNITION_V10_1.md
latest docs/sessions/... handoff
```
