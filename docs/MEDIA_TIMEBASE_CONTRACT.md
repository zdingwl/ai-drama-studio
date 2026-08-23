# AI Drama Studio — Media Timebase Contract

## 1. 目的

系统同时处理原片分析和重制成片。

必须避免把两个不同时间域混成一套：

1. **Source Timeline**：原片证据时间轴；
2. **Production Timeline**：最终重制成片时间轴。

因为生成后的 Shot 时长、目标对白、TTS、Lip Sync 可能与原片不同，所以 Production Timeline 不能被强行等同于 Source Timeline。

---

## 2. 两个权威时间域

### Source Timeline

负责原片相关数据：

- Source Video；
- Proxy / extracted audio；
- 自动/人工 Shot 边界；
- 原片 Character tracks；
- ASR Source Dialogue；
- Speaker Mapping；
- Source Scene evidence。

### Production Timeline

负责最终重制相关数据：

- Approved Shot Spec duration；
- Generated/Selected Shot duration；
- Final Voice；
- Lip Sync；
- Final Audio Mix；
- Final Subtitle Track；
- Final Render / Master。

两者通过：

```text
shot_id
source interval
production shot/version
```

建立映射，而不是假设时间值永远相同。

---

## 3. Shot-local Time

很多生产步骤应优先使用 Shot 内局部时间：

```text
shot_local_start_us = 0
shot_local_end_us = production_duration_us
```

例如：

- Dialogue Fit；
- TTS 在当前 Shot 内的位置；
- Lip Sync；
- Shot 内字幕 cue。

最终合成时，再根据 Shot Sequence 计算 Production Timeline 全局 offset。

这样修改前一个 Shot 时长后，不需要把所有后续对象的内部局部时间硬改一遍。

---

## 4. 统一单位

数据库和业务 Contract 默认使用：

```text
integer microseconds (µs)
```

推荐字段：

```text
start_us
end_us
duration_us
```

禁止把 float 秒作为唯一权威持久化值。

前端可以显示秒/Timecode，但 UI 格式化值不能反向成为权威数据。

---

## 5. 区间语义

默认半开区间：

```text
[start_us, end_us)
```

`duration_us = end_us - start_us`。

相邻片段因此不重复占用边界。

---

## 6. Source 媒体元数据

至少可记录：

```text
duration_us
source_start_time_us
video_time_base_num / den
fps_num / den
avg_frame_rate_num / den
r_frame_rate_num / den
is_vfr
audio_sample_rate
audio_channels
```

精确操作按需保留 PTS/DTS/stream time_base。

---

## 7. CFR / VFR

CFR 使用 rational FPS，例如：

```text
30000 / 1001
```

不要把它长期简化为浮点 `29.97`。

VFR 禁止使用：

```text
frame_index / fps
```

作为唯一定位方式；需要基于 timestamp/PTS 映射。

---

## 8. Proxy Contract

Proxy 属于 Source Domain。

Feature 03 必须保存 Source↔Proxy 的映射信息。

如果 Proxy 从 0 开始而 Source start_time 非 0，必须保存明确 offset。

下游 Source Analysis 不允许自己猜 offset。

---

## 9. Extracted Audio Contract

抽取 WAV 属于 Source Domain。

ASR/Speaker 输出首先映射到 Source Timeline：

```text
source_start_us
source_end_us
```

记录 sample rate、channel、timeline offset。

---

## 10. Source Shot Contract

原片 Shot 推荐：

```text
detected_start_us
detected_end_us
final_start_us
final_end_us
```

这些字段描述 Source Timeline。

算法 float 秒必须通过统一 conversion utility 转整数微秒后持久化。

---

## 11. Dialogue 时间域

### Source Dialogue

```text
source_start_us
source_end_us
```

属于 Source Timeline。

### Target Dialogue

目标对白文本本身不必复制 Source 全局时间作为最终成片时间。

Feature 20 主要记录：

```text
available_duration_us
estimated_speech_duration_us
```

这是 Shot-local / planned duration constraint。

### Final Voice

记录：

```text
voice_duration_us
shot_local_start_us
```

