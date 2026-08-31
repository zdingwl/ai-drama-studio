# Handoff — replay v5 compact alias singleton recovery

## Real replay-v4 result

Completed Run:
`BREAKDOWNRUN_dc678fb017ba49128b7340509f02536b`

User-local read-only replay v4:

```text
Candidate Scenes = 2
Scene1 LocalSubjects = 2
Scene2 LocalSubjects = 3
same_shot_cluster_conflicts = 0
```

Scene2 residual fragment:

```text
main male cluster includes Shots 13,14,16,17,18,19,20,21,22,23,24,27,28,29
main female cluster includes Shots 13,15,16,18,19,20,21,22,23,24,25,26,27,28,30
residual singleton = Shot30 subject_A = 短发，灰卫衣
```

This proves replay-v4 fixed the Stage1 Window-hint cross-binding regression. The remaining issue is a
single compact-appearance alias gap after Stage1.

## Root cause

Accepted Stage2..4 feature extraction recognizes canonical phrases such as `灰色` and `连帽衫`, but
compact Exact-Shot v3 may emit abbreviated equivalents such as `灰卫衣`, `灰衣`, `白衣`, or
`白露肩装`. Shot29 and Shot30 can therefore describe the same male as `短发，灰卫衣` while the
existing fallback fails its strong-feature threshold.

Do not lower thresholds and do not add a broad force-merge stage.

## Read-only replay v5 candidate

New files:

```text
engine/app/breakdown_g1_compact_appearance_normalizer_v1.py
engine/app/breakdown_g1_fusion_replay_v5.py
engine/app/breakdown_g1_fusion_replay_completed_v5.py
scripts/inspect_breakdown_g1_fusion_replay_v5.py
engine/tests/v2/test_breakdown_g1_fusion_replay_v5.py
```

Policy:

```text
Window Stage1 = replay-v4 evidence-gated resolver unchanged
Stages2..4 thresholds = unchanged
same-Shot cannot-link = unchanged
explicit gender / long-short hair guards = unchanged

Only comparison text is canonicalized:
灰卫衣 -> 灰色连帽衫
灰衣 -> 灰色上衣
白衣 -> 白色上衣
白露肩装 -> 白色露肩上衣
露肩装 -> 露肩上衣
灰发卷曲 -> 灰发卷发
```

Persisted VLM evidence and output `source_members.appearance_summary` remain original.

## Next validation

Run cheap local tests first:

```powershell
python -m pytest `
  engine/tests/v2/test_breakdown_g1_fusion_replay_v5.py `
  engine/tests/v2/test_breakdown_g1_fusion_replay_v4.py `
  engine/tests/v2/test_breakdown_g1_fusion_replay_v3.py `
  engine/tests/v2/test_breakdown_g1_fusion_replay_v2_conflict_guard.py `
  -q
```

Then read-only replay the same completed Run:

```powershell
python scripts\inspect_breakdown_g1_fusion_replay_v5.py `
  --run-id BREAKDOWNRUN_dc678fb017ba49128b7340509f02536b
```

Acceptance target:

```text
Candidate Scenes = 2
Scene1 LocalSubjects = 2
Scene2 LocalSubjects = 2
same_shot_cluster_conflicts = 0
providers_executed=[]
mutates_breakdown_run=false
mutates_final_assets=false
```

Production E6 is still unchanged. Do not promote until this completed-run replay passes.
No hosted GitHub Actions were used.
