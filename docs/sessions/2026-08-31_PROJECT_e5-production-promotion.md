# 2026-08-31 — E5 production promotion handoff

## Input real replay result

```text
Run: BREAKDOWNRUN_85be6db2faa94901a2a6db932c71ed62
Candidate Scenes: 2
Scene1: shots 1-12, 公寓走廊, LocalSubjects=10, conflicts=0
Scene2: shots 13-30, 客厅, LocalSubjects=2, conflicts=0
Hard safety: same_shot_cluster_conflicts=0
Replay profile: breakdown-g1-fusion-replay-v2
Subject policy: cluster-visual-plus-common-costar-mutual-best-hard-same-shot-v2
accepted_cluster_bridge_count=4
```

Human interpretation: the focused living-room gate passed. The earlier six fragments converged to the
expected two meaningful anonymous people while preserving the hard same-Shot cannot-link. Corridor
qualifier drift also remained collapsed into one 1-12 Scene, with the living room beginning at Shot13.

## Production changes

```text
NEW engine/app/breakdown_p2_fusion_episode_v5.py
MOD engine/app/breakdown_p2_pipeline_v1.py -> imports E5
MOD engine/app/breakdown_g1_subject_cluster_bridge_v2.py -> policy is now shared by replay + E5
NEW engine/tests/v2/test_breakdown_p2_e5_promoted_continuity.py
NEW docs/BREAKDOWN_E5_PRODUCTION_PROMOTION.md
```

Production profile:

```text
breakdown-p2-fusion-episode-context-e5-v1
```

E4 remains untouched as rollback/comparison baseline.

## Safety invariants preserved

```text
LocalSubject != Character
same-Shot observations = hard cannot-link
subject_A/B are Shot-local only
no Final Asset write from Fusion
Character V10.1 untouched
```

E5 additionally fails closed on final same-Shot cluster conflicts, duplicate observation mapping, or
incomplete observation coverage.

## Validation status

Repository test code has been added. Hosted GitHub Actions were not used. The assistant environment
could not clone GitHub because outbound DNS resolution was unavailable, so repository pytest was not
executed there. The next cheap gate is targeted pytest on the user's Windows checkout before any fresh
ASR/OCR/VLM inference.

## Next action

```text
1. git pull
2. targeted E5/replay pytest
3. add detailed Fast Grounded VLM timing instrumentation
4. one fresh full production E5 run
5. inspect Scene/LocalSubjects/hard conflicts + timing
6. only then decide G1/P2.6 PASS and whether to start G2
```

Do not rerun the model before timing instrumentation if the goal is to avoid another uninformative
~33.7 minute run.
