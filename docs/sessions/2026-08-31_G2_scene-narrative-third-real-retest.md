# Session Handoff — G2.3/G2.4 Third Real Narrative Retest

## Status

- Date: 2026-08-31
- Branch: `main`
- G2.1/G2.2: **FINAL PASS / FROZEN FOUNDATION**
- G2.3 Scene Narrative: **USER-LOCAL REGRESSION PASS / REAL-MODEL RETEST REQUIRED**
- G2.4 Source/Support Validator: **USER-LOCAL REGRESSION PASS / REAL-MODEL RETEST REQUIRED**
- Character V10.1: protected / unchanged

## User-local regression evidence

Command:

```powershell
python -m pytest engine/tests/v2/test_breakdown_scene_narrative_v1.py engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py engine/tests/v2/test_breakdown_scene_narrative_real_regression_v1.py -q
```

Observed:

```text
.......... [100%]
10 passed
```

## Third real-model acceptance evidence

Run:

```text
BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
```

Observed structural/runtime facts:

```text
runner Scene1 = READY
runner Scene2 = READY
scenes = 2
shots = 30
people = [2, 2]
shot1_people = []
shot1_props = ['遥控器', '蓝色玫瑰花束', '玻璃花瓶', '书本']
shot_objects_unchanged = YES
structure_gate = PASS
```

Scene 1 Narrative was accepted:

```text
title = 走廊对峙
summary = 老年女性持袋质问年轻女性关于花束归属，双方争执并以金钱收场，最终背对镜头走向电梯。
```

Scene 2 title was accepted:

```text
title = 客厅对峙
```

Scene 2 summary was rejected because candidate text contained the high-impact term `结婚`, while the then-current validator only allowed such terms from non-ASR lexical source truth:

```text
warning = 场景 2 的 剧情摘要 未通过来源校验：包含来源未支持的新内容字符/关键剧情词“结婚”
overlay_status = READY_WITH_WARNINGS
narrative_gate = FAIL
acceptance_machine_gate = FAIL
```

Therefore G2.3/G2.4 are **NOT FINAL PASS** yet.

## Root-cause refinement

The prior validator treated ASR as context but could not distinguish these two cases:

```text
SAFE:   ASR contains “结婚” -> “双方围绕结婚问题争执”
UNSAFE: ASR contains “结婚” -> “两人结婚”
```

The correct boundary is:

```text
ASR may support a dialogue/topic claim.
ASR must not be promoted into a visually occurred event.
ASR names/self-identifications/relationship labels must not bind anonymous Scene-local people.
```

## Changes after the third retest

### Validator

`engine/app/breakdown_scene_narrative_validator_v1.py`

- high-impact terms may be accepted from a real current-Scene DIALOGUE fact only when the Narrative text expresses them as a conversation topic, such as `围绕/关于/谈到/提到/讨论/询问/质问`;
- matching DIALOGUE `Fxxxx` support is added deterministically;
- the same term is still rejected when promoted to an occurred event;
- explicit names extracted from dialogue forms such as `改名成张三 / 名叫张三 / 我是张三` remain forbidden in anonymous Narrative output.

### Prompt

Profile is now:

```text
breakdown-g2-scene-narrative-zh-v1.3
```

The model is explicitly instructed that ASR-only high-impact relationship/event terms must be written as dialogue topics, not as occurred visual events.

### Regression tests

`engine/tests/v2/test_breakdown_scene_narrative_real_regression_v1.py` now additionally covers:

1. grounded ASR topic `结婚` is allowed as `围绕结婚问题`;
2. the same ASR term cannot become `两人结婚`;
3. dialogue prompt-injection/name text cannot bind `张三` to anonymous people.

### Acceptance diagnostics

`scripts/run_breakdown_g2_scene_narrative_acceptance_v1.py` now prints per Scene:

```text
dialogue_topic_terms = [...]
```

This exposes only detected high-impact topic terms, not full dialogue text, so the next real run can distinguish missing source from incorrect event promotion.

## Next acceptance

Re-run the three test files, then the real acceptance runner. Do not mark G2.3/G2.4 FINAL PASS unless:

```text
runner Scene1/2 = READY
overlay_status = READY
warnings = []
shot_objects_unchanged = YES
structure_gate = PASS
narrative_gate = PASS
acceptance_machine_gate = PASS
```

Human inspection must also confirm both summaries are readable and do not turn ASR topics into unsupported occurred events or identity bindings.

Do not modify frozen G1, G2.1/G2.2, or Character V10.1 to improve Narrative wording.
