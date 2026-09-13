# 复刻短剧 Root Skill

## 目标
把已经验证好看的原短剧换成目标地区的人物、语言和世界重新拍一遍。

## 不可突破的规则
- 故事不乱改，节奏不重做，文化和表达才本土化。
- 必须先完成整集理解，再做逐镜语义拉片。
- P10 `SOURCE_VIDEO_SNAPSHOT` 是 Target 阶段唯一当前 Source 世界版本锚点；Target 不得绕过 Snapshot 自行拼装当前 Source Facts。
- P11 只建立 `ADAPTATION_PLAN + TARGET_BIBLE`；P12 只到 Final Target Dialogue；P13 只做 Target Character / Scene / Prop 视觉身份实现。
- P13 正式硬输入只有 CURRENT `TARGET_BIBLE`；`TARGET_ASSETS = AVAILABLE` 已经由真实人工验收确认。
- 对白链固定为 `Source Dialogue → Translation → Localization → Final Target Dialogue → Target Voice → TTS → Actual Speech Duration → Timing Plan`。
- P14 正式拆成 `target_audio` 与 `dialogue_timing` 两个内部 step，产品阶段统一为“配音与时序”。
- P14 Target Audio 硬输入只有 CURRENT `TARGET_SCRIPT + TARGET_BIBLE` 与用户显式 voice binding；`TARGET_ASSETS` 不是硬输入。
- 已知 `target_character_id` 可用 CHARACTER voice binding；未知人物对白必须显式使用 UTTERANCE binding，禁止猜默认 narrator。
- 每条外部 TTS 调用必须先持久化 ProviderJob；Provider 不得改写 Final Target Dialogue，也不得决定正式 Artifact id/revision。
- `actual_speech_duration_us` 唯一权威来源是服务端对已持久化真实音频的 ffprobe；Provider duration、字数估算、前端计时和人工填写都不是正式事实。
- Target Audio Task succeeded 只产生 `NEEDS_REVIEW` candidate；人工听审 ACCEPT 后才发布 CURRENT `TARGET_AUDIO`。
- P14 Timing 硬输入只有 CURRENT `TARGET_SCRIPT + TARGET_AUDIO`；完全确定性执行，不调用 Provider、不创建 ProviderJob。
- Timing 只做原对白 slot conformance：短于 slot 保留 residual hold；长于 slot 标记 OVERFLOW。存在任何 OVERFLOW 时禁止 ACCEPT 正式 `TIMING_PLAN`。
- P14 v1 不静默改写对白、不压缩/变速音频、不拉伸 Shot、不重排视觉节奏、不使用未来 Storyboard slack。
- Target / Production 不得反向写入 Source；上游新 revision 必须按 Artifact Graph 正确使依赖结果 STALE。
- 未经过生成质检与正式选择的尝试不能进入后期。

## 正式顺序
原片 → 证据 → 整集理解 → 故事骨架 / 节奏骨架 → 逐镜拉片与角色 / 场景 / 道具归一 → 原片分析定稿 → **目标设定** → **目标剧本 / 对白** → **目标资产** → **目标配音（真实媒体 + Actual Speech Duration）** → **对白时序** → 复刻分镜 → 视频生成与选择 → 口型 / 字幕 / 剪辑 → 成片。

## P11 目标设定
P11 读取且只锚定 CURRENT `SOURCE_VIDEO_SNAPSHOT`，确定性锁定故事与节奏 preservation locks，建立目标地区人物、场景、道具、世界、表达策略和 visual continuity。

正式状态：

```text
LOCALIZATION = AVAILABLE
TARGET_BIBLE = AVAILABLE
```

## P12 目标剧本 / 本土化
P12 同时读取 CURRENT Snapshot、Adaptation Plan、Target Bible，只允许针对已有 canonical utterance 输出 `translation_text / localization_text / final_target_dialogue`。Source Speaker → Source Character → Target Character lineage 无法证明时保持空，不让模型猜。

正式状态：

```text
TARGET_SCRIPT = AVAILABLE
```

## P13 目标资产
P13 合同见 `docs/28`、`docs/29`、`docs/30`，最终验收见 `docs/31_P13最终验收与P14准入评估.md`。

```text
replica-target-assets@1.1.0
p13-replica-target-assets-v3
replica-target-visual-identity-v2
TARGET_ASSETS = AVAILABLE
```

P13 只读取 CURRENT `TARGET_BIBLE`，把既有 Target Character / Scene / Prop semantic truth 具体化为跨镜稳定视觉身份包。Provider 成功只产生候选，用户显式 ACCEPT 后才发布正式资产。

## P14 目标配音与对白时序
正式合同见 `docs/32_P14目标配音与对白时序ProfessionalSkill与数据契约.md`。

### P14A Target Audio

```text
Professional Skill: replica-target-audio@1.0.0
hard inputs: CURRENT TARGET_SCRIPT + CURRENT TARGET_BIBLE + explicit voice bindings
capability: TTS
output: TARGET_AUDIO
namespace: PRODUCTION
```

