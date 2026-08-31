---
name: ai-drama-studio-reference-video-v2
version: 3.18.3
description: Reference Video V2 / Fast Grounded Breakdown V2 / Character V10.1；G1/P2.6 与 G2.1/G2.2 已冻结，G2.3 Scene Narrative + G2.4 Source/Support Validator 已实现，待本机测试与真实本地 Qwen 验收。
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
→ docs/BREAKDOWN_G2_SCENE_NARRATIVE_CONTRACT.md when working on G2.3+
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
G2 Scene Narrative Core: v1 / IMPLEMENTED / USER-LOCAL TEST PENDING
G2 Local Qwen text runtime: v1 / IMPLEMENTED / USER-LOCAL TEST PENDING
G2 Source/Support Validator: v1 / IMPLEMENTED / USER-LOCAL TEST PENDING
G2.3/G2.4 real-model acceptance: PENDING
G2.5 Scene Timeline API: NOT IMPLEMENTED
G2.6 ordinary-user Scene Timeline UI: NOT IMPLEMENTED
P5 Draft ↔ Character: PAUSED
```

G2.1/G2.2 have passed both local regression tests and final accepted real-Run deterministic smoke acceptance.
Do not reopen the deterministic foundation without a concrete G2 regression.
G2.3/G2.4 implementation must not be called PASS before user-local tests and final real-model acceptance.

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

Do not change these profiles or inference/continuity thresholds unless a new real regression appears.

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

Therefore:

```text
P2.6 = PASS
G1 = FROZEN
G2 / Scene Timeline = ACTIVE
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

Window Context provides Scene/anonymous continuity context. Exact-Shot owns current-Shot visible truth.
ASR owns dialogue text truth. OCR owns visible text evidence.

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

Final Run smoke:
scenes = 2
shots = 30
people = [2, 2]
shot1_people = []
shot1_props = ['遥控器', '蓝色玫瑰花束', '玻璃花瓶', '书本']
warnings = []
```

Therefore G2.1/G2.2 are **FINAL PASS / FROZEN FOUNDATION**.

## 7. G2.3 / G2.4 implementation

Implemented modules:

```text
engine/app/breakdown_scene_narrative_contract_v1.py
engine/app/breakdown_scene_grounding_v1.py
engine/app/breakdown_scene_narrative_v1.py
engine/app/breakdown_scene_narrative_validator_v1.py
engine/app/breakdown_scene_narrative_qwen3_v1.py
scripts/run_breakdown_scene_narrative_qwen3.py
engine/tests/v2/test_breakdown_scene_narrative_v1.py
engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py
docs/BREAKDOWN_G2_SCENE_NARRATIVE_CONTRACT.md
```

Formal flow:

```text
FINAL PASS scene-timeline-v1
→ per-Scene Grounding Packet
→ deterministic F0001/F0002/... facts
→ SHA-256 source_fingerprint
→ text-only local Qwen3-VL-4B-Instruct
   one model load / Scenes sequential
→ Scene Narrative Candidate
→ Source/Support Validator
→ Validated Narrative Overlay
→ overlay may change only title / story_summary
```

LLM may write only:

```text
readable_title
story_summary
```

LLM cannot own or rewrite:

```text
timestamps
people identity/count
Shot visual
performance/action
ASR dialogue
OCR
prop existence
shot type
composition
camera motion
Final Character / Final Scene / Final Prop
```

Every non-null title/summary must cite real `Fxxxx` facts. Validator rejects bad support, internal P1/P2 leakage,
unknown 人物N, unsupported hard anchor terms, Final Asset/ID declarations and stale fingerprints.

ASR/OCR prompt injection-like strings are wrapped inside `<SCENE_DATA>` and explicitly treated as data only.
Invalid JSON does not trigger an automatic second model call; Narrative degrades while deterministic Timeline remains usable.

## 8. Local text-only Qwen runtime

The G2 adapter reuses the already installed isolated base checkpoint/runtime:

```text
.runtime/TransVLM/inference/.venv
.runtime/TransVLM/inference/pretrained/Qwen3-VL-4B-Instruct
```

It does **not** use the frozen G1 Window/Exact-Shot inference contract and does not open video/images.
One subprocess loads the model once, then runs Scene prompts sequentially.

G2-specific configuration:

```text
AI_DRAMA_G2_LLM_PYTHON
AI_DRAMA_G2_LLM_MODEL_PATH
AI_DRAMA_G2_LLM_DEVICE
AI_DRAMA_G2_LLM_MAX_NEW_TOKENS
AI_DRAMA_G2_LLM_RUNNER
```

Python/model/device can fall back to the existing `AI_DRAMA_P2_VLM_*` runtime configuration.

## 9. Testing / CI discipline

Do not claim assistant-local pytest/CUDA execution. Do not consume hosted GitHub Actions quota. Use `[skip ci]`.

G2.3/G2.4 required user-local tests:

```text
python -m pytest engine/tests/v2/test_breakdown_scene_narrative_v1.py engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py -q
Expected: 8 passed
```

Then runtime preflight:

```text
python -c "from engine.app.breakdown_scene_narrative_qwen3_v1 import Qwen3VLSceneTextLLM; print(Qwen3VLSceneTextLLM().runtime_preflight())"
Expected status: READY
```

Only after those pass should the accepted final Run be used for real text-only Qwen acceptance.

## 10. Immediate safe work

```text
1. user-local G2.3/G2.4 tests
2. local Qwen text runtime preflight
3. real text-only Scene Narrative on BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
4. verify only title/story_summary change; all 30 Shot facts stay deterministic
5. mark G2.3/G2.4 FINAL PASS only after real acceptance
6. implement G2.5 Scene Timeline API
7. build G2.6 ordinary-user UI last
```

If a G2.3/G2.4 regression appears, fix those layers first. Do not retune the frozen G1 chain or alter the accepted G2.1/G2.2 source-truth ownership unless a concrete regression proves it necessary.
