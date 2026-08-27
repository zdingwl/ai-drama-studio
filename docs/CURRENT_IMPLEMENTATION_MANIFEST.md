# AI Drama Studio — Current Implementation Manifest

> Purpose: compact **code-aligned CURRENT manifest** for new conversations.  
> Last synchronized: **2026-08-27 20:15 +09:00**

## Repository baseline

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Architecture: Reference Video V2
FastAPI app version: 2.4.1
Formal Character runtime: Character V10.1
Breakdown-first infrastructure: P1 COMPLETE
```

## Current vs Target — do not merge them

This file is executable CURRENT truth only.

The accepted Breakdown-first workflow is documented at:

```text
docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
```

Target product flow:

```text
Shot + Reference Clip
→ ASR/OCR/Video Understanding
→ anonymous structured Breakdown Draft
→ Draft-guided Character/Scene/Prop Evidence
→ Global Asset Resolution / Final Bindings
→ fill-back
→ Final Breakdown
```

Current implementation has now completed **P1**, which means the anonymous Breakdown **data/runtime contract** exists and is protected by tests. It does **not** mean ASR/OCR/VLM semantic inference or the final Breakdown UI is implemented.

```text
P1 storage/lifecycle/validator/read API/history/STALE = IMPLEMENTED
P2 ASR/OCR/VLM Draft generation                     = NOT IMPLEMENTED
P3 structured 02 拉片 UI                           = NOT IMPLEMENTED
P4+ Draft-guided assets/fill-back/renderers         = NOT IMPLEMENTED
```

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

Historical `shot_detection.py` / `shot_workbench.py` still exist with older F04/F05 naming, but current Reference Video V2 FastAPI wiring uses `media_v2` for preprocess/Shot analysis. Do not reconstruct current architecture from historical feature names alone.

Current `transvlm_runtime_v51.py` uses a Qwen3-VL-based TransVLM route for transition detection/caching. It is **not** the semantic Breakdown engine planned for P2.

## Breakdown P1 — executable infrastructure

Formal modules:

```text
engine/app/breakdown_models_v1.py
engine/app/breakdown_service_v1.py
engine/app/breakdown_validator_v1.py
engine/app/breakdown_serializer_v1.py
engine/app/breakdown_routes_v1.py
engine/app/shot_revision_v2.py              # P1.6 automatic STALE integration
```

P1 uses the formal Reference Video V2 data domain:

```text
engine.app.studio_v2.Base
+ data_v2/studio_v2.sqlite3
```

It does **not** reconnect to historical `core.database/app.db` / `shot_workbench.py`.

### P1 ADD-only tables

```text
v2_breakdown_runs
v2_scene_segment_drafts
v2_shot_semantic_drafts
v2_local_subjects
v2_shot_local_subjects
v2_timeline_events
v2_timeline_event_subjects
v2_draft_prop_hints
v2_draft_prop_occurrences
v2_breakdown_evidence_links
```

Resolution tables remain deferred to later phases as allowed by the frozen Contract; P1 does not add Final Asset foreign keys to Draft rows.

### P1 data semantics

```text
BreakdownRun
= one immutable anonymous semantic evidence snapshot for an Episode ShotRevision

SceneSegmentDraft
= story/continuity segment, not Final Scene

ShotSemanticDraft
= structured understanding of one ShotRevisionItem

LocalSubject
= anonymous local person such as 人物A/人物B, not Character

TimelineEvent
= timed VISUAL/ACTION/DIALOGUE/OCR/AUDIO_EVENT semantic event

DraftPropHint
= later-search hint, not Final Prop
```

Core historical anchors:

```text
BreakdownRun.source_shot_revision_id
→ v2_shot_revisions.id

ShotSemanticDraft.source_shot_revision_item_id
→ v2_shot_revision_items.id

