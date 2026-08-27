# AI Drama Studio — Project State

> **Last synchronized:** 2026-08-27 14:25 +08:00  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Branch:** `main`  
> **Architecture:** Reference Video V2  
> **FastAPI app version:** `2.4.1`  
> **Formal character runtime:** Character V10.1

## 1. Current-state source of truth

This document describes what the repository runs now. Historical V1–V10/F06 plans are not authoritative unless referenced here.

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

Before changing Character logic, inspect:

```text
engine/app/character_runtime_v6.py
engine/app/character_identity_v101.py
engine/app/character_shot_binding_v101.py
engine/app/character_shot_presence_v101.py
engine/app/character_persistence_v6.py
engine/app/asset_final_gate_v10.py
engine/app/asset_workspace_character_v101.py
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

Shot + frame-owned Reference Clip remains the core production unit. Heavy video/model work is sequential by default.

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

YoutuReID is the primary new-identity signal. Face is optional support, a known-identity Shot-presence signal, and a high-quality conflict signal.

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

Never collapse:

```text
Observation / Person Evidence / Track = visual evidence
Identity Class = cross-Shot person identity
Character = Final project asset
```

## 5. New identity creation stays fail-closed

A formal new Character requires at least:

```text
>=3 independent Shots
>=3 model-usable Person Images
stable cross-Shot Person-ReID consistency
unique identity class
same-sample cannot-link preserved
no high-quality Face hard conflict
```

Strong contaminated/substantial partial crops may seed only under stricter confirmation. Weak partials remain attach-only. Shot-presence recovery never creates a Character.

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

## 7. Pass 2 — Shot presence recovery

Module:

```text
engine/app/character_shot_presence_v101.py
```

Source:

```text
V10_1_SHOT_FRAGMENT_AGGREGATION
```

### Body/side/back path

```text
REID_STRONG = 0.84
REID_SUPPORTED = 0.74
RISKY_REID_SUPPORTED = 0.80
MIN_SHOT_SUPPORT_OBSERVATIONS = 3
MIN_SHOT_SUPPORT_TIMESTAMPS = 3
MIN_SHOT_MEDIAN = 0.76
WINNER_MARGIN = 0.075
```

### Known-Face close-up path — current patch

The second real-video rerun showed a useful split:

```text
SHOT 0006 old-woman close-up → fixed
SHOT 0007 young-woman partial/body → fixed
SHOT 0002 young-woman clear face close-up → still missing
SHOT 0004 old + young two-person Shot → young woman still missing
```

This proves the generic fragment/body path is working better, while the remaining misses are concentrated in the Face/close-up known-presence branch.

The old implementation required `FACE_STRONG = 0.52` for positive Face presence and could hard-veto an identity because of one bad Gallery Face crop. That was too brittle for expression/angle changes.

Current rules:

```text
FACE_SUPPORTED = 0.40
FACE_STRONG = 0.50
FACE_PAIR_MIN_SCORE = 0.76
moderate Face recovery requires >=2 supported current-Shot observations
and >=2 distinct current-Shot timestamps
Face support must come from >=2 independent confirmed Gallery Shots
Face-supported identities rank before synthetic-body ReID for face-fallback close-ups
hard Face conflict requires consistent conflict across >=2 Gallery Shots with no positive support
```

One truly strong Face observation can still confirm presence of an already-known identity. Moderate Face cannot recover from a single observation.

This path does not seed a new identity and does not make Face mandatory.

## 8. Recovery provenance and confidence

Recovered Track data lives in:

```text
CharacterTrack.evidence_json.identity_recovery
```

Pass 2 can persist:

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

Identity confidence and Shot-presence confidence are different. A recovered-only Shot binding uses the strongest validated recovery score. Multiple fragments of the same Character in one Shot still materialize one `ShotCharacterBinding`.

## 9. Final Character Gate

Formal V10/V10.1 materialization requires:

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

The adapter reads the actual Track recovery source. Pending diagnostics never become Final Character suggestions.

## 11. Character Gallery labels

Gallery card labels are resolved from real `v2_shots.ordinal`. UUID suffixes are never treated as Shot numbers.

## 12. Current Character code map

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
frontend/src/components/CharacterPersonGalleryV10.vue
```

Compatibility filenames do not imply active algorithm version.

## 13. Current implementation status

```text
01 剧集管理: IMPLEMENTED
02 拉片: IMPLEMENTED; real-media release checks still apply

03 资产:
  Character V10.1 global identity classification working on current real sample
  risky-view identity creation implemented
  Pass-1 Track recovery implemented
  Pass-2 body/fragment aggregation implemented
  real rerun confirmed SHOT 0006/0007 improved
  repeated moderate known-Face presence patch implemented
  exact recovery provenance implemented
  identity vs Shot-presence confidence separation implemented
  V10/V10.1 Final Gate implemented
  NEEDS NEXT WINDOWS REAL-VIDEO RERUN for SHOT 0002/0004/0009

04 内容剧本: PLANNED / partial compatibility code exists
05 重制设计: PLANNED
06 生成 / 导出: PLANNED
```

## 14. Test / CI reality

GitHub Actions is not globally green. Before the newest Face-presence patch, the backend full-test summary was:

```text
28 failed, 176 passed, 1 skipped
```

The repository still has legacy/runtime/environment failures (`cv2`, trackers, FFmpeg/media assumptions and old semantic assertions). Frontend build still has the existing `vue-tsc` / TypeScript compatibility issue.

Focused tests now additionally lock:

```text
three singleton body fragments → known Character may recover
one strong Face → known Character may recover
repeated moderate Face below old 0.52 threshold → may recover
single moderate Face → stays unresolved
Face-supported identity outranks synthetic-body ReID in close-up fallback
same-sample cannot-link → cannot fake repeated support
```

Do not claim the whole repository passes.

## 15. Immediate local acceptance

```text
1. git pull latest main
2. restart backend
3. rerun asset extraction; old Analysis Runs do not auto-rebind
4. confirm Final Character count remains correct
5. check SHOT 0002 → 人物002
6. check SHOT 0004 → 人物001 + 人物002
7. confirm SHOT 0006 → 人物001 remains correct
8. confirm SHOT 0007 → 人物002 remains correct
9. inspect SHOT 0009 for every actually visible known Character
10. if 0002/0004 still miss, inspect identity_recovery.face_support_count and YuNet/SFace observations before any further threshold tuning
```

## 16. Documentation rule

Any Character code change is incomplete until current project docs and the latest session handoff match executable code. Do not mark Character V10.1 `STABLE/FROZEN` until the user accepts real-video Shot binding accuracy.
