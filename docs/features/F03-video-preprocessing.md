# Feature 03 — 视频预处理（Video Preprocessing）

Feature ID: F03  
Status: PLANNED / WAITING_USER_CONFIRMATION  
Official Baseline: main  
Stable Dependencies: F01、F02（STABLE / FROZEN）  
Detailed Functions: `docs/features/F03-function-contracts.md`

> F03 只把 F02 冻结 Source Video 转换成后续分析可稳定复用的 Proxy、分析 WAV、Thumbnail 和明确 Timeline Mapping。F03 不做 Shot Detection、ASR、人物识别或任何 AI。

---

# 1. 一句话目标

```text
F02 ready Source Video
→ FFmpeg 生成分析 Proxy
→ 抽取标准分析 WAV（有音频时）
→ 生成 Thumbnail
→ 校验派生文件
→ 保存 Source ↔ Proxy / Audio 时间映射
→ source_preprocess = ready
→ 重启后仍可读取
```

---

# 2. F03 必须完成

```text
项目内“视频预处理”页面
读取 F02 ready Source
FFmpeg 生成 proxy.mp4
有音频时生成 audio.wav
生成 thumbnail.jpg
派生文件 staging → validate → final
Source 文件 SHA-256 完整性复核
Proxy / Audio / Thumbnail size + SHA-256
Source / Proxy 媒体时间元数据
Source ↔ Proxy timeline mapping
Source ↔ Audio timeline mapping
VFR 不使用 frame_index / fps 猜时间
0003 Migration
中断 Recovery
重启后仍可读取预处理结果
F01 + F02 Regression
真实短剧视频验收
```

明确不做：

```text
自动拉片 / Shot Detection
Shot 边界
ASR
人物识别
Scene
AI
Proxy 人工参数配置
用户切换编码器
GPU/NVENC 优化
多套 Proxy Profile
F02 Source 替换或覆盖
最终音频混音母带
```

F04 才开始自动拉片。

---

# 3. F01 / F02 冻结依赖

F03 不得改变：

```text
PROJECT_<UUID4_HEX>
SOURCE_<UUID4_HEX>
projects 既有字段语义
source_videos 既有字段语义
F02 original.<ext> 路径和只读规则
F02 2 个 API 既有语义
integer microseconds
rational FPS
StudioShell 正式 UI 基线
```

权威快照：

```text
docs/features/F01-stable-snapshot.md
docs/features/F02-stable-snapshot.md
```

---

# 4. F03 Preprocess Profile V1

F03 V1 不给用户暴露复杂转码参数。参数固定后才能保证不同项目和 F04 分析输入一致。

## 4.1 Proxy Video

正式文件：

```text
proxy.mp4
```

V1 固定：

```text
container       = MP4
video codec     = H.264 / libx264
pixel format    = yuv420p
CRF             = 23
preset          = fast
max canvas      = 1280 × 720
aspect ratio    = preserve
upscale         = NO
frame cadence   = passthrough / preserve timestamps
faststart       = YES
```

如果 Source 有音频，Proxy 同时包含可播放 AAC 音频：

```text
audio codec     = AAC
bitrate         = 128k
```

为什么不用 NVENC：

- F03 首先追求可重复和环境兼容；
- CPU libx264 不依赖 NVIDIA 驱动/显卡编码器能力；
- 当前阶段速度不是验收阻塞条件。

为什么不强制 25/30 CFR：

- Source 可能是 VFR；
- F03 是 Source Domain；
- 强行 CFR 会发生丢帧/补帧，给 F04 的 Source 时间回映增加额外误差；
- V1 Proxy 应保留展示时间节奏，后续按 timestamp 而不是 `frame_index / fps` 定位。

## 4.2 Analysis Audio

正式文件：

```text
audio.wav
```

仅当 F02 Source 存在音频流时生成：

```text
codec        = PCM signed 16-bit little-endian
sample rate  = 16000 Hz
channels     = 1 mono
```

用途：

```text
F08 ASR
F09 Speaker / Diarization 等分析输入
```

它不是 F31 最终混音母带。

如果 F02 Source 没有音频：

```text
不伪造静音 WAV
→ audio_relative_path = NULL
→ audio_available = false（由是否存在 audio metadata 表达）
```

## 4.3 Thumbnail

正式文件：

```text
thumbnail.jpg
```

从已经生成并验证的 Proxy 抽取，避免再次复杂定位原始容器。

时间点规则：

```text
thumbnail_proxy_time_us = min(proxy_duration_us / 10, 5_000_000)
```

并限制在实际 Proxy 时长范围内。

同时保存：

