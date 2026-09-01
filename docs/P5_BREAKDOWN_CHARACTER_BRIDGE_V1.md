# P5 Breakdown ↔ Character Safe Bridge V1

Status: **IMPLEMENTED ON MAIN / UNIT CONTRACT PASS / REAL ACCEPTANCE RERUN REQUIRED**

Merged from PR #17. Merge commit: `ab4b11716f5c1c5ead7367119d1b2d787defe8f9`.

This contract defines a one-way, fail-closed bridge from the current anonymous Breakdown to already-confirmed Final Characters.

Core authority:

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
use appearance prose as identity authority
rewrite LocalSubject rows with Character FK
map historical Breakdown to current Shots by ordinal/timestamp
write Final ShotCharacterBinding
```

P5 may resolve a LocalSubject only when current revision-safe Shot-presence structure uniquely identifies one existing Final Character.

## V1 resolution rule

Within one Scene:

1. Build each LocalSubject's exact current-Shot presence signature from `ShotLocalSubject` + exact `ShotRevisionItem` anchors.
2. Build each Final Character's signature from current `ShotCharacterBinding` rows.
3. Ignore Scene Shots where the Breakdown recognized no LocalSubject at all; these provide no anonymous-person discrimination.
4. On the remaining subject-aware Shots, a LocalSubject and Character are compatible only when their presence signatures are exactly equal.
5. Resolve only a one-to-one unique signature. If multiple LocalSubjects or multiple Characters share the same signature, keep all affected subjects `UNRESOLVED`.
6. Empty signatures never resolve.

This deliberately prefers false negatives over false identity bindings.

Examples:

```text
人物1 = Shots 2,4,7
Character A = Shots 1,2,4,7
Shot 1 has no LocalSubject at all
=> compare only subject-aware Shots => exact match => may RESOLVE

人物1 = Shots 2,4
人物2 = Shots 2,4
Character A = Shots 2,4
Character B = Shots 2,4
=> anonymous signatures are not distinguishable => both UNRESOLVED
```

## Revision safety

Only consume a Breakdown Run when:

```text
run.is_current = true
run.status in READY / READY_WITH_WARNINGS
run.source_shot_revision_id = Episode current ShotRevision
ShotSemanticDraft.source_shot_revision_item_id belongs to that revision
ShotSemanticDraft.source_shot_id_snapshot = ShotRevisionItem.original_shot_id
that original Shot still exists in the Episode
```

No ordinal/timestamp-nearest fallback is allowed.

## Output

P5 output is a separate read model. It does not modify frozen Breakdown data.

Each Scene-local person result carries:

```text
scene_person_ref = P1/P2/... aligned with frozen Scene Timeline ordering
local_subject_id
local_subject_ordinal
local_display_name
status = RESOLVED | UNRESOLVED
character_id / character_name only when RESOLVED
support Shot IDs / ordinals
resolution_basis
```

Files on `main`:

```text
engine/app/breakdown_character_bridge_contract_v1.py
engine/app/breakdown_character_bridge_v1.py
engine/tests/v2/test_breakdown_character_bridge_v1.py
scripts/run_breakdown_p5_character_bridge_acceptance_v1.py
```

P6 may later use this read model to render a Final Breakdown with real Character names while leaving the frozen G2 Scene Timeline unchanged.

## User-local acceptance

Unit / safety contract:

```powershell
python -m pytest engine/tests/v2/test_breakdown_character_bridge_v1.py -q
```

Observed user-local result on 2026-08-31:

```text
7 passed
```

Therefore the deterministic/fail-closed P5 unit contract is PASS.

Real current Episode inspection:

```powershell
python scripts/run_breakdown_p5_character_bridge_acceptance_v1.py EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
```

An earlier P5 inspection returned:

```text
status = READY
scene_count = 2
person_count = 4
resolved_count = 0
unresolved_count = 4
warning = 当前剧集还没有 Final Character Shot 绑定，人物将保持未解析。
```

A later direct read of the same project database disproved the upstream-zero-binding diagnosis. Current observed truth is:

```text
Content Analysis Run = CONTENT_RUN_d6f66f45b758459cad69207a4eb81e60
profile = f05-assets-v10.1-person-evidence-model-classification
status = READY_WITH_WARNINGS
resolved CharacterCandidates = 3
current AssetRevision = ASSETREV_d387044c48824c2da67ba61e833dcc6f / revision 14 / AUTO
Final Characters = 3
Episode Final ShotCharacterBindings = 29

人物 001 = Shots 3,4,5,6,9,10,11,22
人物 002 = Shots 7,9,10,12,13,15,16,18,22,23,25,27,28
人物 003 = Shots 14,17,19,21,24,27,28,30
```

Therefore Character V10.1 assignment and Final Gate materialization are present for this Episode. The earlier `bindings=0` P5 output is inconsistent with the current database and with the current `main` bridge query, which reads the same `ShotCharacterBinding` table by project + current Episode Shot IDs.

Current acceptance action is to rerun P5 from an up-to-date `main` working tree and review the actual resolved mappings. Do not keep treating Final Binding materialization as the blocker unless a fresh rerun again proves it.

Under the current exact-signature contract and the observed data, Scene 1 `P2` has the same subject-aware Shot signature as Final `人物 001` (`3,4,5,6,9,10,11`) and is expected to resolve. Scene 1 `P1` and both Scene 2 anonymous people do not exactly match a unique Final Character signature and are expected to remain unresolved. This expectation must still be confirmed by the real runner output before marking P5 FINAL PASS.

Acceptance is not based on maximizing `resolved_count`. A correct real result may leave ambiguous people unresolved. Review instead that every `RESOLVED` mapping is visibly correct and that always-co-occurring/ambiguous people are not guessed.

Do not mark P5 FINAL PASS until the fresh real Final-Character-bound runner result is reviewed.
