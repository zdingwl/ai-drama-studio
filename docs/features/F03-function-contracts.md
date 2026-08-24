# F03 — 视频预处理：核心函数与 Controller 详细职责

Feature ID: F03  
Status: PLANNED / WAITING_USER_CONFIRMATION  
Depends On: F01、F02（STABLE / FROZEN）

> 本文件专门解释 F03 的 7 个核心后端函数和 2 个 Controller 到底是干什么的。
> 目标仍然是：开发时不用猜函数名，直接知道它在完整流程中的位置、输入、输出、副作用、失败边界和禁止行为。
>
> F03 不因为“详细”继续拆成几十个函数；路径、Hash、Fraction、时间换算等只作为私有 helper 或公共 media-time utility。

---

# 1. 完整调用链

用户在“视频预处理”页面点击开始：

```text
POST /api/projects/{project_id}/preprocess
↓
preprocess_source_video_api()
↓
preprocess_source_video()
├─ 验证 F01 Project
├─ 获取 F02 ready Source
├─ 校验 Source size + SHA-256
├─ DB insert processing
├─ generate_proxy_video()
├─ extract_analysis_audio()       # Source 有音频时
├─ generate_thumbnail()
├─ inspect_preprocess_assets()
├─ staging → final
└─ DB ready
```

页面刷新 / 重启后读取：

```text
GET /api/projects/{project_id}/preprocess
↓
get_source_preprocess_api()
↓
get_source_preprocess()
```

应用启动恢复：

```text
recover_source_preprocesses()
└─ 必要时 inspect_preprocess_assets()
```

---

# 2. `generate_proxy_video(...)`

## 它到底是干什么的

把 F02 冻结的 `original.<ext>` 转成后续 F04–F07 等分析流程统一使用的：

```text
proxy.mp4
```

它解决的不是“输出一个能播放的视频”这么简单，而是：

> 生成一个尺寸适中、浏览器和本地算法都容易读取，同时仍能通过明确时间映射回 Source Timeline 的分析视频。

## 为什么需要独立函数

Proxy 的 FFmpeg 参数属于 F03 的固定媒体 Contract。

如果这些参数散落在：

```text
Controller
Service
测试代码
以后 F04
```

就会出现每个地方各自生成不同 Proxy 的风险。

因此所有 Proxy 编码规则只能有一个入口。

## 谁调用

只由：

```text
preprocess_source_video()
```

调用。

Recovery 不重新编码 Proxy；Recovery 只检查已经存在的 final。

## 输入

概念上：

```text
source_path
staging_proxy_path
video_stream_index
audio_stream_index | None
```

其中 stream index 来自 F02 已确认 Source metadata。

## 输出

成功后返回简单生成结果，例如：

```text
GeneratedMediaFile
├─ path
└─ command_summary / exit metadata（仅调试需要）
```

真正的 duration、timebase、Hash、Mapping 统一由后面的 `inspect_preprocess_assets()` 读取和确认。

这样本函数不会同时承担“生成 + 判断最终 Contract 是否正确”两套职责。

## FFmpeg 固定行为

V1 必须保证：

```text
H.264 / libx264
yuv420p
CRF 23
preset fast
MP4
+faststart
最大 1280×720
保持比例
小视频不放大
frame cadence / timestamp passthrough
```

Source 有音频：

```text
映射 F02 选中的 audio stream
AAC 128k
```

Source 无音频：

```text
只生成 video stream
```

调用必须是参数数组：

```python
subprocess.run([...], shell=False)
```

禁止自己拼 Shell 字符串。

## 它会修改什么

只允许创建：

```text
本次 F03 staging 目录中的 proxy.mp4
```

不能碰 final 目录。

## 明确禁止

不能：

```text
不能修改 F02 original.ext
不能写 source_preprocess DB ready
不能生成 WAV
不能生成 Thumbnail
不能跑 Shot Detection
不能把 VFR 强制改成 25/30 CFR
不能因为文件已存在就覆盖
不能自动切 NVENC
```

## 失败

至少识别：

```text
FFmpeg 不存在
libx264 不可用
Source 无法读取
编码失败
写盘失败
目标 staging 文件冲突
```

向上抛稳定 F03 错误，例如：

```text
PREPROCESS_FFMPEG_UNAVAILABLE
PREPROCESS_PROXY_FAILED
```

