# AI Drama Studio — Project State

> **Last synchronized:** 2026-08-27 16:22 +08:00  
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
→ docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md   # TARGET, not executable truth
→ docs/ASSET_CHARACTER_RECOGNITION_V10_1.md    # when Character is involved
→ current code/tests
→ latest session handoff
```

Source-of-truth split:

```text
this file + CURRENT_IMPLEMENTATION_MANIFEST + code/tests
= CURRENT

BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN
= accepted TARGET
```

A Target-vs-Current gap is expected until that Phase is actually implemented. Never mark a planned module as implemented just to make the documents look identical.

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

## 2. Accepted target product plan — NOT YET IMPLEMENTED

The user has accepted a Breakdown-first target workflow:

```text
Original Video
→ Preprocess
→ Shot Detection
→ Shot + Reference Clip
→ ASR / OCR / Video Understanding
→ anonymous structured Breakdown Draft
→ Draft-guided Character / Scene / Prop evidence extraction
→ Global Asset Resolution + Final Shot Bindings
→ identity/asset fill-back
→ Final Breakdown
→ remake
```

Core target principle:

```text
先看懂，再识别，再回填
```

Target details, current-to-target mapping, protection rules and implementation phases are frozen in:

```text
docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
```

Important current-state clarification:

- Current `media_v2.detect_episode_shots()` already performs TransNetV2 Shot boundary detection and creates Reference Clips.
- Current `Shot` stores timing, Reference Clip, thumbnail, keyframes and lightweight description/camera fields.
- Current `02 拉片` does **not** yet implement the accepted anonymous structured Breakdown Draft / SceneSegment / ASR+OCR+VLM semantic timeline.
- Current `transvlm_runtime_v51.py` uses a Qwen3-VL-based TransVLM route for transition detection/caching; it must not be described as an already-implemented semantic breakdown engine.
- Current F05 asset extraction does not formally run ASR/Speaker/Dialogue.
- Current Scene candidate logic remains lightweight and is not the target final semantic Scene resolver.
- Current Prop data boundary exists, but reliable targeted Prop extraction may still be `NOT_CONFIGURED` depending on model setup.

**No business code, database schema or runtime baseline was changed when this target plan was accepted.**

## 3. Product workspaces

```text
01 剧集管理
02 拉片
03 资产
04 内容剧本
05 重制设计
06 生成 / 导出
```

Shot + frame-owned Reference Clip remains the core production unit. Heavy media/model work remains sequential by default.

Target product meaning of `02 拉片` will eventually be broader than the current Shot timeline: Shot segmentation is only the first technical step; the target final result is a structured, timed audiovisual breakdown. Until implemented, current UI/code status remains what this file says below.

## 4. Formal Character V10.1 baseline

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

Breakdown-first planning does not replace these models or change their current identity gates.

## 5. Formal Character pipeline

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

The architecture deliberately separates:

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

Target Breakdown adds another separate layer:

```text
LocalSubject / ShotSemanticDraft / SceneSegmentDraft
= anonymous semantic understanding, not Final identity
```

**Final Shot binding is no longer inferred from `candidate.tracks`, and future Draft prose is not allowed to become a Final binding source by itself.**

## 6. New Character creation stays fail-closed

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

The target anonymous Draft cannot bypass this gate.

## 7. Explicit Shot Character Assignment

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

The engine does **not** move an unresolved Track into a Character just to obtain a binding. Track ownership stays identity evidence; Shot presence is a first-class decision.

### 7.1 Direct identity presence

If Global Identity already assigned original observations to a RESOLVED Character, that Shot receives:

```text
mode = DIRECT_IDENTITY
```

### 7.2 Known-Face presence

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

### 7.3 Body / Person-ReID presence

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

### 7.4 Multi-person Shot occupancy constraints

Same-sample cannot-link is used at Shot-assignment time. If one simultaneous Person Instance is already direct evidence for 人物001, another cannot-link Person Instance cannot also be assigned to 人物001. This gives the second visible person a fair comparison against other known identities and is specifically intended for two-person Shots such as the real `SHOT 0004` case.

Ambiguous winner, repeated high-quality Face conflict, or insufficient temporal support stays unassigned. The engine does not fill empty Shot rows by guessing.

## 8. Shot assignment persistence

For each RESOLVED Candidate, persistence carries:

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

This metadata lives in `CharacterCandidate.evidence_json` via the existing V10.1 persistence bridge. No DB migration is required for the current Character assignment feature.

Individual unresolved Person Evidence may remain `UNRESOLVED` even when the Shot-level aggregate confirms an already-known Character. That is intentional separation of evidence classification from Shot presence.

Future Breakdown Draft provenance/confidence must remain separate from identity confidence and Shot-presence confidence.

## 9. Final Character Gate and Final Shot binding

Formal Character cardinality uses the fail-closed gate:

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

## 10. Asset Workspace Character evidence

```text
evidence_by_shot[shot_id].characters
= RESOLVED known-Character Shot presence

