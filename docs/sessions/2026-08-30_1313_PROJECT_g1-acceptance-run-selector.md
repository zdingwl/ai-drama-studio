# 2026-08-30 13:13 +08:00 — G1 acceptance Run selector handoff

## Repository truth

Base before this change:

```text
c80bc7f226691f7a7127b8adf3d6213233636c1d
feat(breakdown): add G1 real acceptance diagnostics [skip ci]
```

Acceptance truth remains:

```text
Fast Grounded G1 local-real = PENDING
P2-E4 local-real under grounded input = PENDING
P2.6 = NOT PASSED
G2 = NOT IMPLEMENTED
Scene Timeline UI = NOT IMPLEMENTED
```

The latest Fast Grounded real rerun has already shown the Shot 0001 positive regression:
blue roses / glass vase are grounded as current-Shot truth with no leaked neighboring woman.
This remains one accepted gate only, not overall G1 PASS.

## Why this follow-up exists

The first diagnostic CLI required a manual `--run-id`. That is unnecessary friction during local
acceptance and creates a risk of accidentally inspecting an older pre-Fast-Grounded Run.

This follow-up adds a read-only selector that verifies the VLM sidecar metadata:

```text
production_vlm_profile = breakdown-p2-vlm-fast-grounded-v1
```

Only completed `READY` / `READY_WITH_WARNINGS` Fast Grounded Runs are auto-selected.

## Added

```text
engine/app/breakdown_g1_run_selector_v1.py
engine/tests/v2/test_breakdown_g1_run_selector_v1.py
```

Updated:

```text
scripts/inspect_breakdown_g1_run.py
```

The CLI now supports exactly one of:

```powershell
python scripts/inspect_breakdown_g1_run.py --run-id <RUN_ID>
python scripts/inspect_breakdown_g1_run.py --episode-id <EPISODE_ID>
python scripts/inspect_breakdown_g1_run.py --latest
```

Recommended for the just-completed local rerun:

```powershell
python scripts/inspect_breakdown_g1_run.py --latest
```

`--episode-id` prefers the Episode's current READY-like Fast Grounded Run and falls back to its
newest completed Fast Grounded Run. `--latest` chooses the newest completed Fast Grounded Run in
the local database. Explicit `--run-id` now refuses unfinished or non-Fast-Grounded Runs.

The emitted JSON includes a `selection` section with the selected Run id, status, current flag,
timestamps and Fast Grounded VLM profile metadata, then the existing G1 diagnostic snapshot.

## Acceptance order is unchanged

```text
1. Shot 0001 blue roses remains correct.
2. Scene 04 anonymous cast continuity converges near the real one-woman + one-man cast.
3. same_shot_cluster_conflicts is empty.
4. Review whether the current four Scene boundaries are genuine or duplicate corridor/hallway splits.
5. Record whole-run elapsed time and provider timings.
6. Record OCR noise only.
7. Fix G1 if any core gate fails; only then consider G2.
```

No model strategy, E4 policy, Character V10.1, Final Asset tables or UI were changed.

## Validation reality

Targeted tests were added to the repository, but they were **not executed in this environment**.
Do not claim local pytest/Qwen/CUDA PASS from code presence. Hosted GitHub Actions remain unused.
