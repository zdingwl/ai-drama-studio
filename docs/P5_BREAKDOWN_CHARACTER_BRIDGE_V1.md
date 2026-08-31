# P5 Breakdown ↔ Character Safe Bridge V1

Status: **DESIGN LOCK / IMPLEMENTATION STARTING**

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
local_subject_id
local_subject_ordinal
local_display_name
status = RESOLVED | UNRESOLVED
character_id / character_name only when RESOLVED
support Shot IDs / ordinals
resolution_basis
```

P6 may later use this read model to render a Final Breakdown with real Character names while leaving the frozen G2 Scene Timeline unchanged.
