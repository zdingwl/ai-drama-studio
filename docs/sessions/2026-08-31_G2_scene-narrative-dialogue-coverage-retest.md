# G2.3/G2.4 Scene Narrative — dialogue coverage retest handoff

Date: 2026-08-31 +08:00

## Current status

```text
G2.1 Scene Timeline Contract = FINAL PASS / FROZEN FOUNDATION
G2.2 Deterministic Assembler = FINAL PASS / FROZEN FOUNDATION
G2.3 Scene Narrative = USER-LOCAL TEST PASS ON PREVIOUS REVISION / REAL-MODEL RETEST REQUIRED
G2.4 Source/Support Validator = USER-LOCAL TEST PASS ON PREVIOUS REVISION / REAL-MODEL RETEST REQUIRED
Local Qwen text runtime = READY / CUDA / both accepted-run Scenes return READY
G1 = FROZEN
Character V10.1 = PROTECTED
```

Do not mark G2.3/G2.4 FINAL PASS until the newly patched validator + diagnostics pass user-local tests and real-model acceptance.

## User-local evidence before latest patch

User ran:

```powershell
python -m pytest engine/tests/v2/test_breakdown_scene_narrative_v1.py engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py engine/tests/v2/test_breakdown_scene_narrative_real_regression_v1.py -q
```

Observed:

```text
............. [100%]
```

This is 13 tests passed for the revision immediately before the latest dialogue-coverage fix.
Because validator/adapter/tests were changed afterwards, rerun the same 13-test command before final acceptance.

## Fourth real-model acceptance evidence

Run:

```text
BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
```

Observed structural/runtime evidence:

```text
preflight = READY / cuda / max_new_tokens=512 / missing=[]
runner_diagnostics = Scene1 READY / Scene2 READY
scenes = 2
shots = 30
people = [2, 2]
shot1_people = []
shot1_props = ['遥控器', '蓝色玫瑰花束', '玻璃花瓶', '书本']
shot_objects_unchanged = YES
structure_gate = PASS
```

Observed Narrative evidence:

```text
overlay_status = READY_WITH_WARNINGS
narrative_gate = FAIL
acceptance_machine_gate = FAIL
```

Scene 1 was accepted and useful:

```text
dialogue_topic_terms = ['报警']
title = 走廊对峙
summary = 两位女性在公寓走廊因蓝色玫瑰花束争执，最终以金钱交易收场，气氛紧张。
```

Scene 2 dialogue really contains:

```text
['报警', '结婚', '丈夫']
```

Scene 2 was rejected only because:

```text
与来源事实的内容覆盖率过低（23%）
```

This proved that the relevant high-impact terms are real ASR topics rather than model-invented words.

## Root cause found

The validator correctly detected that `结婚 / 丈夫 / 报警` existed in DIALOGUE and could be used as topic expressions, and it appended their DIALOGUE `Fxxxx` facts to support.

But coverage was still calculated using the old non-ASR `supported_chars` set. The newly validated dialogue-topic terms were never added to coverage authority, so a grounded dialogue-topic summary could still fail with low lexical coverage.

## Latest patch

Validator changes:

```text
engine/app/breakdown_scene_narrative_validator_v1.py
```

Behavior now:

1. Full DIALOGUE text is still NOT lexical authority.
2. A sensitive term may contribute coverage only when:
   - that exact term exists in current Scene DIALOGUE, and
   - the claim uses it as an explicit topic expression.
3. Only the validated term itself and the actual topic markers used by the claim contribute dialogue-topic coverage.
4. Relation terms such as `丈夫/妻子/父母/...` are stricter:
   - allowed: `围绕丈夫的问题`, `关于丈夫的话题`, `谈到丈夫`
   - rejected: `人物1是人物2的丈夫`, `质问丈夫`
5. Dialogue identity names remain forbidden from anonymous-person binding.
6. New numbers, unknown 人物N, Final IDs, unsupported hard anchors and unsupported major plot events remain fail-closed.

Adapter/acceptance diagnostics changes:

```text
engine/app/breakdown_scene_narrative_qwen3_v1.py
scripts/run_breakdown_g2_scene_narrative_acceptance_v1.py
```

The adapter now exposes only truncated candidate title/summary previews for local engineering acceptance. No prompt, token, secret or full provider error is exposed.

Acceptance output now includes:

```text
runner_candidate_previews=
raw_candidate_preview=
```

So a rejected LLM candidate can be inspected directly instead of inferred from warnings.

Regression test changes:

```text
engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py
engine/tests/v2/test_breakdown_scene_narrative_real_regression_v1.py
```

The real-regression test now covers `结婚 + 丈夫 + 报警` together and separately verifies that anonymous-person husband binding is still rejected.

## Latest commits

```text
48330d0eaf944983ff0918cc7085fff7d8000f83  dialogue topics participate in summary coverage
9d85fed2d15a7f7b1d4d044e79ee6d3bf9b29401  safe candidate previews in local Qwen adapter
62e426f1b15a50812166e3ec9bb96dfd5822d6d9  candidate previews in real acceptance runner
6574af6b46604cc75fd4c9fcd754546644938a15  adapter preview test coverage
5dc78a70d8ebbd3d1e14233d1104787bdcbec510  realistic multi-topic dialogue regression
A0330161A94455B53AD5BA223F06E84B76299A78  tightened relation-topic suffix handling
```

## Required next gate

Pull latest main, then rerun:

```powershell
python -m pytest engine/tests/v2/test_breakdown_scene_narrative_v1.py engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py engine/tests/v2/test_breakdown_scene_narrative_real_regression_v1.py -q
```

Expected count remains 13 tests.

Then run:

```powershell
python scripts/run_breakdown_g2_scene_narrative_acceptance_v1.py
```

Final real acceptance requires all of:

```text
runner_diagnostics Scene1/Scene2 = READY
overlay_status = READY
warnings = []
Scene1 readable_title + story_summary accepted
Scene2 readable_title + story_summary accepted
shot_objects_unchanged = YES
structure_gate = PASS
narrative_gate = PASS
acceptance_machine_gate = PASS
```

Human inspection is still required for both summaries. A machine PASS is not enough if the prose upgrades dialogue into unsupported identity or occurred visual events.

If the next run fails, inspect `raw_candidate_preview` before changing validator policy again.
