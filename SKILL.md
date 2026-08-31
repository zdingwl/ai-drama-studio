---
name: ai-drama-studio-reference-video-v2
version: 3.17.0
description: Reference Video V2 / Fast Grounded Breakdown V2 / Character V10.1；G1/P2.6 已完成真实生产验收并冻结，下一阶段为 G2 Scene Timeline。
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
G2 Scene-level pure-text LLM: UNBLOCKED / NOT IMPLEMENTED
Scene Timeline UI: UNBLOCKED / NOT IMPLEMENTED
P5 Draft ↔ Character: PAUSED
```

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
G2 / Scene Timeline = UNBLOCKED
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
```

Window Context provides Scene/anonymous continuity context. Exact-Shot owns current-Shot visible truth.
ASR owns dialogue text truth. OCR owns visible text evidence.

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

## 7. Testing / CI discipline

Do not claim assistant-local pytest/CUDA execution. User-local real production evidence is the P2.6
acceptance source. Do not consume hosted GitHub Actions quota. Use `[skip ci]`.

## 8. Immediate safe work

G1 tuning is finished. Start G2 / Scene Timeline from current accepted Draft contracts.

```text
1. define a concise Scene Timeline contract users can directly understand
2. assemble Scene -> Shots -> dialogue -> visible people/actions -> reconstruction props deterministically
3. preserve ASR_SEGMENT as dialogue text truth
4. preserve Exact-Shot as visual truth
5. use Scene-level pure-text LLM only to organize/readability, never to invent evidence
6. design primary UI around direct results; hide Evidence/debug internals by default
```