是否删除 staging / processing row，由 `preprocess_source_video()` 决定。

## 测试

至少：

```text
横屏 1920x1080 → <=1280x720
竖屏 1080x1920 → 约405x720
640x360 不放大
H.264 / yuv420p
有音频 Proxy 可播放
无音频 Source 仍生成 Proxy
VFR 输入不强制 CFR
已有 staging proxy 不覆盖
FFmpeg 失败正常上抛
```

---

# 3. `extract_analysis_audio(...)`

## 它到底是干什么的

从 F02 Source 的选中音频流提取一份后续语音分析专用 WAV：

```text
audio.wav
```

固定：

```text
PCM s16le
16000 Hz
mono
```

## 为什么需要独立函数

这份 WAV 的用途是：

```text
ASR
Diarization
Speaker 分析
```

不是最终音频母带。

它的采样率和声道规则必须固定，避免 F08/F09 各自再做一份不同格式的音频。

## 谁调用

仅：

```text
preprocess_source_video()
```

在：

```text
F02 audio_stream_index != NULL
```

时调用。

## 输入

概念：

```text
source_path
staging_audio_path
audio_stream_index
```

## 输出

成功生成 staging `audio.wav`。

媒体时长、Hash、sample rate、channels 和 Source Mapping 不由这里最终判定，统一交给：

```text
inspect_preprocess_assets()
```

## 明确禁止

不能：

```text
Source 无音频时生成假的静音 WAV
不能写 DB ready
不能改变音频播放速度
不能做降噪
不能做人声分离
不能做响度归一化
不能用于 F31 最终混音母带
```

F03 只做格式标准化。

## 失败

例如：

```text
选中的 Source audio stream 不存在
FFmpeg 失败
磁盘不可写
生成 WAV 损坏
```

抛：

```text
PREPROCESS_AUDIO_FAILED
```

统一由总调度回滚。

## 测试

```text
48k stereo Source → 16k mono WAV
44.1k Source → 16k mono WAV
WAV codec=pcm_s16le
无音频 Source 不调用该函数
Source 文件不被修改
```

---

# 4. `generate_thumbnail(...)`

## 它到底是干什么的

从已经生成的 Proxy 抽取一张代表 F03 Source 的：

```text
thumbnail.jpg
```

用于项目/媒体界面快速预览。

## 为什么从 Proxy 抽，不重新从 Source 抽

因为：

- Proxy 已经是 F03 验证后的统一可读视频；
- 避免对复杂 Source 容器再做一次不同的 seek；
- Thumbnail timestamp 可以直接经过 Proxy→Source Mapping 得到 Source Timeline 位置。

## 谁调用

由：

```text
preprocess_source_video()
```

在 Proxy 生成后调用。

## 输入

```text
proxy_path
staging_thumbnail_path
thumbnail_proxy_time_us
```

时间点由总调度根据 Proxy duration 的固定规则计算。

## 输出

```text
thumbnail.jpg
```

最终还需要由 `inspect_preprocess_assets()` 检查：

```text
文件存在
大小 > 0
JPEG 可被 FFmpeg/基础图片检查读取
```

## 明确禁止

不能：

```text
不能任意随机抽帧
不能由 UI 传用户自选时间
不能写 Source Timeline 值
不能替代 F04 Shot keyframe
不能改 Source/Proxy
```

## 失败

```text
Proxy 不可读
目标时间不合法
FFmpeg 抽帧失败
JPEG 为空/损坏
```

抛：

```text
PREPROCESS_THUMBNAIL_FAILED
```

## 测试

```text
短视频能抽图
长视频按规则<=5s抽图
JPG size > 0
thumbnail Source timestamp 映射正确
```

---

# 5. `inspect_preprocess_assets(...)`

## 它到底是干什么的

这是 F03 的**验收检查员**。

前三个函数只是“生成文件”，但：

```text
FFmpeg exit code = 0
```

并不等于这些文件已经满足 F03 Contract。

本函数负责在发布 final 前统一确认：

```text
Proxy 是否真的可用
Audio 是否真的是 16k mono PCM
Thumbnail 是否存在/可读
每个输出大小 / SHA-256
Source / Proxy timestamp metadata
Source ↔ Proxy Mapping
Source ↔ Audio Mapping
映射误差是否在允许范围
```

## 为什么它必须独立

这是为了避免：

