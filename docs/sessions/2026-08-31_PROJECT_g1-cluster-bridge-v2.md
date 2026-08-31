# G1 Cluster Bridge V2 — handoff

Date: 2026-08-31

## Scope

Read-only G1 candidate replay only. Production `engine/app/breakdown_p2_fusion_episode_v4.py`,
Character V10.1, Draft rows and Final Assets remain unchanged.

## Real Run evidence used

Run:

```text
BREAKDOWNRUN_85be6db2faa94901a2a6db932c71ed62
```

Formal completed result before replay tuning:

```text
30 Shots
4 Scenes = 5 / 5 / 2 / 18
Shot0001 subjects=0, blue roses / glass vase correct
Scene04 LocalSubjects=6
same_shot_cluster_conflicts=0
whole runtime=33.705 min
ASR=17.1s / OCR=265.9s / VLM=1738.0s
```

Read-only Scene replay v1 produced:

```text
Scene1 shots 1-12 = 公寓走廊
Scene2 shots 13-30 = 客厅
same_shot_cluster_conflicts=0
```

This supports the corridor-family Scene compatibility candidate. Subject continuity still remained
6 fragments in Scene2.

## Scene2 bridge diagnostics

Observed fragments:

```text
A shots 13,15 = long black hair + white off-shoulder top
B shots 13,14 = short hair + gray hoodie + white T-shirt
C shots 16,18..30 = female + long hair + white top
D shots 16..24 = male + short hair + gray hoodie
E shots 27..29 = short hair + gray hoodie
F shot 30 = short hair + gray hoodie
```

Machine bridge evidence:

```text
B<->D gap=2 max=4.50 top3=4.50 support4/2=12
D<->E gap=3 max=4.50 top3=4.50 support4/2=4 common-cannot-link=C
E<->F gap=1 max=4.50 top3=3.17 support4/2=1 common-cannot-link=C
A<->C gap=1 max=3.50 top3=3.50 strong stable features=3
A<->D max=1.00
B<->C max=1.00
```

Interpretation for candidate replay:

```text
A + C -> woman chain
B + D + E + F -> man chain
```

This is anonymous Scene-scoped continuity only; it is not Character identity.

## Implemented read-only candidate v2

New modules:

```text
engine/app/breakdown_g1_subject_cluster_bridge_v2.py
engine/app/breakdown_g1_fusion_replay_v2.py
engine/app/breakdown_g1_fusion_replay_completed_v2.py
engine/tests/v2/test_breakdown_g1_subject_cluster_bridge_v2.py
```

CLI `scripts/replay_breakdown_g1_fusion.py` now selects replay v2.

Cluster bridge rules:

```text
1. Existing Window subject continuity hints remain primary.
2. Existing conservative observation fallback remains.
3. Cluster bridge may merge only when:
   - no shared Shot,
   - gap <= 3 Shots,
   - no explicit gender conflict,
   - no explicit long-hair vs short-hair consensus conflict,
   - strong visual consensus OR shared cannot-link co-star anchor,
   - mutual best candidate,
   - best-vs-second margin >= 0.5.
4. Every accepted bridge still calls E4 UnionFind.union(), so transitive same-Shot hard cannot-link
   remains authoritative.
```

Production E4 is intentionally NOT changed yet.

## Next required real check

On the user's Windows repo:

```powershell
git pull
python scripts\replay_breakdown_g1_fusion.py --run-id BREAKDOWNRUN_85be6db2faa94901a2a6db932c71ed62
```

Acceptance focus:

```text
Candidate Scenes should remain near 2 (1-12 corridor, 13-30 living room).
Scene2 should converge near 2 LocalSubjects.
same_shot_cluster_conflicts must remain 0.
```

If that real replay passes human review, only then promote the proven Scene/subject policies into
production Fusion and run targeted local tests before one final full real rerun.

## Validation note

Hosted GitHub Actions were not used. A local container clone attempt was blocked by DNS/network
resolution, so repository pytest/py_compile was not executed in this environment. The bridge rule
was manually simulated against the recorded Scene2 evidence shape before commit; Windows real replay
remains the authoritative next gate.
