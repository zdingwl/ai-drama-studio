# G2.3 / G2.4 — Final real-model acceptance

Date: 2026-08-31
Branch: `main`

## Final status

```text
G1 Fast Grounded                 = REAL ACCEPTED / PRODUCTION / FROZEN
G2.1 Scene Timeline Contract     = FINAL PASS / FROZEN FOUNDATION
G2.2 Deterministic Assembler     = FINAL PASS / FROZEN FOUNDATION
G2.3 Scene Narrative             = FINAL PASS / FROZEN
G2.4 Source/Support Validator    = FINAL PASS / FROZEN
Local Qwen text runtime          = REAL ACCEPTED / FROZEN BASELINE
Character V10.1                  = PROTECTED / UNCHANGED
G2.5 Scene Timeline API          = NEXT
```

## Frozen prompt/runtime profiles

```text
Narrative prompt = breakdown-g2-scene-narrative-zh-v1.5
Qwen runtime = breakdown-g2-scene-narrative-qwen3-local-v1
model = Qwen3-VL-4B-Instruct
mode = text-only / offline / one model load / Scenes sequential
max_new_tokens = 512
```

## User-local regression evidence

User ran:

```powershell
python -m pytest engine/tests/v2/test_breakdown_scene_narrative_v1.py engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py engine/tests/v2/test_breakdown_scene_narrative_real_regression_v1.py -q
```

Observed:

```text
............... [100%]
```

Accepted baseline:

```text
15 passed
```

No assistant-local pytest/CUDA PASS is claimed.

## Final real-model acceptance evidence

Run:

```text
BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
```

Runtime/structure:

```text
preflight = READY
profile = breakdown-g2-scene-narrative-qwen3-local-v1
device = cuda
max_new_tokens = 512
missing = []
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

Narrative gate:

```text
overlay_status = READY
warnings = []
narrative_gate = PASS
acceptance_machine_gate = PASS
```

## Accepted Scene 1

```text
title = 走廊争花
summary = 老年女性质问年轻女性为何将花放在自家花瓶，年轻女性称花在走廊，双方争执并最终以给钱解决，年轻女性愤怒指责对方。
runner = READY
```

The Narrative is substantially more readable than the deterministic shot-list summary and does not modify frozen Shot objects.

## Accepted Scene 2

```text
title = 客厅争执
summary = 人物2指责人物1对邻居偷花一事不作为，称其结婚八年从未支持过自己，人物1则表示自己会自行解决。
runner = READY
dialogue topic diagnostics included = 报警 / 结婚 / 丈夫
```

Human semantic review:

```text
“邻居偷花” remains inside 指责/对白 attribution.
“结婚八年” remains inside 人物2称/指责 attribution.
The summary does NOT assert “人物1与人物2确定结婚八年” as objective identity truth.
The summary does NOT bind 丈夫/妻子/姓名 to anonymous Scene-local people.
“人物1表示自己会自行解决” remains an attributed dialogue claim.
```

Therefore the ASR/visual authority boundary is respected.

## Frozen G2.4 rules

```text
Visual/Timeline fact
→ may be stated directly.

Ordinary ASR claim
→ must remain inside explicit speech/argument attribution.

Sensitive event term from ASR
→ explicit topic OR explicitly attributed statement in same clause.
→ cannot become an unattributed objective event.

Relationship identity term
→ topic-only.
→ cannot bind anonymous people even through 称/指责 framing.

Dialogue identity name
→ cannot bind anonymous people.

Arabic/Chinese quantities
→ must exist in final provenance after automatic Dialogue support completion.
```

Important regression examples:

```text
ASR “结婚八年...” + “人物2称结婚八年...” = valid attributed statement
“人物1与人物2结婚八年” = reject
ASR “八年” → Narrative “十年” = reject
Dialogue “丈夫” → “人物1是人物2丈夫” = reject
Dialogue name “张三” → anonymous-person binding = reject
```

## Frozen ownership

LLM MAY write only:

```text
readable_title
story_summary
```

LLM MUST NOT own or rewrite:

```text
Scene / Shot timestamps or boundaries
people count / identity
Shot visual
performance/action
ASR verbatim dialogue
OCR verbatim text
prop existence
shot type
composition
camera motion
Final Character / Final Scene / Final Prop
```

Overlay application still rechecks Run/ShotRevision/Episode anchors and Scene source_fingerprint.

## Do not reopen

Do not retune these layers to accommodate future API/UI needs unless a concrete new regression proves the frozen layer wrong:

```text
Window Context v4
Exact-Shot Compact v3
Fusion E6-v2
G2.1 Scene Timeline Contract
G2.2 deterministic assembler
G2.3 Narrative prompt v1.5
G2.4 Source/Support Validator v1.5
Character V10.1
```

API/UI must consume this accepted truth; they must not redefine it.

## Next work

```text
G2.5 Scene Timeline API
```

Primary API goal:

```text
Return direct ordinary-user Scene Timeline results:
Scene info
→ people
→ shot cards
→ visual/action/dialogue/props/cinematography/OCR
→ accepted readable title/story_summary
```

Primary API/UI must hide engineering internals such as:

```text
support Fxxxx
Evidence IDs
cluster keys
LocalSubject DB IDs
confidence/provider/model diagnostics
raw validator diagnostics
```

Developer diagnostics may keep those separately.

After G2.5 acceptance:

```text
G2.6 ordinary-user Scene Timeline UI
```