ShotSemanticDraft.source_shot_id_snapshot
= plain historical snapshot, not Current v2_shots FK
```

This preserves old Draft + old Reference Clip readability after Current Shots are replaced.

### P1 Run lifecycle

Implemented states:

```text
PROCESSING
READY
READY_WITH_WARNINGS
FAILED
STALE
```

Rules:

```text
create run → freeze current ShotRevision
validator must pass before READY
failed run never replaces old Current
successful publish atomically switches Current Breakdown
warnings publish READY_WITH_WARNINGS
```

`publish_breakdown_run()` calls the real P1 validator; caller-provided booleans cannot bypass validation.

### P1 read-only API / serializer

Implemented read surfaces include:

```text
Episode Breakdown Run history
Episode current Breakdown
Breakdown by Run ID
historical ShotRevisionItem provenance
historical Reference Clip URL
```

Read-only access to an old/pre-P1 Episode does not silently create a BASELINE ShotRevision or BreakdownRun.

### P1.6 ShotRevision → STALE

Any operation that produces a new Current `ShotRevision` automatically marks active Breakdown Runs from older revisions `STALE`:

```text
auto rerun
manual boundary edit
split
merge
record_manual_revision
restore
```

The Current ShotRevision switch and Breakdown STALE mutation share the **same database transaction**. If the ShotRevision transaction rolls back, the Breakdown status rolls back too.

STALE does not delete historical data:

```text
old BreakdownRun remains readable
old Scene/Shot/Subject/Event/Prop Draft rows remain readable
old ShotRevision remains readable
old ShotRevisionItem remains readable
old Reference Clip remains readable
```

No ordinal/time heuristic automatically migrates old Draft into a new ShotRevision.

## Breakdown P1 validator boundary

P1 validation enforces the frozen contract, including:

```text
Run ↔ Episode ↔ ShotRevision consistency
one ShotSemanticDraft per source ShotRevisionItem
SceneSegment membership/order/time coverage
LocalSubject run/segment ownership
ShotLocalSubject ownership/time consistency
TimelineEvent source/relative timing consistency
TimelineEvent participant ownership
Prop hint/occurrence ownership/time consistency
EvidenceLink ownership/run consistency
confidence range checks
no Final Character/Scene/Prop leakage into Draft
Current READY source consistency
```

A historical `STALE` Run remains structurally readable/valid; it simply cannot masquerade as the Episode Current Breakdown.

## Breakdown P1 compatibility acceptance

P1.7 added a durable Windows CI gate:

```text
job: breakdown-p1-windows
runner: windows-latest
```

It runs the focused P1 lifecycle/validator/history/STALE/compatibility suite.

Acceptance explicitly covers:

```text
fresh empty database init
init_database() idempotence
ADD-only creation of ShotRevision + Breakdown tables
pre-P1 historical V2 Project/Episode/Shot database upgrade
Windows paths containing spaces/Chinese text
legacy Project/Episode/Shot/reference clip remains readable
read-only Breakdown access performs no hidden writes
```

P1.7 PR acceptance result:

```text
Windows focused P1 suite: 32/32 PASS
Ubuntu full pytest: 28 failed, 219 passed, 1 skipped
```

The 28 Ubuntu failures are the same pre-existing repository categories; P1.7 introduced no new failure category.

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

Breakdown P1 does **not** change Character runtime/gates.

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

Those modules remain for historical compatibility/tests only.

## Semantic layers

```text
ShotRevision / ShotRevisionItem / Reference Clip
= media fact/history

BreakdownRun / SceneSegmentDraft / ShotSemanticDraft / LocalSubject / TimelineEvent
= anonymous semantic evidence

Observation / Person Evidence / CharacterTrack
= visual identity evidence

CharacterCandidate / Identity Class
= project-level person identity

Shot Character Assignment
= known Character presence in one Shot

Character / ShotCharacterBinding
= editable Final asset / binding
```

The layers are intentionally separate. P1 Draft text/hints cannot create a Character or write Final Shot bindings.

## New identity confirmation

Formal Character identity creation remains fail-closed:

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

Same-sample cannot-link is also a Shot occupancy constraint. Ambiguous winner, insufficient repetition or repeated high-quality Face conflict remains unassigned.

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

An explicit empty assignment list does **not** fall back to Candidate Track membership. Historical persisted Runs without `shot_assignment_version` retain the old Track-derived fallback.

## Current Scene / Prop analysis reality

`content_analysis_v2.py` currently provides established Evidence data boundaries:

```text
SceneCandidate
ShotSceneEvidence
PropCandidate
ShotPropEvidence
```

Current Scene candidate generation is still lightweight; it is not the target final semantic Scene resolver.

Current Prop behavior remains fail-closed: without a reliable configured object/VLM model, Prop extraction may return `NOT_CONFIGURED` rather than fabricate assets.

P1 Draft Scene/Prop hints are separate from these Final/candidate layers and do not make P4 implemented.

## Current Dialogue / ASR reality

`studio_v2.Dialogue` exists and historical/compatibility ASR/Speaker helpers exist, but the formal Breakdown pipeline still does **not** implement:

```text
ASR + word timing
Speaker diarization
OCR observations
active speaker / LocalSubject mapping
VLM semantic Draft generation
```

These are P2 concerns.

## Current key modules

```text
engine/app/main.py
engine/app/studio_v2.py
engine/app/media_v2.py
engine/app/shot_revision_v2.py
engine/app/shot_edit_routes_v2.py
engine/app/content_analysis_v2.py