```text
thumbnail_source_time_us
```

由 Proxy→Source Mapping 计算，不能把 UI 显示秒数反写成权威值。

---

# 5. Workspace Contract

F02 Source 目录保持不变：

```text
<workspace>/source/SOURCE_<UUID>/original.<ext>
```

F03 派生资产单独保存：

```text
<workspace>/preprocess/
└── SOURCE_<UUID>/
    ├── proxy.mp4
    ├── audio.wav          # Source 有音频时
    └── thumbnail.jpg
```

处理过程：

```text
<workspace>/preprocess/.staging/SOURCE_<UUID>/
├── proxy.mp4
├── audio.wav              # 有音频时
└── thumbnail.jpg
```

规则：

```text
F03 永远不写 source/SOURCE_xxx/original.ext
DB 只保存 Workspace 相对路径
下游不得读取 .staging
正式目录已存在时不覆盖
所有输出先 staging，再校验，再同盘 rename 到 final
```

---

# 6. Database Contract

Migration：

```text
0003_create_source_preprocess
```

新增表：

```text
source_preprocess
```

F03 V1：

```text
1 Source Video → 0 或 1 个 ready Preprocess Asset Set
```

字段建议：

| Field | Nullable | 业务作用 |
|---|---:|---|
| `source_video_id` | No | PK + FK → source_videos.id |
| `project_id` | No | 所属 Project，便于项目查询 |
| `status` | No | `processing / ready` |
| `profile_version` | No | F03 固定预处理配置版本，V1=`1` |
| `source_sha256_snapshot` | No | 运行时重新核验后的 Source SHA-256 |
| `proxy_relative_path` | No | Proxy Workspace 相对路径 |
| `proxy_file_size_bytes` | Yes | processing 阶段未知 |
| `proxy_sha256` | Yes | ready 时必填 |
| `proxy_duration_us` | Yes | Proxy 权威时长 |
| `proxy_video_time_base_num` | Yes | Proxy 视频 time_base 分子 |
| `proxy_video_time_base_den` | Yes | Proxy 视频 time_base 分母 |
| `proxy_fps_num` | Yes | Proxy avg frame rate 分子 |
| `proxy_fps_den` | Yes | Proxy avg frame rate 分母 |
| `proxy_to_source_offset_us` | Yes | `source_us = proxy_us + offset` |
| `audio_relative_path` | Yes | Source 无音频时为空 |
| `audio_file_size_bytes` | Yes | 无音频时为空 |
| `audio_sha256` | Yes | 无音频时为空 |
| `audio_duration_us` | Yes | 分析 WAV 时长 |
| `audio_sample_rate` | Yes | ready+有音频时固定 16000 |
| `audio_channels` | Yes | ready+有音频时固定 1 |
| `audio_to_source_offset_us` | Yes | `source_us = audio_us + offset` |
| `thumbnail_relative_path` | No | Thumbnail 相对路径 |
| `thumbnail_file_size_bytes` | Yes | ready 时必填 |
| `thumbnail_sha256` | Yes | ready 时必填 |
| `thumbnail_source_time_us` | Yes | Thumbnail 在 Source Timeline 上的位置 |
| `source_video_time_base_num` | Yes | Source 主视频 time_base 快照 |
| `source_video_time_base_den` | Yes | Source 主视频 time_base 快照 |
| `created_at` | No | UTC 创建时间 |
| `completed_at` | Yes | ready 后完成时间 |

约束：

```text
PRIMARY KEY(source_video_id)
FOREIGN KEY(source_video_id) → source_videos.id
FOREIGN KEY(project_id) → projects.id
UNIQUE(project_id)
CHECK(status IN ('processing', 'ready'))
CHECK(profile_version >= 1)
ready 时 Proxy + Thumbnail 必须完整
ready + Source 有音频时 Audio metadata 必须完整
```

`processing` 阶段允许输出 metadata 为空，不伪造未知值。

Migration 继续复用已冻结的：

```text
SQLite Connection.backup()
→ backup 成功
→ Alembic upgrade
```

---

# 7. Source Integrity Gate

开始 F03 前必须确认：

```text
F02 Source status = ready
Source 正式文件存在
Source file size 与 F02 记录一致
重新计算 Source SHA-256
重新计算值 == F02 source_videos.sha256
```

如果不一致：

```text
SOURCE_VIDEO_INTEGRITY_MISMATCH
```

F03 不自动修正 F02、不覆盖 Source、不继续预处理。

原因：F03/F04 以后所有证据都建立在这份 Source 上，不能在原片被系统外替换后静默继续。

---

# 8. Timebase / Mapping Contract

