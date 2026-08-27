# AI Drama Studio — Project State

> **Last synchronized:** 2026-08-27 12:12 +08:00  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Branch:** `main`  
> **Architecture:** Reference Video V2  
> **FastAPI app version:** `2.4.1`  
> **Formal character runtime:** Character V10.1

## 1. This file is the current-state source of truth

This document records what the repository actually runs now. It is not a historical plan.

If an older Feature/Frozen document says Character V1–V9, face-only identity, 2-shot Face confirmation, or a planned F06 YuNet-only pipeline, that text is **legacy history** unless this file explicitly says otherwise.

For a new conversation, use this recovery order:

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/CURRENT_IMPLEMENTATION_MANIFEST.md
→ docs/ASSET_CHARACTER_RECOGNITION_V10_1.md
→ current code/tests
→ latest session handoff
```

Before changing character logic, verify the executable wiring in:

```text
engine/app/character_visual_v2.py
engine/app/character_runtime_v6.py
engine/app/character_identity_v101.py
engine/app/character_shot_binding_v101.py
engine/app/asset_final_gate_v10.py
```

## 2. Current product workspaces

```text
01 剧集管理
02 拉片
03 资产
04 内容剧本
05 重制设计
06 生成 / 导出
```

Internal technical stages such as FFprobe, model embedding, MOT, Person Evidence, ASR, and model logs are background capabilities, not separate production pages.

## 3. Current Shot baseline

The project is Reference Video driven. A Shot and its Reference Clip are the core production unit.

Current product principle:

```text
Source Video
→ Shot boundaries
→ frame-owned Reference Clip
→ assets/evidence bound to Shot
→ replacement/localization controls
→ Reference Video driven remake
```

`Episode.sort_order` remains the only formal batch order. Heavy video/model work is sequential by default (`concurrency = 1`).

## 4. Current Character baseline — V10.1

### Formal runtime profiles

```text
Runtime profile:
character-v10.1-capture-first-model-classification

Asset profile:
f05-assets-v10.1-person-evidence-model-classification

Resolver:
person-evidence-model-classifier-v10.1
```

`content_models_v2.model_status()` may still report the **V10 model-package profile** because V10.1 reuses the same fixed model files. That does not mean the runtime resolver reverted to V10.

### Formal pipeline

```text
Reference Clip / Shot
↓
YOLOX Person Detection (~12 fps sampling, bounded on long Shots)
↓
Every detected person becomes an explicit isolated Person Instance
↓
YuNet + optional SFace face evidence
YoutuReID Person embedding (primary identity model signal)
clothing_upper / clothing_lower / body_hist / body_structure support channels
↓
Capture and persist every model-usable Person Evidence crop
(CLEAN / OCCLUDED / CONTAMINATED / substantial PARTIAL)
↓
Mature MOT for temporal organization
BoT-SORT preferred; ByteTrack fallback according to tracker runtime
↓
Project-level Person Evidence model classification
↓
confirmed RESOLVED identities + UNRESOLVED evidence
↓
V10.1 shot-level known-identity recovery
(repeated unresolved Track → already-confirmed identity only)
↓
write classification back to Person Evidence manifest
↓
Final Gate
↓
Character + ShotCharacterBinding
```

### Three layers must never be collapsed

```text
Observation / Person Evidence / Track = visual evidence
Identity Class = cross-Shot person identity
Character = project-level Final Asset
```

Track count, face count, or crop count must never be used as Character cardinality.

## 5. V10.1 identity creation contract

Character V10.1 is **capture-first**. Image condition labels do not decide whether a real person exists.

Normal and risky views can participate in classification, but new identity creation remains fail-closed.

A confirmed formal identity requires at least:

```text
>= 3 independent Shots
>= 3 model-usable Person Images
stable cross-Shot Person-ReID consistency
unique identity class
no same-sample cannot-link violation
no high-quality Face hard conflict
```

For risky seed classes (`CONTAMINATED`, substantial `PARTIAL`), confirmation uses stricter Person-ReID thresholds than normal evidence.

Face is optional support. A confirmed V10/V10.1 identity may materialize without visible Face evidence.

Weak/tiny/low-score partial fragments remain evidence/attach-only and cannot create a new Character.

## 6. Shot-level Character Binding recovery — current fix

The global resolver is intentionally conservative at single-image level. That can leave a Shot unbound even when several observations from the same Track consistently match an already-confirmed Character.

V10.1 therefore performs a second pass after global identity confirmation:

```text
UNRESOLVED Track
→ compare each usable observation against every RESOLVED identity gallery
→ aggregate Person-ReID support across time and independent gallery Shots
→ require >= 3 usable observations
→ require >= 2 supporting observations
→ require a unique winner with margin
→ fail closed on cannot-link / high-quality Face conflict
→ attach whole Track to that existing identity
```

Important invariants:

- This pass **never creates a new Character**.
- It only attaches to an already-confirmed `RESOLVED` identity.
- Ambiguous winner stays `UNRESOLVED`.
- Same-sample cannot-link and strong Face conflict block recovery.
- After recovery, persistence uses the recovered Track membership, so `ShotCharacterBinding` is built from the corrected identity tracks.

Formal module:

```text
engine/app/character_shot_binding_v101.py
```

Formal runtime call order:

```text
resolve_global_identities(tracks)
→ recover_unresolved_tracks(candidates)
→ update_person_evidence_classification(...)
→ persist Candidate / Track
→ Final Gate
→ ShotCharacterBinding
```

## 7. Final Character Gate

Formal V10/V10.1 Final Gate is fail-closed.

A Candidate can materialize only when:

```text
identity_status == RESOLVED
resolver is in the formal resolver allow-list
confirmed_gallery_shots >= 3
confirmed_gallery_images >= 3
final_asset_eligible is not false
```

`UNRESOLVED`, missing/invalid identity status, unknown resolver, or insufficient confirmation never becomes a Final Character.

For V10/V10.1, Face visibility is **not** required by the formal gate.

Formal entry:

```text
engine/app/asset_final_gate_v10.py
```

The implementation currently reuses compatibility logic from `asset_final_gate_v9.py`, with the V10.1 resolver explicitly added to the formal allow-list.

## 8. Evidence / Final Asset separation

```text
v2_content_analysis_runs
v2_character_candidates
v2_character_tracks
Person Evidence files/manifests
= immutable AI Evidence / analysis output

