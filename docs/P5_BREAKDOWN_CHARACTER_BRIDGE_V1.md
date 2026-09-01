# P5 Breakdown ↔ Character Safe Bridge V1

Status: **FINAL PASS / FROZEN**

Merged from PR #17. Merge commit: `ab4b11716f5c1c5ead7367119d1b2d787defe8f9`.
User-local deterministic + real-Episode acceptance completed on 2026-09-01.

This contract defines a one-way, fail-closed bridge from the anonymous Breakdown to already-confirmed Final Characters.

## Authority

```text
Breakdown LocalSubject = anonymous semantic person
Character V10.1 + Final ShotCharacterBinding = identity truth
P5 = deterministic read-only reconciliation
```

P5 MUST NOT:

```text
create Character identity
change Character V10.1 gates
use dialogue/name/relationship prose as identity authority
use appearance/role prose as identity authority
rewrite LocalSubject rows with Character FK
map historical Breakdown to current Shots by ordinal/timestamp
write or modify Final ShotCharacterBinding
```

## Frozen V1 resolution rule

Within each current Scene:

1. Build each LocalSubject exact current-Shot presence signature from `ShotLocalSubject` + exact `ShotRevisionItem` anchors.
2. Build each Final Character signature from current `ShotCharacterBinding` rows.
3. Project Character signatures onto subject-aware Shots only; a Shot with no LocalSubject cannot distinguish anonymous people.
4. Resolve only when anonymous signature and Character signature are exactly equal and unique one-to-one.
5. Duplicate, partial, conflicting, missing or empty signatures remain `UNRESOLVED`.

This deliberately prefers false negatives over false identity bindings.

## Revision safety

Only consume when all of these remain true:

```text
BreakdownRun.is_current = true
BreakdownRun.status in READY / READY_WITH_WARNINGS
BreakdownRun.source_shot_revision_id = Episode current ShotRevision
ShotSemanticDraft.source_shot_revision_item_id belongs to that revision
ShotSemanticDraft.source_shot_id_snapshot = ShotRevisionItem.original_shot_id
original Shot still exists in the Episode
current Final Asset Revision exists before Final identity can resolve
```

No ordinal/timestamp-nearest fallback is allowed.

## Frozen files

```text
engine/app/breakdown_character_bridge_contract_v1.py
engine/app/breakdown_character_bridge_v1.py
engine/tests/v2/test_breakdown_character_bridge_v1.py
scripts/run_breakdown_p5_character_bridge_acceptance_v1.py
```

Do not reopen these semantics without a concrete regression.

## Accepted user-local evidence

Unit / safety contract:

```powershell
python -m pytest engine/tests/v2/test_breakdown_character_bridge_v1.py -q
```

Observed:

```text
7 passed
```

Real Episode inspection:

```powershell
python scripts/run_breakdown_p5_character_bridge_acceptance_v1.py EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
```

Accepted result:

```text
status = READY
breakdown_run = BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
scene_count = 2
person_count = 4
resolved_count = 1
unresolved_count = 3
warnings = []

Scene 1 / P1 = UNRESOLVED / NO_MATCHING_FINAL_CHARACTER_SIGNATURE
Scene 1 / P2 = RESOLVED -> 人物 001 / FINAL_SHOT_BINDING_SIGNATURE_V1
Scene 2 / P1 = UNRESOLVED / NO_MATCHING_FINAL_CHARACTER_SIGNATURE
Scene 2 / P2 = UNRESOLVED / NO_MATCHING_FINAL_CHARACTER_SIGNATURE
```

The accepted unique match is structurally exact:

```text
Scene 1 P2 support Shots = 3,4,5,6,9,10,11
Final 人物 001 projected signature = 3,4,5,6,9,10,11
=> unique exact match => RESOLVED
```

The other three anonymous people do not have a unique exact Final Character signature and correctly remain unresolved. Acceptance is based on correctness and fail-closed behavior, not maximizing `resolved_count`.

## Accepted upstream Character truth used by P5

Current real database evidence confirmed:

```text
Content Run = CONTENT_RUN_d6f66f45b758459cad69207a4eb81e60
profile = f05-assets-v10.1-person-evidence-model-classification
resolved CharacterCandidates = 3
AssetRevision = ASSETREV_d387044c48824c2da67ba61e833dcc6f / revision 14 / AUTO
Final Characters = 3
Episode Final ShotCharacterBindings = 29
```

P5 did not modify Character V10.1, Final Gate, Final assets or frozen G2 objects.

## Next

P6 may compose frozen G2 Scene Timeline + frozen P5 resolution into a separate Final Breakdown read model/rendering layer. P6 may replace only safely resolved anonymous display references with Final Character names/assets. Unresolved people remain anonymous. ASR/OCR and frozen Shot factual objects remain unchanged.
