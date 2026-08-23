# AI Drama Studio — Media Timebase Contract

## 1. 目的

本项目同时处理 Source Video、Proxy、Audio、Shot、Dialogue、Subtitle、TTS、Lip Sync 和最终 Render。

如果每个模块各自使用 float 秒数或假设固定 FPS，后期很容易出现：

- Shot 边界漂移；
- 对白比画面慢/快几帧；
- Proxy 与 Source 时间不一致；
- VFR 视频 frame index 计算错误；
- 字幕、Lip Sync、Render 逐步累积误差。

因此必须建立统一 Timebase Contract。

---

## 2. 唯一业务母时间轴

**Source Timeline 是项目唯一业务母时间轴。**

所有业务时间信息最终都必须能映射回 Source Timeline。

```text
Source Video Timeline
        ↓
Proxy / Audio / Frame / Shot / Dialogue / Subtitle / TTS / Lip Sync / Render
```

Proxy 只是分析与预览媒介，不允许成为第二套独立业务时间轴。

---

## 3. 业务时间统一单位

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

例：

```text
13.213 秒 = 13_213_000 µs
```

禁止把 `float seconds` 作为唯一权威持久化时间值。

前端展示可以转换为：

```text
00:00:13.213
```

API 如为了可读性额外返回 `start_seconds`，也必须以 `start_us` 为权威值。

---

## 4. 区间语义

媒体片段默认采用半开区间：

```text
[start_us, end_us)
```

即：

- 包含 start；
- 不包含 end；
- `duration_us = end_us - start_us`。

这样相邻 Shot：

```text
SHOT_001 [0, 3_210_000)
SHOT_002 [3_210_000, 8_570_000)
```

不会因边界同时属于两个 Shot 而产生重复。

---

## 5. 必须保留的媒体元数据

根据 Feature 需要，至少应能读取/保留：

```text
duration_us
source_start_time_us
video_time_base_num
video_time_base_den
fps_num
fps_den
avg_frame_rate_num
avg_frame_rate_den
r_frame_rate_num
r_frame_rate_den
is_vfr
audio_sample_rate
audio_channels
```

必要的精确媒体操作还应保留原始：

```text
PTS / DTS / stream time_base
```

不要把格式化后的字符串当权威数据。

---

## 6. CFR 与 VFR

### CFR

固定帧率视频可以在明确的 rational FPS 下做 frame/time 映射。

例如 30000/1001 ≠ 29.97 的浮点近似。

应保存：

```text
fps_num = 30000
fps_den = 1001
```

### VFR

可变帧率视频禁止使用：

```text
frame_index / fps
```

作为唯一定位方式。

VFR 的具体帧时间必须来自时间戳/PTS 映射。

如果 Feature 需要 frame-accurate 操作，必须记录使用的映射策略并测试 VFR 样本。

---

## 7. Proxy Contract

Feature 03 生成 Proxy 时必须保证：

1. 业务时间可以映射回 Source Timeline；
2. 不静默裁掉 Source 开头的非零 start time；
3. 不因重编码改变业务 Shot 时间定义；
4. 保存 Source→Proxy 映射必要信息；
5. 验收必须检查开头、中间、结尾多个时间点。

如果为了播放兼容将 Proxy 重新从 0 开始计时，必须明确记录 offset：

```text
proxy_timeline_offset_us
```

并统一通过映射函数转换。

禁止让下游自己猜 offset。

---

## 8. Audio Contract

抽取 WAV 时必须记录：

```text
sample_rate
channel_count
source_timeline_offset_us
```

ASR / Speaker 输出首先是音频时间，再转换为 Source Timeline 的 `start_us/end_us` 后进入业务数据库。

不要让 ASR 下游依赖某个临时 WAV 的独立时间基准。

---

## 9. Shot Contract

Shot 的权威业务字段推荐：

```text
detected_start_us
detected_end_us
final_start_us
final_end_us
```

前端编辑最终写入整数微秒。

如果算法返回 float 秒：

```text
算法结果
→ 单点统一转换/round
→ integer microseconds
→ 持久化
```

禁止不同模块各自用不同 rounding 规则。

---

## 10. Dialogue Contract

Dialogue 必须最终绑定 Source Timeline：

```text
asr_start_us
asr_end_us
final_start_us
final_end_us
```

TTS Duration 也使用 `duration_us` 记录，但必须与 Dialogue 所在 Source Timeline 区分清楚：

```text
dialogue_timeline_*    原剧时间位置
voice_duration_us      生成音频自身长度
```

---

## 11. Frame Stepping

前端“上一帧/下一帧”不能长期依赖简单：

```text
currentTime += 1 / fps
```

V1 如仅支持 CFR，可以明确限制并记录。

正式支持 VFR 后，应通过预计算/按需计算的 frame timestamp index 执行精确跳帧。

---

## 12. Rounding 规则

统一：

- 外部 float 秒 → 微秒：使用项目公共 time conversion utility；
- 不允许业务模块自己 `int(seconds * 1000)` 或 `round(..., 2)`；
- UI 格式化不回写业务值；
- FFmpeg 参数转换必须经过 Media Time Utility。

建议建立统一模块：

```text
engine/media/timebase.py
```

具体代码路径在首次实现该能力的 Feature 中冻结。

---

## 13. 时间转换必须可测试

至少测试：

- 24 fps；
- 25 fps；
- 30000/1001；
- 24000/1001；
- VFR 样本；
- Source start_time 非 0；
- 音频 44.1kHz；
- 音频 48kHz；
- 视频结尾边界；
- 多次 Source→Proxy→Source round trip。

---

## 14. Feature Contract 必须回答

涉及时间的 Feature 必须写清：

1. 输入时间属于哪个 timeline？
2. 内部使用什么单位？
3. 输出是否已经转换为 Source Timeline？
4. 是否支持 VFR？如果暂不支持，限制是什么？
5. 是否涉及 rounding？公共函数在哪里？
6. 时间误差的验收方式是什么？

---

## 15. Stable Gate

- [ ] Source Timeline 权威性未被破坏
- [ ] DB 未用 float 秒作为唯一权威值
- [ ] 时间单位明确
- [ ] 区间语义明确
- [ ] Proxy/Audio offset 有记录
- [ ] Rational FPS 未被错误简化
- [ ] VFR 行为明确
- [ ] 时间转换使用公共逻辑
- [ ] Round-trip / 边界测试通过
