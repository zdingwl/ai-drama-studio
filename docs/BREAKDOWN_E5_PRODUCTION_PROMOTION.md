# Breakdown E5 Production Promotion

## Status

```text
Production Fusion code              = E5 IMPLEMENTED
Pipeline route                       = E5
Historical E4                        = PRESERVED / rollback baseline
Accepted G1 read-only replay policy = PROMOTED UNCHANGED
Fresh E5 production real run         = NOT RUN YET
G1/P2.6 overall                      = NOT PASSED YET
Character V10.1                      = UNCHANGED / protected
```

## Real evidence used for promotion

Completed immutable Run:

```text
Run     = BREAKDOWNRUN_85be6db2faa94901a2a6db932c71ed62
Episode = EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
```

Read-only replay v2 result:

```text
Candidate Scenes = 2
Scene 1 = Shots 1-12, location=公寓走廊
Scene 2 = Shots 13-30, location=客厅

Scene 2 LocalSubjects = 2
same_shot_cluster_conflicts = 0
accepted_cluster_bridge_count = 4
```

Before the accepted replay, the same grounded sidecars produced four Scene drafts and six anonymous
subject fragments in the 18-Shot living-room segment. The accepted replay therefore fixes the two
specific G1 failures under investigation without rerunning ASR/OCR/VLM.

## E5 production profile

```text
module  = engine/app/breakdown_p2_fusion_episode_v5.py
profile = breakdown-p2-fusion-episode-context-e5-v1
base    = breakdown-p2-fusion-episode-context-e4-v1
```

Production pipeline:

```text
engine/app/breakdown_p2_pipeline_v1.py
from engine.app import breakdown_p2_fusion_episode_v5 as fusion
```

E4 remains in the repository and is not rewritten, so profile comparison and rollback remain explicit.

## Scene policy promoted

```text
corridor-family-qualifier-drift-with-direct-new-scene-v1
```

Rules:

```text
公寓走廊 / 酒店走廊 / 楼道 / 过道 / hallway / corridor
-> same corridor spatial family by default

qualifier drift alone
-> does not cut Scene

Window shot_scene_hint:
  scene_continuity=NEW_SCENE
  scene_basis=DIRECT
-> still forces a cut

real incompatible location
-> still cuts

INT <-> EXT contradiction
-> still cuts
```

## Anonymous subject policy promoted

```text
cluster-visual-plus-common-costar-mutual-best-hard-same-shot-v2
```

Order:

```text
1. Window Context subject continuity hints
2. conservative observation-level stable-appearance gap bridge
3. cluster-level bridge
   - stable visual consensus
   - mutual best match
   - ambiguity margin
   - shared same-Shot co-star cannot-link support when available
4. every final union still passes E4 _UnionFind hard same-Shot cannot-link
```

Hard semantic boundary remains:

```text
LocalSubject != Character
subject_A/B = Shot-local observation labels only
same-Shot observations = hard cannot-link
Character V10.1 / explicit Shot assignment / Final Gate are untouched
```

## Production fail-closed additions

E5 refuses to continue when:

```text
accepted subject policy yields a final same-Shot cluster conflict
one observation maps to multiple clusters
cluster output fails to cover the Scene's exact observations
Run is no longer PROCESSING during post-Fusion rewrite
```

E5 metadata records:

```text
scene_segmentation_policy
subject_continuity_policy
observation_gap_policy
cluster_bridge_union_count
final_same_shot_conflict_count
promotion_source=g1-read-only-replay-v2-real-accepted
```

## Regression coverage added

```text
engine/tests/v2/test_breakdown_p2_e5_promoted_continuity.py
```

Coverage includes:

```text
pipeline routes to E5
corridor qualifier drift stays one Scene
DIRECT NEW_SCENE still forces corridor cut
A/C + B/D/E/F living-room shape converges to two anonymous people
final same-Shot conflict count remains zero
```

Tests were added to the repository but have not yet been executed on the user's Windows environment.
Hosted GitHub Actions are intentionally not used.

## Remaining acceptance work

Do not mark G1/P2.6 PASS yet.

The existing full Fast Grounded run was ~33.7 minutes, above the first <30 minute target. Before the
next expensive full rerun, add detailed VLM timing instrumentation for model load, Window Context and
Exact-Shot batches. Then execute targeted local tests and one fresh E5 production run.
