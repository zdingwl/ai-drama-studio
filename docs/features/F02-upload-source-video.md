# Feature 02 — 上传原视频（Upload Source Video）

Feature ID: F02  
Status: PLANNED / WAITING_USER_CONFIRMATION  
Official Baseline: main  
Stable Dependency: F01 — 创建项目（STABLE / FROZEN）

> F02 只负责把一份原始视频安全导入项目 Workspace，并读取/保存基础媒体元数据。
> 不做转码、Proxy、WAV、Thumbnail、自动拉片、ASR 或任何 AI。

---

# 0. 一句话目标

用户进入一个已经创建好的项目，选择原视频，系统把原始文件流式复制到该项目 Workspace，计算 SHA-256，用 FFprobe 验证确实是可读取的视频并保存基础媒体元数据；软件重启后仍能看到这份 Source Video。

---

# 1. F02 必须完成

```text
项目内“视频导入”页面
选择/拖拽本地视频
选择后可重新选择，真正导入前不锁定
大文件流式上传/复制，不整文件进内存
导入进度显示
稳定 Source Video ID
原片复制进项目 Workspace
SHA-256 + file size
FFprobe 基础媒体校验与元数据读取
source_videos 数据表
导入中断恢复
重启后 Source Video 仍存在
原片只读保护
F01 全量回归
真实短剧视频验收
```

---

# 2. F02 明确不做

以下全部属于 F03 或以后：

```text
FFmpeg 转码
proxy.mp4
audio.wav
thumbnail.jpg
Source ↔ Proxy timeline mapping
VFR 精确逐帧分析
自动拉片
人物识别
ASR
Scene
AI
Source Video 替换/删除
多集 Episode
多 Source Video
```

F02 不提前创建 Proxy、Audio、Thumbnail 目录或数据。

---

# 3. F01 冻结依赖

F02 只读取并扩展 F01，不修改 F01 V1 语义。

依赖：

```text
Project ID: PROJECT_<UUID4_HEX>
projects.workspace_path
projects.status = ready
project.json
POST /api/projects/{project_id}/open
正式 StudioShell 深色 UI
```

F02 不修改：

```text
F01 Project ID
projects 既有字段语义
project.json V1 字段语义
F01 API 路径/返回结构
F01 creating/ready 语义
```

---

# 4. Source Video V1 Contract

## 4.1 一个 Project 一个 Source Video

F02 V1 明确采用：

```text
1 Project
→ 0 或 1 个 ready Source Video
```

原因：当前 Feature Sequence 的后续 F03–F35 都以当前 Project 的唯一 Source Video 为生产入口，当前没有 Episode Feature。

F02 不实现“替换原片”。用户在点击正式导入前可以任意重新选择文件；一旦导入成功，Source Video 进入只读状态。

以后如果确实需要多集/替换 Source，必须作为显式 V2/新 Feature 设计，不能静默覆盖原片。

## 4.2 Source Video ID

```text
SOURCE_<32位UUID4小写hex>
```

例如：

```text
SOURCE_86f767c94f2c4f96a1676ce36f615406
```

ID 创建后永不因原文件名变化而改变。

---

# 5. Workspace Contract

F01 项目初始：

```text
<workspace>/
└── project.json
```

F02 导入成功后：

```text
<workspace>/
├── project.json
└── source/
    └── SOURCE_<UUID>/
        └── original.<ext>
```

数据库保存相对路径，例如：

```text
source/SOURCE_xxx/original.mp4
```

不保存绝对媒体路径作为 Source Asset Contract；绝对位置由 F01 `workspace_path + relative_path` 解析。

## 5.1 Staging

导入过程中：

```text
<workspace>/source/.staging/SOURCE_<UUID>/original.<ext>
```

流程完成后，同一文件系统内将整个 SOURCE staging 目录发布到最终目录。

规则：

- `source/.staging` 不是正式资产；
- 下游永远不能读取 staging；
- ready Source 不允许覆盖；
- 未知用户文件不能由 Recovery 递归删除。

## 5.2 文件名规则

