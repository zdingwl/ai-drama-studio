# F05 — 资产内容分析（Reference Video V2 / Character V10.1）

> **Current status:** IMPLEMENTED for Character / Scene evidence path; Character V10.1 latest Shot Binding change still needs real Windows-video regression.
>
> This document supersedes the old Character V1 / HOG / 3-frame / ASR-in-F05 description.

## 1. F05 current responsibility

F05/03 资产 does not try to convert the whole original video into a giant textual shot report.

It extracts AI Evidence that must be explicitly controlled or bound for later remake production:

```text
Character Candidate / Track / Person Evidence
Scene Candidate / Shot Scene Evidence
Key Prop Candidate / Shot Prop Evidence
```

Source Dialogue / Speaker processing belongs to the later content-script workflow. Historical Speaker/Dialogue tables/helpers may still exist for compatibility, but the current asset run does not treat them as the main F05 output.

Reference Video itself keeps action, framing, movement, camera motion, and most spatial relationships.

## 2. Run scope

Asset analysis is Project-level and reads all current Shots in `Episode.sort_order` order.

Every analysis creates a new:

```text
v2_content_analysis_runs
```

A new run becomes current only after the full analysis succeeds. Old runs are retained.

Code changes do **not** mutate an old Run in place. To validate new Character identity or Shot Binding behavior, rerun asset extraction.

## 3. Character V10.1 formal pipeline

```text
Current Shot / Reference Clip
↓
YOLOX Person Detection (~12fps bounded sampling)
↓
one detected person → one isolated Person Instance crop
↓
Capture every model-usable Person Evidence crop
↓
separated feature channels
  YoutuReID = primary Person identity model
  clothing_upper / clothing_lower = support
  body_hist / body_structure = support
  YuNet/SFace Face = optional support / conflict
↓
Mature MOT organizes temporal Tracks
↓
Project-level model classification
↓
RESOLVED identity classes + UNRESOLVED evidence
↓
V10.1 known-identity Track recovery
↓
persist CharacterCandidate / CharacterTrack
↓
Final Gate
↓
Character + ShotCharacterBinding
```

Formal identifiers:

```text
runtime profile: character-v10.1-capture-first-model-classification
asset profile: f05-assets-v10.1-person-evidence-model-classification
resolver: person-evidence-model-classifier-v10.1
```

## 4. Person Evidence first, identity second

F05 must not discard a real person simply because Face is not visible or the crop condition is imperfect.

Model-usable classes include:

```text
CLEAN
OCCLUDED
CONTAMINATED
PARTIAL
```

Rules:

- Every eligible Person Instance is captured before classification.
- Whole-frame identity images are forbidden when multiple people are visible.
- Face is optional.
- YoutuReID is the primary cross-view identity signal.
- Strong contaminated/substantial partial crops may help form a new identity only under stricter cross-Shot confirmation.
- Weak/tiny partial crops remain evidence/attach-only.

## 5. Formal identity confirmation

A new formal V10/V10.1 identity requires at least:

```text
>= 3 independent Shots
>= 3 model-usable Person Images
stable cross-Shot Person-ReID support
unique class
same-sample cannot-link preserved
no high-quality Face hard conflict
```

This deliberately prevents one strong crop, one Face, or one Track from becoming a Final Character by itself.

## 6. Shot-level known-identity recovery

The global resolver is conservative. Therefore a Shot can still contain an unresolved Track even when the person has already been confirmed elsewhere.

V10.1 adds a second pass:

```text
UNRESOLVED Track
→ compare repeated observations to RESOLVED identity galleries
→ >=3 usable observations
→ >=2 supporting observations
→ unique winner with margin
→ fail closed on cannot-link / Face conflict
→ attach whole Track to existing identity
```

This pass only recovers an existing Character's presence in a Shot. It cannot create a new identity.

Formal module:

```text
engine/app/character_shot_binding_v101.py
```

## 7. Character persistence and Final Gate

F05 writes AI Evidence:

