---
name: ai-drama-studio-reference-video-v2
version: 3.18.2
description: Reference Video V2 / Fast Grounded Breakdown V2 / Character V10.1；G1/P2.6 已冻结，G2.1 Scene Timeline Contract + G2.2 Deterministic Assembler 已完成本机回归与最终真实 Run 烟测，正式 FINAL PASS / FROZEN FOUNDATION。
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
→ docs/BREAKDOWN_G2_SCENE_TIMELINE_CONTRACT.md when working on G2
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
G2 Scene-level pure-text LLM: UNBLOCKED / NOT IMPLEMENTED
Scene Timeline UI: UNBLOCKED / NOT IMPLEMENTED
P5 Draft ↔ Character: PAUSED
```

G2.1/G2.2 have passed both local regression tests and final accepted real-Run deterministic smoke acceptance.
Do not reopen the deterministic foundation without a concrete G2 regression.

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
   ├─ accepted Scene policy
   ├─ ASR_SEGMENT dialogue truth
   └─ replay-v5 compact-safe anonymous continuity
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

Final user-local real production Run:

```text
Run = BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
status = READY
whole run ~= 841.039s = 14.017 min
ASR ~= 15.276s
OCR ~= 264.917s
VLM ~= 559.267s
Window Context ~= 84.349s
Exact-Shot ~= 455.284s
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
raw Evidence / Draft != Final binding truth
subject_A/B = Shot-local observation labels only
same-Shot observations = hard cannot-link
G2 Scene-local P1/P2 != Character identity
G2 Scene Timeline != Final Character / Final Scene / Final Prop truth
```

Window Context provides Scene/anonymous continuity context. Exact-Shot owns current-Shot visible truth.
ASR owns dialogue text truth. OCR owns visible text evidence.

G2.2 copies ASR-origin DIALOGUE and OCR-origin text verbatim. It does not use an LLM.

## 5. Accepted E6-v2 anonymous continuity

```text
Stage1:
  Window-listed ordinal = candidate presence only
  Exact-Shot stable appearance must positively support the hint

Stages2..4:
  canonicalize compact aliases for matching only
  preserve source appearance text
  preserve accepted thresholds

Hard guards:
  same-Shot cannot-link
  explicit gender conflict
  explicit long-hair vs short/bald conflict
```

Policies:

```text
window hint resolver = window-hint-positive-appearance-support-compact-alias-v2
compact appearance = compact-observation-stable-alias-normalization-v1
```

## 6. Character V10.1 protected baseline

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

## 7. G2 Scene Timeline frozen foundation

Accepted:

```text
Contract:
  engine/app/breakdown_scene_timeline_contract_v1.py

Deterministic assembler:
  engine/app/breakdown_scene_timeline_assembler_v1.py

Tests:
  engine/tests/v2/test_breakdown_scene_timeline_v1.py

Contract doc:
  docs/BREAKDOWN_G2_SCENE_TIMELINE_CONTRACT.md
```

Deterministic semantics:

```text
SceneSegmentDraft
→ Scene info
→ Scene-local P1/P2 anonymous people
→ ordered Shots
   → Exact-Shot visual_description
   → grounded performance
   → ASR-only dialogue, verbatim
   → Shot prop occurrences
   → shot type / Exact-Shot composition
   → reliable non-UNKNOWN camera motion only
   → OCR-only visible text, verbatim
→ existing Scene summary as non-LLM baseline
```

Primary output intentionally excludes Evidence, cluster, confidence, LocalSubject IDs, provider diagnostics and Final Asset IDs.

## 8. Testing / CI discipline

Do not claim assistant-local pytest/CUDA execution. User-local real production evidence is the P2.6
acceptance source. Do not consume hosted GitHub Actions quota. Use `[skip ci]`.

G2.1/G2.2 user-local regression evidence:

```text
python -m pytest engine/tests/v2/test_breakdown_scene_timeline_v1.py -q
....
4 passed
```

Final accepted real-Run smoke evidence:

```text
Run = BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
scenes = 2
shots = 30
people = [2, 2]
shot1_people = []
shot1_props = ['遥控器', '蓝色玫瑰花束', '玻璃花瓶', '书本']
warnings = []
```

Therefore G2.1/G2.2 are **FINAL PASS / FROZEN FOUNDATION**.

## 9. Immediate safe work

```text
1. implement G2.3 Scene-level pure-text LLM on top of the frozen deterministic Timeline
2. LLM only improves organization/readability and Scene narrative summary
3. implement G2.4 support/source validator with fail-closed fallback
4. preserve deterministic timestamps, people refs/count, ASR dialogue, OCR text, props, shot type and composition
5. validate G2.3/G2.4 against BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
6. add G2.5 Scene Timeline API
7. build G2.6 ordinary-user Scene Timeline UI last
```

If a G2.3/G2.4 regression appears, fix those layers first. Do not retune the frozen G1 chain or alter the accepted G2.1/G2.2 source-truth ownership unless a concrete regression proves it necessary.
