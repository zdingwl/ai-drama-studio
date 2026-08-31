# E6-v2 compact-safe continuity promotion handoff

Date: 2026-08-31 +08:00

## Trigger

Final production Run:

```text
BREAKDOWNRUN_dc678fb017ba49128b7340509f02536b
whole run = 14.098 min
Scenes=2
Shot0001 subjects=0
same_shot_cluster_conflicts=0
```

Performance and Shot/Scene truth passed, but E6-v1 anonymous continuity regressed:

```text
Scene1 LocalSubjects=4
Scene2 LocalSubjects=16
```

## Root cause

Provider-free Stage diagnostics showed Stage1 Window hint resolution was the dominant fault. The
legacy resolver auto-bound a one-person Shot without appearance validation, allowing Window hints to
cross-bind the wrong anonymous person.

Replay-v4 introduced evidence-gated Window hint resolution and restored:

```text
Scene1=2
Scene2=3
conflicts=0
```

The final Scene2 singleton was compact appearance wording drift (`灰卫衣` vs `灰色连帽衫`).
Replay-v5 canonicalized compact aliases for Stages2..4 comparison only, preserving source text and
all accepted thresholds/hard guards.

## User-local replay-v5 acceptance

```text
12 tests PASS
providers_executed=[]
mutates_breakdown_run=false
mutates_final_assets=false
Candidate Scenes=2
Scene1 LocalSubjects=2
Scene2 LocalSubjects=2
same_shot_cluster_conflicts=0
```

Policies:

```text
window hint resolver = window-hint-positive-appearance-support-compact-alias-v2
compact appearance   = compact-observation-stable-alias-normalization-v1
```

## Production promotion

`engine/app/breakdown_p2_fusion_episode_v6.py` is now E6-v2:

```text
FUSION_PROFILE = breakdown-p2-fusion-episode-context-e6-v2
FUSION_VERSION = 2
subject policy = accepted replay-v5
```

Production metadata records the Window hint resolver and compact appearance policy. Scene policy,
ASR dialogue truth, Draft schema, same-Shot cannot-link and Character V10.1 are unchanged.

New production regression:

```text
engine/tests/v2/test_breakdown_p2_e6_v2_compact_continuity.py
```

## Current gate

E6-v2 code is promoted, but user-local production regression has not yet been reported and no fresh
E6-v2 full production Run has been executed.

P2.6 therefore remains NOT FINAL PASS.

Next:

```text
1. run cheap E6-v2 production regression suite
2. if green, run exactly one fresh production Breakdown
3. require Fusion=e6-v2
4. require Scenes=2, Scene1=2 LocalSubjects, Scene2=2 LocalSubjects
5. require same_shot_cluster_conflicts=0
6. require Shot0001 subjects=0 + blue roses/glass vase props
7. require whole-run <30min
8. only then review P2.6 PASS and unblock G2 / Scene Timeline
```

Hosted GitHub Actions remain unused.
