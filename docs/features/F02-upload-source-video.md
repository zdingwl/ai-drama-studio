# Feature 02 — 上传原视频（Upload Source Video）

Feature ID: F02  
Status: IN_PROGRESS / CONTRACT_CONFIRMED  
Official Baseline: main  
Stable Dependency: F01 — 创建项目（STABLE / FROZEN）
Detailed Functions: `docs/features/F02-function-contracts.md`

> 用户已确认 F02 主 Contract 和详细函数职责。F02 只负责安全导入一份 Source Video 并读取基础媒体元数据，不做 F03 的预处理，也不做任何 AI。

---

# 1. 一句话目标

```text
用户选择原视频
→ 流式写入 Project Workspace
→ 计算文件大小 + SHA-256
→ FFprobe 验证并读取基础媒体信息
→ source_videos = ready
→ 软件重启后仍可读取
```

---

# 2. F02 必须完成

```text
项目内“视频导入”页面
选择 / 拖拽本地视频
正式导入前允许重新选择
大文件流式写入，不整文件进内存
导入进度
稳定 Source Video ID
原片复制进 Project Workspace
SHA-256 + file size
FFprobe 基础视频验证和媒体元数据
source_videos 表
导入中断恢复
重启后仍存在
原片只读保护
F01 完整回归
真实短剧视频验收
```

明确不做：

```text
FFmpeg 转码
proxy.mp4
audio.wav
thumbnail.jpg
Source ↔ Proxy 映射
VFR 精确逐帧分析
自动拉片
人物识别
ASR
Scene
AI
Source Video 替换 / 删除
多 Episode
多 Source Video
```

---

# 3. F01 冻结依赖

F02 只做 Additive 扩展，不修改 F01：

```text
PROJECT_<UUID4_HEX>
projects 既有字段语义
project.json V1
Workspace Root
F01 API
projects creating / ready
StudioShell 正式 UI 基线
```

F01 冻结快照：`docs/features/F01-stable-snapshot.md`。

---

# 4. Source Video V1

## 4.1 数量

```text
1 Project → 0 或 1 个 Source Video
```

一个 Project 已存在 `importing` 或 `ready` Source 后，F02 不允许再次导入覆盖。

用户在点击“开始导入”前可以任意重新选择文件；一旦 ready，原片进入只读 Source Contract。

## 4.2 Source ID

```text
SOURCE_<32位UUID4小写hex>
```

ID 与原文件名无关，创建后稳定不变。

---

# 5. Workspace / File Contract

导入成功后：

```text
<workspace>/
├── project.json
└── source/
    └── SOURCE_<UUID>/
        └── original.<ext>
```

导入过程：

```text
<workspace>/source/.staging/SOURCE_<UUID>/original.<ext>
```

数据库只保存相对路径，例如：

```text
source/SOURCE_xxx/original.mp4
```

用户原始文件名保存在 `original_filename`；内部磁盘文件统一使用 `original.<安全扩展名>`，避免中文、特殊字符或路径符号影响内部路径。

扩展名只用于保存和展示，不作为“是不是视频”的判断；真实视频校验必须由 FFprobe 完成。

安全规则：

```text
ready Source 不覆盖
下游不得读取 .staging
未知用户文件不得被 Recovery 递归删除
后续 Feature 不得重编码覆盖 original.ext
```

---

# 6. Database Contract

Migration：

```text
0002_create_source_videos
```

新增表：

```text
source_videos
```

字段：

| Field | Nullable | 业务作用 |
|---|---:|---|
| `id` | No | `SOURCE_<UUID4_HEX>` |
| `project_id` | No | 所属 F01 Project |
| `original_filename` | No | 用户原始文件名 |
| `relative_path` | No | Workspace 相对正式路径 |
| `file_size_bytes` | Yes | 完整写入后得到；importing 时未知 |
| `sha256` | Yes | 完整写入后得到；importing 时未知 |
| `status` | No | `importing / ready` |
| `container_format` | Yes | FFprobe 后得到 |
| `duration_us` | Yes | FFprobe 后得到，整数微秒 |
| `source_start_time_us` | Yes | Source 起始时间，未知可空 |
| `video_stream_index` | Yes | 主视频流 index，ready 时必填 |
| `video_codec` | Yes | 主视频 codec，ready 时必填 |
| `width` | Yes | 视频宽度，ready 时 > 0 |
| `height` | Yes | 视频高度，ready 时 > 0 |
| `fps_num` | Yes | avg_frame_rate 分子 |
| `fps_den` | Yes | avg_frame_rate 分母 |
| `audio_stream_index` | Yes | 无音频可空 |
| `audio_codec` | Yes | 无音频可空 |
| `audio_sample_rate` | Yes | 无音频可空 |
| `audio_channels` | Yes | 无音频可空 |
| `created_at` | No | UTC 创建时间 |

