# Breakdown P2 — 本地生产运行与真实短剧验收

> Status: **P2.6 PASS / G1 REAL ACCEPTED / FROZEN**  
> Date: 2026-08-31  
> Production pipeline: `breakdown-p2-full-v1`  
> Production G1 VLM: `breakdown-p2-vlm-fast-grounded-v1`  
> Production Fusion: `breakdown-p2-fusion-episode-context-e6-v2`  
> Legacy E3/E4/E5 and E6-v1: rollback/historical only where documented

## 1. 最终验收结论

```text
P1/P2 实现验收                         = CONDITIONAL PASS
Fast Grounded G1                       = REAL ACCEPTED / PRODUCTION / FROZEN
Window Segment-index v4                = REAL ACCEPTED / FROZEN
Exact-Shot Compact-reconstruction v3   = REAL ACCEPTED / FROZEN
P2-E6-v2 Episode-context Fusion        = REAL PRODUCTION ACCEPTED / FROZEN
P2.6 Windows / 真实模型验收             = PASS
G2 Scene-level text LLM                = UNBLOCKED / NOT IMPLEMENTED
Scene Timeline UI                      = UNBLOCKED / NOT IMPLEMENTED
```

G1 不再继续调参。只有出现新的、可复现的真实回归时才允许重新打开对应层。

## 2. 最终真实生产 Run

```text
Run = BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
Episode = EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
ShotRevision = SHOTREV_1462ac6d9f3948b994fc9bc575fee3a0
Shots = 30
status = READY
is_current = true
started_at = 2026-08-31T06:57:22.353834
completed_at = 2026-08-31T07:11:23.392582
whole run ~= 841.039s = 14.017 min
```

Provider timings:

```text
ASR = 15.275958s
OCR = 264.916802s
VLM = 559.267248s
```

Runtime gate:

```text
<30 min = PASS
<=20 min = PASS
```

## 3. 最终生产链

```text
Episode Current ShotRevision
→ frozen BreakdownRun
→ Episode ASR
→ OCR
→ one-load Qwen3-VL Fast Grounded
   ├─ Window Segment-index v4
   │    24s / 25% overlap / 1 FPS / 262144 max pixels
   └─ Exact-Shot Compact-reconstruction v3
        <1.2s -> 1 frame
        1.2..3s -> 2 frames
        >3s -> 3 frames
        5 Shots/batch
        524288 max pixels
        current-Shot visible facts only
→ immutable VLM_OUTPUT sidecar
→ E6-v2 Episode-context Fusion
   ├─ accepted Scene policy
   ├─ ASR_SEGMENT dialogue truth
   └─ compact-safe anonymous continuity
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

## 4. Window / Exact-Shot 验收

Final Run:

```text
Window Context total = 84.3492s
Window count = 4
4/4 READY
0 failed Window

