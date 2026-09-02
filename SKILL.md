---
name: ai-drama-studio-localized-remake-v2
version: 6.0.0
description: AI 短剧本土化重做项目当前规则入口，使用本地 MiniMax H3 完成原片理解、目标版本设计、重拍、质检和成片。
---

# AI Drama Studio — 当前项目技能规则

## 1. 读取顺序

开始任何项目任务前先读：

```text
docs/00_短剧重做系统开发总纲.md
→ docs/01_十个模块详细设计.md
→ docs/02_工作流V2技术实现规范.md
→ docs/03_当前项目状态与验收.md
→ AGENTS.md
→ 相关当前代码和测试
```

历史文档规则见：

```text
docs/99_历史文档说明.md
```

旧 Breakdown / Character / P/R/G 阶段文档仅用于回归和理解历史实现，不能覆盖当前中文正式文档。

## 2. 项目目标

```text
原短剧
→ 拆镜头
→ 看懂剧情/人物/动作/镜头/对白
→ Final Character / Scene / Prop / Speaker
→ SourceDramaSnapshot
→ TargetCharacter / TargetScene / Voice
→ TargetDialogue / TTS / 真实语音时长
→ RemakeTimeline
→ GenerationSegment
→ Local MiniMax H3
→ QC / Retry / GenerationSelection
→ Lip Sync / 目标音轨 / 字幕 / 安全背景
→ EpisodeOutput
→ 人工看听验收
```

普通用户正式工作区只有：

```text
Project
Review Center
Output
```

内部算法、Evidence、GenerationSegment、H3 Context、QC、Lip Sync、Audio Separation 默认不做顶层页面。

## 3. 10 个业务模块

```text
1. 创建项目
2. 拆分原片
3. 看懂原片
4. 整理原片人物和场景
5. 固化原片事实
6. 设计目标版本
7. 生成目标对白和声音
8. 重排时间并准备生成
9. H3 重拍与质检
10. 后期和成片
```

开发新功能必须先说明属于哪个模块、输入是什么、正式输出是什么、下游怎么消费、完成条件是什么。

## 4. 当前最重要的数据边界

### SourceDramaSnapshot

模块 6—10 唯一原片正式事实入口。

源 ASR / OCR / Shot facts 下游只读。

### 人物

```text
Face / Detection != Character
Track != Character
LocalSubject != Final Character
Final Character != TargetCharacter
```

Character V10.1 保持 fail-closed，不为了减少人工问题降低身份门槛。

### 对白

```text
SourceDialogueUtterance 1:N ShotDialogueProjection
```

一条完整对白跨多个 Shot，只保存一条完整业务对白，Shot 只保存投影和 offset。

TargetDialogue 按完整 dialogue group 生成，不按 Shot 投影复制。

## 5. 目标对白和时间规则

顺序固定：

```text
翻译
→ 本土化
→ 最终目标台词
→ Target Speaker / Voice
→ TTS
→ 真实 speech duration
→ RemakeTimeline
→ GenerationSegment
```

禁止把目标语言硬塞进原片时长。

禁止先估算最终时长再把真实 TTS 强制适配进去。

可用时间策略包括：

```text
KEEP
TRIM
CARRY_OVER_REACTION
EXTEND
HUMAN_REVIEW
```

## 6. H3 规则

```text
Shot != GenerationSegment
GenerationAttempt != Selected Output
```

当前生成边界：

```text
业务层
→ VideoGenerationProvider
→ MiniMaxH3Provider
→ H3RuntimeManager
→ local SGLang
```

H3 当前生成窗口：

```text
4..15 秒
```

源 Reference Video 用于导演参考，必须去掉源音轨；Target TTS 是目标音频条件。

### QC

```text
GenerationAttempt
→ ffprobe
→ full ffmpeg decode
→ duration gate
→ Qwen3-VL semantic QC
→ PASS / RETRY / REVIEW
→ GenerationSelection
```

只有 GenerationSelection 能进入后期。

结构失败不能人工绕过；语义失败有限重试，禁止无限循环。

## 7. 后期规则

```text
GenerationSelection
→ PostProductionSegment
→ EpisodeOutput
```

口型：

- 画外对白跳过 mouth edit；
- 单说话人可整段 LatentSync；
- 多脸必须先确认 Target Speaker identity，再做 ROI Lip Sync；
- 模型离线是 WAITING_RUNTIME；
- 身份不确定才是 LIP_SYNC_QC。

音频硬规则：

```text
raw source audio 不能直接混入目标成片
```

安全背景流程：

```text
源音频
→ separator
→ SourceDramaSnapshot dialogue windows 再次硬抑制
→ 目标时间映射
→ conservative mix / duck / limiter
```

背景音失败时保留目标对白-only有效输出，不阻塞 Episode。

## 8. Workflow V2 状态

阶段分开记录：

```text
Validity
Readiness
Execution
```

只有：

```text
Validity = CURRENT
Readiness = READY
```

才可下游消费。

`Execution = SUCCEEDED` 不等于业务完成。

上游 fingerprint 改变时，下游旧结果保留历史，但必须 STALE / SUPERSEDED，不能继续当 current。

## 9. 页面和任务

页面打开、刷新、切换：只 GET。

GET：

- 不写业务数据；
- 不创建 Task；
- 不关闭 Review Case；
- 不启动模型；
- 不隐式重算。

重任务：只有用户明确点击后才 POST。

任务必须服务端幂等，并逐步支持：

- Idempotency-Key；
- expected workflow revision；
- input fingerprint；
- checkpoint；
- heartbeat；
- retry limit；
- interrupted resume；
- current result reuse。

任务完成只刷新状态，不自动启动下一项重任务。

## 10. Review Center

人工审核只处理系统无法安全决定的**根问题**。

一个人物影响很多 Shot/对白时，只创建一个人物 Case；下游显示被阻塞。

人工处理必须：

```text
写正式业务对象
→ Validator
→ 阻塞消失
→ Case RESOLVED
```

不能只把提醒设为 resolved。

Runtime offline 不创建人工内容 Case。

## 11. 当前开发优先级

```text
P0 停止页面隐式任务 / GET 写入 / stale 误计数
P1 对白组+投影 / Person Mapping / Snapshot V2 / ReviewCase / FlowState
P2 只读 Validator
P3 幂等 + checkpoint + heartbeat + resume
P4 前端统一 Workflow Snapshot
P5 当前真实项目迁移 + 本地端到端验收
```

不要在 P0/P1 未收口时继续增加新的推测性后续业务层。

## 12. 验收纪律

必须分开记录：

```text
代码是否实现
仓库测试是否通过
本地模型是否真实可用
真实项目是否真正跑通
用户是否真实看听并验收
```

不能用其中一种替代另一种。

当前事实以 `docs/03_当前项目状态与验收.md` 为准。