用户原始文件名完整保存在 DB 的 `original_filename`。

磁盘正式文件统一叫：

```text
original.<安全扩展名>
```

这样中文、特殊字符、路径分隔符不会进入内部目录规则。

扩展名只用于保存和显示，不作为“是不是视频”的安全判断；真正校验由 FFprobe 完成。

---

# 6. Database Contract

新增 Migration：

```text
0002_create_source_videos
```

新增唯一业务表：

```text
source_videos
```

V1 字段：

| Field | Type | Nullable | 业务作用 |
|---|---|---:|---|
| `id` | TEXT PK | No | `SOURCE_<UUID4_HEX>` 稳定 Source ID |
| `project_id` | TEXT | No | 所属 F01 Project ID |
| `original_filename` | TEXT | No | 用户选择时的原始文件名，只用于显示/追溯 |
| `relative_path` | TEXT | No | 相对 Project Workspace 的正式原片路径 |
| `file_size_bytes` | INTEGER | No | 导入后的真实文件字节数 |
| `sha256` | TEXT | No | 原片内容 SHA-256，小写 hex |
| `status` | TEXT | No | `importing / ready` |
| `container_format` | TEXT | No | FFprobe format_name |
| `duration_us` | INTEGER | No | Source Timeline 权威时长，整数微秒 |
| `source_start_time_us` | INTEGER | Yes | FFprobe start_time 转整数微秒；未知可空 |
| `video_stream_index` | INTEGER | No | F02 选中的主视频流 index |
| `video_codec` | TEXT | No | 主视频流 codec_name |
| `width` | INTEGER | No | 编码视频宽度 |
| `height` | INTEGER | No | 编码视频高度 |
| `fps_num` | INTEGER | Yes | 主视频流 avg_frame_rate 分子 |
| `fps_den` | INTEGER | Yes | 主视频流 avg_frame_rate 分母 |
| `audio_stream_index` | INTEGER | Yes | 主音频流 index；无音频可空 |
| `audio_codec` | TEXT | Yes | 主音频流 codec_name |
| `audio_sample_rate` | INTEGER | Yes | 主音频流采样率 |
| `audio_channels` | INTEGER | Yes | 主音频流声道数 |
| `created_at` | DATETIME | No | Source 导入创建时间 |

约束：

```text
PRIMARY KEY(id)
UNIQUE(project_id)
UNIQUE(relative_path)
CHECK(status IN ('importing', 'ready'))
CHECK(file_size_bytes >= 0)
CHECK(duration_us > 0 when ready)
```

`UNIQUE(project_id)` 是 F02 V1 “一个项目一份 Source Video”的数据库保护。

---

# 7. FFprobe Contract

F02 只调用原生 FFprobe，不做 FFmpeg 转码。

命令目标等价于：

```text
ffprobe
→ show_format
→ show_streams
→ JSON
```

不使用 shell 拼字符串，必须使用 subprocess 参数数组，避免文件名注入。

## 7.1 主视频流选择

规则固定：

```text
排除 attached_pic
→ 优先 disposition.default = 1 的 video stream
→ 否则第一个普通 video stream
```

## 7.2 主音频流选择

```text
优先 disposition.default = 1 的 audio stream
→ 否则第一个 audio stream
→ 没有音频允许为空
```

## 7.3 必须通过的基础校验

导入 ready 前至少满足：

```text
文件大小 > 0
FFprobe 成功
存在主 video stream
width > 0
height > 0
duration_us > 0
```

没有音频不视为导入失败。

## 7.4 时间规则

F02 首次引入 Source 媒体时间数据，必须遵守 `docs/MEDIA_TIMEBASE_CONTRACT.md`：

```text
duration_us            integer microseconds
source_start_time_us    integer microseconds / nullable
fps                     rational num/den
```

禁止把 float 秒作为数据库唯一权威值。

F02 不负责 VFR 精确判断和 Source↔Proxy 映射；这属于 F03。

---

# 8. 导入流程 / 崩溃安全

正式导入：

