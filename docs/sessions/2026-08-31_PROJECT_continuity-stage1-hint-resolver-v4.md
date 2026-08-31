# 2026-08-31 — Stage1 Window subject-hint resolver replay v4

## Trigger

Fresh final production Run:

```text
BREAKDOWNRUN_dc678fb017ba49128b7340509f02536b
whole run = 14.098 min
Scenes = 2
Shot0001 subjects=0 / reconstruction props present
same_shot_cluster_conflicts=0
Scene1 LocalSubjects=4
Scene2 LocalSubjects=16
```

Performance is accepted. Anonymous continuity is the only open G1 issue.

## Real stage diagnostic root cause

User-local read-only stage diagnostic showed:

```text
Scene1: observations=16
Stage1 clusters=4 / unions=12
Stage2..4 unions=0

Scene2: observations=30
Stage1 clusters=18 / unions=12
Stage2 clusters=16 / unions=2
Stage3..4 unions=0
```

The decisive evidence was incorrect Window-hint resolution, for example:

```text
hint: 穿白色露肩上衣的女性
resolved Shot14 -> 黑发男子，灰卫衣
resolved Shot17 -> 短发，灰连帽衫

hint: 穿灰色连帽衫的男性
resolved Shot15 -> 黑发女性，白露肩上衣
```

Legacy `e4._resolve_hint_nodes()` automatically accepted a Shot when it had exactly one visible
candidate, without requiring appearance compatibility. Window v4 `shot_ordinals` are soft model
belief, not proof of presence, so that shortcut is invalid.

## Candidate implementation

New read-only modules:

```text
engine/app/breakdown_g1_subject_hint_resolver_v2.py
engine/app/breakdown_g1_fusion_replay_v4.py
engine/app/breakdown_g1_fusion_replay_completed_v4.py
scripts/inspect_breakdown_g1_fusion_replay_v4.py
engine/tests/v2/test_breakdown_g1_fusion_replay_v4.py
```

Candidate policy:

```text
window-hint-positive-appearance-support-compact-alias-v2
```

Rules:

```text
- explicit Window members remain highest-confidence compatibility evidence
- ordinal-only hints never auto-bind the only visible person
- each hinted Shot is only a candidate location
- Exact-Shot observation must provide positive stable appearance support
- compact aliases are normalized locally:
  灰衣 / 灰卫衣 / 灰色连帽衫
  白衣 / 白上衣 / 白衬衫
  露肩装 / 露肩上衣
  卫衣 / 连帽衫
  花衬衫 / 花卉 / 印花
- gender and explicit long-vs-short hair contradictions still block
- same-Shot hard cannot-link is unchanged
- Stages 2,3,4 are unchanged from accepted replay v3
- Character V10.1 is untouched
```

## Next local gate

```powershell
git pull

python -m py_compile `
  engine/app/breakdown_g1_subject_hint_resolver_v2.py `
  engine/app/breakdown_g1_fusion_replay_v4.py `
  engine/app/breakdown_g1_fusion_replay_completed_v4.py `
  scripts/inspect_breakdown_g1_fusion_replay_v4.py

python -m pytest `
  engine/tests/v2/test_breakdown_g1_fusion_replay_v4.py `
  engine/tests/v2/test_breakdown_g1_fusion_replay_v3.py `
  engine/tests/v2/test_breakdown_g1_fusion_replay_v2_conflict_guard.py `
  -q
```

If green, run no model. Replay the completed final Run:

```powershell
python scripts\inspect_breakdown_g1_fusion_replay_v4.py `
  --run-id BREAKDOWNRUN_dc678fb017ba49128b7340509f02536b
```

Acceptance target before any production promotion:

```text
Scenes=2
Scene1 LocalSubjects ~=2
Scene2 LocalSubjects ~=2
same_shot_cluster_conflicts=0
providers_executed=[]
mutates_breakdown_run=false
mutates_final_assets=false
```

Do not rerun Qwen and do not change performance parameters until this replay gate is resolved.