```text
generate_proxy_video() 自己检查一点
extract_audio() 自己检查一点
Service 再猜一点
Recovery 又复制一套
```

正常处理和 Recovery 必须共用同一套“什么叫合法 F03 final”的标准。

## 谁调用

```text
preprocess_source_video()
recover_source_preprocesses()
```

## 输入

概念：

```text
F02 SourceVideoRecord
source_path
proxy_path
audio_path | None
thumbnail_path
```

## 输出

返回：

```text
PreprocessInspection
```

至少包含可直接写 DB ready 的：

```text
proxy size/hash/duration/timebase/fps
proxy_to_source_offset_us
source video timebase
audio size/hash/duration/sample_rate/channels
audio_to_source_offset_us
thumbnail size/hash/source_time_us
```

## Source Integrity 也在这里检查吗？

分两层：

正式开始前，总调度先做 Source size/hash Gate，避免浪费 FFmpeg 时间。

本函数仍要确认：

```text
Source 当前路径存在
必要 Source timestamp metadata 仍可读取
```

但不会修改 F02 记录。

## Time Mapping 规则

### Proxy

保存：

```text
source_us = proxy_us + offset_us
```

Proxy 不改变播放速度，因此 mapping 只允许是：

```text
scale = 1
+ offset
```

不允许出现隐式 speed ratio。

### Audio

WAV 时间从第一个输出 sample 的 0 开始。

保存：

```text
source_us = audio_us + audio_to_source_offset_us
```

### VFR

禁止通过：

```text
frame_index / fps
```

计算 mapping。

必须依据 FFprobe timestamp / stream start / timebase 信息。

## 验证内容

Proxy 至少：

```text
存在普通 video stream
H.264
width/height > 0
<= 1280x720 box
pixel format yuv420p
proxy_duration_us > 0
```

Audio（如存在）：

```text
PCM s16le
16000 Hz
1 channel
duration > 0
```

Thumbnail：

```text
存在
size > 0
可读取
```

Mapping：

```text
Source→Proxy→Source round-trip 可逆
目标媒体 timestamp 误差 <= 1 ms
```

## 它会修改什么

```text
什么都不修改
```

只读取文件、跑 FFprobe、计算 Hash 和返回检查结果。

## 明确禁止

不能：

```text
不能重新编码失败文件
不能修复 Proxy
不能删除文件
不能写 DB ready
不能把验证失败自动忽略
不能为了通过检查伪造 metadata
```

## 失败

```text
PREPROCESS_VALIDATION_FAILED
PREPROCESS_MAPPING_INVALID
```

## 测试

这是 F03 最重要的测试组之一：

```text
24 / 25 / 24000/1001 / 30000/1001
VFR
non-zero start_time
Source→Proxy→Source round trip
16k mono WAV
无音频
错误 codec
损坏 Proxy
缺 Thumbnail
Hash 正确
```

---

# 6. `preprocess_source_video(project_id)`

## 它到底是干什么的

这是 F03 最重要的**业务总调度函数**。

用户点击：

```text
开始视频预处理
```

真正控制：

```text
什么时候创建 processing
什么时候调用 FFmpeg
什么时候认为输出有效
什么时候发布 final
什么时候 DB 才能 ready
失败删除什么
崩溃后保留什么
```

全部由它负责。

## 谁调用

只由：

```text
preprocess_source_video_api()
```

调用。

## 输入

```text
project_id
```

不再上传文件，因为 F02 Source 已经存在 Workspace。

## 完整业务步骤

### 1. 验证 Project

确认：

```text
Project 存在
status = ready
Workspace / project.json 合法
```

必须复用 F01 已冻结能力，不能 Controller 自己判断。

### 2. 获取 F02 Source

确认：

```text
Source exists
status = ready
formal source file exists
```

无 Source：

```text
PREPROCESS_SOURCE_REQUIRED
```

### 3. Source Integrity Gate

检查：

```text
实际 file size == F02 file_size_bytes
实际 SHA-256 == F02 sha256
```

不一致：

```text
SOURCE_VIDEO_INTEGRITY_MISMATCH
```

停止，绝不自动修改 Source。

### 4. 防重复

当前 Source 已经存在：

```text
processing
或
ready
```

则拒绝再次创建：

```text
PREPROCESS_ALREADY_EXISTS
```

F03 V1 不做 rerun/version UI。