```text
验证 Project ready + Workspace/project.json
↓
确认当前 Project 尚无 Source Video
↓
generate_source_video_id()
↓
DB insert status=importing
↓
创建 source/.staging/SOURCE_<id>/
↓
流式写 original.<ext>
同时计算 file_size_bytes + SHA-256
↓
flush / close
↓
FFprobe staging 文件
↓
校验媒体元数据
↓
同盘 rename staging SOURCE 目录 → final SOURCE 目录
↓
DB 更新 metadata + relative_path + status=ready
↓
返回 SourceVideoDTO
```

## 8.1 写文件失败

Final 尚未发布时：

```text
清理本 Source ID 的 staging
删除 importing row
返回明确错误
```

禁止删除 `source/` 根目录、其它 Source、未知文件。

## 8.2 Final 已发布但 DB ready 失败

```text
保留 final 原片
保留 importing row
返回 SOURCE_VIDEO_FINALIZATION_PENDING
```

下次启动 Recovery 重新 FFprobe/校验 final，成功后转 ready。

不能为了“数据库干净”删除已经成功落盘的原片。

## 8.3 启动 Recovery

`recover_source_video_imports()`：

```text
importing + 合法 final
→ 补 metadata / ready

importing + 只有本 Source staging
→ 安全删除 staging + importing row
→ 用户重新导入

importing + 什么都没有
→ 删除 importing row

出现未知文件 / 归属不明确
→ 保留现场 + 日志
```

F02 不实现断点续传；中断的浏览器上传由用户重新开始。

---

# 9. API Contract

F01 API 保持不变，F02 Additive 新增：

```text
GET  /api/projects/{project_id}/source-video
POST /api/projects/{project_id}/source-video
```

## 9.1 GET source-video

作用：页面加载/刷新后读取当前项目的 ready Source Video。

无 Source 时：

```json
null
```

HTTP 仍返回 `200`，前端直接进入空导入状态。

## 9.2 POST source-video

请求：

```text
multipart/form-data
file = 用户选择的视频
```

成功：

```text
201 Created
```

同一 Project 已存在 ready/importing Source：

```text
409 SOURCE_VIDEO_ALREADY_EXISTS
```

Controller 只负责：

```text
HTTP UploadFile
→ 调用 import_source_video()
→ Response
```

Controller 禁止自己 mkdir、写文件、跑 FFprobe、SQL、hash。

---

# 10. SourceVideoDTO

前端至少得到：

```text
id
project_id
original_filename
relative_path
file_size_bytes
sha256
status
container_format
duration_us
source_start_time_us
video_stream_index
video_codec
width
height
fps_num
fps_den
audio_stream_index
audio_codec
audio_sample_rate
audio_channels
created_at
```

UI 显示秒数/FPS 时只做格式化，不反写数据库权威值。

---

# 11. 错误码

F02 新增：

```text
SOURCE_VIDEO_ALREADY_EXISTS
SOURCE_VIDEO_EMPTY
SOURCE_VIDEO_FFPROBE_UNAVAILABLE
SOURCE_VIDEO_PROBE_FAILED
SOURCE_VIDEO_UNSUPPORTED
SOURCE_VIDEO_IMPORT_FAILED
SOURCE_VIDEO_FINALIZATION_PENDING
```

继续沿用 F01 error envelope：

```json
{
  "error": {
    "code": "SOURCE_VIDEO_UNSUPPORTED",
    "message": "选择的文件不是系统可读取的视频"
  }
}
```

HTTP 建议：

```text
422 EMPTY / PROBE_FAILED / UNSUPPORTED
409 ALREADY_EXISTS
503 FFPROBE_UNAVAILABLE
500 IMPORT_FAILED / FINALIZATION_PENDING
```

---

# 12. UI Contract

新增路由：

```text
/projects/:projectId/source-video
```

StudioShell 左侧：

```text
01 项目总览   已完成
02 视频导入   当前可进入
03 自动拉片   后续
...
```

> 这里的“自动拉片”仍然不能点击；F03 是视频预处理，项目流程文案在 F03 开发时再按最终产品导航统一细化。

