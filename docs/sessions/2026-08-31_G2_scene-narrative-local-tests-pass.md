# Session Handoff — G2.3/G2.4 Local Test Gate Passed

## Status

- Date: 2026-08-31
- Branch: `main`
- G2.1 Scene Timeline Contract: **FINAL PASS / FROZEN FOUNDATION**
- G2.2 Deterministic Assembler: **FINAL PASS / FROZEN FOUNDATION**
- G2.3 Scene Narrative: **USER-LOCAL TEST PASS / REAL-MODEL ACCEPTANCE PENDING**
- G2.4 Source/Support Validator: **USER-LOCAL TEST PASS / REAL-MODEL ACCEPTANCE PENDING**
- Character V10.1: protected / unchanged

## User-local evidence

Command:

```powershell
python -m pytest engine/tests/v2/test_breakdown_scene_narrative_v1.py engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py -q
```

Observed:

```text
........ [100%]
8 passed
```

Runtime preflight:

```powershell
python -c "from engine.app.breakdown_scene_narrative_qwen3_v1 import Qwen3VLSceneTextLLM; print(Qwen3VLSceneTextLLM().runtime_preflight())"
```

Observed:

```text
profile = breakdown-g2-scene-narrative-qwen3-local-v1
status = READY
device = cuda
max_new_tokens = 512
missing = []
```

Therefore code/contract tests and local runtime configuration are accepted. G2.3/G2.4 must still not be called FINAL PASS until the real text-only Qwen acceptance on the final accepted BreakdownRun passes.

## Real-model acceptance runner

Added:

```text
scripts/run_breakdown_g2_scene_narrative_acceptance_v1.py
```

Run from repository root:

```powershell
python scripts/run_breakdown_g2_scene_narrative_acceptance_v1.py
```

Default target:

```text
BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
```

The runner verifies before/after invariants:

```text
Scenes = 2
Shots = 30
Scene-local people = [2, 2]
Shot0001 people = []
Shot0001 contains 蓝色玫瑰花束 + 玻璃花瓶
all Shot objects remain structurally unchanged after Narrative overlay
```

It then prints the two deterministic titles/summaries, accepted Narrative titles/summaries, support refs, validator warnings, and final machine gate.

Expected final line for the structural gate:

```text
shot_objects_unchanged= YES
acceptance_machine_gate= PASS
```

Narrative quality still requires human inspection. `READY_WITH_WARNINGS` is not automatically a failure if the validator correctly rejects unsafe claims and the deterministic fallback remains accurate.

## Next action

1. run the real-model acceptance runner;
2. inspect the two Scene Narrative title/summary outputs and warnings;
3. if factual/readability acceptance is good and structural gate is PASS, mark G2.3/G2.4 FINAL PASS;
4. then implement G2.5 Scene Timeline API;
5. then G2.6 ordinary-user Scene Timeline UI.

Do not retune frozen G1 or change G2.1/G2.2 truth ownership to improve Narrative wording.