Exact-Shot total = 455.284273s
Grounding batches = 6
6/6 READY
0 failed grounding
0 missing Shot semantics
58 grounding frames
10 generation attempts
0 MAXED
```

Window output tokens:

```text
276 / 304 / 237 / 233 out of 1600
```

Exact-Shot output tokens:

```text
993 / 763 / 1027 / 1055 / 1088 / 1061 out of 4096
```

## 5. Shot0001 Exact-Shot 验收

真实素材 Shot0001 是蓝色玫瑰 / 玻璃花瓶特写。

Final Run：

```text
subjects=[]
summary=蓝色玫瑰花束在玻璃花瓶中
visual_description=蓝色玫瑰花束在玻璃花瓶中
props include:
- 蓝色玫瑰花束
- 玻璃花瓶
- 遥控器
- 书本
neighbor woman leakage = NO
```

结论：**PASS**。

## 6. Scene 连续性验收

Final Run：

```text
Scene count = 2
Scene1 = Shots 1-12  | 公寓走廊 | INTERIOR / DAY
Scene2 = Shots 13-30 | 客厅     | INTERIOR / DAY
```

结论：**PASS**。

历史 4-Scene / Scene04 结果不再是 CURRENT truth。

## 7. 匿名人物连续性验收

Final Fusion provenance：

```text
profile = breakdown-p2-fusion-episode-context-e6-v2
window_hint_resolution_policy = window-hint-positive-appearance-support-compact-alias-v2
compact_appearance_policy = compact-observation-stable-alias-normalization-v1
same_shot_cannot_link = hard
promotion_source = g1-read-only-replay-v5-real-accepted
```

Final counts：

```text
observation_count = 46
cluster_count = 4
merged_cluster_count = 4
local_subject = 4
Scene1 LocalSubjects = 2
Scene2 LocalSubjects = 2
final_same_shot_conflict_count = 0
```

结论：**PASS**。

注意：

```text
LocalSubject != Character
subject_A/B = Shot-local observation labels only
Window subject hint != Character identity
```

## 8. Dialogue / OCR truth

```text
ASR_SEGMENT = Episode-time dialogue text truth
Shot DIALOGUE TimelineEvent = projection
OCR = visible text evidence only
```

ASR / OCR 不允许直接定义 Character identity。

OCR 仍可能包含短字/环境文字噪声，这不阻塞 P2.6，因为它没有污染本轮 Scene/anonymous-subject/Shot0001 核心真相。后续 UI/G2 应默认隐藏调试型 OCR 噪声，而不是把它作为主结果展示。

## 9. Identity / Final Asset 禁止事项

```text
LocalSubject != Character
subject continuity hint != ReID evidence
ASR speaker != Character
Draft Scene/Prop != Final Scene/Prop
```

Character V10.1 保持：

```text
YOLOX Person Detection
→ capture-first Person Evidence
→ mature MOT
→ YoutuReID project identity
→ RESOLVED / UNRESOLVED
→ explicit Shot × known-Character Assignment
→ Final Character Gate
```

不得因为 Breakdown 已经得到稳定匿名人物就放宽 Character V10.1 的 same-sample cannot-link、face hard conflict、>=3 independent evidence、ambiguity、explicit Shot assignment 或 Final Gate。

## 10. P2.6 PASS 门

最终全部满足：

```text
Fusion=e6-v2                         PASS
Window=v4                            PASS
Exact-Shot=v3                        PASS
Scenes=2                             PASS
Scene1 LocalSubjects=2               PASS
Scene2 LocalSubjects=2               PASS
same-Shot conflicts=0                PASS
Shot0001 subjects=0                  PASS
Shot0001 blue roses + glass vase     PASS
whole-run <30min                     PASS
whole-run <=20min                    PASS
```

**P2.6 = PASS。**

## 11. G1 冻结规则

以下内容现在冻结：

```text
Window v4 Prompt/adapter/inference parameters
Exact-Shot compact v3 Prompt/adapter/inference parameters
E6-v2 Scene policy
E6-v2 Stage1 evidence-gated hint resolver
E6-v2 compact appearance normalization
E6-v2 Stage2/3/4 thresholds
same-Shot hard cannot-link
```

没有真实回归证据，不允许为了“再快一点/再像一点”继续修改 G1。

## 12. 下一阶段：G2 / Scene Timeline

G2 现在正式解锁。

输入：

```text
SceneSegmentDraft
ShotSemanticDraft
ASR_SEGMENT truth
OCR evidence
LocalSubject anonymous continuity
DraftPropHint / PropOccurrence
```

目标：

```text
Scene
→ 场景概览
→ 出场匿名人物
→ 按时间排列的 Shot
→ 每 Shot 画面描述 / 动作 / 景别 / 构图
→ 对白
→ 重建需要的道具
→ 必要时 Scene-level readable summary
```

原则：

```text
先确定结构化 Scene Timeline contract
再做 deterministic assembler
再考虑纯文本 LLM 润色/组织
最后做用户主结果 UI
```

G2 不负责重新看视频，也不能覆盖 G1 Exact-Shot/ASR/OCR 的证据真相。

## 13. UI 验收方向

主结果应直接让用户看到：

```text
Scene -> Shot -> 人物/动作 -> 对白 -> 道具 -> 画面描述
```

默认不要把下列调试信息堆在主界面：

```text
Evidence link ID
fingerprint
provider metadata
raw OCR noise
cluster bridge internals
subject_A/B internal labels
confidence/debug policy strings
```

这些内容可以保留在调试/详情层，但不是用户拉片结果的主要阅读界面。

## 14. 测试 / CI

本次 PASS 来自用户本地真实生产 Run，不是 hosted CI。不要声称 assistant-local pytest/CUDA 运行。Hosted GitHub Actions 不使用，提交继续使用 `[skip ci]`。
