# F03 视频预处理规划启动

时间：2026-08-24 10:46 +08:00  
分支：main（未创建新分支）

## 用户指令

用户明确：

```text
开始F03
```

因此开始 F03 规划，但按项目 Feature 流程，本次只完成 Contract 和详细函数职责，不直接写业务代码。

## 上游冻结基线

F01、F02 都已：

```text
STABLE / FROZEN
```

F03 不得覆盖 F02 Source 原片，也不得改变 Source ID / source_videos 既有语义。

## 新增权威文档

```text
docs/features/F03-video-preprocessing.md
docs/features/F03-function-contracts.md
```

并更新：

```text
docs/PROJECT_STATE.md
```

## F03 Draft 目标

```text
Source integrity check
→ proxy.mp4
→ audio.wav（有音频时）
→ thumbnail.jpg
→ metadata/hash
→ Source↔Proxy / Audio Mapping
→ ready
```

F03 不做 F04 Shot Detection。

## Preprocess Profile Draft

Proxy：

```text
H.264/libx264
CRF23
preset fast
yuv420p
最大 1280×720
保持比例
不放大小视频
不强制 CFR
保留 timestamp 节奏
```

Analysis WAV：

```text
PCM s16le
16kHz
mono
```

无音频 Source 不生成假静音 WAV。

Thumbnail：从 Proxy 固定时间点抽取。

## Timebase Draft

F03 属于 Source Domain。

```text
source_us = proxy_us + proxy_to_source_offset_us
source_us = audio_us + audio_to_source_offset_us
```

权威单位 integer microseconds。

VFR 不允许通过 frame_index/fps 猜 Source 时间。

目标 timestamp mapping 误差 <= 1ms；超过必须在 F04 前重新评估。

## Database Draft

```text
0003_create_source_preprocess
source_preprocess
status = processing / ready
```

一份 Source V1 最多一个 ready Preprocess Asset Set。

## Workspace Draft

```text
preprocess/.staging/SOURCE_xxx/
preprocess/SOURCE_xxx/
```

正式包含：

```text
proxy.mp4
audio.wav（可选）
thumbnail.jpg
```

## 7 个核心函数

```text
generate_proxy_video()
extract_analysis_audio()
generate_thumbnail()
inspect_preprocess_assets()
preprocess_source_video()
get_source_preprocess()
recover_source_preprocesses()
```

2 个 Controller：

```text
GET  /api/projects/{project_id}/preprocess
POST /api/projects/{project_id}/preprocess
```

详细职责已写入 `F03-function-contracts.md`，包括真实业务作用、调用者、输入输出、副作用、失败、禁止行为和测试。

## 当前状态

```text
F03 = PLANNED
Contract = DRAFTED / WAITING_USER_CONFIRMATION
Business Code = NOT STARTED
F04 = NOT STARTED
```

用户确认后才进入编码。
