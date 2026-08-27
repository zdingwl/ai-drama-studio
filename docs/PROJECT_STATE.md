# AI Drama Studio — Project State

> **Last synchronized:** 2026-08-27 14:59 +08:00  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Branch:** `main`  
> **Architecture:** Reference Video V2  
> **FastAPI app version:** `2.4.1`  
> **Formal Character runtime:** Character V10.1

## 1. Current-state source of truth

This file describes what the repository actually runs now. Older V1–V10/F06 plans are historical unless explicitly referenced here.

New-conversation recovery order:

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/CURRENT_IMPLEMENTATION_MANIFEST.md
→ docs/ASSET_CHARACTER_RECOGNITION_V10_1.md
→ current code/tests
→ latest session handoff
```

Before changing Character behavior, inspect at least:

```text
engine/app/character_runtime_v6.py
engine/app/character_identity_v101.py
engine/app/character_shot_binding_v101.py
engine/app/character_shot_presence_v101.py
engine/app/character_persistence_v6.py
engine/app/character_gallery_routes_v10.py
engine/app/asset_final_gate_v10.py
engine/app/asset_workspace_character_v101.py
frontend/src/components/CharacterPersonGalleryV10.vue
frontend/src/components/AssetReviewMatrixV4.vue
```

## 2. Product workspaces

```text
01 剧集管理
02 拉片
03 资产
04 内容剧本
05 重制设计
06 生成 / 导出
```

Shot + frame-owned Reference Clip remains the core production unit. Heavy media/model work remains sequential by default.

## 3. Formal Character V10.1 baseline

```text
Runtime profile: character-v10.1-capture-first-model-classification
Asset profile: f05-assets-v10.1-person-evidence-model-classification
Resolver: person-evidence-model-classifier-v10.1
```

Models:

```text
YOLOX Person Detection
YoutuReID Person Re-identification
YuNet Face Detection
SFace Face embedding/support
```

YoutuReID is the primary new-identity model signal. Face is optional support, may confirm presence of an already-known identity in a Shot, and remains a high-quality conflict signal.

## 4. Formal Character pipeline

```text
Reference Clip / Shot
↓
YOLOX Person Detection + YuNet Face fallback
↓
isolated Person Instance observations
↓
YoutuReID + clothing/body channels + optional SFace
↓
Mature MOT
↓
project-level identity classification
↓
RESOLVED identities + UNRESOLVED evidence
↓
Pass 1: repeated unresolved Track → known identity
↓
Pass 2: same-Shot unresolved fragments / close-up Face → known identity presence
↓
persist exact Track recovery provenance
↓
Final Gate
↓
Character + ShotCharacterBinding
↓
Asset Workspace V10.1 adapter
```

Never collapse these layers:

```text
Observation / Person Evidence / CharacterTrack = immutable AI visual evidence
Identity Class / CharacterCandidate = cross-Shot identity classification
Character = Final project asset
ShotCharacterBinding = editable Final Shot binding
```

## 5. New Character creation stays fail-closed

A formal new Character requires at least:

```text
>=3 independent Shots
>=3 model-usable Person Images
stable cross-Shot Person-ReID consistency
unique identity class
same-sample cannot-link preserved
no high-quality Face hard conflict
```

Strong contaminated/substantial partial crops may seed only under stricter confirmation. Weak/tiny partials remain attach-only. Neither Shot-presence recovery pass creates a new Character.

## 6. Pass 1 — repeated Track recovery

Module:

```text
engine/app/character_shot_binding_v101.py
```

Source:

```text
V10_1_TRACK_KNOWN_IDENTITY_RECOVERY
```

Guardrails:

```text
MIN_TRACK_OBSERVATIONS = 3
MIN_SUPPORTING_OBSERVATIONS = 2
NORMAL_TRACK_MEDIAN = 0.74
RISKY_TRACK_MEDIAN = 0.79
STRONG_TRACK_MEDIAN = 0.84
WINNER_MARGIN >= 0.07
```

Ambiguous winner, same-sample cannot-link, or strong Face conflict stays unresolved.

## 7. Pass 2 — same-Shot known-presence recovery

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

Known-Face path after real-video regressions:

```text
FACE_SUPPORTED = 0.40
FACE_STRONG = 0.50
FACE_PAIR_MIN_SCORE = 0.76
moderate Face recovery requires >=2 current-Shot observations
and >=2 distinct current-Shot timestamps
positive Face comparison must be supported by >=2 independent confirmed Gallery Shots
very strong Face may confirm an already-known Character from one observation
Face-supported identities rank before synthetic-body ReID for face-fallback close-ups
hard Face conflict requires consistent conflict across >=2 Gallery Shots with no positive support
```

The current real sample already showed improved binding for `SHOT 0006` and `SHOT 0007`; `SHOT 0002 / 0004 / 0009` remain the priority real-material checks after the latest Face patch.

## 8. Recovery provenance and Shot confidence

Recovered Track metadata persists at:

```text
CharacterTrack.evidence_json.identity_recovery
```

Pass 2 may include:

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

Identity confidence and Shot-presence confidence are separate. Recovered-only Final bindings use the strongest validated recovery score. Multiple fragments of one Character in one Shot still materialize one `ShotCharacterBinding`.

## 9. Final Character Gate

Formal V10/V10.1 Final materialization requires:

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

## 10. Asset Workspace Character evidence

```text
evidence_by_shot[shot_id].characters
= RESOLVED Character evidence only