最终全局播放位置由 Production Timeline 组装时计算。

---

## 12. Production Shot Duration

生产镜头需要区分：

```text
source_duration_us
planned_production_duration_us
actual_generation_duration_us
selected_final_duration_us
```

这些值可以相同，也可以不同。

不能因为原 Shot 5 秒，就假定最终生成视频永久必须恰好 5 秒。

如果业务策略要求尽量保持原时长，这是 Constraint，不是 Timebase 恒等关系。

---

## 13. Production Timeline 计算

最终 Shot Sequence 确认后：

```text
SHOT_001 production_start_us = 0
SHOT_002 production_start_us = SHOT_001 final duration
SHOT_003 production_start_us = previous end
...
```

推荐由统一 Timeline Builder 计算，不要把全局 production_start_us 分散硬编码到多个模块。

如果前一个 Shot 时长改变，应重新构建 Production Timeline，并按 Dependency/Stale 规则影响字幕、音频、Render 等下游。

---

## 14. Subtitle Contract

Source ASR timestamp 只能作为翻译/定位参考。

最终字幕必须基于：

```text
Approved Target Dialogue
+ Final/Selected Shot duration
+ Shot-local cue timing
+ Production Timeline offset
```

因此最终 SRT/VTT 属于 Production Domain。

禁止直接复制 Source ASR 时间作为最终字幕时间。

---

## 15. Final Audio Contract

Final Audio Mix 属于 Production Domain。

所有 Dialogue/BGM/SFX/Ambience 必须最终对齐到 Production Timeline 或 Shot-local timeline + production offset。

原片音效如果复用，需要显式 Source→Production 映射/剪切，而不是假设原时间位置仍然正确。

---

## 16. Frame Stepping

Source Player 的 frame stepping 与 Production Preview 的 frame stepping必须明确属于哪个时间域。

V1 如果只对 CFR 做精确 stepping，必须记录限制；支持 VFR 时使用 frame timestamp index。

---

## 17. Rounding / Conversion

所有：

- float seconds → µs；
- PTS ↔ µs；
- Source↔Proxy；
- Shot-local↔Production global；

必须走公共 media time utility。

禁止业务模块各自：

```text
round(..., 2)
int(seconds * 1000)
currentTime += 1/fps
```

作为权威逻辑。

---

## 18. 推荐公共能力

首次实现时冻结实际路径，建议概念上包含：

```text
MediaTime
SourceTimeMapper
ShotLocalTime
ProductionTimelineBuilder
```

不要让每个 Feature 自己重写时间换算。

---

## 19. 测试

Source Domain 至少覆盖：

- 24 / 25 fps；
- 24000/1001；
- 30000/1001；
- VFR；
- source start_time 非 0；
- 44.1k / 48k audio；
- Source→Proxy→Source round trip。

Production Domain 至少覆盖：

- 生成 Shot 与 Source 时长相同；
- 生成 Shot 比 Source 长/短；
- 前一个 Shot 时长变化后的 timeline rebuild；
- subtitle cue 全局 offset；
- final audio 对齐；
- render 总时长一致性。

---

## 20. Feature Contract 必须回答

涉及时间的 Feature 必须写清：

1. 属于 Source / Shot-local / Production 哪个 domain？
2. 输入 timeline 是什么？
3. 输出 timeline 是什么？
4. 权威单位是否为 integer microseconds？
5. 是否存在 timeline mapping？
6. 是否支持 VFR？
7. rounding/conversion utility 在哪里？
8. 上游时长改变会让什么 stale？
9. 时间误差如何验收？

---

## 21. Stable Gate

```text
[ ] Source 与 Production 时间域没有混用
[ ] DB 未把 float 秒作为唯一权威值
[ ] Shot-local 时间定义明确
[ ] Proxy/Audio 映射明确
[ ] Rational FPS/VFR 行为明确
[ ] Production Timeline Builder 行为明确（如适用）
[ ] Subtitle/Audio 使用 Production Domain（如适用）
[ ] 公共转换逻辑已测试
[ ] Source/Production 边界与 round-trip 测试通过
```
