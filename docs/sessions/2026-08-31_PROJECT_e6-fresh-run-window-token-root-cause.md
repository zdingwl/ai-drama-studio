# Session Handoff — E6 Fresh Run + Window Token Root Cause

Date: 2026-08-31 +08:00

## Fresh production Run

```text
Run = BREAKDOWNRUN_7d27295da479475f92888351bbfb9839
Episode = EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
Whole Run = 1820.013s = 30.334 min
ASR = 17.951s
OCR = 240.770s
VLM = 1559.171s
```

### Quality result

```text
Shot0001:
subjects=0
props=蓝色玫瑰花束, 玻璃花瓶, 木质桌面
visible truth remains correct; no neighboring person leakage

Scenes total=2
Scene1 = 00:00.000–00:22.800 / 12 Shots / LocalSubjects=2 / 公寓走廊 / INTERIOR / DAY
Scene2 = 00:22.800–01:06.360 / 18 Shots / LocalSubjects=2 / 客厅 / INTERIOR / DAY
same_shot_cluster_conflicts=0
```

E6 production quality therefore reproduces the accepted replay-v3 structure. Fusion remains frozen.
This is still not overall P2.6 PASS because Window Context reliability and the <30 minute performance
gate are not yet fully accepted.

## Detailed VLM timing

```text
Host Window materialization = 4.842s
Exact-Shot frame extraction = 6.161s
Grounding frames = 58
Subprocess wall = 1548.119s

Model load = 4.723s
Window Context total = 465.062s
Exact-Shot total = 1076.135s
Runner total = 1547.107s
```

Exact-Shot top-level batches all READY:

```text
1-5   / 10 frames / 188.417s
6-10  /  7 frames / 151.961s
11-15 /  9 frames / 175.219s
16-20 / 10 frames / 192.218s
21-25 / 11 frames / 179.481s
26-30 / 11 frames / 187.481s
```

## Window failure root cause — CONFIRMED

A read-only Window-only rerun against the same completed frozen Run produced:

```text
Host materialization = 4.725s
Model load = 4.686s
Window total = 211.732s
Runner total = 217.569s

window-0001 / 12 Shots / 54.858s / FAILED / 1600/1600 tokens / MAXED
  ValueError: model output JSON object is invalid
window-0002 / 12 Shots / 54.715s / FAILED / 1600/1600 tokens / MAXED
  ValueError: model output JSON object is invalid
window-0003 /  9 Shots / 54.111s / FAILED / 1600/1600 tokens / MAXED
  ValueError: model output JSON object is invalid
window-0004 /  7 Shots / 47.985s / READY  / 1442/1600 tokens
```

Conclusion: the previous Window prompt is prose-heavy enough that larger windows hit
`max_new_tokens=1600`, truncate JSON and fail parsing. This is not a model-load, FFmpeg or random
parser issue.

## Fix implemented after diagnosis

Do NOT raise the 1600 token limit and do NOT shorten the 24s Window yet.

Added compact Window Context prompt v2:

```text
scripts/run_breakdown_vlm_window_compact_v2.py
profile = breakdown-p2-vlm-window-context-compact-zh-v2
```

Production timed runner now routes Window Context through compact v2 while Exact-Shot grounding is
unchanged:

```text
scripts/run_breakdown_vlm_fast_grounded_qwen3_timed.py
```

Compact Window output retains only production-consumed context:

```text
window_summary <= 40 Chinese chars
subject_continuity_hints: stable appearance + shot_ordinals only
prop_continuity_hints: label + shot_ordinals only
shot_scene_hints for every Shot:
  revision_item_id
  ordinal
  scene_continuity
  scene_basis
  location_hint
  interior_exterior
  time_of_day
```

Removed from model output:

```text
context_note
environment_description
continuity_summary
scene_change_candidates
other prose-heavy fields
```

Exact-Shot remains authoritative for visible facts. Character V10.1 is untouched.

## Next action

1. `git pull`.
2. Run py_compile + compact Window unit tests.
3. Re-run only:

```powershell
python scripts\diagnose_breakdown_vlm_windows.py --run-id BREAKDOWNRUN_7d27295da479475f92888351bbfb9839
```

Acceptance for compact Window v2:

```text
4/4 Windows READY
0 max-token hits
all 12/12/9-Shot windows below 1600 tokens
no DB/Draft/Final mutation
```

Only after this focused gate passes should another full production Run be considered. Exact-Shot
1076s is the next performance optimization target, but do not change its 4096-token cap/batch size
until its actual generated-token diagnostics are reviewed from a fresh timed Run.

Hosted GitHub Actions remain intentionally unused.
