# Character V10.1 — Capture-first Identity + Explicit Shot Character Assignment

> **Status:** IMPLEMENTED / NEEDS WINDOWS REAL-VIDEO BINDING ACCEPTANCE  
> **Formal runtime profile:** `character-v10.1-capture-first-model-classification`  
> **Formal asset profile:** `f05-assets-v10.1-person-evidence-model-classification`  
> **Formal resolver:** `person-evidence-model-classifier-v10.1`  
> **Shot assignment:** `v10.1-shot-character-assignment-1` / `V10_1_SHOT_CHARACTER_ASSIGNMENT`  
> **Last synchronized:** 2026-08-27 16:22 +08:00

## 1. Why the binding architecture changed

Real-video testing established a clear split:

```text
Global Character identities can be correct
while some Shot rows still miss a visible known Character
```

The old V10.1 approach tried to solve this by moving unresolved Tracks into already-confirmed identities. That improved some rows but kept Final Shot binding coupled to Candidate Track ownership.

The current architecture separates the decisions completely:

```text
Who are the project-level people?
!=
Which known people are present in this Shot?
```

Global identity remains conservative. After identities are confirmed, a dedicated Shot assignment engine independently scores every Shot against the known Character galleries.

## 2. Formal pipeline

```text
Shot / Reference Clip
↓
YOLOX Person Detection + safe YuNet Face fallback
↓
one detected person → one isolated Person Instance
↓
YoutuReID
+ clothing_upper / clothing_lower
+ body_hist / body_structure
+ optional SFace
↓
persist model-usable Person Evidence
↓
Mature MOT
↓
resolve_global_identities(tracks)
↓
RESOLVED identities + UNRESOLVED visual evidence
↓
assign_shot_characters(all_original_tracks, candidates)
↓
explicit Shot × known-Character presence assignments
↓
write identity classification back to Person Evidence
↓
persist CharacterCandidate / CharacterTrack / assignment metadata
↓
Final Character Gate
↓
ShotCharacterBinding from explicit assignments
↓
Asset Workspace V10.1 adapter
```

The formal runtime no longer calls the historical Track-recovery passes:

```text
recover_unresolved_tracks
recover_fragmented_shot_presence
```

Their modules remain in the repository only for historical compatibility/tests.

## 3. Four semantic layers

```text
Observation / Person Evidence / CharacterTrack
= visual evidence

CharacterCandidate / Identity Class
= project-level person identity

Shot Character Assignment
= whether an already-confirmed Character appears in one Shot

Character + ShotCharacterBinding
= editable Final asset / binding
```

A Track may remain unresolved identity evidence while the Shot-level aggregate still confidently says that 人物002 is present. That is valid and intentional.

The accepted future Breakdown-first plan adds a **separate** semantic Draft layer:

```text
LocalSubject / ShotSemanticDraft / SceneSegmentDraft
= anonymous content understanding
```

It is not a fifth Character identity layer and cannot be treated as Final Character truth.

## 4. Capture-first identity contract is unchanged

Evidence condition is metadata, not Character cardinality:

```text
CLEAN
OCCLUDED
CONTAMINATED
PARTIAL
```

YoutuReID remains the primary new-identity model channel. Clothing/body channels remain separate supporting evidence. Face is optional support and a high-quality conflict signal.

A formal new identity still requires:

```text
>=3 independent Shots
>=3 model-usable Person Images
stable cross-Shot Person-ReID support
unique identity class
same-sample cannot-link preserved
no high-quality Face hard conflict
```

Strong risky views may seed only under stricter confirmation. Weak/tiny partial evidence cannot create a Character.

The Shot assignment engine can only select among already-RESOLVED identities; it cannot create one.

A future VLM/Breakdown Draft cannot bypass these requirements.

## 5. Formal Shot assignment module

```text
engine/app/character_shot_assignment_v101.py
```

Version/source:

```text
ASSIGNMENT_VERSION = v10.1-shot-character-assignment-1
ASSIGNMENT_SOURCE = V10_1_SHOT_CHARACTER_ASSIGNMENT
```

Input:

```text
all original Tracks / Observations from the Run
+ every already-RESOLVED Character identity gallery
```

Output on each RESOLVED Candidate:

```text
shot_presence_assignments[]
```

The engine **never mutates `candidate.tracks`**. This is the central correctness rule.

## 6. Direct identity Shot presence

When original observations are already part of a RESOLVED identity, their Shot gets an explicit assignment:

```text
mode = DIRECT_IDENTITY
```

This converts an already-proven identity occurrence into the same formal output used by all recovered Shot-presence paths.

## 7. Known-Face Shot presence

Face is used only after the Character identity already exists.

Current gates:

```text
FACE_PAIR_MIN_SCORE = 0.72
FACE_SUPPORTED = 0.36
FACE_STRONG = 0.50
FACE_WINNER_MARGIN = 0.08
MIN_FACE_REPEAT_OBSERVATIONS = 2
MIN_FACE_REPEAT_TIMESTAMPS = 2
MIN_FACE_REPEAT_MEDIAN = 0.40
```

Rules:

```text
current Shot Face
→ compare with confirmed Gallery Face evidence
→ require support from >=2 independent Gallery Shots
→ compare against every RESOLVED Character
→ require unique winner + margin
```

One sufficiently strong unique Face match may produce:

```text
mode = FACE_STRONG
```

Moderate Face support must repeat at multiple current-Shot timestamps and may produce:

```text
mode = FACE_REPEATED
```

A repeated high-quality Face conflict is fail-closed. One noisy Gallery crop is not enough to veto an otherwise valid identity.

This path never makes Face mandatory for identity creation.

## 8. Body / Person-ReID Shot presence

Current gates:

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

Non-direct body presence must repeat through the Shot and remain uniquely attributable to one known Character.

Successful recovery produces:

```text
mode = BODY_REID
```

Normal non-risky evidence may combine Person-ReID with one supporting appearance channel. Risky `CONTAMINATED/PARTIAL` evidence requires stronger Person-ReID plus more appearance support.

## 9. Multi-person Shot occupancy / cannot-link

Same-sample different Person Instances remain hard cannot-link.

The assignment engine additionally uses this as a current-Shot occupancy constraint:

```text
same timestamp:
Person Instance A = direct 人物001
Person Instance B cannot-link A

⇒ B cannot also be assigned to 人物001
⇒ B must compete among other known identities or stay unassigned
```

This is essential for two-person Shots where one Character is already obvious but the second Character is partial, side-view or briefly visible.

The real `SHOT 0004` case is the primary acceptance target for this rule.

## 10. Grouping fragmented Tracks without changing ownership

MOT may split one visible person into several short Tracks. The assignment engine may aggregate several compatible fragment votes in the same Shot.

But it does not merge/move those Tracks in identity storage.

```text
fragment A ─┐
fragment B ─┼→ same known Character + repeated support → one Shot presence
fragment C ─┘

CharacterTrack ownership remains unchanged
```

Cannot-link fragments cannot jointly support the same Character.

## 11. Assignment persistence

Candidate metadata persists:

```text
shot_assignment_version
shot_assignment_source
shot_assignment_policy
shot_presence_assignments
shot_presence_shot_ids
shot_presence_count
shot_presence_recovered_count
```

Each assignment may contain:

```text
shot_id
shot_ordinal
episode_order
confidence
mode
source
support_count
support_timestamp_count
track_count
face_support_count
winner_margin
```

The existing persistence bridge writes this into `CharacterCandidate.evidence_json`; no DB migration is required.

`CharacterTrack.evidence_json.identity_recovery` remains readable for historical old Runs but is no longer the formal V10.1 binding source.

## 12. Identity confidence vs Shot-presence confidence

```text
CharacterCandidate.confidence
= confidence in the project-level identity

shot_presence_assignments[].confidence
= confidence that the already-known Character is present in this Shot
```

These are deliberately separate quantities.

Direct identity assignments use the identity evidence confidence band. Face/Body recovered Shot assignments use their validated Shot-presence evidence score.

Future Breakdown Draft confidence / DraftResolution confidence must remain a third, separate provenance domain. It cannot be silently reused as Character identity or Shot-presence confidence.

## 13. Final Character Gate

Identity materialization remains fail-closed:

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

## 14. Final ShotCharacterBinding rule

Current V10.1 Runs are recognized by:

```text
shot_assignment_version is present
```

For those Runs:

```text
Final ShotCharacterBinding
= shot_presence_assignments only
```

This means:

```text
Candidate Track exists in Shot
but explicit assignment rejects that Shot
→ NO Final binding
```

and:

```text
Candidate has no Track ownership in Shot
but explicit aggregate confirms known Character presence
→ Final binding IS created
```

This is the key architectural correction.