### 5. DB Recovery Anchor

先写：

```text
source_preprocess.status = processing
```

保存：

```text
project_id
source_video_id
profile_version
source_sha256_snapshot
预定 relative paths
created_at
```

并提交。

这样应用崩溃后 Recovery 才知道处理没有结束。

### 6. Staging

建立：

```text
preprocess/.staging/SOURCE_xxx/
```

确认 final：

```text
preprocess/SOURCE_xxx/
```

不存在。

未知目录不能覆盖。

### 7. Proxy

调用：

```text
generate_proxy_video()
```

### 8. Audio

如果 F02 有 audio stream：

```text
extract_analysis_audio()
```

否则明确跳过，不造假。

### 9. Thumbnail

根据 Proxy 时长计算固定 thumbnail time，然后：

```text
generate_thumbnail()
```

### 10. Inspection

调用：

```text
inspect_preprocess_assets()
```

得到最终 metadata + mapping。

只有 Inspection PASS 才能继续。

### 11. Publish

把整个：

```text
.staging/SOURCE_xxx
```

同盘原子 rename：

```text
preprocess/SOURCE_xxx
```

这是：

```text
F03 FILE PUBLISH POINT
```

### 12. DB Ready

写入 Inspection 数据并：

```text
status = ready
completed_at = now
```

然后提交。

## 失败边界

### Final 发布前

可以安全清理：

```text
本 Source F03 staging
processing DB row
```

但只能清理已知 F03 文件。

### Final 发布后

如果 DB ready commit 失败：

```text
不能删除 final Proxy/Audio/Thumbnail
保留 processing row
→ PREPROCESS_FINALIZATION_PENDING
→ Startup Recovery
```

## 明确禁止

不能：

```text
不能覆盖 Source
不能覆盖现有 final preprocess
不能顺手执行 F04 Shot Detection
不能用 float 秒持久化权威时间
不能把 Proxy timeline 直接当 Source timeline
不能静默接受 Source Hash 变化
```

## 测试

至少：

```text
正常有音频 Source
正常无音频 Source
Source hash mismatch
已有 ready
已有 processing
Proxy fail rollback
Audio fail rollback
Thumbnail fail rollback
Inspection fail rollback
final publish 后 DB fail 保留 final
最终 DB ready 数据完整
Source 原片 hash 前后完全一致
```

---

# 7. `get_source_preprocess(project_id)`

## 它到底是干什么的

读取这个 Project 已经完成的 F03 结果，供：

```text
视频预处理页面刷新
软件重启
F04 后续读取 Proxy/Mapping
```

使用。

## 谁调用

```text
get_source_preprocess_api()
```

后续 F04 Service 也可以复用业务读取能力。

## 输入

```text
project_id
```

## 输出

```text
SourcePreprocessRecord | None
```

无 preprocess：

```text
None
```

只返回：

```text
ready
```

记录。

## 文件完整性检查

不能只看数据库。

ready 时至少确认：

```text
proxy.mp4 exists
thumbnail.jpg exists
如果 DB 记录 audio path，则 audio.wav exists
```

如果缺失：

```text
PREPROCESS_FILE_MISSING
```

V1 页面读取不每次重算几 GB 文件 Hash，避免每次刷新都长时间阻塞；Hash 在处理完成/Recovery 时验证。

## 明确禁止

不能：

```text
不能重新跑 FFmpeg
不能自动修复缺文件
不能把 processing 当 ready 返回给 F04
不能偷偷修改 DB
```

## 测试

```text
无结果 → None
ready → DTO
processing → None/内部不可作为正式结果
缺 Proxy → FILE_MISSING
缺 Audio（DB 有路径）→ FILE_MISSING
无音频 ready → 正常
```

---

# 8. `recover_source_preprocesses()`

## 它到底是干什么的

应用启动时处理上次异常退出留下的：

```text
source_preprocess.status = processing
```

记录。

它不是“重跑 FFmpeg”。它只决定：

> 已经生成到什么程度，哪些状态可以安全恢复，哪些只能清理，哪些必须保留现场。

## 谁调用

应用 Lifespan：

```text
init_database()
→ recover_creating_projects()
→ recover_source_video_imports()
→ recover_source_preprocesses()
```

顺序必须保证上游 Project / Source 已先恢复。

## Case A：final 完整存在