为什么部分字段允许 NULL：

```text
DB importing 记录必须先于文件写入存在
↓
此时还不知道 SHA / size / duration / codec / width / height
↓
FFprobe 完成后才补齐
```

所以数据库规则是“**importing 可以缺媒体元数据；ready 必须完整**”，而不是在导入开始前伪造未知值。

约束：

```text
PRIMARY KEY(id)
FOREIGN KEY(project_id) → projects.id
UNIQUE(project_id)
UNIQUE(relative_path)
CHECK(status IN ('importing', 'ready'))
CHECK(file_size_bytes IS NULL OR file_size_bytes >= 0)
CHECK(ready 时 file_size / sha256 / format / duration / 主视频流 / codec / width / height 必须合法)
```

---

# 7. FFprobe Contract

F02 使用 Native FFprobe，只读取，不转码。

调用目标：

```text
ffprobe
→ show_format
→ show_streams
→ JSON
```

必须使用 subprocess 参数数组，禁止 shell 字符串拼接。

主视频流：

```text
排除 attached_pic
→ 优先 default video stream
→ 否则第一个普通 video stream
```

主音频流：

```text
优先 default audio stream
→ 否则第一个 audio stream
→ 没有音频允许为空
```

ready 前至少满足：

```text
文件大小 > 0
FFprobe 成功
存在普通 video stream
width > 0
height > 0
duration_us > 0
```

时间规则遵守 `docs/MEDIA_TIMEBASE_CONTRACT.md`：

```text
duration_us          integer microseconds
source_start_time_us integer microseconds / nullable
FPS                   rational num / den
```

F02 不负责 VFR 精确映射；F03 才做 Proxy/Audio 与 Source Timeline 映射。

---

# 8. 导入与 Recovery

正常流程：

```text
验证 F01 Project ready + Workspace/project.json
→ 确认项目尚无 Source
→ generate_source_video_id()
→ DB insert importing
→ 建立本 Source staging
→ copy_upload_to_staging()
→ 得到 size + SHA-256
→ probe_source_video()
→ staging SOURCE 目录发布到 final
→ DB 写 metadata + status=ready
→ SourceVideoDTO
```

Final 尚未发布时失败：

```text
只清理本 Source ID 的 staging
→ 删除本次 importing row
→ 返回明确错误
```

Final 已发布、DB ready 更新失败：

```text
保留 final 原片
保留 importing row
→ SOURCE_VIDEO_FINALIZATION_PENDING
→ 下次启动 Recovery 恢复
```

禁止为了让数据库“干净”删除已经完整落盘的原片。

启动 Recovery：

```text
importing + 合法 final
→ 重新校验 / 补 metadata / ready

importing + 只有明确归属本 Source 的 staging
→ 清理 staging + importing row

importing + 文件都不存在
→ 删除 importing row

未知文件 / 归属不明确 / final 已存在但损坏
→ 不删除用户现场
→ 保留记录并记日志
```

F02 不做浏览器断点续传；上传中断后由用户重新导入。

---

# 9. API Contract

Additive 新增：

```text
GET  /api/projects/{project_id}/source-video
POST /api/projects/{project_id}/source-video
```

GET：页面加载、刷新、重启后读取当前 ready Source；无 Source 返回 `200 null`。

POST：

```text
multipart/form-data
file=<用户选择的视频>
```

成功：`201 Created`。

同 Project 已存在 importing/ready Source：

```text
409 SOURCE_VIDEO_ALREADY_EXISTS
```

Controller 只做 HTTP 边界，不自己 SQL、mkdir、hash、FFprobe 或 Recovery。详细职责见 `F02-function-contracts.md`。

---

# 10. SourceVideoDTO

前端 ready 状态至少获得：

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

UI 可以格式化秒数/FPS，但不能把显示值写回成为权威数据。

---

# 11. 错误码

```text
SOURCE_VIDEO_ALREADY_EXISTS
SOURCE_VIDEO_EMPTY
SOURCE_VIDEO_FFPROBE_UNAVAILABLE
SOURCE_VIDEO_PROBE_FAILED
SOURCE_VIDEO_UNSUPPORTED
SOURCE_VIDEO_IMPORT_FAILED
SOURCE_VIDEO_FINALIZATION_PENDING
SOURCE_VIDEO_FILE_MISSING
```

继续使用 F01 冻结 error envelope。

---

# 12. UI Contract

路由：

```text
/projects/:projectId/source-video
```

左侧项目流程：

```text
01 项目总览   已完成
02 视频导入   当前开放
后续步骤       禁用
```

