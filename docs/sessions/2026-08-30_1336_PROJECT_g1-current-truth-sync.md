# 2026-08-30 13:36 +08:00 — G1 current-truth sync handoff

## Repository baseline

Before this documentation sync, `main` had already added the complete read-only G1 acceptance toolchain:

```text
c80bc7f  add G1 real acceptance diagnostics
7025bc7  auto-select completed Fast Grounded Run
893f20e  add compact G1 terminal summary
```

No inference/E4/Character/UI strategy was changed during the current truth sync.

## Current executable truth

```text
Architecture = Reference Video V2 + Breakdown Fast Grounded V2
Formal Character runtime = Character V10.1
Fast Grounded G1 = IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E4 = IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
legacy text-only per-Shot E3 = RETIRED FROM PRODUCTION
G2 Scene-level text LLM = NOT IMPLEMENTED
Scene Timeline UI = NOT IMPLEMENTED
P2.6 = NOT PASSED
```

## Real-run truth now synchronized

Historical pre-Fast-Grounded failure remains only a comparison baseline:

```text
30 Shots
21 LocalSubjects
old Scene04 / 19 Shots -> 14 LocalSubjects
actual visible cast -> mainly one woman + one man
Shot0001 actual -> blue roses / glass vase
old result -> neighboring woman leakage
legacy E3 -> 30/30 TimeoutExpired
runtime -> multi-hour class
```

A new Fast Grounded V2 real rerun has already completed. Current UI result:

```text
30 Shots
4 Scenes
Scene01 5 Shots
Scene02 5 Shots
Scene03 2 Shots
Scene04 18 Shots
```

Confirmed positive gate:

```text
Shot0001 = blue roses / glass vase
subjects=[]
neighbor woman leakage no longer observed
```

This is only one G1 gate. Overall G1/P2.6 is still pending.

## Remaining acceptance from the same completed Run

```text
1. Scene04 anonymous subject continuity
   - expected direction: mainly one woman + one man -> roughly two stable LocalSubjects
   - subject_A/B label swaps must not create new people
2. same_shot_cluster_conflicts must be empty
3. Review whether current 4 Scene boundaries are genuine
   - especially corridor / hallway / living-room synonym splitting
4. Record authoritative whole-run elapsed
   - BreakdownRun.started_at -> completed_at
5. Record ASR/OCR/VLM provider timings separately
6. Record OCR short-noise samples only; do not derail G1
```

## Correct local action

Do not rerun the Episode simply to inspect acceptance evidence.

```powershell
git pull
python scripts/inspect_breakdown_g1_run.py --latest --summary
```

The selector only accepts completed Fast Grounded Runs by checking:

```text
production_vlm_profile = breakdown-p2-vlm-fast-grounded-v1
```

The command still writes the full JSON acceptance artifact by default while printing a compact one-screen summary.

## Read-only G1 acceptance modules

```text
engine/app/breakdown_g1_acceptance_diagnostics_v1.py
engine/app/breakdown_g1_run_selector_v1.py
engine/app/breakdown_g1_acceptance_summary_v1.py
scripts/inspect_breakdown_g1_run.py
```

These modules do not rerun ASR/OCR/VLM, do not mutate Breakdown Draft rows, do not touch Character V10.1, and do not create Final assets.

## Current decision gate

```text
existing Run diagnostics
→ Scene04 continuity acceptable?
→ same-Shot safety clean?
→ Scene boundaries acceptable?
→ whole-run runtime acceptable?

NO -> fix only failing G1 layer -> rerun -> inspect again
YES -> begin G2 Scene-level pure-text LLM
```

Do not implement/accept G2 or Scene Timeline UI as a substitute for G1 correctness. P5 remains paused until P2.6 genuinely passes.

## Documentation synchronized in this pass

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/BREAKDOWN_FAST_GROUNDED_V2_PLAN.md
docs/BREAKDOWN_EPISODE_CONTEXT_PLAN.md
docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md
```

All commits use `[skip ci]`; hosted GitHub Actions remain unused.

## Validation reality

Repository tests exist for Fast Grounded grounding, E4 continuity, diagnostics, Run selection, and compact summary. They were not executed by this remote documentation pass. Do not claim fresh local pytest/Qwen/CUDA PASS from repository presence alone.