```text
v2_character_candidates
v2_character_tracks
Person Evidence files/manifests under analysis/<run_id>/person_evidence
```

Formal V10/V10.1 Final Character gate requires:

```text
identity_status == RESOLVED
formal resolver allow-list
confirmed_gallery_shots >= 3
confirmed_gallery_images >= 3
final_asset_eligible is not false
```

Face visibility is not required for formal V10/V10.1 candidates.

`UNRESOLVED`, unknown resolver, broken/missing status, or insufficient confirmation stays Evidence only.

## 8. Final Shot Binding

`ShotCharacterBinding` is created from persisted Character Tracks that belong to a Final-eligible Character identity.

The important order is:

```text
Global Identity
→ Track recovery
→ persist corrected Candidate/Track membership
→ Final Character materialization
→ ShotCharacterBinding
```

If recovery happened after persistence, the asset page could be correct while the Shot page stayed wrong. V10.1 intentionally performs recovery before persistence/materialization.

## 9. Scene

Scene extraction remains a lighter evidence path than Character identity.

Current implementation groups visually similar **contiguous** Shots within an Episode and tolerates a single visual outlier when the next Shot returns to the same scene context.

Scene Candidate is still AI Evidence, not a guaranteed semantic Scene name.

Formal tables:

```text
v2_scene_candidates
v2_shot_scene_evidence
```

## 10. Key Prop

Formal evidence tables exist:

```text
v2_prop_candidates
v2_shot_prop_evidence
```

If a reliable key-prop model/path is not configured, the system must not fabricate props for completeness.

Generic object detection alone is not enough to decide that an object is a story-critical prop.

## 11. Historical Speaker / Dialogue compatibility

`content_analysis_v2.py` still contains historical `SpeakerSegment`, `AnalysisDialogue`, ASR and mapping helpers for compatibility/future migration.

Do not interpret their presence as the current F05 product contract.

Current product workspace boundary is:

```text
03 Assets: Character / Scene / Key Prop
04 Content Script: ASR / Speaker / Dialogue / structured source script
```

## 12. Current APIs

Compatibility/current asset endpoints include:

```text
GET  /api/models/f05/status
POST /api/models/f05/prepare

POST /api/projects/{project_id}/content-analysis
GET  /api/projects/{project_id}/content-analysis/current
GET  /api/content-analysis/{run_id}

GET /api/content-analysis/characters/{candidate_id}/cover
GET /api/content-analysis/scenes/{candidate_id}/cover
```

The production UI may use task-based asset routes rather than the synchronous compatibility endpoint.

## 13. Fixed Character model package

```text
YOLOX
YoutuReID
YuNet
SFace
```

V10.1 reuses the V10 model package. `content_models_v2.model_status()` may still expose `character-v10-capture-first-model-classification` as the model-package profile while the formal runtime resolver is V10.1.

## 14. Current acceptance focus

On the user's Windows real-video environment, verify:

```text
1. all real people produce Person Evidence when visually usable
2. same-frame people stay separate
3. Final Character count does not inflate with Track/crop count
4. side/back/occluded views attach to the correct existing identity
5. risky views only create identities with strict >=3-Shot support
6. ambiguous evidence stays unresolved
7. Character list and ShotCharacterBinding agree
8. previously wrong Shots now bind to the confirmed Character
9. rerun failure does not destroy the old current Run
10. old Run does not magically change after a code update
```

## 15. Current code map

```text
engine/app/content_analysis_v2.py
engine/app/character_visual_v2.py
engine/app/character_runtime_v6.py
engine/app/character_observation_v10.py
engine/app/character_tracking_v10.py
engine/app/character_identity_v101.py
engine/app/character_shot_binding_v101.py
engine/app/character_evidence_store_v10.py
engine/app/asset_final_gate_v10.py
engine/app/asset_workspace_v3.py
```

For detailed Character V10.1 rules, read:

```text
docs/ASSET_CHARACTER_RECOGNITION_V10_1.md
```
