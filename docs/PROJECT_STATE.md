# AI Drama Studio — Project State

> **Last synchronized:** 2026-08-27 15:52 +08:00  
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

Before changing Character identity or Shot binding, inspect at least:

```text
engine/app/character_runtime_v6.py
engine/app/character_identity_v101.py
engine/app/character_shot_assignment_v101.py
engine/app/character_persistence_v6.py
engine/app/asset_final_gate_v10.py
engine/app/asset_final_gate_v9.py
engine/app/asset_workspace_character_v101.py
```

Historical `character_shot_binding_v101.py` and `character_shot_presence_v101.py` remain in the repository for compatibility/tests, but they are no longer called by the formal V10.1 runtime.

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
Shot assignment version: v10.1-shot-character-assignment-1
Shot assignment source: V10_1_SHOT_CHARACTER_ASSIGNMENT
```

Models:

```text
YOLOX Person Detection
YoutuReID Person Re-identification
YuNet Face Detection
SFace Face embedding/support
```

YoutuReID remains the primary **new-identity** model signal. Face remains optional identity support, a known-identity Shot-presence signal, and a high-quality conflict signal.

## 4. Formal Character pipeline

```text
Reference Clip / Shot
↓
YOLOX Person Detection + safe YuNet Face fallback
↓
isolated Person Instance observations
↓
YoutuReID + clothing/body channels + optional SFace
↓
persist model-usable Person Evidence
↓
Mature MOT
↓
project-level identity classification
↓
RESOLVED identities + UNRESOLVED visual evidence
↓
explicit Shot × known-Character assignment
  using ALL original Track / Observation evidence
↓
persist Candidate identity metadata + explicit Shot presence assignments
↓
Final Character Gate
↓
Character + ShotCharacterBinding
  from explicit Shot assignments
↓
Asset Workspace V10.1 adapter
```

The architecture now deliberately separates four layers:

```text
Observation / Person Evidence / CharacterTrack
= visual evidence

CharacterCandidate / Identity Class
= project-level person identity

Shot Character Assignment
= whether an already-confirmed Character is present in one Shot

Character + ShotCharacterBinding
= editable Final asset / Final binding
```

**Final Shot binding is no longer inferred from `candidate.tracks`.**

## 5. New Character creation stays fail-closed

A formal new Character still requires at least:

```text
>=3 independent Shots
>=3 model-usable Person Images
stable cross-Shot Person-ReID consistency
unique identity class
same-sample cannot-link preserved
no high-quality Face hard conflict
```

Strong contaminated/substantial partial crops may seed only under stricter confirmation. Weak/tiny partial evidence cannot create a new Character.

The Shot assignment engine runs only after RESOLVED identities exist and **cannot create identities**.

## 6. Explicit Shot Character Assignment

Formal module:

```text
engine/app/character_shot_assignment_v101.py
```

Formal source/version:

```text
V10_1_SHOT_CHARACTER_ASSIGNMENT
v10.1-shot-character-assignment-1
```

Purpose:

```text
已确认 人物001 / 002 / 003 ...
+
某个 Shot 的全部原始 Track / Observation
↓
独立判断每个已知人物是否真实出现在该 Shot
↓
shot_presence_assignments
```

The engine does **not** move an unresolved Track into a Character just to obtain a binding. Track ownership stays identity evidence; Shot presence becomes a first-class decision.

### 6.1 Direct identity presence

If Global Identity already assigned original observations to a RESOLVED Character, that Shot receives:

```text
mode = DIRECT_IDENTITY
```

### 6.2 Known-Face presence

Current rules:

```text
FACE_PAIR_MIN_SCORE = 0.72
FACE_SUPPORTED = 0.36
FACE_STRONG = 0.50
FACE_WINNER_MARGIN = 0.08
MIN_FACE_REPEAT_OBSERVATIONS = 2
MIN_FACE_REPEAT_TIMESTAMPS = 2
MIN_FACE_REPEAT_MEDIAN = 0.40
```

Face comparisons must be backed by at least two independent confirmed Gallery Shots. A sufficiently strong unique Face match may confirm one known Character from one current-Shot observation; moderate Face support must repeat over current-Shot time.

### 6.3 Body / Person-ReID presence

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

Body/ReID presence must repeat through the Shot unless evidence is already part of direct identity classification.

### 6.4 Multi-person Shot occupancy constraints

Same-sample cannot-link is used at Shot-assignment time. If one simultaneous Person Instance is already direct evidence for 人物001, another cannot-link Person Instance cannot also be assigned to 人物001. This gives the second visible person a fair comparison against other known identities and is specifically intended for two-person Shots such as the real `SHOT 0004` case.

Ambiguous winner, repeated high-quality Face conflict, or insufficient temporal support stays unassigned. The engine does not fill empty Shot rows by guessing.

## 7. Shot assignment persistence

For each RESOLVED Candidate, persistence now carries:

```text
shot_assignment_version
shot_assignment_source
shot_assignment_policy
shot_presence_assignments[]
shot_presence_shot_ids
shot_presence_count
shot_presence_recovered_count
```

Each assignment can include:

```text
shot_id
shot_ordinal
episode_order
confidence
mode = DIRECT_IDENTITY | FACE_STRONG | FACE_REPEATED | BODY_REID
support_count
support_timestamp_count
track_count
face_support_count
winner_margin
```

This metadata lives in `CharacterCandidate.evidence_json` via the existing V10.1 persistence bridge. No DB migration is required.

Individual unresolved Person Evidence may remain `UNRESOLVED` even when the Shot-level aggregate confirms an already-known Character. That is intentional separation of evidence classification from Shot presence.

## 8. Final Character Gate and Final Shot binding

Formal Character cardinality still uses the unchanged fail-closed gate:

```text
identity_status == RESOLVED
resolver in formal allow-list
confirmed_gallery_shots >= 3
confirmed_gallery_images >= 3
final_asset_eligible is not false
```

Face visibility is not required.

For a new V10.1 Run containing `shot_assignment_version`:

```text
ShotCharacterBinding
= ONLY shot_presence_assignments
```

Candidate Track ownership is not consulted as a fallback. An explicit empty assignment list therefore means no Final bindings for that Candidate.

Old persisted V9/V10/V10.1 Runs without `shot_assignment_version` retain the historical Track-derived fallback for backward compatibility.

Formal entries:

```text
engine/app/asset_final_gate_v10.py
engine/app/asset_final_gate_v9.py
```

## 9. Asset Workspace Character evidence

```text
evidence_by_shot[shot_id].characters
= RESOLVED known-Character Shot presence

