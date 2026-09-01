# P5 Breakdown ↔ Character Safe Bridge — Implementation Handoff

Date: 2026-08-31  
Final acceptance recorded: 2026-09-01

Status: **FINAL PASS / FROZEN**

Historical branch: `p5-breakdown-character-bridge`  
PR: `#17` / merged / closed  
Merge commit: `ab4b11716f5c1c5ead7367119d1b2d787defe8f9`

## Authority direction

```text
Character V10.1 identity
→ explicit Shot × known Character Assignment
→ Final Character + ShotCharacterBinding
→ P5 deterministic presence-signature reconciliation
→ LocalSubject may become RESOLVED for later rendering
```

Never reverse this arrow. Breakdown prose, ASR names/speaker labels, relationship terms, role hints, appearance summaries and P1/P2 labels are not Character identity evidence.

## Frozen V1 algorithm

For each current Scene:

```text
LocalSubject -> set of exact current Shot IDs
Final Character -> set of current ShotCharacterBinding Shot IDs
subject-aware Shots = union of all LocalSubject Shot IDs
project Character signatures onto subject-aware Shots
unique exact signature <-> unique exact signature => RESOLVED
anything ambiguous / duplicated / partial => UNRESOLVED
```

Shots where Breakdown recognizes zero LocalSubjects are ignored for discrimination. Always-co-occurring or non-unique people remain unresolved.

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

## Frozen files

```text
engine/app/breakdown_character_bridge_contract_v1.py
engine/app/breakdown_character_bridge_v1.py
engine/tests/v2/test_breakdown_character_bridge_v1.py
scripts/run_breakdown_p5_character_bridge_acceptance_v1.py
docs/P5_BREAKDOWN_CHARACTER_BRIDGE_V1.md
```

No frozen G1/G2 module and no Character V10.1 module was modified by P5.

## Final user-local acceptance

Deterministic contract:

```powershell
python -m pytest engine/tests/v2/test_breakdown_character_bridge_v1.py -q
```

Observed:

```text
7 passed
```

Real Episode:

```powershell
python scripts/run_breakdown_p5_character_bridge_acceptance_v1.py EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
```

Observed and accepted:

```text
status = READY
breakdown_run = BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
scene_count = 2
person_count = 4
resolved_count = 1
unresolved_count = 3
warnings = []

Scene1 P1 -> UNRESOLVED
Scene1 P2 -> RESOLVED -> 人物 001 / FINAL_SHOT_BINDING_SIGNATURE_V1
Scene2 P1 -> UNRESOLVED
Scene2 P2 -> UNRESOLVED
```

The unique accepted match is exact on Shots `3,4,5,6,9,10,11`. The three unresolved people have no unique exact Final Character signature and correctly remain anonymous.

Real upstream Character evidence for the same project:

```text
Content Run = CONTENT_RUN_d6f66f45b758459cad69207a4eb81e60
resolved CharacterCandidates = 3
AssetRevision = ASSETREV_d387044c48824c2da67ba61e833dcc6f / revision 14 / AUTO
Final Characters = 3
Episode Final ShotCharacterBindings = 29
```

Acceptance criterion was correctness, not maximizing resolution. Every RESOLVED mapping is supported by the frozen exact-signature rule and ambiguous/non-matching people are not guessed.

Therefore:

```text
P5 = FINAL PASS / FROZEN
```

## Next after P5

P6 is the next code frontier. It should compose frozen G2 Scene Timeline + frozen P5 resolution into a separate Final Breakdown read model/rendering layer:

```text
P5 RESOLVED -> render existing Final Character name/assets
P5 UNRESOLVED -> keep 人物N
ASR/OCR -> unchanged
frozen Shot factual objects -> unchanged
Final Character bindings -> read-only
```

P6 must not rewrite frozen G2 or P5 semantics and must not introduce prose/name/speaker fallback identity inference.
