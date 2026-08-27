# AI Drama Studio — Current Implementation Manifest

> Purpose: compact code-aligned manifest for new conversations.  
> Last synchronized: **2026-08-27 14:59 +08:00**

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
Face role: optional identity support / known-identity Shot presence / high-quality conflict
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
→ character_shot_presence_v101.recover_fragmented_shot_presence
→ character_evidence_store_v10.update_person_evidence_classification
→ character_persistence_v6.persist_results_v6
→ asset_final_gate_v10.apply_analysis_to_assets
→ Character / ShotCharacterBinding
→ asset_routes_v3
→ asset_workspace_character_v101
```

## New identity confirmation

Formal identity creation stays fail-closed:

```text
>=3 independent Shots
>=3 model-usable Person Images
stable cross-Shot Person-ReID class
unique identity result
same-sample cannot-link preserved
no high-quality Face hard conflict
```

Neither Shot recovery pass can create a new Character.

## Shot-presence recovery

Pass 1:

```text
engine/app/character_shot_binding_v101.py
V10_1_TRACK_KNOWN_IDENTITY_RECOVERY
```

Repeated evidence inside one unresolved Track may attach the whole Track to an already-confirmed identity. Key gates include >=3 Track observations, >=2 supporting observations, unique winner + margin, cannot-link/Face conflict fail closed.

Pass 2:

```text
engine/app/character_shot_presence_v101.py
V10_1_SHOT_FRAGMENT_AGGREGATION
```

Remaining short fragments are aggregated by Shot and known Character. Body/side/back needs repeated timestamps/support; close-up Face may confirm only an already-known identity. Current Face presence patch uses `FACE_SUPPORTED=0.40`, `FACE_STRONG=0.50`, `FACE_PAIR_MIN_SCORE=0.76`, repeated moderate current-Shot Face support, independent Gallery-Shot support, and consistent multi-Gallery Face conflict before hard veto.

## Recovery persistence / confidence

```text
CharacterTrack.evidence_json.identity_recovery
```

stores the exact recovery source, target, Shot, score and pass-specific diagnostics.

```text
direct Track in Shot
→ binding confidence falls back to global identity confidence

recovered-only Shot
→ binding confidence uses strongest validated recovery score
```

## Final Character gate

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
```

UNRESOLVED diagnostics never become Final suggestions.

## Character Evidence visualization contract

Three layers are explicitly different:

```text
CharacterTrack Shot membership
= exhaustive immutable AI identity evidence

V10 Gallery
= bounded/diversified identity representative subset

ShotCharacterBinding
= editable Final binding
```

Formal read API:

```text
GET /api/content-analysis/characters/{candidate_id}/gallery
```

returns:

```text
evidence_shot_count
evidence_shots[]          # exhaustive CharacterTrack Shot set
gallery_image_count       # true bounded Gallery images
images[]                  # visual evidence covering every evidence Shot
```

For an evidence Shot omitted from the bounded Gallery, `images[]` contains one genuine on-demand persisted Track representative crop:

```text
GET /api/content-analysis/characters/{candidate_id}/evidence-shot/{shot_id}
```

`source_kind` distinguishes:

```text
gallery
track_representative
```

This prevents “not selected into bounded Gallery” from being misread as “no AI evidence”.

## Asset library Evidence-vs-Final comparison

Character asset detail now loads **all** `source_candidate_ids` and compares AI evidence Shots with Final `shot_ids`.

Each Shot card shows:

```text
whole-Shot context thumbnail
+ Person Evidence crop(s)
+ one status
```

Status contract:

```text
Evidence + Final = Track evidence and Final binding both exist
AI ONLY         = Track evidence exists, Final binding missing
FINAL ONLY      = Final binding exists, source Candidate has no Track evidence
```

`AI ONLY` is therefore the direct UI signal for a likely Shot-binding recall failure.

## Character Gallery UI

`CharacterPersonGalleryV10.vue` groups by real Shot and displays:

```text
Evidence Shots
Gallery 代表图
可视证据图
```

Fallback Track crops are labelled `Track 代表图`. Shot labels always come from real `v2_shots.ordinal`, never UUID suffixes.

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

Do not infer active algorithm generation from historical compatibility filenames.

## Current validation state

```text
Character V10.1 identity classification: implemented
Pass-1 known identity recovery: implemented
Pass-2 fragmented/Face known-presence recovery: implemented
Per-Track provenance: implemented
Shot-presence confidence separation: implemented
Face-optional workspace evidence: implemented
RESOLVED/UNRESOLVED workspace split: implemented
Real Shot ordinal Gallery labels: implemented
Exhaustive CharacterTrack evidence-Shot API: implemented
On-demand Track representative crop: implemented
Gallery grouped by Shot: implemented
Evidence-vs-Final Asset library comparison: implemented
Real Windows UI + remaining binding regression: pending
Whole repository CI: not green
```

Latest backend CI after this work:

```text
28 failed, 179 passed, 1 skipped
```

The new exhaustive-evidence test is not among failures. Compile and FastAPI import pass. Existing failures remain legacy/runtime/environment categories (`cv2`, `trackers`, FFmpeg and obsolete historical assertions).

Frontend CI still fails before project type checking at the existing `vue-tsc` / TypeScript package incompatibility (`typescript` does not export `./lib/tsc`).

## New-conversation guardrail

Before changing Character/binding behavior verify:

```text
character_runtime_v6 runs both recovery passes
character_persistence_v6 persists identity_recovery
asset_final_gate_v10 contains resolver v10.1
asset_workspace_character_v101 keeps RESOLVED and diagnostics separate
character_gallery_routes_v10 distinguishes exhaustive Track evidence from bounded Gallery
AssetReviewMatrixV4 compares Evidence and Final without treating Shot thumbnail as a Person crop
```

If code differs, reconcile this manifest and `PROJECT_STATE.md` before continuing.