一条 canonical target utterance 对应一条真实音频 clip 和独立 ProviderJob provenance。媒体落盘后服务端探测真实时长；候选必须人工听审。

### P14B Dialogue Timing

```text
Professional Skill: replica-dialogue-timing@1.0.0
hard inputs: CURRENT TARGET_SCRIPT + CURRENT TARGET_AUDIO
capability: TIMING
output: TIMING_PLAN
namespace: PRODUCTION
```

逐句计算：

```text
source_slot_duration_us = source_end_us - source_start_us
planned_speech_start_us = source_start_us
planned_speech_end_us = source_start_us + actual_speech_duration_us
residual_hold_us = max(0, source_slot_duration_us - actual_speech_duration_us)
overflow_us = max(0, actual_speech_duration_us - source_slot_duration_us)
```

有 overflow 只能返回 TTS 重录/换 voice/调整 provider 支持的自然语速，或回到 P12 修改 Final Target Dialogue；当前 P14 不替 Storyboard 做视觉时长重排。

### Artifact Graph

```text
TARGET_SCRIPT --DERIVED_FROM--> TARGET_AUDIO
TARGET_BIBLE  --USES----------> TARGET_AUDIO
TARGET_AUDIO  --DERIVED_FROM--> TIMING_PLAN
TARGET_SCRIPT --USES----------> TIMING_PLAN
```

Target Script 新 revision 会递归 stale Target Audio / Timing；Target Bible 新 revision stale Target Audio 并继续 stale Timing；Target Audio 新 revision stale Timing；Target Assets revision 不 stale P14。

### 当前准入状态
P14 合同和工程实现可以存在，但在真实 TTS Provider、真实媒体、逐句人工听审、Timing 人工审核和用户明确 `P14 PASS` 前：

```text
TTS = PLANNED
TIMING = PLANNED
P14 PASS = NO
```

## P15 复刻分镜 / Generation Segments

正式合同见 `docs/49_P15ReplicaStoryboard与GenerationSegments数据契约.md`。P15 不调用自由创作 Provider，确定性继承 CURRENT Source Snapshot 的 Shot 顺序、authoritative timing 与 camera language，把 CURRENT Target Bible / Script / Assets / Audio / Timing 编译成 `TARGET_STORYBOARD + GENERATION_SEGMENTS` candidate。显式 ACCEPT 后才原子发布正式两个 Artifact。

## P16 视频生成 / QC / Selection

正式合同见 `docs/50_P16VideoGenerationQCSelection数据契约.md`。每个 MiniMax H3 GenerationAttempt 请求前先持久化 ProviderJob，远程视频必须下载本地、SHA256 + ffprobe。Technical QC 只判断媒体技术可用，不冒充人物/动作/连续性语义审核。每个 Segment 的正式 selected attempt 必须由用户显式确认后才发布 `GENERATED_VIDEO + GENERATION_SELECTION`。

## P17 Lip Sync / Post / Final Output

正式合同见 `docs/51_P17PostProductionFinalOutput数据契约.md`。只消费 CURRENT `GENERATION_SELECTION + TARGET_AUDIO + TARGET_SCRIPT + TIMING_PLAN`。需要可见口型的正式 segment 才调用 Lip Sync Runtime；随后按 authoritative segment timing trim/pad/concat，丢弃生成视频未知音轨，只混入正式 Target Audio；SRT 只来自 Target Script + Timing。Task 成功只产生待审核成片，用户显式 ACCEPT 后才发布 `FINAL_OUTPUT`。

## 当前 P14-P17 准入状态

这些阶段现在可以有完整工程合同、代码和自动测试，但在统一真实项目端到端、真实 TTS/H3/Lip Sync Runtime 与用户人工验收结束前：

```text
TTS = PLANNED
TIMING = PLANNED
STORYBOARD = PLANNED
VIDEO_GENERATION = PLANNED
QC_SELECTION = PLANNED
LIP_SYNC = PLANNED
POST_PRODUCTION = PLANNED
P14-P17 PASS = NO
```

## 需要用户决策
故事/节奏偏离、核心关系改变、P13 视觉身份候选、P14 voice binding、P14 音频听审、Timing overflow 解决方式、P15 分镜确认、P16 正式选片以及 P17 最终成片确认都属于显式用户决策边界。

## 完成标准
Source / Target / Production lineage 清晰；P11~P13 正式结果保持既有验收状态；P14 每条目标对白有真实音频、可验证 SHA、服务端实际时长和 voice provenance；Timing 完整覆盖且正式版本无 unresolved overflow；P15 正式分镜和生成分段可追溯；P16 正式 Selection 只引用 Technical QC PASS 的本地视频；P17 成片严格使用正式视频选择、Target Audio、Target Script 与 Timing。工程完成仍不等于 P14-P17 真实人工 PASS。
