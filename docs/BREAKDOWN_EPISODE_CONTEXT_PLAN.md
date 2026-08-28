# AI Drama Studio — 整集上下文拉片 / Episode-context Breakdown

> **Status:** ACCEPTED TARGET / P2-E1 IMPLEMENTED ON MAIN / LOCAL-REAL ACCEPTANCE PENDING  
> **Accepted:** 2026-08-28  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Architecture:** Reference Video V2 / Breakdown-first / Character V10.1

## 1. 为什么要改

用户在真实短剧拉片中确认了两个结构性问题：

1. 一句对白跨过切镜点时，旧 Fusion 会按 Shot 边界把一句话拆成多段，导致拉片文案不自然；
2. 同一场景里的特写、背影、插入镜头或虚化背景镜头缺少环境信息时，旧逐 Shot 场景签名会把同一场景拆成多个 Scene Segment。

当前代码根因：

```text
ASR = 已经是整集音频时间轴
VLM = 每个 Reference Clip 独立分析
Fusion Scene = 当前 Shot signature 缺失/变化就可能切 Scene
Fusion Dialogue = ASR segment 按 Shot 边界切文本
```

因此正式产品原则调整为：

> **Shot 是拉片结果的最小展示单位，不是 AI 理解内容的上下文边界。**

## 2. 新的目标流程

```text
Episode 原视频 / proxy / audio
        ↓
Shot Detection + ShotRevision
只提供精确切镜时间坐标
        ↓
Episode ASR
完整对白时间轴，不按 Shot 改写原句
        ↓
Episode OCR timeline
        ↓
连续视频理解（overlapping windows）
        ↓
Scene continuity / Episode context
        ↓
Shot contextual refinement
Scene + Previous + Current + Next + ASR + OCR
        ↓
Episode-context Fusion
        ↓
SceneSegmentDraft / ShotSemanticDraft / LocalSubject / TimelineEvent
        ↓
03 资产专用 Evidence 验证
        ↓
Final Asset / Binding
```

## 3. 不变的边界

以下已有结构继续作为正式基线，不推倒：

```text
FFprobe / FFmpeg
TransNetV2 Shot boundaries
integer microseconds
ShotRevision / ShotRevisionItem
Reference Clip / thumbnail / keyframes
immutable P2 Evidence sidecars
P1 Draft tables / lifecycle
Character V10.1 hard identity gates
Final Scene/Prop visual verification gates
```

仍然严格禁止：

```text
LocalSubject == Character
SceneSegmentDraft == Final Scene
DraftPropHint == Final Prop
ASR speaker == Character
VLM prose bypassing Final Asset evidence
```

历史 BreakdownRun / sidecar 不重写。新策略只作用于新创建并重新运行的 BreakdownRun。

## 4. P2-E1 — Episode-context Fusion

### 状态

```text
IMPLEMENTED ON MAIN
local-real acceptance = PENDING
```

正式模块：

```text
engine/app/breakdown_p2_fusion_episode_v2.py
profile = breakdown-p2-fusion-episode-context-e1-v2
```

生产 orchestrator 已从：

```text
breakdown_p2_fusion_v1
```

切换到：

```text
breakdown_p2_fusion_episode_v2
```

`breakdown-p2-full-v1` 顶层 pipeline profile 暂时保持不变，避免无意义破坏 API / Run Contract；具体 Fusion 子 profile 在 provenance 中记录新版本。

### 4.1 Scene continuity

旧逻辑：

```text
当前 Shot scene signature 不存在
或与上一 Shot 不完全相同
→ 新 Scene Segment
```

E1：

```text
明确地点
→ 当前 Scene anchor

特写 / 虚化 / UNKNOWN / “室内” / “房间”等弱提示
→ 继承当前 Scene

兼容的更具体地点
病房 → 医院病房
客厅 → 家中客厅
→ 仍然同一 Scene，并升级 anchor 描述

明确地点冲突
客厅 → 医院走廊
或明确 INT ↔ EXT 冲突
→ 新 Scene Segment
```

E1 使用“宁可暂时少切 Scene，也不要因为信息不足误切 Scene”的保守策略。连续窗口 VLM 到位后，P2-E2/E4 会提供更强的换场证据。

### 4.2 Dialogue truth

正式真值：

```text
ASR_SEGMENT = 一句/一段对白的 Episode-time text truth
```

Shot-local `TimelineEvent(DIALOGUE)` 的角色改为：

```text
ASR Segment 在某个 Shot 上的时间投影
!= 对白文本真值本身
```

例如：

```text
ASR Segment
00:10.200 → 00:12.800
“你怎么现在才回来？”

Shot 005
00:09.500 → 00:11.300

Shot 006
00:11.300 → 00:13.100
```