evidence_by_shot[shot_id].character_diagnostics
= UNRESOLVED diagnostics only
```

The V10.1 workspace adapter reads the exact Track recovery source. UNRESOLVED diagnostics never become Final Character suggestions.

## 11. Character Gallery, exhaustive AI Evidence and Final Binding are now visibly separated

A real UI regression exposed a conceptual ambiguity: the Character Gallery showed several Person crops from one Shot while the Asset library showed one whole-Shot thumbnail, so the two pages looked inconsistent even when they referred to the same Shot.

The formal distinction is now explicit:

```text
CharacterTrack rows
= exhaustive persisted AI identity evidence by Shot

V10 Gallery
= bounded/diversified strong representative subset

Gallery/Evidence viewer images
= Gallery crops
+ one persisted CharacterTrack representative crop for any evidence Shot omitted by the bounded Gallery

Shot.thumbnail_url
= whole-Shot context image

ShotCharacterBinding
= editable Final binding
```

`engine/app/character_gallery_routes_v10.py` now returns both:

```text
evidence_shot_count / evidence_shots
= exhaustive Candidate CharacterTrack Shot membership

gallery_image_count
= true bounded Gallery image count

images
= visual comparison images that cover every evidence Shot
  (real Gallery crop when available; otherwise one on-demand persisted Track representative crop)
```

The on-demand fallback crop endpoint is:

```text
GET /api/content-analysis/characters/{candidate_id}/evidence-shot/{shot_id}
```

It reads the persisted Track `representative_source_us + bbox_json`, decodes the Shot Reference Clip, and returns the actual person crop. It does not invent a classification or modify identity state.

### Asset library comparison UI

For a Character, the Asset library now shows:

```text
Final Binding Shots
Evidence Shots
Person crop count
Mismatch Shots
```

Every comparison card contains:

```text
top:    Shot whole-frame thumbnail / context
bottom: AI Person Evidence crops
status: Evidence + Final | AI ONLY | FINAL ONLY
```

Status semantics:

```text
Evidence + Final
= immutable Candidate Track evidence exists AND Final binding exists

AI ONLY
= AI has persisted identity evidence in this Shot but Final binding is missing
  → primary signal for a Shot-binding recall defect

FINAL ONLY
= Final binding exists but this Character's source Candidate has no persisted Track evidence in the Shot
  → often manual binding, stale version, or a condition requiring review
```

Merged Final Characters load all `source_candidate_ids`; comparison is not limited to the first historical Candidate.

### Character Gallery UI

`CharacterPersonGalleryV10.vue` now groups visual evidence by real Shot ordinal and labels:

```text
N Evidence Shots
M Gallery 代表图
K 可视证据图
```

A crop labelled `Track 代表图` means that Shot has real persisted CharacterTrack identity evidence but was not selected into the bounded Gallery subset. This prevents the UI from falsely presenting “not selected into Gallery” as “no AI evidence”.

## 12. Character Gallery Shot labels

All human-facing Gallery Shot labels resolve immutable `shot_id` through real `v2_shots.ordinal`. UUID suffixes are never interpreted as Shot numbers.

## 13. Current Character / Asset code map

```text
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

Compatibility filenames do not imply the active algorithm version.

## 14. Current implementation status

```text
01 剧集管理: IMPLEMENTED
02 拉片: IMPLEMENTED; real-media release checks still apply

03 资产:
  Character V10.1 global identity classification working on current real sample
  risky-view identity creation implemented
  Pass-1 Track recovery implemented
  Pass-2 body/fragment aggregation implemented
  repeated moderate known-Face presence implemented
  exact recovery provenance implemented
  identity vs Shot-presence confidence separation implemented
  V10/V10.1 Final Gate implemented
  exhaustive CharacterTrack Evidence Shot API implemented
  per-evidence-Shot on-demand Track crop implemented
  Gallery grouped by real Shot implemented
  Evidence-vs-Final Asset library comparison implemented
  NEEDS LOCAL UI / REAL-VIDEO CHECK for remaining Shot binding misses

04 内容剧本: PLANNED / partial compatibility code exists
05 重制设计: PLANNED
06 生成 / 导出: PLANNED
```

## 15. Test / CI reality

GitHub Actions is **not globally green**.

Latest backend run after the Evidence-vs-Final comparison work:

```text
28 failed, 179 passed, 1 skipped
```

The new `test_character_gallery_routes_v10.py` is not among the failures. Backend compile and FastAPI import pass. Existing failures remain repository-level legacy/runtime/environment issues including missing CI `cv2`, missing `trackers`, FFmpeg assumptions, and obsolete V6-era semantic assertions.

Frontend build remains blocked before project type checking by the existing `vue-tsc` / TypeScript package compatibility problem (`typescript` does not export `./lib/tsc`). Do not claim the frontend or whole repository build is green.

## 16. Immediate local acceptance

```text
1. git pull latest main
2. restart backend + frontend
3. open 03 资产 → 资产库 → 人物
4. select 人物001 / 002 / 003 and verify the comparison cards
5. confirm top image is Shot whole-frame context and bottom images are actual Person crops
6. use AI ONLY to identify binding misses directly
7. use FINAL ONLY to identify manual/stale/no-track cases
8. verify Character Gallery counts distinguish Evidence Shots from bounded Gallery representatives
9. for the algorithm regression, rerun asset extraction if needed and recheck SHOT 0002 / 0004 / 0006 / 0007 / 0009
10. do not tune identity thresholds based only on Gallery representative counts
```

## 17. Documentation rule

Any Character code change is incomplete until current state docs and the latest session handoff match executable code. Do not mark Character V10.1 `STABLE/FROZEN` until the user accepts real-video Shot binding accuracy.