页面状态：

```text
无 Source
→ 拖拽 / 选择视频

已选择未导入
→ 文件名 / 大小 / MIME提示 / 重新选择 / 开始导入

导入中
→ 百分比 / 已发送字节 / 总字节
→ 字节 100% 后显示“正在读取媒体信息…”

Ready
→ 文件名 / 大小 / 时长 / 分辨率 / 视频编码 / FPS
→ 音频编码 / 采样率 / 声道
→ SHA-256 / Workspace 相对路径
→ 明确提示 Source 已锁定，不显示替换按钮
```

前端上传进度使用原生 `XMLHttpRequest.upload.onprogress`，不为了这一功能新增 Axios。

---

# 13. 核心函数

正式核心函数仍只有 6 个：

```text
generate_source_video_id()
copy_upload_to_staging()
probe_source_video()
import_source_video()
get_source_video()
recover_source_video_imports()
```

Controller 只有 2 个：

```text
get_source_video_api()
import_source_video_api()
```

它们的完整业务职责、输入输出、副作用、失败行为、禁止行为和测试要求统一见：

```text
docs/features/F02-function-contracts.md
```

简单路径解析、时间转换、格式化等只作为私有 helper，不升级成新的核心业务函数。

---

# 14. Migration Safety Gate

F02 是第一次升级用户已经使用过的 F01 `app.db`。

规则：

```text
全新数据库
→ 直接 Alembic → 0002
→ 不制造无意义备份

已有 app.db 且 current revision != head
→ SQLite Connection.backup()
→ <app-data>/backups/app_<UTC>_<old-revision>.db
→ 备份成功
→ Alembic upgrade

已经是 head
→ 不重复备份
```

禁止在数据库可能使用 WAL 时仅用普通文件复制代替 SQLite 一致性 backup API。

当前实现：

```text
engine/app/core/database.py
engine/migrations/versions/0002_create_source_videos.py
```

隔离工作副本已验证：

```text
fresh DB → 0002，无备份                    PASS
0001 DB → 先备份，再升级 0002              PASS
backup 保留原 F01 项目数据                 PASS
backup revision 仍为 0001                  PASS
升级后 F01 项目数据仍存在                  PASS
再次 init 不重复生成 backup                PASS
importing 可在 metadata 未知时先入库        PASS
ready 缺核心 metadata 会被 DB CHECK 拒绝   PASS
```

完整仓库测试和用户 Windows 目标环境测试仍需在后续 Gate 执行。

---

# 15. Environment Gate

F02 首次正式依赖 Native FFprobe。

目标 Windows 验收必须记录：

```text
ffprobe -version
```

并写入 `docs/ENVIRONMENT_BASELINE.md`。

Python 只允许新增 multipart 上传所必需依赖；不提前安装 OpenCV/PyTorch/Whisper/Shot Detection。

---

# 16. 自动测试与验收

Backend 至少覆盖：

```text
SOURCE ID
分块写入 size/hash
空文件
FFprobe JSON/流选择/时间/FPS
无音频视频
非法文件
正常导入
重复导入
GET null / ready
staging Recovery
final + importing Recovery
未知文件保护
Migration backup
```

共享数据库/API 改动必须完整跑 F01 Regression。

真实验收必须使用真实短剧视频，并检查：

```text
选择 / 重新选择
真实导入进度
metadata 正确展示
Workspace 原片路径正确
没有提前生成 proxy/audio/thumbnail
重启后仍存在
再次上传被阻止
损坏文件不会留下 ready Source
F01 创建/打开仍正常
```

只有用户明确确认测试通过后：

```text
F02 → STABLE / FROZEN
```

之后才能进入 F03。

---

# 17. 已确认关键设计

用户已确认：

```text
1. 一个 Project 一个 Source Video
2. ready 后原片只读，不提供替换/删除
3. 原片复制进 Workspace
4. Source ID = SOURCE_<UUID4_HEX>
5. final = source/<source_id>/original.<ext>
6. 浏览器开发阶段 multipart + 后端流式写入
7. F02 只用 FFprobe 读取基础媒体信息，不转码
8. duration/start_time 用整数微秒，FPS 用 rational
9. 新增 source_videos + 0002 Migration
10. pending Migration 前先安全备份 app.db
11. 6 个核心函数 + 2 个 Controller 的详细职责按 F02-function-contracts.md 执行
```

当前开发顺序：

```text
Migration Backup Gate       已开始并通过隔离验证
→ Source ID
→ Streaming Copy
→ FFprobe
→ Import / Get / Recovery
→ API
→ Vue 视频导入页
→ 自动测试 + F01 Regression
→ 真实短剧视频验收
```
