# Session Handoff — Character V10.1 Shot Binding Provenance

Date: 2026-08-27 12:50 +08:00  
Scope: PROJECT / 03 资产 / Character V10.1  
Branch: `main`

## 1. Goal

Continue the planned fix for the real-sample failure where global Character recognition is correct but per-Shot Character binding is missing/wrong.

This session hardened the already-implemented `recover_unresolved_tracks()` path so the recovery decision survives persistence, Final Binding can use Shot-specific presence confidence, and the Asset review API no longer hides confirmed face-optional Tracks or mixes unresolved fragments into the main Character evidence list.

## 2. Starting state

Before this session the repository already had:

```text
resolve_global_identities()
→ recover_unresolved_tracks()
→ persist Candidate / Track
→ Final Gate
→ ShotCharacterBinding
```

But three gaps remained:

1. recovery score/source lived only in candidate summary metadata and was not attached to the exact persisted Track;
2. `ShotCharacterBinding.confidence` always reused global `CharacterCandidate.confidence`, conflating identity confidence with Shot presence;
3. the Asset Workspace diagnostic serializer still filtered Character Tracks by `face_visible`, so a valid V10.1 body/side/back/recovered Track could disappear from the Shot table, while an unresolved face fragment could still show as `待解析人物` in the main AI line.

## 3. Code completed

### Track-level recovery provenance

Updated:

```text
engine/app/character_shot_binding_v101.py
```

A successful known-identity recovery now sets:

```text
track.identity_recovery = {
  source: "V10_1_TRACK_KNOWN_IDENTITY_RECOVERY",
  target_candidate_id,
  shot_id,
  score,
  observation_count,
  policy
}
```

Candidate summary still records `track_recovery_*` for audit/debug.

### Persistence bridge

Updated:

```text
engine/app/character_persistence_v6.py
```

The historical filename remains for compatibility, but current behavior now:

```text
CharacterTrack.evidence_json.identity_recovery
= persisted exact Track recovery provenance
```

It also preserves an already-formal V9/V10/V10.1 Run profile instead of temporarily replacing it with the historical V6 profile during persistence.

### Final Shot binding confidence

Updated shared materializer:

```text
engine/app/asset_final_gate_v9.py
```

Formal V10/V10.1 entry remains:

```text
engine/app/asset_final_gate_v10.py
```

Current rule:

```text
normal/direct Track exists in Shot
→ binding confidence = candidate/global identity confidence fallback

Shot represented only by recovered Track(s)
→ binding confidence = max(valid Track recovery score)
```

Multiple fragments for one Character in one Shot still create one `ShotCharacterBinding`.

Final Character metadata also carries candidate-level `track_recovery_*` audit fields.

### Face-optional Shot evidence API

Added:

```text
engine/app/asset_workspace_character_v101.py
```

Reason: `asset_workspace_v3._evidence_by_shot()` still contains a historical `track.face_visible` filter.

Formal API response now uses:

```text
evidence_by_shot[shot_id].characters
= RESOLVED Character evidence only

evidence_by_shot[shot_id].character_diagnostics
= UNRESOLVED evidence only
```

A confirmed V10.1 Character is no longer hidden merely because the Track has no visible Face.

UNRESOLVED diagnostics have no Final Asset ID and no Final-binding confidence.

Updated:

```text
engine/app/asset_routes_v3.py
```

Every Asset Workspace response returned by the route layer is decorated with the V10.1 Character evidence adapter.

Task/status wording was also aligned from V10 to V10.1.

### Frontend API types

Updated:

```text
frontend/src/types/studio.ts
```

`AssetEvidenceItem` now describes:

```text
identity_status
face_required
recovered_track
confidence_source
recovery_source
```

`ShotAssetEvidence` now allows:

```text
character_diagnostics
```

No current component must render diagnostics; the current Shot review table consumes `characters`, so unresolved fragments no longer contaminate its final Character evidence calculation.

## 4. Regression tests added/updated

Updated:

```text
engine/tests/v2/test_character_shot_binding_v101.py
```

Locks:

```text
successful recovery provenance
ambiguous winner has no recovery provenance
cannot-link failure has no recovery provenance
```

