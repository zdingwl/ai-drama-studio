# AI Drama Studio — Project State

> **Last synchronized:** 2026-08-27 13:35 +08:00  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Branch:** `main`  
> **Architecture:** Reference Video V2  
> **FastAPI app version:** `2.4.1`  
> **Formal character runtime:** Character V10.1

## 1. Current-state source of truth

This document records what the repository actually runs now. It is not a historical plan.

For a new conversation, recover context in this order:

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/CURRENT_IMPLEMENTATION_MANIFEST.md
→ docs/ASSET_CHARACTER_RECOGNITION_V10_1.md
→ current code/tests
→ latest session handoff
```

Before changing Character logic, verify the executable wiring in:

```text
engine/app/character_visual_v2.py
engine/app/character_runtime_v6.py
engine/app/character_identity_v101.py
engine/app/character_shot_binding_v101.py
engine/app/character_shot_presence_v101.py
engine/app/character_persistence_v6.py
engine/app/asset_final_gate_v10.py
engine/app/asset_workspace_character_v101.py
```

Older V1–V10, face-only identity, 2-Shot confirmation, or planned F06 documents are historical unless this file explicitly references them.

## 2. Current product workspaces

```text
01 剧集管理
02 拉片
03 资产
04 内容剧本
05 重制设计
06 生成 / 导出
```

The project is Reference Video driven. Shot + frame-owned Reference Clip is the production unit. `Episode.sort_order` is the formal batch order and heavy model work remains sequential by default.

## 3. Formal Character V10.1 baseline

```text
Runtime profile:
character-v10.1-capture-first-model-classification

Asset profile:
f05-assets-v10.1-person-evidence-model-classification

Resolver:
person-evidence-model-classifier-v10.1
```

V10.1 reuses the fixed V10 model package, so model-package status may still contain a V10 label without meaning the active runtime reverted.

Formal model set:

```text
YOLOX Person Detection
YoutuReID Person Re-identification
YuNet Face Detection
SFace Face embedding/support
```

YoutuReID is the primary identity signal. Clothing/body channels support it. Face is optional support and a high-quality conflict signal; Face is not required for a formal Character.

## 4. Formal Character pipeline

```text
Reference Clip / Shot
↓
YOLOX Person Detection (~12 fps, bounded on long Shots)
↓
every detected person → isolated Person Instance
↓
YoutuReID Person embedding
+ clothing_upper / clothing_lower / body_hist / body_structure
+ optional YuNet/SFace Face evidence
↓
capture/persist model-usable Person Evidence
(CLEAN / OCCLUDED / CONTAMINATED / substantial PARTIAL)
↓
Mature MOT temporal organization
↓
Project-level Person Evidence identity classification
↓
RESOLVED identity classes + UNRESOLVED evidence
↓
Pass 1: known-identity Track recovery
  repeated evidence inside one unresolved Track
↓
Pass 2: known-identity Shot-fragment aggregation
  several short unresolved Track fragments inside one Shot
  + optional strong high-quality Face confirmation
