# AI Drama Studio — Current Implementation Manifest

> Purpose: compact **code-aligned CURRENT manifest** for new conversations.  
> Last synchronized: **2026-08-27 16:22 +08:00**

## Repository baseline

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Architecture: Reference Video V2
FastAPI app version: 2.4.1
```

## Current vs Target — do not merge them

This file is executable CURRENT truth only.

The user has accepted a future Breakdown-first workflow, but it is documented separately at:

```text
docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
```

That Target Plan currently means:

```text
Shot + Reference Clip
→ ASR/OCR/Video Understanding
→ anonymous structured Breakdown Draft
→ Draft-guided Character/Scene/Prop Evidence
→ Global Asset Resolution / Final Bindings
→ fill-back
→ Final Breakdown
```

**The existence of that plan does not mean those modules are implemented.** Current code/wiring below remains authoritative until each target Phase actually lands with tests and acceptance.

## Current Shot / media wiring

FastAPI current routes use:

```text
main.py
→ media_v2.preprocess_episode
→ media_v2.detect_episode_shots
→ studio_v2.Shot
→ shot_revision_v2
→ Reference Clip / thumbnail / keyframes
```

Current `media_v2.detect_episode_shots()` performs:

```text
FFprobe authoritative timing
+ TransNetV2 Shot boundary detection
+ Source-domain Shot boundaries
+ per-Shot Reference Clip rendering
+ thumbnail rendering
+ safe current Shot revision switch
```

Current `Shot` has:

```text
id
episode_id
ordinal
start_us / end_us / duration_us
reference_clip_path
thumbnail_path
keyframes_json
short_description
shot_type
camera_motion
status
```

Current gap vs accepted Target:

```text
anonymous LocalSubject          NOT IMPLEMENTED
ShotSemanticDraft               NOT IMPLEMENTED
structured TimelineEvent        NOT IMPLEMENTED
SceneSegmentDraft               NOT IMPLEMENTED
unified ASR/OCR semantic facts  NOT IMPLEMENTED
Draft-guided asset resolution   NOT IMPLEMENTED
DraftResolution / fill-back     NOT IMPLEMENTED
Final script-style renderer     NOT IMPLEMENTED
```

Historical `shot_detection.py` / `shot_workbench.py` still exist with older F04/F05 naming, but current Reference Video V2 FastAPI wiring uses `media_v2` for preprocess/Shot analysis. Do not reconstruct current architecture from historical feature names alone.

Also, current `transvlm_runtime_v51.py` uses `TransVLM-Qwen3-VL-4B-Instruct` for transition-segment detection/caching. It is **not** a currently implemented semantic breakdown engine.

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

The accepted Breakdown-first plan does **not** change the current Character runtime/gates.

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

Target-only concepts are separate and currently not executable entities:

```text
LocalSubject
ShotSemanticDraft
TimelineEvent
SceneSegmentDraft
DraftResolution
```

Track ownership is no longer the Final Shot-binding source. Target Draft prose is also not allowed to become a Final binding source by itself.

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

The future anonymous Breakdown Draft cannot bypass this contract.

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

## Current Scene / Prop analysis reality

`content_analysis_v2.py` currently provides established Evidence data boundaries:

```text
SceneCandidate
ShotSceneEvidence
PropCandidate
ShotPropEvidence
```

Current Scene candidate generation is still lightweight: it uses Shot thumbnail environment descriptors and Episode-contiguous grouping. It must not be described as the accepted Target final Scene identity resolver.

Current Prop behavior deliberately fails closed: if no reliable configured object/VLM model is available, Prop extraction may return `NOT_CONFIGURED` rather than fabricate assets.

Accepted future Scene/Prop upgrades are TARGET only and live in `BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md`.

## Current Dialogue / ASR reality

`studio_v2.Dialogue` exists as a core entity and `content_analysis_v2` retains some historical/compatibility ASR/Speaker helper structures, but the current formal asset extraction responsibility does not constitute the accepted future unified:

```text
ASR + word timing
Speaker diarization
OCR
active speaker / LocalSubject mapping
anonymous Breakdown timeline
```

Those remain planned Target phases.

## Asset Workspace contract

```text
evidence_by_shot.characters
= RESOLVED Character Shot presence

evidence_by_shot.character_diagnostics
= UNRESOLVED visual diagnostics only
```

For explicit-assignment Runs, `asset_workspace_character_v101` follows the assignment map. A RESOLVED Candidate Track absent from that map cannot silently recreate a Shot suggestion.

Gallery/Evidence comparison UI is diagnostic only and is not a binding source.

## Fixed current Character model package

```text
YOLOX person detection
YoutuReID person re-identification
YuNet face detection
SFace face embedding/support
```

Any ASR/OCR/VLM/open-vocabulary model mentioned in the Target Plan is only a candidate until a later implementation phase explicitly selects, licenses, wires and tests it.

## Current key modules

```text
engine/app/main.py
engine/app/studio_v2.py
engine/app/media_v2.py
engine/app/shot_revision_v2.py
engine/app/shot_edit_routes_v2.py
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

Historical compatibility files not in the formal Character runtime path:

```text
engine/app/character_shot_binding_v101.py
engine/app/character_shot_presence_v101.py
```

Do not infer active algorithm generation from compatibility filenames.

## Current validation state

```text
01 Project/Episode import/order: implemented
02 Preprocess: implemented
02 Shot detection + Reference Clip: implemented
02 anonymous structured Breakdown Draft: NOT IMPLEMENTED / TARGET
02 SceneSegment/TimelineEvent: NOT IMPLEMENTED / TARGET

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
Windows real-video SHOT 0001–0009 Character acceptance: pending

Draft-guided Character integration: NOT IMPLEMENTED / TARGET
Target semantic Scene resolver: NOT IMPLEMENTED / TARGET
Targeted Prop detector/tracker pipeline: NOT IMPLEMENTED / TARGET
Draft → Final Asset fill-back: NOT IMPLEMENTED / TARGET
Final standard/international Breakdown renderer: NOT IMPLEMENTED / TARGET
Whole repository CI: not green
```

## Accepted Target phase pointer

Do not implement ad hoc from conversation history. Use the frozen phase order in:

```text
docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
```

Current accepted order:

```text
P0 docs/contract
P1 Draft data contract ADD-only
P2 ASR/OCR/VLM anonymous Draft sidecar
P3 02 拉片 structured Draft UI
P4 Draft-guided Scene / Prop evidence
P5 Draft ↔ Character safe integration after current V10.1 baseline acceptance
P6 Final fill-back + renderers
P7 downstream remake integration
```

## CI reality

Latest known backend CI after the explicit assignment work:

```text
28 failed, 187 passed, 1 skipped
```

Backend compile and FastAPI import pass. The explicit Shot assignment tests, explicit Final Gate tests and explicit workspace assignment test are not among failures. Existing failures remain legacy/runtime/environment categories (`cv2`, `trackers`, FFmpeg and obsolete historical assertions).

Frontend CI still has the existing `vue-tsc` / TypeScript package compatibility failure.

The current documentation-only Breakdown-first planning work changes no test/runtime result.

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

Before implementing any Breakdown-first Phase verify:

```text
read docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
identify one explicit Phase only
check current Shot/media/content-analysis wiring
preserve integer microseconds + shot_id + Reference Clip
use ADD-only compatibility first
keep semantic Draft separate from Final Asset/Binding
update CURRENT docs only after code/tests/acceptance exist
```

## Next Windows Character acceptance

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