## 12.1 无 Source 状态

页面包含：

```text
原视频导入标题
拖拽/选择视频区域
格式说明
“选择视频”按钮
```

文件选择使用系统浏览器文件选择器。

建议 accept：

```text
video/*,.mkv,.mov,.m4v,.avi,.ts,.m2ts
```

这只是 UI 过滤，不是后端信任边界。

## 12.2 已选择但未导入

显示：

```text
原始文件名
文件大小
浏览器 MIME（仅提示）
重新选择
开始导入
```

用户此时可以无成本换文件。

可选提供浏览器本地 object URL 预览；如果浏览器不支持该编码，不能因此判定视频非法。

## 12.3 导入中

显示：

```text
上传/复制进度百分比
已发送字节 / 总字节
当前文件名
```

前端使用原生 `XMLHttpRequest.upload.onprogress`，不为了进度单独引入 Axios。

文件字节达到 100% 后，如果后端仍在 FFprobe：

```text
正在读取媒体信息…
```

## 12.4 Ready

显示：

```text
文件名
文件大小
时长
分辨率
视频编码
FPS
音频编码
采样率 / 声道
SHA-256（缩略展示，可复制完整值）
Workspace 相对路径
```

明确提示：

```text
原片已锁定为 Source Video，不会被后续流程覆盖。
统一 Proxy/音频/缩略图将在 F03 视频预处理生成。
```

F02 Ready 后不显示“重新上传/替换”按钮。

---

# 13. 核心函数职责（精简版）

F02 不再把每个小 helper 都写成正式 Contract，只保留真正影响文件/DB/媒体边界的函数。

## 13.1 `generate_source_video_id()`

作用：生成稳定 `SOURCE_<UUID4_HEX>`。

禁止：SQL、文件、FFprobe。

测试：格式、UUID4、大批量不重复。

## 13.2 `copy_upload_to_staging(upload_file, staging_file)`

作用：分块读取上传内容并写入 staging，同时计算字节数与 SHA-256。

必须：

```text
chunked streaming
不调用 read() 一次吃完整文件
flush/close
```

返回：

```text
file_size_bytes
sha256
```

禁止：DB ready、Final rename、FFprobe。

## 13.3 `probe_source_video(path)`

作用：调用 FFprobe 并返回规范化 `SourceVideoMetadata`。

必须负责：

```text
选择主 video/audio stream
Decimal → integer microseconds
rational fps 解析
基础视频合法性校验
```

禁止：转码、修改源文件。

## 13.4 `import_source_video(project_id, upload_file)`

F02 核心业务总调度。

调用：

```text
F01 Project 验证
generate_source_video_id
DB importing
copy_upload_to_staging
probe_source_video
publish staging → final
DB ready
```

它负责决定 commit/rollback/recovery 边界。

禁止：在 Controller 复制这套逻辑。

## 13.5 `get_source_video(project_id)`

作用：返回项目当前 ready Source Video；无数据返回 None。

只读；不修改 last_opened_at、不跑 FFprobe。

## 13.6 `recover_source_video_imports()`

作用：应用启动时处理 F02 importing 残留。

只能清理系统明确拥有的 staging；Ready/Final 原片不能自动删除。

---

# 14. Controller

只新增 2 个：

```text
get_source_video_api()
import_source_video_api()
```

不要新增复杂 Media Controller 层。

---

# 15. 前端核心动作

只保留 4 个：

```text
fetchSourceVideo(projectId)
uploadSourceVideo(projectId, file, onProgress)
loadSourceVideo(projectId)
importSourceVideo(projectId, file)
```

其它格式化：

```text
formatBytes
formatDuration
formatFps
```

属于简单 UI helper，不写大篇 Function Contract。

---

# 16. Migration 安全前置

F02 会新增 `0002_create_source_videos`，因此首次对已经存在的 F01 `app.db` 做 Schema Upgrade。

按 `docs/DATA_RECOVERY_AND_MIGRATION_RULES.md`，F02 编码前必须补最小数据库升级备份：