engine/app/breakdown_models_v1.py
engine/app/breakdown_service_v1.py
engine/app/breakdown_validator_v1.py
engine/app/breakdown_serializer_v1.py
engine/app/breakdown_routes_v1.py

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

## Current validation state

```text
01 Project/Episode import/order: IMPLEMENTED
02 Preprocess: IMPLEMENTED
02 Shot detection + Reference Clip: IMPLEMENTED
02 ShotRevision/manual edit/history: IMPLEMENTED

Breakdown P1.1 ADD-only data model: IMPLEMENTED
Breakdown P1.2 Run lifecycle: IMPLEMENTED
Breakdown P1.3 fail-closed validator: IMPLEMENTED
Breakdown P1.4 read-only serializer/API: IMPLEMENTED
Breakdown P1.5 focused/compatibility tests: IMPLEMENTED
Breakdown P1.6 ShotRevision automatic STALE integration: IMPLEMENTED
Breakdown P1.7 docs + Windows empty/historical compatibility acceptance: IMPLEMENTED

P2 ASR/OCR/VLM anonymous Draft generation: NOT IMPLEMENTED
P3 02 拉片 structured Draft UI: NOT IMPLEMENTED
P4 Draft-guided Scene/Prop evidence: NOT IMPLEMENTED
P5 Draft ↔ Character safe integration: NOT IMPLEMENTED
P6 Final fill-back/renderers: NOT IMPLEMENTED
P7 downstream remake integration: NOT IMPLEMENTED

Character V10.1 global identity classification: IMPLEMENTED
Independent Shot × known-Character assignment: IMPLEMENTED
Final Gate explicit assignment consumption: IMPLEMENTED
Historical old-Run fallback: PRESERVED
Windows real-video SHOT 0001–0009 Character acceptance: separate/pending

Whole repository CI: NOT GREEN
```

## Accepted Target phase pointer

Do not implement ad hoc from conversation history. Use the frozen phase order in:

```text
docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
```

Current phase status:

```text
P0 planning/contracts                            = COMPLETE
P1 Draft data/runtime contract + compatibility   = COMPLETE
P2 ASR/OCR/VLM anonymous Draft sidecar           = NEXT / PLANNED
P3 02 拉片 structured Draft UI                   = PLANNED
P4 Draft-guided Scene / Prop evidence            = PLANNED
P5 Draft ↔ Character safe integration            = PLANNED
P6 Final fill-back + renderers                    = PLANNED
P7 downstream remake integration                 = PLANNED
```

## CI reality

P1.7 acceptance PR baseline:

```text
Ubuntu backend compile: PASS
FastAPI import/version: PASS (AI Drama Studio 2.4.1)
Ubuntu full pytest: 28 failed, 219 passed, 1 skipped
Windows Breakdown P1 focused suite: 32/32 PASS
Frontend build: existing vue-tsc / TypeScript compatibility failure
```

Existing backend failures remain legacy/runtime/environment categories such as missing lightweight-CI `cv2`, missing `trackers`, FFmpeg assumptions, obsolete V6-era assertions and historical Final Gate/workspace expectations.

Do **not** claim the whole repository is green.

## Required new-conversation checks

Before any new Breakdown work:

```text
1. verify main SHA
2. read PROJECT_STATE + this manifest
3. read BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN
4. read BREAKDOWN_DRAFT_DATA_CONTRACT
5. read latest Breakdown session handoff
6. verify current code/tests before changing anything
```

For P2 specifically:

```text
consume P1 entities; do not invent a parallel schema
bind a Run to Current ShotRevision
write only anonymous Draft/Evidence layers
preserve integer microseconds
preserve immutable READY history
never write Final Character/Scene/Prop/Bindings
keep provider metadata/provenance
keep Windows compatibility
```

Before changing Character binding behavior, continue to verify the formal V10.1 runtime and explicit `shot_presence_assignments` path. Do not use P1 Draft prose to bypass identity or assignment gates.