↓
persist exact Track recovery provenance
↓
write Person Evidence identity assignment back
↓
Final Gate
↓
Character + ShotCharacterBinding
↓
Asset Workspace V10.1 evidence adapter
```

Three layers must never be collapsed:

```text
Observation / Person Evidence / Track = visual evidence
Identity Class = cross-Shot person identity
Character = Final project asset
```

Track count, Face count, crop count, or number of fragments must never determine Character cardinality.

## 5. New-identity creation contract

Character V10.1 is capture-first. Image-condition labels describe evidence quality, not whether a real person exists.

A formal new identity requires at least:

```text
>= 3 independent Shots
>= 3 model-usable Person Images
stable cross-Shot Person-ReID consistency
unique identity class
same-sample cannot-link preserved
no high-quality Face hard conflict
```

Strong `CONTAMINATED` / substantial `PARTIAL` evidence can seed only under stricter cross-Shot confirmation. Weak/tiny partial fragments remain evidence/attach-only and cannot create a Character.

## 6. Shot presence recovery — two formal passes

The real-video regression on 2026-08-27 confirmed a specific architecture boundary: the global Character classes were correct, but several Shot rows still missed a visible known Character. The observed examples included:

```text
SHOT 0002  young woman visible, no binding
SHOT 0004  old + young visible, only old woman bound
SHOT 0006  old woman close-up, no binding
SHOT 0007  young woman partial/body view, no binding
SHOT 0009  two-person view, second known Character likely missing
```

This means identity classification can be correct while Shot-presence recall is still insufficient.

### 6.1 Pass 1 — repeated evidence inside one Track

Formal module:

```text
engine/app/character_shot_binding_v101.py
```

Rule:

```text
UNRESOLVED Track
→ compare usable observations with every RESOLVED identity gallery
→ require >=3 observations and repeated support
→ require unique winner + margin
→ cannot-link / high-quality Face conflict fail closed
→ attach whole Track to existing identity
```

Source:

```text
V10_1_TRACK_KNOWN_IDENTITY_RECOVERY
```

Important thresholds remain:

```text
MIN_TRACK_OBSERVATIONS = 3
MIN_SUPPORTING_OBSERVATIONS = 2
NORMAL_TRACK_MEDIAN = 0.74
RISKY_TRACK_MEDIAN = 0.79
STRONG_TRACK_MEDIAN = 0.84
WINNER_MARGIN >= 0.07
```

### 6.2 Pass 2 — fragmented Shot presence aggregation

A short Shot can be split by MOT/classification into several 1–2 observation fragments. Pass 1 cannot recover these because each Track is individually too short. V10.1 now adds a second pass:

```text
remaining UNRESOLVED short Track fragments
→ compare each observation with confirmed identity galleries
→ Person-ReID primary
→ clothing/body support
→ optional strong high-quality Face positive confirmation
→ choose a unique known Character per fragment
→ aggregate mutually-compatible fragments by (Shot, Character)
→ require repeated independent Shot-time support for body-only recovery
→ same-sample cannot-link / high-quality Face conflict fail closed
→ attach supported fragments to that already-RESOLVED Character
```

Formal module:

```text
engine/app/character_shot_presence_v101.py
```

Formal source:

```text
V10_1_SHOT_FRAGMENT_AGGREGATION
```

Current guardrails:

```text
REID_STRONG = 0.84
REID_SUPPORTED = 0.74
RISKY_REID_SUPPORTED = 0.80
FACE_STRONG = 0.52
FACE_POSITIVE_MIN_SCORE = 0.76
WINNER_MARGIN = 0.075
body-only MIN_SHOT_SUPPORT_OBSERVATIONS = 3
body-only MIN_SHOT_SUPPORT_TIMESTAMPS = 3
body-only MIN_SHOT_MEDIAN = 0.76
```

Strong Face is allowed only as a **positive Shot-presence signal for an already-confirmed identity** and requires support from independent gallery Shots. It does not create a new identity and does not make Face mandatory.

### 6.3 Non-negotiable invariants

Both recovery passes:

- never create a new Character;
- only attach evidence to an already independently confirmed `RESOLVED` identity;
- leave ambiguous evidence unresolved;
- preserve same-sample cannot-link;
- fail closed on high-quality Face conflict;
- write provenance to the exact recovered Track before persistence.

## 7. Recovery provenance and Shot confidence

Persisted Track evidence carries:

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

The fragment pass additionally records `support_count` and `strong_face_support`.

Identity confidence and Shot-presence confidence are separate:

```text
Shot contains a direct identity-assigned Track
→ ShotCharacterBinding.confidence = candidate/global identity confidence fallback

Shot is represented only by recovered Track fragment(s)
→ ShotCharacterBinding.confidence = strongest validated recovery score
```

Multiple Track fragments for the same Character in one Shot still materialize one `ShotCharacterBinding`.

No DB migration is required; the existing Track Evidence JSON and binding confidence column carry the new semantics.

## 8. Final Character Gate

Formal V10/V10.1 materialization is fail-closed:

```text
identity_status == RESOLVED
resolver in formal allow-list
confirmed_gallery_shots >= 3
confirmed_gallery_images >= 3
final_asset_eligible is not false
```

`UNRESOLVED`, unknown resolver, insufficient confirmation, or explicit ineligibility never materializes. Face visibility is not required.

Formal entry:

```text
engine/app/asset_final_gate_v10.py
```

The shared materializer in `asset_final_gate_v9.py` consumes per-Track recovery scores for Final Shot binding confidence.

## 9. Asset Workspace Character evidence

Formal workspace responses are decorated by:

```text
engine/app/asset_workspace_character_v101.py
```

Contract:

```text
evidence_by_shot[shot_id].characters
= RESOLVED Character evidence only

evidence_by_shot[shot_id].character_diagnostics
= UNRESOLVED diagnostics only
```

A confirmed front/side/back/body/recovered Track is visible even when `face_visible=false`.

The adapter now preserves the **actual per-Track recovery source**. A fragment-aggregation Shot therefore reports `V10_1_SHOT_FRAGMENT_AGGREGATION` rather than being mislabeled as the older Track-recovery source.

Unresolved diagnostics have no Final asset id or Final-binding confidence and do not contaminate the main frontend Character suggestion.

## 10. Character Gallery Shot labels

A separate UI defect was found while reviewing the real-video screenshots: Gallery cards derived a fake Shot number from the trailing digits of the UUID-based `shot_id`.

That was incorrect because `studio_v2.new_id()` generates UUID ids.

The Gallery API now resolves each immutable `shot_id` against `v2_shots.ordinal` and returns:

```text
shot_ordinal
episode_id
episode_order
```

`CharacterPersonGalleryV10.vue` renders `SHOT ####` from `shot_ordinal`. It no longer interprets UUID suffixes as Shot numbers.