E1 输出：

```text
Shot 005 projection
text = “你怎么现在才回来？”
dialogue_group_id = same ASR segment id
continues_to_next_shot = true

Shot 006 projection
text = “你怎么现在才回来？”
dialogue_group_id = same ASR segment id
continues_from_previous_shot = true
```

而不是：

```text
Shot 005 = “你怎么现在”
Shot 006 = “才回来？”
```

ASR_WORD 仍保留为 immutable raw Evidence，并重新挂回每个 Shot projection 作为 SUPPORT provenance / confidence evidence。

### 4.3 E1 数据兼容策略

P1 当前 `TimelineEvent` 必须属于一个 `shot_draft_id`。E1 不为此立刻做破坏性数据库迁移，而是通过 metadata 表达跨 Shot Dialogue Group：

```text
dialogue_group_id
asr_segment_id
dialogue_source_start_us
dialogue_source_end_us
projection_start_us
projection_end_us
projection_index
projection_count
continues_from_previous_shot
continues_to_next_shot
```

这样可以先修真实产品错误，又保留现有 P1 / P3 / P4 Contract。

## 5. P2-E2 — 连续窗口 VLM

### 状态

```text
PLANNED / NOT IMPLEMENTED
```

当前 Qwen3-VL 仍然逐 Reference Clip 分析；E1 只是让 Fusion 不再把“看不出来”误判成“换场”。

E2 目标：逻辑上整集理解，模型执行采用重叠连续窗口，避免一次把整集视频塞进显存。

建议默认策略：

```text
window duration ≈ 20–40 秒
window overlap ≈ 20–35%
保留 exact Episode source-us
每个 window 携带所覆盖的 Shot boundaries
按 Episode 顺序串行推理
```

窗口模型输出至少包含：

```text
window summary
scene continuity / scene change candidates
anonymous subject continuity hints
key actions
prop continuity hints
shot-aware semantic observations
```

E2 不能输出 Final Character / Scene / Prop ID。

## 6. P2-E3 — Shot contextual refinement

### 状态

```text
PLANNED
```

每个 Shot 的精细描述不再只看自己，而是使用：

```text
Current Scene context
+ Previous Shot
+ Current Shot
+ Next Shot
+ overlapping Episode ASR
+ overlapping OCR
+ window-level visual context
```

目标是准确生成用户最终真正关心的：

```text
镜头画面
人物/匿名主体 presence
动作
对白投影
关键道具
景别
运镜
叙事作用
```

## 7. P2-E4 — Final Episode-context Fusion

### 状态

```text
PLANNED
```

E4 将以连续窗口 Evidence 为主，E1 的规则变成保守 fallback：

```text
Scene = Episode-time range spanning multiple Shots
Dialogue = Episode-time range spanning one or more Shots
LocalSubject = Scene/window scoped anonymous continuity
Shot = 上述信息在切镜区间内的展示/检索投影
```

关键原则：

```text
看不出来 != 换场
切镜 != 对白断句
人物暂时出画 != 人物从剧情上下文消失
Shot boundary != semantic context boundary
```

## 8. 当前生产真值

截至本文件同步时：

```text
Shot Detection                    = existing Reference Video V2
ASR                               = Episode-level, existing
OCR                               = current provider, existing
VLM                               = single-Reference-Clip, still current limitation
Fusion                            = P2-E1 Episode-context Fusion v2
P2-E2 continuous-window VLM       = NOT IMPLEMENTED
P2-E3 contextual shot refinement  = NOT IMPLEMENTED
P2-E4 final Episode Fusion        = NOT IMPLEMENTED
P2.6 real-model acceptance        = NOT PASSED
```

因此禁止对外描述为“整集连续 VLM 拉片已经完成”。准确说法是：

> **整集上下文迁移已经开始，E1 场景连续性与跨镜对白 Fusion 已落地；连续窗口视觉理解仍是下一阶段。**

## 9. 验收重点

P2-E1 本地真实短剧验收至少检查：

```text
1. 一句对白跨 2+ 镜头时，文本不能被切成残句
2. 所有投影拥有同一 dialogue_group_id
3. Scene 大全景 → 人物特写 → 插入镜头 → 特写，不应因为背景不足自动换场
4. 明确从客厅切到医院/街道等，应创建新 Scene Segment
5. ASR_WORD / VLM_OUTPUT sidecar fingerprint 与 raw Evidence 不被重写
6. P1 validator / lifecycle / STALE behavior 不退化
7. Character V10.1 / Final Asset tables 不被 E1 写入
```

P2-E1 真实素材通过后，再进入 P2-E2 连续窗口 VLM；P5 Character safe integration 在新的 Episode-context semantic baseline 稳定前暂停推进。
