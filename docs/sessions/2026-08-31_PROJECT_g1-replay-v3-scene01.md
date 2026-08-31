# G1 Replay v3 — Scene01 coherent-component candidate

Date: 2026-08-31

## Preconditions already passed

Real completed Run:

```text
BREAKDOWNRUN_85be6db2faa94901a2a6db932c71ed62
```

Latest v2 real replay after exact-Shot conflict guard:

```text
Candidate Scenes = 2
Scene1 = shots 1-12 / 公寓走廊 / LocalSubjects=10
Scene2 = shots 13-30 / 客厅 / LocalSubjects=2
same_shot_cluster_conflicts = 0
```

Local targeted tests supplied by the user before v3 work:

```text
21 passed
```

That green set covered E4 continuity, E5 promoted continuity, cluster bridge v2, replay v1, and replay-v2 explicit conflict guard.

## Scene01 real diagnostic truth

The 10 v2 fragments visually form two obvious anonymous appearance chains:

```text
white / long-hair chain: A, B, D, E, G, J
curly gray-white hair / orange floral shirt chain: C, F, H, I
```

Representative evidence:

```text
A @2  深色长发，白色上衣
B @3  深色长发，白色露肩上衣
D @4  深色长发，白色露肩上衣 + 白色长裤
E @5  深色长发，白色露肩上衣
G @7  黑长发，白色露肩上衣
J @11 黑发长发，白色露肩上衣 + 白色阔腿裤

C @3  灰白卷发，橙色花卉图案衬衫
F @6  灰白卷发，橙色花卉图案衬衫
H @9  灰白卷发，橙色花卉图案衬衫
I @11 灰发卷发，橙色花卉图案衬衫
```

Why v2 freezes Scene01:

- several white/long-hair pairs have the same 3.50 score;
- v2 mutual-best treats tied best candidates as ambiguous and accepts none;
- the coarse E4 stable feature vocabulary reduces `橙色花卉图案衬衫` mostly to generic `衬衫`, losing distinctive attire evidence.

This is a conservative false-negative, not evidence that the 10 fragments are 10 different people.

## v3 candidate

Production E5 is intentionally unchanged.

New read-only modules:

```text
engine/app/breakdown_g1_subject_component_bridge_v3.py
engine/app/breakdown_g1_fusion_replay_v3.py
engine/app/breakdown_g1_fusion_replay_completed_v3.py
```

CLI `scripts/replay_breakdown_g1_fusion.py` now points to replay v3 only. It still executes no providers and writes no DB/Final rows.

v3 keeps all accepted v2 stages and adds Stage4:

```text
v2 Window hints + exact-Shot contradiction guard
→ v2 observation fallback + exact-Shot contradiction guard
→ v2 mutual-best cluster bridge
→ v3 coherent-component bridge (candidate only)
```

Stage4 rules:

- max component gap = 3 Shots;
- no pair may share a Shot;
- explicit gender conflict blocks;
- explicit long-hair vs short/bald conflict blocks;
- recover stable extra attire/color details such as `露肩`, `连帽衫`, `花卉`, `橙色`, etc.;
- seed a component only with either a common same-Shot cannot-link co-star anchor or a shared distinctive attire detail;
- reject the entire component if its combined members would violate same-Shot uniqueness;
- after a safe multi-fragment component exists, only a <=2-observation fragment may grow into it via strong base appearance evidence;
- no hard-coded cast count;
- LocalSubject remains anonymous Scene-local continuity, not Character identity.

## New tests

```text
engine/tests/v2/test_breakdown_g1_fusion_replay_v3.py
```

Covers:

1. Scene01-shaped white-long-hair + floral-curly-hair evidence should become two anonymous clusters.
2. Two people that co-occur in the same Shots must remain separate.
3. Explicit long-hair vs short-hair guard remains authoritative.

Fresh local pytest for v3 has NOT yet been observed at handoff time.

## Next commands

```powershell
git pull

python -m pytest `
  engine/tests/v2/test_breakdown_g1_fusion_replay_v3.py `
  engine/tests/v2/test_breakdown_g1_fusion_replay_v2_conflict_guard.py `
  engine/tests/v2/test_breakdown_g1_subject_cluster_bridge_v2.py `
  -q

python scripts\replay_breakdown_g1_fusion.py `
  --run-id BREAKDOWNRUN_85be6db2faa94901a2a6db932c71ed62
```

Acceptance gate for v3:

```text
Candidate Scenes = 2
Scene1 LocalSubjects should substantially converge toward 2
Scene2 LocalSubjects must remain 2
same_shot_cluster_conflicts = 0
```

If Scene1 does not improve, or Scene2 regresses, or conflicts > 0: reject v3 and do not modify production E5.

If v3 passes real replay + tests: then decide whether to promote only the proven Stage4 policy into a versioned production Fusion successor. Do not silently mutate historical E4; Character V10.1 remains untouched.
