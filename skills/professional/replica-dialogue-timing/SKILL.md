# Replica Dialogue Timing

## 目标

把 CURRENT `TARGET_AUDIO` 的真实语音时长与 CURRENT `TARGET_SCRIPT` 冻结的对白 source slot 做确定性对齐，形成可审核的 `TIMING_PLAN`。

## 计算规则

对每条 utterance：

- `source_slot_duration_us = source_end_us - source_start_us`
- `planned_speech_start_us = source_start_us`
- `planned_speech_end_us = source_start_us + actual_speech_duration_us`
- 音频短于 slot：`residual_hold_us = slot - speech_duration`，`overflow_us = 0`
- 音频长于 slot：`overflow_us = speech_duration - slot`，标记 `OVERFLOW`

所有时间统一使用整数微秒。

## Overflow

存在任何 `OVERFLOW` 时，候选可以展示，但不得 ACCEPT 为正式 `TIMING_PLAN`。用户必须显式返回 TTS 重录/换速，或返回 P12 修改 Final Target Dialogue 后重新生成。当前 v1 不允许自动压缩音频、拉伸 Shot、重排视觉节奏或改写对白。

## Provider

本 Skill 完全确定性执行，不调用外部 Provider，也不创建虚假的 ProviderJob。

## 边界

本 Skill 不进入 Target Storyboard、Video Generation、QC、Lip Sync 或 Post Production。