evidence_by_shot[shot_id].character_diagnostics
= UNRESOLVED visual diagnostics only
```

For current explicit-assignment Runs, the workspace adapter also follows `shot_presence_assignments`. A Candidate Track that is absent from the explicit assignment map does not silently recreate a Character suggestion.

The Gallery / Evidence-vs-Final UI remains a diagnostic aid only. It is not the source of binding truth and is not a substitute for the Shot assignment engine.

## 10. Current Character / Asset code map

```text
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

Historical compatibility modules still present but no longer in the formal runtime call path:

```text
engine/app/character_shot_binding_v101.py
engine/app/character_shot_presence_v101.py
```

Compatibility filenames do not imply the active algorithm generation.

## 11. Current implementation status

```text
01 剧集管理: IMPLEMENTED
02 拉片: IMPLEMENTED; real-media release checks still apply

03 资产:
  Character V10.1 global identity classification working on current real sample
  explicit Shot × known-Character assignment implemented
  direct identity Shot presence implemented
  strong/repeated known-Face Shot presence implemented
  repeated Body/ReID Shot presence implemented
  current-Shot cannot-link occupancy constraints implemented
  Track ownership mutation removed from formal binding path
  Final Gate consumes explicit Shot assignments for new Runs
  historical old-Run Track fallback preserved
  workspace consumes explicit Shot assignments for new Runs
  NEEDS WINDOWS REAL-VIDEO ACCEPTANCE for precise SHOT 0001–0009 binding

04 内容剧本: PLANNED / partial compatibility code exists
05 重制设计: PLANNED
06 生成 / 导出: PLANNED
```

## 12. Test / CI reality

GitHub Actions is **not globally green**.

Latest backend run after the explicit Shot-assignment tests:

```text
28 failed, 187 passed, 1 skipped
```

Backend compile and FastAPI import pass. The new explicit Shot assignment tests and explicit workspace-assignment tests are not among the failures.

Existing failures remain repository-level legacy/runtime/environment issues such as missing lightweight-CI `cv2`, missing `trackers`, FFmpeg assumptions, obsolete V6-era assertions, and historical workspace expectations.

Frontend build remains blocked by the existing `vue-tsc` / TypeScript package compatibility issue. Do not claim the whole repository is green.

## 13. Immediate Windows real-video acceptance

A **fresh asset extraction Run is mandatory**; old Runs do not gain explicit Shot assignments automatically.

Priority expected result for the current sample:

```text
SHOT 0001 → []
SHOT 0002 → [人物002]
SHOT 0003 → [人物001]
SHOT 0004 → [人物001, 人物002]
SHOT 0005 → [人物001]
SHOT 0006 → [人物001]
SHOT 0007 → [人物002]
SHOT 0008 → []
SHOT 0009 → verify every actually visible known Character
```

If a row is still wrong, inspect the relevant Candidate's `shot_presence_assignments` first. That now isolates the actual Face/ReID/temporal/cannot-link decision directly; do not return to generic Gallery UI changes or blindly lower global identity thresholds.

## 14. Documentation rule

Any Character identity/binding code change is incomplete until current state docs and the latest session handoff match executable code. Do not mark Character V10.1 `STABLE/FROZEN` until the user accepts real-video Shot binding accuracy.
