# 2026-08-30 13:48 +08:00 — G1 read-only diagnostics API handoff

## Base

```text
a7c9cac3b125990ce4b0da586a1ea891202c7d7c
docs: hand off G1 current truth sync [skip ci]
```

Current acceptance truth remains unchanged:

```text
Fast Grounded real rerun = completed
Shot 0001 exact-shot regression = positive / no leaked neighboring woman
current UI = 30 Shots / 4 Scenes / Scene04 18 Shots
G1 local-real = PENDING
P2-E4 local-real = PENDING
P2.6 = NOT PASSED
G2 = NOT IMPLEMENTED
```

## Why this follow-up exists

The G1 diagnostics already had a local CLI:

```powershell
python scripts/inspect_breakdown_g1_run.py --latest --summary
```

That remains the simplest local acceptance command. This follow-up exposes the same already-computed
read-only diagnostic logic through the existing Breakdown router so the application/front-end can
inspect the real Run without duplicating selector/diagnostic rules.

## Added read-only APIs

```text
GET /api/episodes/{episode_id}/breakdown-g1-diagnostics
GET /api/breakdown-runs/{run_id}/g1-diagnostics
```

The Episode endpoint selects the current READY-like Fast Grounded Run when available, otherwise the
newest completed Fast Grounded Run for that Episode. The Run endpoint requires that exact Run to be
completed and produced by `breakdown-p2-vlm-fast-grounded-v1`.

Response:

```text
selection   -> selected Run metadata + verified Fast Grounded profile
summary     -> compact human-readable G1 terminal-style summary
diagnostics -> full read-only G1 snapshot
```

Hard boundary:

```text
GET only
no provider/model execution
no Draft mutation
no Character/Final Asset write
no acceptance artifact write
no automatic G1/P2.6 PASS
```

The API reuses:

```text
breakdown_g1_run_selector_v1
breakdown_g1_acceptance_diagnostics_v1
breakdown_g1_acceptance_summary_v1
```

No duplicated acceptance policy was introduced.

## Targeted coverage

Added:

```text
engine/tests/v2/test_breakdown_g1_routes_v1.py
```

It covers payload wiring, missing-Episode 404, rejection of a non-Fast-Grounded Run and route path
registration. Tests were added but were not executed in this environment. Hosted GitHub Actions remain unused.

## Next

Use either:

```powershell
python scripts/inspect_breakdown_g1_run.py --latest --summary
```

or, while the local FastAPI app is running:

```text
GET /api/episodes/<EPISODE_ID>/breakdown-g1-diagnostics
```

Then decide G1 only from the current real Run:

1. Scene04 18-Shot LocalSubject continuity;
2. same-Shot conflict list must be empty;
3. whether the four Scene boundaries are semantically correct;
4. authoritative whole-run elapsed time and provider timings.

Do not change G1 algorithms or start G2 until those real diagnostics are reviewed.