evidence_by_shot[shot_id].character_diagnostics
= UNRESOLVED visual diagnostics only
```

For current explicit-assignment Runs, the workspace adapter follows `shot_presence_assignments`. A Candidate Track that is absent from the explicit assignment map does not silently recreate a Character suggestion.

The Gallery / Evidence-vs-Final UI remains a diagnostic aid only. It is not the source of binding truth and is not a substitute for the Shot assignment engine.

## 11. Current Character / Asset code map

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

Current Shot/media baseline important to the Target Plan:

```text
engine/app/main.py
engine/app/studio_v2.py
engine/app/media_v2.py
engine/app/shot_revision_v2.py
engine/app/shot_edit_routes_v2.py
engine/app/content_analysis_v2.py
```

`main.py` currently wires `media_v2.preprocess_episode` and `media_v2.detect_episode_shots`; do not infer the current formal V2 product path only from historical F04/F05 module docstrings.

## 12. Current implementation status

```text
01 剧集管理: IMPLEMENTED

02 拉片:
  Shot detection / timing: IMPLEMENTED
  Shot + Reference Clip: IMPLEMENTED
  Shot revision / manual edit support: IMPLEMENTED
  Breakdown-first anonymous semantic Draft: PLANNED / NOT IMPLEMENTED
  SceneSegmentDraft / TimelineEvent: PLANNED / NOT IMPLEMENTED
  ASR/OCR/VLM unified breakdown facts: PLANNED / NOT IMPLEMENTED
  Final standard/international breakdown renderer: PLANNED / NOT IMPLEMENTED

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
  Character integration with semantic Draft: PLANNED / NOT IMPLEMENTED
  Scene target semantic resolver: PLANNED; current candidate path is lightweight
  Prop targeted open-vocabulary extraction: PLANNED; current data boundary exists
  NEEDS WINDOWS REAL-VIDEO ACCEPTANCE for precise SHOT 0001–0009 Character binding

04 内容剧本: PLANNED / partial compatibility code exists
05 重制设计: PLANNED
06 生成 / 导出: PLANNED
```

This is the key anti-drift rule: the accepted Target Plan does not change the above CURRENT statuses until code/tests/acceptance actually land.

## 13. Target implementation order

The accepted safe order is:

```text
P0 docs/contract only                         = CURRENT TASK / DONE when docs land
P1 Draft data contract, ADD-only              = PLANNED
P2 ASR/OCR/VLM anonymous Draft sidecar         = PLANNED
P3 02 拉片 structured Draft UI                 = PLANNED
P4 Draft-guided Scene / Prop evidence          = PLANNED
P5 Draft ↔ Character safe integration          = PLANNED, only after V10.1 baseline acceptance
P6 Final fill-back + renderers                  = PLANNED
P7 downstream remake integration               = PLANNED
```

Implementation details and protection rules are authoritative in `docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md`.

## 14. Test / CI reality

GitHub Actions is **not globally green**.

Latest known backend run after the explicit Shot-assignment tests:

```text
28 failed, 187 passed, 1 skipped
```

Backend compile and FastAPI import pass. The new explicit Shot assignment tests and explicit workspace-assignment tests are not among the failures.

Existing failures remain repository-level legacy/runtime/environment issues such as missing lightweight-CI `cv2`, missing `trackers`, FFmpeg assumptions, obsolete V6-era assertions, and historical workspace expectations.

Frontend build remains blocked by the existing `vue-tsc` / TypeScript package compatibility issue. Do not claim the whole repository is green.

The documentation-only Breakdown-first planning commits do not change these test results.

## 15. Immediate Windows real-video Character acceptance

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

If a row is still wrong, inspect the relevant Candidate's `shot_presence_assignments` first. That isolates the actual Face/ReID/temporal/cannot-link decision; do not return to generic Gallery UI changes or blindly lower global identity thresholds.

## 16. Documentation rule

Any Character identity/binding code change is incomplete until current state docs and the latest session handoff match executable code. Do not mark Character V10.1 `STABLE/FROZEN` until the user accepts real-video Shot binding accuracy.

Any Breakdown-first Phase is also incomplete until all of these agree:

```text
AGENTS.md
SKILL.md
PROJECT_STATE.md
CURRENT_IMPLEMENTATION_MANIFEST.md
BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
current code/tests
latest session handoff
```

When only a plan is accepted, update the Target Plan and record `PLANNED / NOT IMPLEMENTED`; do not rewrite CURRENT as if code already exists.
