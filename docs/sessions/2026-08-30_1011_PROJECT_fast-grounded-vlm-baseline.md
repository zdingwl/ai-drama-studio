# 2026-08-30 10:11 +08:00 — Fast Grounded Breakdown V2 handoff

## Context

Real short-drama review rejected the previous Episode-context Breakdown despite the pipeline completing.

Observed failures:

```text
Episode ~1 minute / 30 Shots
runtime -> roughly 5~6 hour class
Scene 04 / 19 Shots -> 14 LocalSubjects although visible cast stayed one woman + one man
Shot 0001 visible frame -> blue roses in a vase
old result -> "young woman's face close-up / surprised"
legacy E3 -> 30/30 TimeoutExpired fallback
```

A competitor reference also showed a more useful product shape: Scene header + cast/props + timestamped visual/action/dialogue timeline, rather than one large database-style card per Shot.

Decision:

```text
Shot = smallest visual evidence/location unit
Scene Timeline = primary user-readable Breakdown unit
Exact-Shot visible fact > Window Context
expensive video VLM should only do necessary continuity context
```

## Production change implemented

New provider:

```text
engine/app/breakdown_p2_vlm_fast_grounded_v1.py
profile = breakdown-p2-vlm-fast-grounded-v1
```

New isolated runner:

```text
scripts/run_breakdown_vlm_fast_grounded_qwen3.py
```

Stable runtime:

```text
engine/app/breakdown_p2_vlm_runtime_v1.py
```

Pipeline import surface:

```text
engine/app/breakdown_p2_vlm_continuity_v1.py
```

That wrapper now subclasses the Fast Grounded stable runtime and keeps E4 continuity-hint normalization.

Pipeline itself remains:

```text
ASR -> OCR -> VLM -> E4 Fusion -> P1 validator
```

No API / frozen P2 sidecar / P1 Draft schema migration was introduced.

## G1 execution model

One Episode VLM subprocess loads Qwen3-VL once.

Phase A — Window Context:

```text
24s target
25% overlap
1 FPS
262144 max pixels
```

Window output is intentionally small:

```text
window_summary
scene_change_candidates
subject_continuity_hints
prop_continuity_hints
shot_scene_hints
```

It does not own final current-Shot people/actions/props/shot visual prose.

Phase B — Exact-Shot frame grounding:

```text
<1.2s  -> 1 frame at 50%
1.2..3s -> 2 frames at 25% / 75%
>3s -> 3 frames at 15% / 50% / 85%
default 5 Shots per image batch
```

Visible truth comes only from exact frozen Shot images. Window context may only conservatively fill Scene fields.

Mandatory regression:

```text
Shot 0001 blue roses/vase
=> subjects=[]
=> no neighboring woman leak
```

The runner was additionally hardened so malformed optional model ordinals do not crash Scene-context matching.

## Legacy E3

Text-only per-Shot E3 is retired from production. Its files remain for historical artifact/test compatibility:

```text
engine/app/breakdown_p2_refinement_v1.py
scripts/run_breakdown_refinement_qwen3.py
```

Compatibility helper exports remain in `breakdown_p2_vlm_runtime_v1.py`; historical E2/E3 tests were aligned so they test historical helpers without claiming E3 is current production truth.

## E4

`engine/app/breakdown_p2_fusion_episode_v4.py` remains production Fusion.

It now receives exact-Shot grounded subjects plus Window Context continuity hints. Character V10.1 and Final Asset gates are untouched.

## Test coverage

```text
engine/tests/v2/test_breakdown_p2_fast_grounded_v1.py
engine/tests/v2/test_breakdown_p2_e4_subject_continuity.py
```

Fast Grounded coverage includes frame sampling, Scene-only context inheritance, no neighbor people/props leakage and production runtime wiring.

No local pytest/Qwen/CUDA execution was available. A best-effort local clone for syntax validation also failed because this execution environment could not resolve `github.com`. Do not report tests or model quality as passed yet.

## Acceptance/preflight

`engine/app/breakdown_p2_acceptance_v1.py` now imports the production OCR and continuity/Fast-Grounded VLM provider, so runtime preflight points to the current runner/model parameters rather than the historical single-Shot Qwen runner.

Preflight remains environment-only and is not model-quality/performance PASS.

## Formal docs synchronized

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/BREAKDOWN_FAST_GROUNDED_V2_PLAN.md
docs/BREAKDOWN_EPISODE_CONTEXT_PLAN.md
docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md
```

## Performance target

Reference Episode:

```text
60s / ~30 Shots / ~4 Scenes
```

Targets:

```text
first engineering target: <30 min total
second target: 10..20 minute class
5..6h: FAIL
```

These are budgets, not measured acceptance results.

## G2 — deliberately not implemented yet

After G1 passes real visual/speed acceptance:

```text
Scene
+ grounded Shot visual facts
+ ASR
+ OCR
+ E4 LocalSubjects
+ prop continuity
→ pure-text LLM once per Scene
→ Scene Timeline Breakdown
→ Scene-first result UI
```

Do not implement the prettier Scene Timeline UI as a substitute for fixing visual truth.

## Required next local run

```text
1. git pull
2. run the exact same rejected Episode with current production chain
3. inspect Shot 0001 blue roses first
4. inspect Scene 04 / 19-Shot one-woman+one-man continuity
5. record total elapsed time and available provider stage elapsed times
6. if G1 has any visual leak / runtime failure, fix G1 before G2 or P5
```

Current acceptance truth remains:

```text
Fast Grounded G1 local-real = PENDING
P2-E4 local-real under grounded input = PENDING
P2.6 = NOT PASSED
P5 = PAUSED
```
