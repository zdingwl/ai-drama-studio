# 2026-08-31 — G2 Scene Narrative real acceptance #5 / attributed ASR

## Status

```text
G2.1 Scene Timeline Contract = FINAL PASS / FROZEN FOUNDATION
G2.2 Deterministic Assembler = FINAL PASS / FROZEN FOUNDATION
G2.3 Scene Narrative = USER-LOCAL BASELINE PASS / REAL-MODEL RETEST REQUIRED
G2.4 Source/Support Validator = USER-LOCAL BASELINE PASS / REAL-MODEL RETEST REQUIRED
Character V10.1 = PROTECTED / UNCHANGED
G1/P2.6 = FROZEN / UNCHANGED
```

Do not mark G2.3/G2.4 FINAL PASS yet.

## User-local test evidence before v1.4 change

User ran:

```powershell
python -m pytest engine/tests/v2/test_breakdown_scene_narrative_v1.py engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py engine/tests/v2/test_breakdown_scene_narrative_real_regression_v1.py -q
```

Observed:

```text
............. [100%]
```

Therefore the prior 13-test code baseline passed on the user machine.

## Real local-Qwen acceptance #5

Run:

```text
BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
```

Structural/runtime evidence:

```text
preflight = READY / cuda / max_new_tokens=512 / missing=[]
runner Scene1 = READY
runner Scene2 = READY
scenes = 2
shots = 30
people = [2,2]
Shot0001 people = []
Shot0001 props = 遥控器 / 蓝色玫瑰花束 / 玻璃花瓶 / 书本
shot_objects_unchanged = YES
structure_gate = PASS
```

Scene1 accepted Narrative:

```text
title = 走廊对峙
summary = 两位女性在公寓走廊因蓝色玫瑰花束争执，最终以金钱交易收场，气氛紧张。
```

Scene2 raw Qwen candidate:

```text
title = 客厅对峙
summary = 人物1与人物2在客厅争论邻居偷花事件，人物2指责人物1不帮说话、偏袒小偷，人物1则称对方事多矫情。
```

Scene2 known dialogue topic terms from frozen ASR:

```text
报警
结婚
丈夫
```

Validator result:

```text
overlay_status = READY_WITH_WARNINGS
warning = Scene2 summary content coverage 42%
narrative_gate = FAIL
acceptance_machine_gate = FAIL
```

## Root cause

The Scene2 candidate is written as attributed dialogue claims (`争论 / 指责 / 称`) and is much closer to a useful plot summary than the deterministic visual list.

The previous validator only allowed:

```text
visual / Scene summary lexical coverage
+
explicit sensitive ASR topic terms such as 结婚/丈夫/报警
```

It did not allow ordinary ASR plot content such as:

```text
邻居偷花
不帮说话
偏袒小偷
事多矫情
```

to contribute to grounded coverage even when the model correctly framed those statements as dialogue claims.

## New semantic rule

ASR is now a **restricted Narrative source**, not visual truth.

```text
Visual/Timeline fact
→ may be stated directly

DIALOGUE/ASR
→ may support what people argued / accused / said / claimed
→ must remain inside a dialogue-reporting frame
→ may not silently become objective visual truth
```

Allowed examples:

```text
双方争论邻居偷花一事
人物2指责人物1不帮说话
人物1称对方事多矫情
```

Rejected examples:

```text
邻居偷花
人物1偏袒小偷
人物1是人物2的丈夫
两人已经结婚
```

## Implemented changes after acceptance #5

### Validator

`engine/app/breakdown_scene_narrative_validator_v1.py`

Now:

```text
1. Split summary into clauses.
2. Find claim/dialogue lexical overlap per clause.
3. If ASR-only content is used, that clause must contain a reporting marker such as:
   争论 / 指责 / 称 / 表示 / 质问 / 回应 / 认为 / 抱怨 / 反驳 / 解释 ...
4. Add only relevant DIALOGUE Fxxxx support facts.
5. Add only actual overlapping claim characters to coverage.
6. Never add the whole ASR transcript to lexical authority.
7. Keep separate stricter gates for names, relationship words and high-impact events.
```

### Prompt

Profile upgraded to:

```text
breakdown-g2-scene-narrative-zh-v1.4
```

Prompt explicitly distinguishes:

```text
visual fact
vs
attributed dialogue claim
```

### Regression

`engine/tests/v2/test_breakdown_scene_narrative_real_regression_v1.py`

New real-Scene2-style case requires this to pass:

```text
人物1与人物2在客厅争论邻居偷花事件，
人物2指责人物1不帮说话、偏袒小偷，
人物1则称对方事多矫情。
```

and requires unframed objective promotion to fail:

```text
邻居偷花，人物1偏袒小偷。
```

## Next user gate

Current code has one additional regression test, so expected count is now:

```text
14 passed
```

Run:

```powershell
python -m pytest engine/tests/v2/test_breakdown_scene_narrative_v1.py engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py engine/tests/v2/test_breakdown_scene_narrative_real_regression_v1.py -q
```

Then rerun:

```powershell
python scripts/run_breakdown_g2_scene_narrative_acceptance_v1.py
```

Final acceptance still requires:

```text
overlay_status = READY
warnings = []
shot_objects_unchanged = YES
structure_gate = PASS
narrative_gate = PASS
acceptance_machine_gate = PASS
```

Human inspection remains mandatory after machine PASS.