F03 完全属于：

```text
Source Domain
```

权威单位继续：

```text
integer microseconds
```

## 8.1 Proxy Mapping

F03 Proxy 不改变播放速度，只做转码/缩放并保留时间节奏。

Mapping 固定为：

```text
source_us = proxy_us + proxy_to_source_offset_us
proxy_us  = source_us - proxy_to_source_offset_us
```

`proxy_to_source_offset_us` 必须由实际 Source / Proxy timestamp 信息确定并持久化。

F04 禁止：

```text
假设 Proxy 0 == Source 0
用 frame_index / fps 代替 timestamp mapping
自己重新猜 offset
```

## 8.2 Audio Mapping

WAV 自身从第一个提取音频 sample 开始计时 0。

因此保存：

```text
source_us = audio_us + audio_to_source_offset_us
```

`audio_to_source_offset_us` 来自 Source 选中音频流的实际起始 timestamp；如果流没有可靠 start time，再按明确 fallback 规则使用 Source start。

Source 无音频时 Audio Mapping 为空。

## 8.3 VFR

F03 V1 支持 VFR 的原则：

```text
Proxy 不强制 CFR
保留 presentation timestamp 节奏
后续定位使用 timestamp
不使用 frame_index / fps 作为唯一权威定位
```

F03 必须测试：

```text
24 / 25 fps
24000/1001
30000/1001
VFR
source start_time != 0
Source→Proxy→Source round trip
```

Time Mapping 验收误差：

```text
整数微秒换算本身必须可逆；
FFmpeg/容器 timestamp 量化导致的媒体映射误差，目标 <= 1 ms；
若特定输入超过 1 ms，必须测试记录并在进入 F04 前重新评估，不得静默接受。
```

---

# 9. Processing / Recovery

正常流程：

```text
验证 F01 Project
→ 读取并验证 F02 ready Source
→ Source size + SHA-256 Integrity Gate
→ 确认不存在 processing/ready Preprocess
→ DB insert processing
→ 创建本 Source staging
→ generate_proxy_video()
→ extract_analysis_audio()（有音频时）
→ generate_thumbnail()
→ inspect_preprocess_assets()
→ 校验 Proxy/Audio/Thumbnail + Time Mapping
→ atomic rename staging/SOURCE → preprocess/SOURCE
→ DB metadata + ready
→ 返回 DTO
```

Final 发布前失败：

```text
只清理本 Source 的 F03 staging
+ 删除本次 processing row
```

Final 已发布但 DB ready 更新失败：

```text
保留 final Preprocess 资产
保留 processing row
→ PREPROCESS_FINALIZATION_PENDING
→ 下次启动 Recovery 补全
```

Recovery：

```text
processing + 合法 final
→ 重新 inspect
→ ready

processing + 只有系统明确拥有的 staging
→ 清理 staging + processing row

processing + 无文件
→ 删除 processing row

final 损坏 / unknown file / 归属不明确
→ 保留现场
→ 不递归删除
```

F03 Recovery 绝不能删除 F02 Source 原片。

---

# 10. API Contract

新增：

```text
GET  /api/projects/{project_id}/preprocess
POST /api/projects/{project_id}/preprocess
```

GET：

```text
无结果 → 200 null
ready → 200 SourcePreprocessDTO
```

POST：

```text
不需要上传文件
Project ID 已经能找到 F02 Source
```

成功：

```text
201 Created
```

已有 processing / ready：

```text
409 PREPROCESS_ALREADY_EXISTS
```

V1 POST 为同步本地任务：前端请求等待 FFmpeg 完成，不引入 Celery/Redis/WebSocket/SSE。

因为本地单用户、GPU/媒体任务并发默认 1，V1 先保证流程正确；页面显示“处理中，可能需要几分钟”的明确状态，不伪造百分比。

Controller 继续只做：

```text
HTTP → Business → Response
```

不能直接拼 FFmpeg、SQL、删除 staging 或计算 mapping。

---

# 11. SourcePreprocessDTO

前端 ready 状态至少获得：

```text
source_video_id
project_id
status
profile_version
source_sha256_snapshot
proxy_relative_path
proxy_file_size_bytes
proxy_sha256
proxy_duration_us
proxy_video_time_base_num / den
proxy_fps_num / den
proxy_to_source_offset_us
audio_relative_path
audio_file_size_bytes
audio_sha256
audio_duration_us
audio_sample_rate
audio_channels
audio_to_source_offset_us
thumbnail_relative_path
thumbnail_file_size_bytes
thumbnail_sha256
thumbnail_source_time_us
source_video_time_base_num / den
created_at
completed_at
```

