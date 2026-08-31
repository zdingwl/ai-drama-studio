# 2026-08-31 — G1 candidate Fusion read-only replay

## Why

Real Fast Grounded Run:

```text
BREAKDOWNRUN_85be6db2faa94901a2a6db932c71ed62
30 Shots / 4 Scenes
Scene04 = 18 Shots / 6 LocalSubjects
same_shot_cluster_conflicts=0
Runtime=33.705 min
ASR=17.1s / OCR=265.9s / VLM=1738.0s
```

The run proves:
- Shot0001 exact-Shot grounding is correct (blue roses / glass vase, subjects=[]).
- same-Shot hard cannot-link is correct and must not be relaxed.
- Scene04 anonymous continuity is still fragmented.
- 公寓走廊 -> 酒店走廊 -> 公寓走廊 is suspicious qualifier drift.
- VLM is the dominant performance bottleneck.

## What was added

`engine/app/breakdown_g1_fusion_replay_v1.py` and
`scripts/replay_breakdown_g1_fusion.py` provide a candidate **read-only** replay over the existing
immutable sidecars.

The candidate Scene policy treats corridor-family aliases / qualifier drift as compatible unless a
Window hint explicitly says `NEW_SCENE` with `scene_basis=DIRECT`. INT/EXT contradictions and real
spatial-type contradictions still cut.

The candidate anonymous-subject fallback can bridge a 3..6 Shot absence only when stable appearance
is strong, the match is reciprocal, and ambiguity margins are sufficient. The existing transitive
same-Shot hard cannot-link is reused unchanged.

## Safety boundary

```text
providers_executed=[]
no ASR/OCR/VLM execution
no BreakdownRun mutation
no Draft mutation
no Character V10.1 mutation
no Final Asset mutation
```

This candidate has **not** been promoted to production Fusion yet. First run it against the real Run:

```powershell
git pull
python scripts/replay_breakdown_g1_fusion.py --run-id BREAKDOWNRUN_85be6db2faa94901a2a6db932c71ed62
```

Review candidate Scene count/boundaries, Scene04 LocalSubjects, and require
`same_shot_cluster_conflicts=0`.

Only after the replay is acceptable should the candidate policy be promoted to production and a
final real provider rerun be performed.

Tests are repository coverage only and were not executed in this environment. Hosted GitHub Actions
were not used.

## Performance follow-up

Do not tune FPS/resolution/tokens blindly yet. After continuity replay acceptance, add Fast Grounded
stage timing for model load, each Window Context inference, and each Exact-Shot grounding batch.
Then optimize the measured VLM bottleneck.
