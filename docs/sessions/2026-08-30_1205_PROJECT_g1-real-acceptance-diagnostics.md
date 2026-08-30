# 2026-08-30 12:05 +08:00 — G1 real-acceptance diagnostics handoff

## Repository truth checked first

Current `main` before this change was still:

```text
5e525fbeebedb2cf78d16031d4233bc5750209e4
docs: finalize Fast Grounded V2 handoff [skip ci]
```

No later commit superseded the Fast Grounded V2 handoff.

Current acceptance truth remains unchanged:

```text
Fast Grounded G1 local-real = PENDING
P2-E4 local-real under grounded input = PENDING
P2.6 = NOT PASSED
G2 = NOT IMPLEMENTED
Scene Timeline UI = NOT IMPLEMENTED
```

The latest real rerun has already shown the important positive Shot 0001 regression result: the blue
roses / glass vase insert is grounded as flowers/vase with no person, rather than leaking the woman
from the neighboring Shot. That is one G1 gate only; it is not enough to claim G1/P2.6 PASS.

## Why a diagnostic layer was added

The existing P2 acceptance report records structural status and human scores, and E4 already stores
subject-continuity counters in `BreakdownRun.component_status_json`. However, the current real G1
review still required manually joining multiple Draft tables to answer:

```text
Scene 04 has how many LocalSubjects?
Which Shot-local subject_A/B observations belong to each anonymous cluster?
Did any cluster accidentally contain two observations from the same Shot?
Are the current 4 Scene boundaries actually 4 distinct SceneSegmentDrafts?
What was the true whole-Run elapsed time?
What are the ASR/OCR/VLM provider timings?
What does final Shot 0001 Draft say?
Which short OCR noise strings are still present?
```

Also, `p2_pipeline.timings_seconds` persists ASR/OCR/VLM provider elapsed only. The authoritative
whole-Run elapsed is `BreakdownRun.started_at -> completed_at`, which includes Fusion/validation/IO.

## Added read-only diagnostics

New module:

```text
engine/app/breakdown_g1_acceptance_diagnostics_v1.py
```

New CLI:

```text
scripts/inspect_breakdown_g1_run.py
```

New targeted tests:

```text
engine/tests/v2/test_breakdown_g1_acceptance_diagnostics_v1.py
```

The diagnostics are read-only. They do not rerun providers, mutate Draft rows, touch Character V10.1
or create Final assets.

## Local command for the just-completed real Run

```text
python scripts/inspect_breakdown_g1_run.py --run-id <BREAKDOWN_RUN_ID>
```

By default it writes:

```text
<episode>/breakdown/<run_id>/acceptance/g1-real-acceptance-<run_id>.json
```

Use `--stdout-only` when no artifact should be written.

The snapshot includes:

```text
runtime.total_elapsed_seconds / minutes
runtime.provider_timings_seconds
runtime.targets under_30_minutes / at_or_below_20_minutes
E4 subject continuity stats
all Scene boundaries + shot ordinals
per-Scene LocalSubject count
per-LocalSubject E4 source_members with original Shot-local labels
same-Shot cluster conflict list
Scene 04 focused count
Shot 0001 summary / visual description / subject count / prop labels
short OCR text samples for later cleanup only
```

## Acceptance order remains

```text
1. Confirm Shot 0001 blue roses stays correct.
2. Inspect Scene 04: expected visible cast is mainly one woman + one man, so anonymous continuity
   should converge near two stable LocalSubjects; label swaps must not create new people.
3. Confirm same-Shot cluster conflicts list is empty.
4. Review the four Scene boundaries, especially apartment corridor / hallway / living-room naming,
   and decide whether they are true location contradictions or duplicate splitting.
5. Record true whole-Run elapsed plus provider timings.
6. Record OCR noise only; do not derail G1 with OCR cleanup yet.
7. Only if subject continuity, Scene continuity and runtime are acceptable should G2 begin.
```

Do not auto-promote G1/P2.6 based on counters alone; human review remains mandatory.