Updated:

```text
engine/tests/v2/test_asset_final_gate_v10.py
```

Locks:

```text
recovered-only Shot → recovery score
normal/direct Shot → identity confidence fallback
mixed direct + recovered Track → direct fallback wins
```

Added:

```text
engine/tests/v2/test_asset_workspace_character_v101.py
```

Locks:

```text
face_visible=false recovered Track → still RESOLVED Shot Character evidence
Scene/Prop evidence survives decoration
UNRESOLVED Track → character_diagnostics only
UNRESOLVED has final_asset_id=null and confidence=null
```

## 5. API / DB / file contract changes

DB schema: **no change**.

Existing fields are reused:

```text
CharacterTrack.evidence_json
ShotCharacterBinding.confidence
Character.metadata_json
```

Workspace JSON adds an optional diagnostic field:

```text
evidence_by_shot[shot_id].character_diagnostics
```

Character items additionally expose optional identity/recovery metadata.

## 6. Technical decisions

1. Do not fake `face_visible=true` to make V10.1 evidence appear in the UI.
2. Do not make unresolved Evidence a Final Character just to fill a Shot.
3. Keep identity confidence and Shot presence confidence semantically separate.
4. Store recovery provenance on the exact Track because Candidate summary alone cannot tell which Shot/Track caused a Final binding.
5. Keep unresolved evidence available for diagnostics, but remove it from the main resolved Character list used by the current review matrix.
6. Avoid a DB migration for this fix; the current JSON Evidence contract can carry provenance without losing auditability.
7. The old `asset_workspace_v3` core remains for Final Asset/Revision behavior; V10.1 Character evidence is adapted at the API response boundary until the legacy serializer is fully retired/refactored.

## 7. Important commits in this coding session

```text
e676445  fix: persist V10.1 track recovery provenance
d75a8f5  fix: persist recovered track identity evidence
d1d48d5  fix: use shot-level recovery confidence in bindings
a8cb6c2  test: lock track recovery provenance
5ec4a22  test: separate identity and shot binding confidence
ccc8bf1  feat: expose face-optional V10.1 shot character evidence
a07ec46  fix: surface V10.1 face-optional shot evidence
371af74  test: show recovered face-optional shot evidence
b3d82f8  fix: keep unresolved people out of final shot evidence
84b3109  test: separate unresolved shot diagnostics
9bea9ae  types: model V10.1 shot character diagnostics
```

Documentation commits follow these code commits in the same session.

## 8. CI / validation reality

GitHub Actions was observed during this session.

Recent backend jobs still show:

```text
Compile V2 backend: PASS
Import FastAPI app: PASS
Full pytest: FAIL
```

Frontend still fails at the pre-existing build step.

The repository-wide CI remains non-green for already-documented legacy/environment categories; this session must not be described as “all tests pass”.

The focused tests above were added as regression coverage, but final acceptance remains the real Windows short-drama rerun.

## 9. What is not completed

No real-media rerun was possible from the GitHub coding environment.

Therefore the following are still pending:

```text
real Final Character count verification
real SHOT binding comparison against the user's sample
threshold tuning if any previously wrong Shot still fails
```

## 10. Next exact action

On the Windows project checkout:

```text
1. pull latest main
2. verify F05 models + Mature MOT runtime
3. rerun asset extraction; do not reuse the old analysis Run
4. verify the known global Character count is still correct
5. verify the previously wrong Shot rows now bind the same Final Character IDs
6. check that the main AI Character line shows RESOLVED characters instead of pending fragments
7. if still wrong, inspect CharacterTrack.evidence_json.identity_recovery and candidate track_recovery_* before changing thresholds
```

## 11. New conversation read order

Read:

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/ASSET_CHARACTER_RECOGNITION_V10_1.md
this session handoff
```

Then inspect:

```text
engine/app/character_shot_binding_v101.py
engine/app/character_persistence_v6.py
engine/app/asset_final_gate_v9.py
engine/app/asset_final_gate_v10.py
engine/app/asset_workspace_character_v101.py
engine/app/asset_routes_v3.py
```