This display fix does not change identity or binding decisions.

## 11. Evidence / Final Asset separation

```text
v2_content_analysis_runs
v2_character_candidates
v2_character_tracks
Person Evidence files/manifests
= immutable AI Evidence / analysis result

Character / Scene / Prop
ShotCharacterBinding / ShotSceneBinding / ShotPropBinding
= Final Asset / Final Binding
```

Old Runs do not automatically gain new recovery metadata or new bindings. Validation of a code change requires a new asset-extraction Run.

## 12. Current Character code map

```text
engine/app/character_visual_v2.py              compatibility facade → V10.1
engine/app/character_runtime_v6.py             formal V10.1 runtime entry
engine/app/character_observation_v10.py        Person detection/capture
engine/app/character_person_evidence_v10.py    evidence policy
engine/app/character_person_features_v9.py     separated feature channels
engine/app/character_tracking_v10.py           temporal tracking
engine/app/character_identity_v10.py           V10 base classifier helpers
engine/app/character_identity_v101.py          formal V10.1 global resolver
engine/app/character_shot_binding_v101.py      pass-1 known-identity Track recovery
engine/app/character_shot_presence_v101.py     pass-2 same-Shot fragment aggregation
engine/app/character_persistence_v6.py         persistence bridge + Track recovery JSON
engine/app/character_gallery_v10.py            classified Person gallery
engine/app/character_gallery_routes_v10.py     gallery API + real Shot ordinal lookup
engine/app/character_evidence_store_v10.py     pre/post-classification evidence store
engine/app/asset_final_gate_v10.py             formal Final Gate entry
engine/app/asset_final_gate_v9.py              shared materializer / Shot confidence
engine/app/asset_workspace_v3.py               legacy Final Asset workspace core
engine/app/asset_workspace_character_v101.py   V10.1 Character evidence adapter
engine/app/asset_routes_v3.py                  workspace routes
frontend/src/components/CharacterPersonGalleryV10.vue
frontend/src/types/studio.ts
```

Compatibility filenames do not imply active algorithm version.

## 13. Current implementation status

```text
01 剧集管理: IMPLEMENTED
02 拉片: IMPLEMENTED; real-media release checks still apply

03 资产:
  Character V10.1 capture-first identity classification implemented
  risky-view identity creation implemented
  pass-1 known-identity Track recovery implemented
  pass-2 fragmented Shot-presence aggregation implemented
  optional strong-Face known-presence support implemented
  exact per-Track recovery provenance implemented
  identity confidence / Shot-presence confidence separation implemented
  face-optional RESOLVED workspace evidence implemented
  RESOLVED vs UNRESOLVED diagnostics separation implemented
  real Gallery Shot ordinal display implemented
  V10/V10.1 fail-closed Final Gate implemented
  NEEDS WINDOWS REAL-VIDEO REGRESSION after latest fragment recovery

04 内容剧本: PLANNED / partial compatibility code exists
05 重制设计: PLANNED
06 生成 / 导出: PLANNED
```

## 14. Current test / CI reality

GitHub Actions is **not globally green**.

For the fragment-presence change, the latest full backend run still fails in the pre-existing repository-level categories, but the new focused test file did not appear among failures and the full summary reached:

```text
28 failed, 176 passed, 1 skipped
```

The new focused coverage locks:

```text
three singleton fragments in one Shot → one known Character can recover
one strong high-quality Face fragment → may confirm presence of an existing identity
one weak body fragment → stays unresolved
same-sample cannot-link → cannot be counted as duplicate support
```

Existing compile and FastAPI import steps pass. Frontend build remains blocked by the existing `vue-tsc` / TypeScript compatibility problem. Other known backend failures remain legacy/runtime/environment related (`cv2`, trackers, FFmpeg/media assumptions and old semantic assertions).

Do not claim the whole repository passes.

## 15. Immediate local acceptance

```text
1. git pull latest main.
2. Restart backend/frontend as needed.
3. Rerun asset extraction; do not reuse the old Analysis Run.
4. Verify Final Character count stays correct first.
5. Recheck SHOT 0002 / 0004 / 0006 / 0007 / 0009.
6. For newly recovered Shots inspect CharacterTrack.evidence_json.identity_recovery.source.
7. Expect fragment cases to report V10_1_SHOT_FRAGMENT_AGGREGATION.
8. If 0002/0006 still fail, inspect Face detection/face_score/SFace evidence before changing ReID thresholds.
9. If 0004/0009 still miss the second person, verify YOLOX created a separate Person Instance; missing detection cannot be repaired by binding logic.
10. If 0007 still fails, inspect fragment support_count / timestamps / winner margin before tuning thresholds.
```

## 16. Documentation rule

A Character code change is incomplete until the active project-state documents and latest session handoff match executable code. Do not mark Character V10.1 `STABLE/FROZEN` until the user accepts the real-video result.