```text
现有 app.db + 当前 revision != head
→ SQLite safe backup
→ %LOCALAPPDATA%/AI Drama Studio/backups/
→ 再执行 Alembic upgrade
```

备份只在确实有 pending migration 时执行，不在每次启动重复备份。

这是 F02 引入 0002 必须做的 P0-04 安全措施，不改变 F01 已冻结的 app.db 路径和业务字段语义。

共享 `init_database()` 因此发生修改时，必须跑完整 F01 Regression。

---

# 17. Environment Gate

F02 首次正式使用 Native FFprobe。

编码/验收必须记录目标 Windows 上：

```text
ffprobe -version
```

得到的精确版本/build，写入 `docs/ENVIRONMENT_BASELINE.md`。

后端仅新增必要 Python 依赖：

```text
python-multipart（用于 FastAPI multipart UploadFile）
```

正式编码时必须固定精确版本，不写 latest。

不安装：

```text
OpenCV
PyTorch
Whisper
Shot Detection
```

它们都不是 F02 需要。

---

# 18. 自动测试

## 18.1 Backend

至少覆盖：

```text
SOURCE ID 格式/唯一性
安全内部文件名
分块写入 size/hash 正确
0 字节文件拒绝
FFprobe JSON 解析
默认 video/audio stream 选择
无音频视频允许
无 video stream 拒绝
非法文件 Probe 失败后无 ready row/final file
正常导入 → ready DB + final source file
同 Project 第二次导入 → 409
GET 无 Source → null
GET Ready → DTO
staging 中断恢复
final 已发布 + importing → Recovery ready
未知文件不误删
```

## 18.2 F01 Regression

必须完整重跑 F01 冻结基线，包括：

```text
创建项目
项目列表
打开项目
重启恢复
固定语言/地区
CORS
Workspace/project.json
```

## 18.3 Frontend

至少覆盖：

```text
空导入状态
文件选择
拖拽
重新选择
无文件时不能开始导入
进度更新
100% 后显示“读取媒体信息”
导入成功显示 metadata
刷新路由仍能加载 Source Video
后端错误正确显示
已有 Source 时不显示第二次导入入口
```

---

# 19. 真实素材验收

使用一份真实短剧原视频，不只使用 1 秒测试视频。

建议验收：

```text
1. 打开 F01 已存在项目
2. 进入“视频导入”
3. 选择真实 MP4/MOV/MKV 原片
4. 导入前可以重新选择
5. 点击开始导入
6. 能看到进度，不出现页面假死
7. 完成后显示文件名/大小/时长/分辨率/编码/FPS/音频信息
8. Workspace 出现 source/SOURCE_xxx/original.ext
9. 不出现 proxy.mp4/audio.wav/thumbnail.jpg
10. 关闭前后端并重启
11. 再进入项目，Source Video 仍存在并显示 metadata
12. 尝试再次上传，系统明确阻止覆盖原片
13. 上传一个文本/损坏文件，必须失败且不能留下 ready Source
14. F01 创建/打开项目流程仍正常
```

如果用户确认上述流程无问题：

```text
F02 → STABLE / FROZEN
```

之后才能进入 F03。

---

# 20. 当前等待确认的关键设计

进入编码前请确认以下 10 点：

```text
1. F02 V1 一个 Project 只允许一个 Source Video
2. 导入成功后原片只读，不提供替换/删除
3. 原片复制进 Workspace，不只记录电脑外部路径
4. Source ID = SOURCE_<UUID4_HEX>
5. 正式路径 = source/<source_id>/original.<ext>
6. 浏览器开发阶段使用 multipart + 流式后端写入
7. F02 使用 FFprobe，只读取基础媒体信息，不转码
8. duration/start_time 使用整数微秒，FPS 使用 rational
9. F02 新增 source_videos 表和 0002 Migration
10. 0002 执行前先做安全 app.db backup
```

确认后：

```text
F02 Status → IN_PROGRESS
→ 先完成 Migration Backup Gate
→ 再按核心函数顺序开发
```