Character / Scene / Prop
ShotCharacterBinding / ShotSceneBinding / ShotPropBinding
= Final Asset / Final Binding
```

A new AI Run must not silently overwrite MANUAL / RESTORE asset revisions.

Old analysis runs do not automatically rebind after code changes. To test a new identity/binding algorithm, rerun asset extraction so new `CharacterTrack` and `ShotCharacterBinding` records are produced.

## 9. Current character code map

Formal or currently-wired modules:

```text
engine/app/character_visual_v2.py            compatibility facade; points to V10.1
engine/app/character_runtime_v6.py           formal V10.1 runtime entry (filename retained for compatibility)
engine/app/character_observation_v10.py      Person Instance detection/capture
engine/app/character_person_evidence_v10.py  evidence eligibility / crop policy
engine/app/character_person_features_v9.py   separated Person feature channels
engine/app/character_tracking_v10.py         temporal tracking
engine/app/character_identity_v10.py         V10 base classifier helpers
engine/app/character_identity_v101.py        formal V10.1 global identity classifier
engine/app/character_shot_binding_v101.py    V10.1 known-identity Track recovery
engine/app/character_gallery_v10.py          classified person gallery
engine/app/character_evidence_store_v10.py   pre/post-classification evidence store
engine/app/asset_final_gate_v10.py           formal V10/V10.1 Final Gate entry
engine/app/asset_workspace_v3.py             Final Asset workspace/bindings
engine/app/content_analysis_v2.py            Project asset analysis persistence
```

Do not infer the active version from filenames alone. Some compatibility filenames (`character_runtime_v6.py`, `character_person_features_v9.py`) intentionally remain while their formal caller is V10.1.

## 10. Models / runtime

Fixed local model set remains:

```text
YOLOX person detection
YoutuReID person re-identification
YuNet face detection
SFace face embedding/support
```

YoutuReID is the primary identity model signal. Clothing/body channels are supporting signals. Face is optional support and a hard-conflict signal when high-quality Face evidence disagrees.

Do not silently bundle non-commercial/research-only InsightFace/ArcFace pretrained weights. A future Face provider replacement must have a clear commercial/license path and must not change the Track → Identity → Final Asset contract.

## 11. Current implementation status

```text
01 剧集管理:
  IMPLEMENTED

02 拉片:
  IMPLEMENTED; real Windows/video regression remains release gate

03 资产:
  Character V10.1 capture-first classification implemented
  V10.1 risky-view identity creation implemented
  V10.1 shot-level known-identity Track recovery implemented
  V10/V10.1 fail-closed Final Gate implemented
  NEEDS LOCAL REAL-VIDEO REGRESSION after latest binding change

04 内容剧本:
  PLANNED / partial low-level compatibility code exists

05 重制设计:
  PLANNED

06 生成 / 导出:
  PLANNED
```

## 12. Current test / CI reality

The latest GitHub Actions run after the shot-binding change is **not globally green**.

Backend import/compile now passes after CI dependency/version fixes, but the whole legacy test suite still has failures caused by a mix of:

- CI missing `cv2` / full media runtime;
- CI missing the external `trackers` package/runtime;
- legacy V6 assertions that intentionally no longer match V10/V10.1 semantics;
- tests expecting FFmpeg where the lightweight CI runner does not provide it;
- legacy workspace dictionary expectations;
- frontend `vue-tsc` / TypeScript package compatibility failure.

Therefore do **not** claim “all tests pass” from the current repository state.

The new V10.1 shot-level recovery regression tests were added specifically to cover:

```text
repeated unresolved Track → confirmed identity
ambiguous winner → stays unresolved
cannot-link conflict → no recovery
```

Real-video release validation must still happen on the user's Windows environment with the installed model/MOT/FFmpeg runtime.

## 13. Immediate next action

```text
1. Pull latest main locally.
2. Prepare/verify F05 character models and MOT runtime.
3. Rerun asset extraction on the same real short-drama sample.
4. Verify Final Character count first.
5. Verify ShotCharacterBinding for the previously wrong Shots.
6. Inspect recovered Track metadata (`track_recovery_*`) if a Shot is still unbound.
7. Only after real-video confirmation continue threshold tuning or the next content-script feature.
```

## 14. Documentation rule for future sessions

Any character code change is incomplete until these are reconciled in the same work session:

```text
AGENTS.md (if baseline changes)
SKILL.md (if formal project rules/baseline changes)
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/ASSET_CHARACTER_RECOGNITION_V10_1.md (or the active successor)
latest docs/sessions/... handoff
```

If code and documents disagree, stop and reconcile them before continuing feature work.