An explicit empty assignment list never silently falls back to Track ownership.

Old persisted Runs without `shot_assignment_version` keep historical Track-derived binding so existing projects remain readable.

A future anonymous Draft is **not** a fallback source either.

## 15. Asset Workspace semantics

Formal adapter:

```text
engine/app/asset_workspace_character_v101.py
```

Contract:

```text
evidence_by_shot.characters
= RESOLVED Character Shot presence

evidence_by_shot.character_diagnostics
= UNRESOLVED visual diagnostics only
```

For current assignment-enabled Runs, resolved Character presence follows the explicit assignment map. Candidate Tracks that the assignment engine rejected do not leak back into the main Character line.

Gallery and Evidence-vs-Final pages remain diagnostics only. They do not define Final binding truth.

## 16. Formal code map

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
```

Historical compatibility modules not called by the formal runtime:

```text
engine/app/character_shot_binding_v101.py
engine/app/character_shot_presence_v101.py
```

## 17. Required regression contracts

At minimum keep these locked:

```text
1. multi-person frame → independent Person Instances
2. same-sample different people → cannot-link
3. weak Partial → cannot create Character
4. strong risky views across >=3 Shots → may form one identity
5. Face absent → confirmed identity may pass Final Gate
6. high-quality Face conflict → never merge identity
7. direct identity Track → explicit DIRECT_IDENTITY Shot assignment
8. strong known Face → may assign Character without moving Track ownership
9. repeated moderate known Face → may assign known Character
10. body/ReID presence requires repeated temporal support
11. ambiguous body fragment → stays unassigned
12. two-person Shot cannot-link occupancy prevents second instance from collapsing onto already-occupied Character
13. assignment engine never creates Character
14. assignment engine never moves candidate.tracks
15. explicit assignment may create Final binding without Candidate Track ownership in that Shot
16. Candidate Track absent from explicit assignment map cannot recreate Final binding
17. explicit empty assignment list does not fallback to Track ownership
18. historical Run without assignment version keeps old Track fallback
19. workspace follows explicit assignment map
20. UNRESOLVED evidence remains diagnostics only
21. Final identity gate still requires resolver + >=3 Shots/images
22. future Breakdown Draft alone cannot create Character or ShotCharacterBinding
23. future semantic context cannot override hard cannot-link / high-quality Face conflict without a separately approved successor contract
```

Focused tests:

```text
engine/tests/v2/test_character_shot_assignment_v101.py
engine/tests/v2/test_asset_final_gate_v10.py
engine/tests/v2/test_asset_workspace_character_v101.py
```

## 18. Validation status

Latest known backend CI after the explicit assignment work:

```text
28 failed, 187 passed, 1 skipped
```

Backend compile and FastAPI import pass. The new assignment-focused tests are not among the failures.

Existing failures remain known repository-level legacy/runtime/environment categories: lightweight CI lacks `cv2`, tracker runtime and FFmpeg; some historical V6 assertions no longer describe the formal V10.1 behavior.

Frontend CI remains blocked by the existing `vue-tsc` / TypeScript compatibility issue.

Do not mark Character V10.1 `STABLE/FROZEN` until the user accepts the real Windows binding result.

The documentation-only Breakdown-first plan does not change this validation status.

## 19. Real-video acceptance

A fresh asset extraction Run is mandatory after pulling this architecture. Old Runs do not gain `shot_presence_assignments` automatically.

Expected early-Shot binding on the current real sample:

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

If a Shot remains wrong, inspect that Character's persisted `shot_presence_assignments` and its mode/support/winner margin. Do not solve the next miss by adding more Gallery UI or blindly lowering global identity thresholds.

## 20. Future Breakdown-first integration guardrail

The accepted target workflow is documented in:

```text
docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
```

Its future Character-related phase is deliberately late:

```text
P1-P4
→ build and validate anonymous Draft / Scene / Prop path first

P5
→ only after current V10.1 real-video baseline acceptance
→ connect LocalSubject / Draft context to Character as an auxiliary, traceable layer
```

Until a separate successor Character contract is explicitly approved and tested:

```text
Draft says “人物A”
!= Character identity

Draft says “这里应该是人物001”
!= ShotCharacterBinding evidence

Semantic context
!= permission to bypass cannot-link / Face conflict / Final Gate
```

Therefore future developers must not “simplify” the Breakdown-first implementation by replacing V10.1 visual identity/assignment with VLM text classification.
