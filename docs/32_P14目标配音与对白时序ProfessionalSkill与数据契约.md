# P14 目标配音与对白时序 Professional Skill 与数据契约

> 日期：2026-09-12  
> 状态：P14 正式合同已建立并进入工程实现；真实 Provider / 真实音频 / 人工听审尚未完成，因此 `TTS = PLANNED`、`TIMING = PLANNED`。

## 1. 阶段定义

P14 正式名称：**目标配音与对白时序 / Target Voice Binding, TTS & Dialogue Timing**。

P14 是一个产品阶段，内部拆为两个严格顺序的能力：

1. `target_audio` / `replica-target-audio@1.0.0` / Capability `TTS` / 输出 `TARGET_AUDIO`；
2. `dialogue_timing` / `replica-dialogue-timing@1.0.0` / Capability `TIMING` / 输出 `TIMING_PLAN`。

Root phase 固定为 `配音与时序`。未来 `replica_storyboard` 继续属于 `分镜`，防止未来 Storyboard capability 未准入时错误阻塞 P14 产品阶段展示。

## 2. P14A Target Audio

硬输入：

```text
CURRENT TARGET_SCRIPT
CURRENT TARGET_BIBLE
explicit voice bindings
```

`TARGET_ASSETS` 不是硬输入。P13 是视觉实现，不能为 P14 制造错误 STALE 耦合。

`TARGET_SCRIPT` 提供 Final Target Dialogue、utterance id、source slot 与 target_character_id；`TARGET_BIBLE` 提供目标人物身份语义。已绑定人物可使用 CHARACTER voice binding；`target_character_id = null` 必须使用 UTTERANCE binding，不得猜 narrator。

每条外部 TTS 调用必须先持久化 ProviderJob。Provider 只负责真实音频合成，不得拥有 Artifact id/revision、修改 Final Target Dialogue 或决定正式时长。

Actual Speech Duration 权威来源唯一固定为：**服务端对已持久化真实音频执行 ffprobe，得到整数微秒。** Provider duration、字数估算、前端计时或人工填写都不是正式事实。

Task succeeded 只产生 `NEEDS_REVIEW` candidate。人工听审显式 ACCEPT 后才发布 CURRENT `TARGET_AUDIO`。ACCEPT 前服务端必须再次验证媒体存在且 SHA256 一致。

## 3. P14B Dialogue Timing

硬输入：

```text
CURRENT TARGET_SCRIPT
CURRENT TARGET_AUDIO
```

本能力完全确定性，不调用 Provider、不创建 ProviderJob。

逐句规则：

```text
source_slot_duration_us = source_end_us - source_start_us
planned_speech_start_us = source_start_us
planned_speech_end_us = source_start_us + actual_speech_duration_us
residual_hold_us = max(0, source_slot_duration_us - actual_speech_duration_us)
overflow_us = max(0, actual_speech_duration_us - source_slot_duration_us)
```

`overflow_us > 0` 时状态为 `OVERFLOW`。候选允许展示，但正式 ACCEPT 必须 fail closed。用户只能显式选择重新 TTS，或回到 P12 修改 Final Target Dialogue 后重建下游。

P14 v1 禁止静默：改写对白、压缩/变速音频、拉伸镜头、重排视觉节奏、使用未来 Storyboard slack。

## 4. Artifact Graph

```text
TARGET_SCRIPT --DERIVED_FROM--> TARGET_AUDIO
TARGET_BIBLE  --USES----------> TARGET_AUDIO
TARGET_AUDIO  --DERIVED_FROM--> TIMING_PLAN
TARGET_SCRIPT --USES----------> TIMING_PLAN
new same-type artifact --SUPERSEDES--> previous revision
```

因此：Target Script 新 revision 会使 Target Audio 与 Timing 递归 STALE；Target Bible 新 revision 可直接 stale Target Audio 并继续 stale Timing；Target Audio 新 revision stale Timing。Target Assets revision 不影响 P14。

`TARGET_AUDIO` 与 `TIMING_PLAN` 都位于 `PRODUCTION` namespace，Target / Production 不得反向写入 Source。

## 5. Idempotency / resume / provenance

TTS 任务 fingerprint 必须至少包含两个硬输入 artifact id/revision/fingerprint、生成序列、provider profile 与 voice binding。每句独立 ProviderJob，已完成 clip 以不可变媒体 + sidecar checkpoint 恢复；只有文本 hash、voice id 与媒体 SHA 都仍一致时 resume 才可跳过付费调用。

正式 Artifact revision 只在人工 ACCEPT 时递增。Candidate/Task/Provider success 不等于正式 revision。

## 6. UI 与人工验收

普通产品入口名称为“配音与时序”。目标配音区域必须提供显式 voice binding、逐句真实音频播放、服务端真实时长、候选 ACCEPT/REJECT。Timing 区域必须显示 source slot、actual speech duration、residual/overflow 与 fit 状态；任何 unresolved overflow 不允许 ACCEPT。

真实验收至少要求：真实 Provider、真实 ProviderJob、真实媒体 bytes、可解码与 ffprobe、逐句人工听审、人物声线稳定、对白文本一致、无明显截断/异常静音、局部重试不重复生成其他已完成句子，以及 Timing 对真实 duration 精确一致。

只有真实 Provider + 真实媒体 + 人工听审 + Timing 人工审核 + 用户明确 `P14 PASS` 后，才允许另行把 `TTS / TIMING` 升级为 AVAILABLE。

## 7. 明确禁止

P14 不进入：

```text
TARGET_STORYBOARD
VIDEO_GENERATION
QC_SELECTION
LIP_SYNC
POST_PRODUCTION
```

本次工程实现不得伪造 Provider、remote job id、音频、duration 或人工 PASS。
