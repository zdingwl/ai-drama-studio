# Character V10.1 — Risky-view Identity Recovery

V10.1 fixes a structural false-negative in V10: image-condition labels no longer decide whether a real person can ever become a Character.

## Problem

V10 captured all model-usable Person Instance crops, but only CLEAN / OCCLUDED crops could seed a new identity. A real person who appears mostly seated near a frame edge, overlapped by another person, or in a substantial partial-body crop could therefore be detected and persisted many times but remain permanently UNRESOLVED.

## Formal rule

Capture remains first:

```text
Frame
→ detect every Person Instance
→ split multi-person frame into isolated person crops
→ persist Person Evidence
→ extract YoutuReID + clothing/body + optional Face
→ classify identities
```

Image condition is evidence metadata, not identity cardinality:

- CLEAN / OCCLUDED: normal identity seed candidates when quality is sufficient.
- CONTAMINATED: may seed when the person crop is large enough, detector-backed and high quality.
- PARTIAL: may seed only when it is a substantial detector-backed person crop with sufficient visible area and quality.
- weak/tiny/low-score PARTIAL: save and classify/attach only; never creates a Character.

Risky seeds are confirmed with a stricter model contract:

```text
>= 3 independent Shots
+ >= 3 model-usable Person Images
+ strong cross-shot YoutuReID consistency
+ stricter threshold than normal CLEAN identity creation
+ same-sample cannot-link must never be violated
→ CONFIRMED Person Identity
```

Face remains optional support and is never required.

## Acceptance

For a real person who appears in three or more independent Shots mostly as contaminated / frame-edge / substantial partial crops:

1. the crops must exist in `analysis/<run_id>/person_evidence/`;
2. the crops may participate in new-identity formation;
3. a stable strong Person-ReID class may become one Final Character;
4. isolated weak fragments must remain UNRESOLVED;
5. same-frame different people must never merge.

Formal runtime profile:

```text
character-v10.1-capture-first-model-classification
```

Formal asset profile:

```text
f05-assets-v10.1-person-evidence-model-classification
```