UI 显示秒数/MB/FPS 可以格式化，但不能成为 DB 权威值。

---

# 12. Error Contract

新增建议错误码：

```text
PREPROCESS_SOURCE_REQUIRED
SOURCE_VIDEO_INTEGRITY_MISMATCH
PREPROCESS_ALREADY_EXISTS
PREPROCESS_FFMPEG_UNAVAILABLE
PREPROCESS_PROXY_FAILED
PREPROCESS_AUDIO_FAILED
PREPROCESS_THUMBNAIL_FAILED
PREPROCESS_VALIDATION_FAILED
PREPROCESS_MAPPING_INVALID
PREPROCESS_FINALIZATION_PENDING
PREPROCESS_FILE_MISSING
```

继续使用 F01/F02 已冻结 error envelope。

---

# 13. UI Contract

路由：

```text
/projects/:projectId/preprocess
```

左侧项目流程：

```text
01 项目总览      已完成
02 视频导入      已完成
03 视频预处理    当前开放
04 自动拉片      禁用
后续              禁用
```

页面状态：

## 无 Source

理论上正常流程不会进入，但直接 URL 可能发生：

```text
提示“请先完成视频导入”
→ 返回 02 视频导入
```

## Source Ready / 尚未预处理

显示：

```text
原片文件名
Source ID
时长
分辨率
FPS
文件大小

固定预处理 Profile：
Proxy H.264 / max 1280×720 / preserve timestamps
Audio WAV 16k mono PCM（有音频时）
Thumbnail JPEG

[开始视频预处理]
```

## Processing

显示：

```text
正在生成分析素材…
可能需要几分钟，请不要关闭后端服务。
```

V1 不伪造百分比。

## Ready

展示：

```text
Proxy
- path
- size
- duration
- FPS/timebase

Analysis Audio
- path / 或“原片无音频”
- size
- duration
- 16000 Hz / mono

Thumbnail
- path
- Source timestamp

Timeline Mapping
- Proxy 0 ↔ Source offset
- Audio 0 ↔ Source offset
- Source SHA snapshot
```

Ready 后不提供“重新预处理”按钮；如未来需要 Profile V2，先单独设计版本迁移/多版本策略。

---

# 14. 核心函数

F03 V1 保留 7 个核心后端函数：

```text
generate_proxy_video()
extract_analysis_audio()
generate_thumbnail()
inspect_preprocess_assets()
preprocess_source_video()
get_source_preprocess()
recover_source_preprocesses()
```

Controller 2 个：

```text
get_source_preprocess_api()
preprocess_source_video_api()
```

完整职责见：

```text
docs/features/F03-function-contracts.md
```

Hash、路径拼接、整数微秒转换、Fraction 解析等仍作为私有 helper / 公共 media-time utility，不扩成几十个核心函数。

---

# 15. Environment Gate

F03 首次正式依赖：

```text
FFmpeg 转码能力
libx264 encoder
AAC encoder
PCM WAV
JPEG output
```

用户 Windows 验收至少记录：

```powershell
ffmpeg -version
ffmpeg -hide_banner -encoders | findstr /I "libx264 aac pcm_s16le"
ffprobe -version
```

F03 不新增 PyTorch / OpenCV / Shot Detection 依赖。

---

# 16. 自动测试 / Regression

Backend 至少：

```text
Source SHA mismatch 阻止处理
Proxy 生成与 FFprobe 校验
小视频不放大
横屏 / 竖屏比例
有音频 / 无音频
16k mono WAV
Thumbnail 生成
24/25/24000-1001/30000-1001
VFR timestamp mapping
non-zero source start
Source↔Proxy round trip
Audio↔Source mapping
processing → ready
失败回滚
final+processing Recovery
unknown file 保护
GET null / ready
POST API
0002 → backup → 0003 Migration
```

共享代码改动必须完整回归：

```text
F01
F02
```

真实素材验收：

```text
至少 1 个真实短剧视频
建议再补 1 个竖屏视频
如果手头有 VFR 手机/平台视频，再用 1 个 VFR 样本
```

检查 Workspace：

```text
preprocess/SOURCE_xxx/proxy.mp4
preprocess/SOURCE_xxx/audio.wav（有音频时）
preprocess/SOURCE_xxx/thumbnail.jpg
```

确认 F02 original 完全未改变。

---

# 17. User Acceptance Gate

F03 开发完成后最多进入：

```text
READY_FOR_REVIEW
```

只有用户明确确认实际测试通过后，才允许：

```text
F03 → STABLE / FROZEN
```

然后才允许开始 F04 自动拉片。
