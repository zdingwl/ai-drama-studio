# Session Handoff — G2.3/G2.4 Real Narrative Gate 2

## Status

- Date: 2026-08-31
- Branch: `main`
- G1 / P2.6: **PASS / FROZEN**
- G2.1 / G2.2: **FINAL PASS / FROZEN FOUNDATION**
- G2.3 / G2.4 unit tests before this real run: **8 passed**
- Local Qwen runtime: **READY / CUDA / missing=[]**
- Real-model structure gate: **PASS**
- Real-model Narrative gate: **FAIL**
- G2.3 / G2.4: **NOT FINAL PASS / RETEST REQUIRED**

## User-local evidence

```text
python -m pytest engine/tests/v2/test_breakdown_scene_narrative_v1.py engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py -q
........ [100%]
8 passed
```

Real acceptance:

```text
runner_diagnostics = {
  "1": {"status": "READY"},
  "2": {"status": "READY"}
}
scenes = 2
shots = 30
people = [2, 2]
shot1_people = []
shot1_props = ['遥控器', '蓝色玫瑰花束', '玻璃花瓶', '书本']
shot_objects_unchanged = YES
structure_gate = PASS
narrative_gate = FAIL
acceptance_machine_gate = FAIL
```

Accepted titles:

```text
Scene 1: 走廊对峙
Scene 2: 客厅争执
```

Rejected summaries:

```text
Scene 1:
  reason = strict lexical novelty guard rejected reasonable abstraction characters

Scene 2:
  reason = output mentioned 人物2 but model support omitted a person-linked Fxxxx
```

The deterministic summaries remained active by fallback. No frozen Shot object changed.

## Diagnosis

The generation layer is now healthy: both Scenes returned READY candidates. The remaining failure is G2.4 validation policy.

The old summary rule required essentially every substantive generated character to occur in the model-declared support text. That is too strict for a text organizer: reasonable compression such as “双方互不相让” can introduce harmless connective/abstract wording even when all underlying events are grounded.

The old person rule also treated a missing person-linked support ref as fatal even when:

```text
人物N exists in the frozen current Scene
+ full Grounding Packet contains PERSON_APPEARANCE / Shot presence provenance for that P*
```

This is a provenance formatting omission, not evidence that the person is absent.

## Implemented fix after this failed gate

Validator now:

```text
1. validates all model-supplied Fxxxx refs first;
2. auto-adds SCENE_BASE_SUMMARY to story_summary when available;
3. auto-adds exact hard-anchor facts used in text;
4. auto-adds a conservative person-existence fact for an existing 人物N when model support omitted it;
5. rejects unknown 人物N exactly as before;
6. rejects unsupported new numbers;
7. rejects unsupported high-risk plot/relationship terms such as 杀死/绑架/枪击/结婚/怀孕 etc.;
8. requires story_summary to remain mainly covered by frozen lexical facts using a minimum content coverage gate;
9. keeps title abstraction on a separate narrow allow-list;
10. never modifies any frozen Shot or Final Asset truth.
```

Prompt profile advanced to:

```text
breakdown-g2-scene-narrative-zh-v1.2
```

The compact model input now includes `PERSON_APPEARANCE` facts so the model can cite person provenance directly.

New regression tests:

```text
engine/tests/v2/test_breakdown_scene_narrative_real_regression_v1.py
```

They verify:

```text
reasonable grounded compression + missing person support -> accepted with deterministic support completion
unsupported major event “杀死” -> still rejected
```

## Required next gate

Run after pulling latest `main`:

```powershell
python -m pytest engine/tests/v2/test_breakdown_scene_narrative_v1.py engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py engine/tests/v2/test_breakdown_scene_narrative_real_regression_v1.py -q
```

Expected target: **10 passed**.

Then:

```powershell
python scripts/run_breakdown_g2_scene_narrative_acceptance_v1.py
```

Final acceptance still requires all of:

```text
runner Scene 1 = READY
runner Scene 2 = READY
overlay_status = READY
both Scenes have accepted title + story_summary
shot_objects_unchanged = YES
structure_gate = PASS
narrative_gate = PASS
acceptance_machine_gate = PASS
```

Human review must also confirm both summaries are concise, readable, and do not add unsupported plot facts.

Do not change frozen G1, Character V10.1, or G2.1/G2.2 to solve Narrative wording.
