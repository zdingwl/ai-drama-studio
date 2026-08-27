# AI Drama Studio — Project State

> **Last synchronized:** 2026-08-27 12:49 +08:00  
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
engine/app/character_persistence_v6.py
engine/app/asset_final_gate_v10.py
engine/app/asset_workspace_character_v101.py
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
persist Track recovery provenance / Shot-presence confidence
↓
write classification back to Person Evidence manifest
↓
Final Gate
↓
Character + ShotCharacterBinding
↓
Asset Workspace V10.1 evidence adapter
(RESOLVED Character evidence separated from UNRESOLVED diagnostics)
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

## 6. Shot-level Character Binding recovery — implemented V10.1 path

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
- Recovery provenance is attached to the exact Track before persistence.
- `CharacterTrack.evidence_json.identity_recovery` records `source`, target identity/candidate, Shot, score, observation count, and policy.
- Candidate-level `track_recovery_*` summary metadata remains available for debugging/audit.

Formal recovery source:

```text
V10_1_TRACK_KNOWN_IDENTITY_RECOVERY
```

Formal module:

```text
engine/app/character_shot_binding_v101.py
```

Formal runtime call order:

```text
resolve_global_identities(tracks)
→ recover_unresolved_tracks(candidates)
→ update_person_evidence_classification(...)
→ persist Candidate / Track + recovery provenance
→ Final Gate
→ ShotCharacterBinding
```

### Identity confidence and Shot-presence confidence are now separate

A Character identity confidence is project/global evidence. A recovered Track score answers a different question: “how confidently is this already-known Character present in this Shot?”

Current Final Binding rule:

```text
Shot has a normal/direct identity-assigned Track
→ ShotCharacterBinding.confidence = candidate/global identity confidence fallback

Shot is represented only by V10.1 recovered Track(s)
→ ShotCharacterBinding.confidence = strongest validated Track recovery score
```

Multiple Track fragments for the same Character in one Shot still materialize exactly one `ShotCharacterBinding`.

No DB schema change was required; recovery provenance is stored inside immutable Track Evidence JSON and the existing binding `confidence` column stores Shot-presence confidence.

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

The implementation currently reuses compatibility logic from `asset_final_gate_v9.py`, with the V10.1 resolver explicitly added to the formal allow-list. `asset_final_gate_v9.py` also contains the shared V10/V10.1 materializer and now consumes per-Track recovery provenance for Shot binding confidence.

## 8. Asset Workspace Character evidence contract

The historical `asset_workspace_v3` serializer contains a face-visible diagnostic filter from an older Character generation. Formal API responses are now decorated by:

```text
engine/app/asset_workspace_character_v101.py
```

Current API contract:

```text
evidence_by_shot[shot_id].characters
= RESOLVED Character evidence only

Evidence may be front / side / back / body-visible / recovered Track.
face_visible == false does NOT hide a confirmed V10.1 Character.

evidence_by_shot[shot_id].character_diagnostics
= UNRESOLVED Person/Track diagnostics only
```

`UNRESOLVED` diagnostics:

- have no `final_asset_id`;
- expose no Final-binding confidence;
- do not participate in the frontend “unbound/conflict/low-confidence” Character calculation because the existing table consumes only `characters`;
- are retained for future diagnostic UI rather than deleted.

This fixes the old UI mismatch where Final Character identity was correct but the Shot table could still display only `待解析人物` or hide a face-optional recovered Track.

## 9. Evidence / Final Asset separation

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

Old analysis runs do not automatically gain the new recovery metadata. To test the new identity/binding algorithm, rerun asset extraction so new `CharacterTrack` and `ShotCharacterBinding` records are produced.

## 10. Current character code map

Formal or currently-wired modules:

