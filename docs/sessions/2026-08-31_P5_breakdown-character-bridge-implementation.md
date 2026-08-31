# P5 Breakdown ↔ Character Safe Bridge — Implementation Handoff

Date: 2026-08-31

Status: **IMPLEMENTED ON BRANCH / USER-LOCAL ACCEPTANCE PENDING**

Branch: `p5-breakdown-character-bridge`

## Why P5 is resumed now

P5 was previously paused because the anonymous Episode-context Breakdown baseline was not stable enough to safely reconcile with Character identity. That blocker is now removed by the accepted/frozen G1 + G2 baseline.

P5 does not reopen Character V10.1 or G2.

## Authority direction

```text
Character V10.1 identity
→ explicit Shot × known Character Assignment
→ Final Character + ShotCharacterBinding
→ P5 deterministic presence-signature reconciliation
→ LocalSubject may become RESOLVED for later rendering
```

Never reverse this arrow. Breakdown prose, ASR names, relationship terms, role hints, appearance summaries and P1/P2 labels are not Character identity evidence.

## V1 algorithm

For each current Scene:

```text
LocalSubject -> set of exact current Shot IDs
Final Character -> set of current ShotCharacterBinding Shot IDs
subject-aware Shots = union of all LocalSubject Shot IDs
project Character signatures onto subject-aware Shots
unique exact signature <-> unique exact signature => RESOLVED
anything ambiguous / duplicated / partial => UNRESOLVED
```

Shots where the Breakdown recognizes zero LocalSubjects are ignored for discrimination, because they cannot tell P5 which anonymous person was present.

Always-co-occurring anonymous people remain unresolved even when the same number of Final Characters are present.

## Revision safety

P5 consumes only:

```text
current READY/READY_WITH_WARNINGS BreakdownRun
exact current ShotRevision
exact ShotRevisionItem anchors
source_shot_id_snapshot == original_shot_id
original Shot still current
current Final Asset Revision
current Final ShotCharacterBinding rows
```

No ordinal or nearest-timestamp history remapping exists.

## Files

```text
engine/app/breakdown_character_bridge_contract_v1.py
engine/app/breakdown_character_bridge_v1.py
engine/tests/v2/test_breakdown_character_bridge_v1.py
scripts/run_breakdown_p5_character_bridge_acceptance_v1.py
docs/P5_BREAKDOWN_CHARACTER_BRIDGE_V1.md
```

No frozen G1/G2 module and no Character V10.1 module is modified.

## Acceptance commands

```powershell
python -m pytest engine/tests/v2/test_breakdown_character_bridge_v1.py -q
python scripts/run_breakdown_p5_character_bridge_acceptance_v1.py EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
```

For real review, do not require every anonymous person to resolve. The acceptance question is:

```text
Are all RESOLVED mappings visibly correct?
Are ambiguous co-occurring people left UNRESOLVED rather than guessed?
```

Do not mark P5 FINAL PASS until user-local evidence is supplied.

## Next after P5 acceptance

P6 can compose frozen G2 Scene Timeline + accepted P5 resolution into a Final Breakdown renderer that replaces only resolved anonymous display references with Final Character names/assets. P6 must not rewrite frozen G2 factual objects or ASR/OCR text.