```text
preprocess/SOURCE_xxx/
```

存在且：

```text
inspect_preprocess_assets() PASS
source hash snapshot 仍匹配
```

则：

```text
补 metadata
→ ready
```

## Case B：只有 staging

如果目录内容只包含 F03 已知文件：

```text
proxy.mp4
audio.wav（可选）
thumbnail.jpg
```

则：

```text
安全清理 staging
→ 删除 processing row
→ 用户重新开始
```

V1 不做 FFmpeg 断点续跑。

## Case C：什么都没有

```text
删除无意义 processing row
```

## Case D：final 损坏

```text
不删除 final
不标 ready
保留 processing
记录错误
```

因为 final 已经跨过 Publish Point，需要保留现场供诊断。

## Case E：出现 unknown file

```text
不递归删除
保留 processing
记录错误
```

## 最重要安全边界

Recovery 永远不能：

```text
删除 source/SOURCE_xxx/original.ext
修改 F02 source_videos
递归清理 Project Workspace
```

## 测试

```text
valid final → ready
known staging → cleanup + row delete
no files → row delete
invalid final → preserve
unknown staging file → preserve
Source hash changed → preserve + not ready
F02 Source 永远存在
```

---

# 9. `get_source_preprocess_api(project_id)`

## HTTP

```text
GET /api/projects/{project_id}/preprocess
```

## 它到底做什么

页面打开、刷新或应用重启后，询问后端：

> 当前 Project 有没有已经完成的 F03 预处理结果？

## 完整职责

```text
读取 URL project_id
→ 调用 get_source_preprocess(project_id)
→ None 返回 200 null
→ ready 返回 SourcePreprocessDTO
```

## 明确禁止

Controller 不得：

```text
自己 SELECT source_preprocess
自己 Path.exists
自己 FFprobe
自己 Hash
自己计算 Mapping
```

这些都是业务层职责。

## 测试

```text
200 null
200 ready DTO
Project/文件错误使用统一 error envelope
```

---

# 10. `preprocess_source_video_api(project_id)`

## HTTP

```text
POST /api/projects/{project_id}/preprocess
```

## 它到底做什么

这是用户点击：

```text
开始视频预处理
```

之后的 HTTP 入口。

它本身不是“FFmpeg Controller”。

## 完整职责

```text
读取 URL project_id
→ 调用 preprocess_source_video(project_id)
→ 完成后返回 SourcePreprocessDTO
→ status 201
```

V1 是同步请求。

浏览器可能等待数分钟；页面需要显示：

```text
正在预处理，可能需要几分钟
```

但不能自己猜转码百分比。

## 明确禁止

不能：

```text
不能在 Controller 里拼 ffmpeg command
不能直接 SQL
不能建立 staging
不能删除文件
不能计算 SHA
不能写 mapping
不能把 timeout 当作“处理失败后删除 final”的依据
```

## 测试

```text
无 Source → 409/422 对应稳定错误
正常 → 201
已有 Preprocess → 409
FFmpeg 不存在 → 稳定错误 envelope
未知异常 → 安全 500，不暴露 Python stack
```

---

# 11. F03 不升级成核心函数的内容

下面如果实现需要，可以存在，但不要为了“单函数开发”再把文档膨胀成几十项：

```text
_build_proxy_command()
_build_audio_command()
_safe_hash_file()
_parse_fraction()
_seconds_text_to_us()
_resolve_preprocess_paths()
_is_known_staging_layout()
_choose_thumbnail_time_us()
```

要求：

- 名字清楚；
- 复杂逻辑有简体中文注释；
- 时间换算必须集中复用；
- 有关键边界时写单测。

---

# 12. 最终职责边界

```text
generate_proxy_video()
= 生成 Proxy 字节

extract_analysis_audio()
= 生成分析 WAV 字节

generate_thumbnail()
= 生成 Thumbnail 字节

inspect_preprocess_assets()
= 验收输出 + 计算 metadata/hash/mapping

preprocess_source_video()
= 整个 F03 业务事务总调度

get_source_preprocess()
= 读取正式 ready 结果

recover_source_preprocesses()
= 应用启动恢复 processing

Controller
= HTTP 边界
```

只要开发过程中某段逻辑不能明确放进以上职责之一，先审查是不是：

```text
职责设计漏了
或
其实属于 F04+
```

不能直接为了方便再造一层大架构。
