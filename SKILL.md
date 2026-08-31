---
name: ai-drama-studio-reference-video-v2
version: 3.18.4
description: Reference Video V2 / Fast Grounded Breakdown V2 / Character V10.1；G1/P2.6、G2.1/G2.2、G2.3/G2.4 均已真实验收并冻结，下一阶段为 G2.5 Scene Timeline API。
---

# AI Drama Studio — Reference Video V2 / Fast Grounded Breakdown V2 / Character V10.1

## 0. 恢复项目上下文

必须先读取 GitHub 当前仓库事实：

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/CURRENT_IMPLEMENTATION_MANIFEST.md
→ Breakdown plans/contracts
→ docs/BREAKDOWN_G2_SCENE_TIMELINE_CONTRACT.md
→ docs/BREAKDOWN_G2_SCENE_NARRATIVE_CONTRACT.md
→ Character docs when relevant
→ current code/tests
→ latest docs/sessions/*.md handoff
```

Executable CURRENT = `PROJECT_STATE + CURRENT_IMPLEMENTATION_MANIFEST + current code/tests`.

## 1. Current baseline

```text
Architecture: Reference Video V2 + Breakdown Fast Grounded V2
Formal Character runtime: Character V10.1
P1/P2 implementation acceptance: CONDITIONAL PASS
Fast Grounded G1: REAL ACCEPTED / PRODUCTION / FROZEN
Window Context: Segment-index v4 / REAL ACCEPTED / FROZEN
Exact-Shot: Compact-reconstruction v3 / REAL ACCEPTED / FROZEN
P2-E6 Fusion: E6-v2 / REAL PRODUCTION ACCEPTED / FROZEN
P2.6 Windows / real-model acceptance: PASS
G2 Scene Timeline Contract: v1 / FINAL PASS / FROZEN FOUNDATION
G2 Deterministic Assembler: v1 / FINAL PASS / FROZEN FOUNDATION
G2 Scene Narrative Core: v1.5 / FINAL PASS / FROZEN
G2 Local Qwen text runtime: REAL ACCEPTED / FROZEN BASELINE
G2 Source/Support Validator: v1.5 / FINAL PASS / FROZEN
G2.3/G2.4 real-model acceptance: PASS
G2.5 Scene Timeline API: NOT IMPLEMENTED
G2.6 ordinary-user Scene Timeline UI: NOT IMPLEMENTED
P5 Draft ↔ Character: PAUSED
```

Do not reopen G1 or any accepted G2 layer without a concrete new regression.

## 2. Frozen production flow

```text
Original Episode
→ Preprocess
→ Shot Detection + frozen ShotRevision
→ PROCESSING BreakdownRun
→ Episode ASR
→ OCR
→ one-load Qwen3-VL Fast Grounded
   ├─ Window Segment-index v4
   └─ Exact-Shot Compact-reconstruction v3
→ immutable exact-Shot VLM_OUTPUT
→ P2-E6-v2 Episode-context Fusion
→ anonymous P1 Draft
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Profiles:

```text
Window = breakdown-p2-vlm-window-context-segment-index-zh-v4
Exact-Shot = breakdown-p2-vlm-exact-shot-compact-reconstruction-zh-v3
Fusion = breakdown-p2-fusion-episode-context-e6-v2
Pipeline = breakdown-p2-full-v1
```

## 3. Final P2.6 acceptance truth

```text
Run = BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
status = READY
whole run ~= 841.039s = 14.017 min
Window = 4/4 READY
Exact-Shot = 6/6 READY
MAXED = 0
Scenes = 2
Scene1 LocalSubjects = 2
Scene2 LocalSubjects = 2
same_shot_cluster_conflicts = 0
Shot0001 subjects = 0
Shot0001 props include 蓝色玫瑰花束 + 玻璃花瓶
Fusion = breakdown-p2-fusion-episode-context-e6-v2
```

## 4. Core semantic boundaries

> **先看懂，再识别，再回填。**

> **Shot 是最小视觉证据与定位单位，不是连续理解的上下文上限。**

> **Exact-Shot visible fact > Window Context.**

> **Scene Timeline 是最终用户阅读拉片结果的主要单位。**

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
subject_A/B = Shot-local observation labels only
same-Shot observations = hard cannot-link
G2 Scene-local P1/P2 != Character identity
G2 Scene Timeline != Final Character / Final Scene / Final Prop truth
ASR-origin dialogue text = verbatim truth
OCR-origin visible text = verbatim truth
```

Window Context provides Scene/anonymous continuity context. Exact-Shot owns current-Shot visible truth. ASR owns dialogue text truth. OCR owns visible text evidence.

## 5. Character V10.1 protected baseline

```text
YOLOX Person Detection
→ capture-first Person Evidence
→ mature MOT
→ YoutuReID project identity
→ RESOLVED / UNRESOLVED
→ explicit Shot × known-Character Assignment
→ Final Character Gate
```

Never weaken Character identity safety because of Breakdown anonymous hints.

## 6. G2.1 / G2.2 frozen Scene Timeline foundation

Accepted:

```text
engine/app/breakdown_scene_timeline_contract_v1.py
engine/app/breakdown_scene_timeline_assembler_v1.py
engine/tests/v2/test_breakdown_scene_timeline_v1.py
docs/BREAKDOWN_G2_SCENE_TIMELINE_CONTRACT.md
```

Acceptance:

```text
python -m pytest engine/tests/v2/test_breakdown_scene_timeline_v1.py -q
4 passed

scenes = 2
shots = 30
people = [2, 2]
shot1_people = []
shot1_props = ['遥控器', '蓝色玫瑰花束', '玻璃花瓶', '书本']
warnings = []
```

## 7. G2.3 / G2.4 frozen Scene Narrative

Formal flow:

```text
FINAL PASS scene-timeline-v1
→ per-Scene Grounding Packet
→ deterministic Fxxxx facts
→ SHA-256 source_fingerprint
→ text-only local Qwen3-VL-4B-Instruct
   one model load / Scenes sequential
→ Scene Narrative Candidate
→ Source/Support Validator
→ Validated Narrative Overlay
→ title/story_summary only
```

Prompt profile:

```text
breakdown-g2-scene-narrative-zh-v1.5
```

LLM may write only:

```text
readable_title
story_summary
```

It cannot own/rewrite timestamps, people identity/count, Shot facts, ASR/OCR, props, cinematography or Final Assets.

ASR Narrative rule:

```text
Visual/Timeline fact → may be stated directly.
Ordinary ASR claim → must remain inside attributed speech/argument framing.
Sensitive event term from ASR → explicit topic OR explicitly attributed statement only.
Relationship identity term → topic-only; cannot bind anonymous people.
Dialogue identity name → cannot bind anonymous people.
Chinese/Arabic quantities → must exist in final support.
```

Final user-local + real-model acceptance:

```text
15 tests passed
preflight = READY / cuda / missing=[]
runner Scene1 = READY
runner Scene2 = READY
overlay_status = READY
warnings = []
shot_objects_unchanged = YES
structure_gate = PASS
narrative_gate = PASS
acceptance_machine_gate = PASS
```

Accepted examples:

```text
Scene1: 走廊争花
老年女性质问年轻女性为何将花放在自家花瓶，年轻女性称花在走廊，双方争执并最终以给钱解决，年轻女性愤怒指责对方。

Scene2: 客厅争执
人物2指责人物1对邻居偷花一事不作为，称其结婚八年从未支持过自己，人物1则表示自己会自行解决。
```

Human review: PASS. Sensitive ASR claims remain attributed; no anonymous-person relationship binding is created; frozen Shot objects remain unchanged.

## 8. Local text-only Qwen runtime

```text
.runtime/TransVLM/inference/.venv
.runtime/TransVLM/inference/pretrained/Qwen3-VL-4B-Instruct
```

The G2 runner is text-only, offline, loads the model once and processes Scenes sequentially.

## 9. Testing / CI discipline

Do not claim assistant-local pytest/CUDA execution. User-local evidence is acceptance truth. Hosted GitHub Actions must not be used; commits use `[skip ci]`.

Frozen G2 Narrative regression command:

```text
python -m pytest engine/tests/v2/test_breakdown_scene_narrative_v1.py engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py engine/tests/v2/test_breakdown_scene_narrative_real_regression_v1.py -q
Expected accepted baseline: 15 passed
```

## 10. Immediate safe work

```text
1. keep G1 + G2.1/G2.2 + G2.3/G2.4 frozen
2. implement G2.5 Scene Timeline API
3. expose direct user-readable Scene Timeline result
4. keep support Fxxxx / model/provider diagnostics out of ordinary UI
5. implement G2.6 ordinary-user UI after API acceptance
```
