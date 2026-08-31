---
name: ai-drama-studio-reference-video-v2
version: 3.15.0
description: Reference Video V2 / Fast Grounded Breakdown V2 / Character V10.1；Window v4 与 Exact-Shot compact v3 已真实抽样验收并升产，P2.6 仅剩最后一次完整生产 Run 验收。
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
Window Context: Segment-index v4 / REAL ACCEPTED / PRODUCTION / FROZEN
Exact-Shot: Compact-reconstruction v3 / SELECTED-BATCH REAL ACCEPTED / PRODUCTION
P2-E6 Fusion: FRESH QUALITY POSITIVE / FROZEN
P2-E5: ROLLBACK BASELINE
P2-E4: OLDER ROLLBACK BASELINE
G2 Scene-level pure-text LLM: NOT IMPLEMENTED
Scene Timeline UI: NOT IMPLEMENTED
P2.6: NOT FINAL PASS — one fresh final production Run pending
P5 Draft ↔ Character: PAUSED
```

## 2. Current production flow

```text
Original Episode
→ Preprocess
→ Shot Detection + frozen ShotRevision
→ PROCESSING BreakdownRun
→ Episode ASR
→ OCR
→ one-load Qwen3-VL Fast Grounded
   ├─ Window Segment-index v4
   │    24s / 25% overlap / 1 FPS / 262144 px / 1600 max tokens
   │    Scene + anonymous subject/prop continuity only
   └─ Exact-Shot Compact-reconstruction v3
        <1.2s -> 1 frame
        1.2..3s -> 2 frames
        >3s -> 3 frames
        524288 px / 4096 max tokens / 5 Shots per batch
        current-Shot visible description / people / reconstruction props / framing
→ immutable exact-Shot VLM_OUTPUT
→ P2-E6 Episode-context Fusion
→ anonymous P1 Draft
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Profiles:

```text
Window = breakdown-p2-vlm-window-context-segment-index-zh-v4
Exact-Shot = breakdown-p2-vlm-exact-shot-compact-reconstruction-zh-v3
Fusion = breakdown-p2-fusion-episode-context-e6-v1
Pipeline = breakdown-p2-full-v1
```

## 3. Core semantic boundaries

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
```

Window Context only provides Scene/anonymous continuity. Exact-Shot owns current-Shot visible truth.
ASR owns dialogue text truth. OCR owns visible text evidence.

## 4. Window v4 accepted truth

Real Window-only diagnostic:

```text
4/4 READY
Window Context total = 41.920s
tokens = 233..304 / 1600
0 MAXED
0 JSON truncation
0 range errors
```

The model emits Window-local 1-based indexes only; host code maps them to frozen Shot ordinal and
revision_item_id.

## 5. Exact-Shot compact v3 accepted truth

Original selected batches were ~85..97s and ~2158..2374 tokens per 5-Shot batch. Compact v2 proved
performance but lost Shot1 structured props. Reconstruction-safe v3 fixed that regression.

User-local targeted tests:

```text
3/3 PASS
```

Real selected-batch v3 diagnostic:

```text
batch 1 | 10 frames | 36.421s |  993/4096 | READY
batch 4 | 10 frames | 58.451s | 1055/4096 | READY
batch 6 | 11 frames | 44.921s | 1061/4096 | READY
```

Shot1:

```text
subjects=0
props include 蓝色玫瑰花束 + 玻璃花瓶
```

Reconstruction rule:

```text
画面中显著、可独立识别、后续重建需要保留的物体必须进入 props，
即使没有人物与其互动。
```

Host restores canonical fields:

```text
revision_item_id <- frozen manifest
subject_A/B <- current-Shot people order
summary/visual_description <- visible
speaking_state=UNKNOWN
camera_motion_hint=UNKNOWN for static sampled frames
events=[] with Fusion summary fallback
```

## 6. E6 anonymous continuity

```text
subject_A/B = Shot-local labels only
same-Shot observations = hard cannot-link
explicit gender conflict blocks soft union
explicit long-vs-short hair conflict blocks soft union
missing attribute is not conflict
action/expression/pose/speaking/framing are not identity keys
```

Fresh E6 baseline:

```text
Scenes=2
Scene1 Shots 1-12 / 公寓走廊 / LocalSubjects=2
Scene2 Shots 13-30 / 客厅 / LocalSubjects=2
same_shot_cluster_conflicts=0
Shot0001 subjects=0
```

## 7. Character V10.1 protected baseline

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

## 8. Testing / CI discipline

User-reported local PASS evidence:

```text
12/12 E6/v3 Fusion targeted tests
3/3 Exact-Shot compact-v3 targeted tests
Window v4 real diagnostic 4/4 READY
Exact-Shot v3 real selected batches 1/4/6 READY
```

Do not claim assistant-local pytest/CUDA PASS. Do not consume hosted GitHub Actions quota. Use
`[skip ci]`.

## 9. Immediate safe work

```text
git pull
→ run production-routing regression tests
→ if green, run exactly one fresh full production Breakdown
→ inspect G1 quality + VLM performance
→ require Window v4 + Exact-Shot v3 + E6
→ require Scenes ~=2 and anonymous cast ~=2 per real Scene
→ require same_shot_cluster_conflicts=0
→ require Shot0001 subjects=0 and roses/vase props
→ require whole-run <30min
→ if all pass, stop G1 tuning and review P2.6 final PASS
→ only then start G2 / Scene Timeline
```
