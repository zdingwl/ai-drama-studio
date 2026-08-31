# G2.3 / G2.4 — Real acceptance #6: attributed sensitive ASR

Date: 2026-08-31
Branch: `main`

## Status

```text
G2.1 Scene Timeline Contract   = FINAL PASS / FROZEN FOUNDATION
G2.2 Deterministic Assembler   = FINAL PASS / FROZEN FOUNDATION
G2.3 Scene Narrative           = REAL-MODEL RETEST REQUIRED
G2.4 Source/Support Validator  = REAL-MODEL RETEST REQUIRED
Character V10.1                = PROTECTED / UNCHANGED
G1                             = FROZEN / UNCHANGED
```

Do not mark G2.3/G2.4 FINAL PASS yet.

## User-local regression evidence before v1.5 change

User ran:

```powershell
python -m pytest engine/tests/v2/test_breakdown_scene_narrative_v1.py engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py engine/tests/v2/test_breakdown_scene_narrative_real_regression_v1.py -q
```

Observed:

```text
.............. [100%]
```

Therefore the pre-v1.5 suite had **14 user-local passing tests**.

## Real-model acceptance #6 evidence

Run:

```text
BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
```

Observed structural/runtime evidence:

```text
preflight = READY / cuda / missing=[]
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

Scene 1 was accepted:

```text
title = 走廊对峙
summary = 两位女性在公寓走廊因蓝色玫瑰花束归属争执，最终以金钱交易收场，气氛紧张。
```

Scene 2 raw Qwen candidate:

```text
title = 客厅对峙
summary = 人物2抱怨邻居偷花并骂人，人物1不以为意，两人争论是否该报警，人物1称对方事多矫情，人物2指责其结婚八年从未说过一句支持的话。
```

Scene 2 Dialogue diagnostic terms included:

```text
报警
结婚
丈夫
```

Validator rejected Scene 2 only because `结婚` was restricted to topic-only form:

```text
场景 2 的 剧情摘要未通过：关键剧情词“结婚”被写成既成事件
```

Final gate:

```text
overlay_status = READY_WITH_WARNINGS
narrative_gate = FAIL
acceptance_machine_gate = FAIL
```

## Interpretation

This failure is not a runtime failure and not a frozen Timeline regression.

The candidate did not independently assert `两人已经结婚八年`; the sensitive content appeared inside the explicitly attributed clause:

```text
人物2指责其结婚八年从未说过一句支持的话
```

Therefore the validator needed to distinguish:

```text
unattributed event assertion
vs.
explicitly attributed ASR statement
```

The existing generic attributed-ASR layer already made this distinction for ordinary dialogue content, but the sensitive-event gate still required topic-only wording.

## v1.5 change

Prompt profile:

```text
breakdown-g2-scene-narrative-zh-v1.5
```

Validator now uses these boundaries:

```text
Visual/Timeline fact
→ may be stated directly.

Ordinary ASR claim
→ must remain inside reporting/argument framing such as 指责/称/表示/质问/争论.

Sensitive event term from ASR, e.g. 结婚/死亡/报警
→ may be either an explicit topic OR an explicitly attributed statement in the same clause.
→ may not become an unattributed objective event.

Relationship identity term, e.g. 丈夫/妻子/父亲/男友
→ remains topic-only.
→ cannot be bound to 人物N even through 称/指责 framing.

Dialogue identity name
→ remains forbidden for anonymous-person binding.
```

Chinese quantities are now also provenance-checked after automatic Dialogue support is completed:

```text
八年 / 十年
一句 / 三次 / 两个月
```

Example:

```text
ASR = 结婚八年...
Attributed Narrative with 八年 = potentially valid
Attributed Narrative changed to 十年 = reject
```

## New regression gate

Added one regression test for:

```text
人物2指责对方，称结婚八年从未帮自己说过一句支持的话。
```

It also verifies:

```text
人物1与人物2结婚八年... -> reject as unattributed objective relation/event
ASR 八年 -> Narrative 十年 -> reject as unsupported quantity
```

Current target is now:

```text
15 tests passed
```

## Next required action

Run:

```powershell
python -m pytest engine/tests/v2/test_breakdown_scene_narrative_v1.py engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py engine/tests/v2/test_breakdown_scene_narrative_real_regression_v1.py -q
```

Expected:

```text
15 passed
```

Then rerun:

```powershell
python scripts/run_breakdown_g2_scene_narrative_acceptance_v1.py
```

Final acceptance still requires all of:

```text
overlay_status = READY
warnings = []
shot_objects_unchanged = YES
structure_gate = PASS
narrative_gate = PASS
acceptance_machine_gate = PASS
```

Machine PASS must still be followed by human inspection of both Scene summaries before marking G2.3/G2.4 FINAL PASS.