```text
engine/app/character_visual_v2.py              compatibility facade; points to V10.1
engine/app/character_runtime_v6.py             formal V10.1 runtime entry (filename retained for compatibility)
engine/app/character_observation_v10.py        Person Instance detection/capture
engine/app/character_person_evidence_v10.py    evidence eligibility / crop policy
engine/app/character_person_features_v9.py     separated Person feature channels
engine/app/character_tracking_v10.py           temporal tracking
engine/app/character_identity_v10.py           V10 base classifier helpers
engine/app/character_identity_v101.py          formal V10.1 global identity classifier
engine/app/character_shot_binding_v101.py      V10.1 known-identity Track recovery + recovery provenance
engine/app/character_persistence_v6.py         current persistence bridge; preserves formal V10.1 profile + Track recovery JSON
engine/app/character_gallery_v10.py            classified person gallery
engine/app/character_evidence_store_v10.py     pre/post-classification evidence store
engine/app/asset_final_gate_v10.py             formal V10/V10.1 Final Gate entry
engine/app/asset_final_gate_v9.py              shared materializer + Shot-presence confidence aggregation
engine/app/asset_workspace_v3.py               Final Asset workspace/bindings legacy core
engine/app/asset_workspace_character_v101.py   formal V10.1 Character evidence API adapter
engine/app/asset_routes_v3.py                  always decorates workspace responses with V10.1 Character evidence
engine/app/content_analysis_v2.py              Project asset analysis tables/core
```

Do not infer the active version from filenames alone. Some compatibility filenames (`character_runtime_v6.py`, `character_persistence_v6.py`, `character_person_features_v9.py`) intentionally remain while their formal caller is V10.1.

## 11. Models / runtime

Fixed local model set remains:

```text
YOLOX person detection
YoutuReID person re-identification
YuNet face detection
SFace face embedding/support
```

YoutuReID is the primary identity model signal. Clothing/body channels are supporting signals. Face is optional support and a hard-conflict signal when high-quality Face evidence disagrees.

Do not silently bundle non-commercial/research-only InsightFace/ArcFace pretrained weights. A future Face provider replacement must have a clear commercial/license path and must not change the Track → Identity → Final Asset contract.

## 12. Current implementation status

```text
01 剧集管理:
  IMPLEMENTED

02 拉片:
  IMPLEMENTED; real Windows/video regression remains release gate

03 资产:
  Character V10.1 capture-first classification implemented
  V10.1 risky-view identity creation implemented
  V10.1 shot-level known-identity Track recovery implemented
  Per-Track recovery provenance persistence implemented
  Identity confidence / Shot-presence confidence separation implemented
  Face-optional Shot evidence API adapter implemented
  RESOLVED vs UNRESOLVED workspace evidence separation implemented
  V10/V10.1 fail-closed Final Gate implemented
  NEEDS LOCAL REAL-VIDEO REGRESSION after latest binding change

04 内容剧本:
  PLANNED / partial low-level compatibility code exists

05 重制设计:
  PLANNED

06 生成 / 导出:
  PLANNED
```

## 13. Current test / CI reality

GitHub Actions is **not globally green**. Recent runs after these changes continue to show the same repository-level pattern:

- backend compile step passes;
- FastAPI import step passes;
- full pytest job fails because the repository CI is still missing/full of legacy runtime assumptions (`cv2`, external `trackers`, media/FFmpeg paths and old semantic assertions among the known categories);
- frontend build remains blocked by the existing `vue-tsc` / TypeScript compatibility issue.

Therefore do **not** claim “all tests pass” from the current repository state.

New/updated focused regression coverage now locks:

```text
repeated unresolved Track → confirmed identity
recovery Track gets source/target/shot/score provenance
ambiguous winner → stays unresolved
cannot-link conflict → no recovery
recovered-only Shot → binding uses Track presence confidence
normal/direct Shot → binding keeps identity-confidence fallback
mixed direct + recovered fragments → direct assignment takes precedence
face_visible=false recovered Track → still visible as RESOLVED Shot evidence
UNRESOLVED Track → moves to character_diagnostics, never Final suggestion
```

Real-video release validation must still happen on the user's Windows environment with the installed model/MOT/FFmpeg runtime.

## 14. Immediate next action

```text
1. Pull latest main locally.
2. Prepare/verify F05 Character models and Mature MOT runtime.
3. Rerun asset extraction on the same real short-drama sample (old Run will not be auto-upgraded).
4. Verify Final Character count first.
5. Verify previously wrong ShotCharacterBinding rows, especially single-character closeups and two-character Shots.
6. Confirm the Shot table AI line now shows RESOLVED Final Character evidence; pending fragments should no longer replace it.
7. If a Shot is still unbound, inspect CharacterTrack.evidence_json.identity_recovery and candidate track_recovery_* metadata before tuning thresholds.
8. Only after real-video confirmation continue threshold tuning or the next content-script feature.
```

## 15. Documentation rule for future sessions

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
