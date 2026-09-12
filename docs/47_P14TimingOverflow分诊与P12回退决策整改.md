# P14 Timing OVERFLOW 分诊与 P12 回退决策整改

> 日期：2026-09-13  
> 状态：P14 真实项目验收中的产品分诊整改；补充 `docs/32`、`docs/42`。  
> 本文不改变 Timing 算法、Artifact 合同或阶段状态。

## 1. 真实项目问题

真实 P14 项目已经产生人工确认后的 TARGET_AUDIO，并按 `docs/32` 使用真实 ffprobe 时长计算 Timing candidate。

当前 Timing v1 的确定性规则仍为：

```text
source_slot_duration_us = source_end_us - source_start_us
actual_speech_duration_us = 服务端 ffprobe 真实 WAV
actual > source slot => OVERFLOW
```

真实项目出现某一整集 `35 / 35 OVERFLOW` 的情况。此时直接要求用户逐句盲目 Retake，会把一个“本土化对白长度是否适合原片时间槽”的系统性问题转化为大量无效 TTS 调用。

## 2. 本整改不改变 Timing 合同

不得因为大量 OVERFLOW 就静默：

- 拉伸原镜头；
- 使用未来 Storyboard slack；
- 重排视觉节奏；
- 自动改写 Final Target Dialogue；
- 自动把全部对白设为极端语速；
- 将数学估算当成真实生成时长。

正式 Timing 是否 FIT 仍只由实际生成 WAV 的 ffprobe 时长重新计算决定。

## 3. OVERFLOW 分诊

对每个 Timing item 只计算一个只读数学指标：

```text
required_duration_factor = source_slot_duration_us / actual_speech_duration_us
```

该值不是 Provider 结果，也不是自动执行参数，只用于判断当前 overflow 是否值得进入 Retake 尝试。

P14 v1.1 产品允许的 `duration_factor` 下限为 `0.8`，因此分诊规则为：

```text
FIT
  -> 无需处理

OVERFLOW 且 required_duration_factor >= 0.8
  -> RETAKE_TRY
  -> 可进入逐句 Retake，人工选择 duration factor 后重新真实生成

OVERFLOW 且 required_duration_factor < 0.8
  -> SCRIPT_REWRITE
  -> 即使按产品允许的最快 0.8 估算也理论上放不下
  -> 优先返回 P12 缩短 Final Target Dialogue
```

IndexTTS duration factor 与最终真实 WAV 时长不保证严格线性，因此 `RETAKE_TRY` 只表示“值得尝试”，不表示一定 FIT。任何 Retake 完成后仍必须重新 ffprobe、重新发布 TARGET_AUDIO、重新计算 Timing。

## 4. 产品 UI

在“对白时序”和“逐句 Retake”之间新增 `P14 · Timing 分诊` 面板，只在存在待审核 Timing candidate 时显示。

面板必须显示：

- 总对白数；
- FIT 数；
- OVERFLOW 数；
- 可尝试 Retake 数；
- 优先回 P12 数；
- 按集统计；
- 最严重的 overflow 明细：集 / utterance number / Final Target Dialogue / source slot / actual duration / overflow / 理论 factor / 分诊路径。

该面板不创建 Task、ProviderJob、Candidate、Artifact，不修改任何数据库事实。

## 5. 用户决策顺序

大量 OVERFLOW 时推荐：

```text
Timing candidate
-> 先看分诊
-> SCRIPT_REWRITE 先回 P12 缩短本土化对白
-> 重建下游 TARGET_AUDIO
-> 剩余轻量 OVERFLOW 再做 Retake
-> ffprobe
-> 重算 Timing
-> 全部 FIT 后才允许 ACCEPT TIMING_PLAN
```

这样避免把“对白本身过长”误当成“需要把 89 句全部重录”。

## 6. 阶段状态

本整改只是 P14 验收辅助，不等于 P14 PASS。

继续保持：

```text
P13 = PASS
TARGET_ASSETS = AVAILABLE
P14 PASS = NO
```

不得因此进入 Target Storyboard / Generation / QC / Lip Sync / Post。
