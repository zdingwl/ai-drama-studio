# F02 — 上传原视频 Stable / Frozen Snapshot

Feature ID: F02  
Status: STABLE / FROZEN  
User Acceptance: PASSED  
Official Baseline: main  
Accepted At: 2026-08-24 10:44 +08:00

> 本文件是 F02 用户验收后的冻结快照。后续 Feature 可以兼容性扩展，但不得静默改变本文件中的 F02 对外 Contract。

## 1. 用户验收结论

用户明确确认：

```text
测试通过
```

因此：

```text
F02 = STABLE / FROZEN
```

F03 尚未开始。

---

## 2. 冻结业务能力

F02 固定提供：

```text
进入项目“视频导入”
→ 选择 / 拖拽本地原视频
→ 正式导入前允许重新选择
→ multipart 上传到本机 FastAPI
→ 1 MiB 分块写入 staging
→ 同步计算 file_size_bytes + SHA-256
→ FFprobe 校验并读取基础媒体信息
→ staging 发布为正式 Source 原片
→ source_videos.status = ready
→ 页面展示 Source metadata
→ 重启后仍可读取同一份 Source Video
```

F02 不负责：

```text
转码
proxy.mp4
audio.wav
thumbnail.jpg
VFR 精确映射
自动拉片
ASR
人物识别
Scene
AI
Source 替换/删除
多 Source / Episode
```

这些不得在回归修复中偷偷加入 F02。

---

## 3. Source Video Identity

冻结规则：

```text
1 Project → 0 或 1 个 Source Video
Source ID = SOURCE_<32位UUID4小写hex>
```

Source ID：

- 与原始文件名无关；
- 创建后稳定不变；
- 用于 `source_videos.id`；
- 用于 Workspace `source/SOURCE_<UUID>/`；
- 供 F03+ 下游引用。

ready Source 不允许被 F02 再次上传覆盖。

---

## 4. Workspace Contract

正式 Source：

```text
<project-workspace>/
├── project.json
└── source/
    └── SOURCE_<UUID>/
        └── original.<ext>
```

导入中：

```text
<project-workspace>/source/.staging/SOURCE_<UUID>/original.<ext>
```

冻结规则：

- DB 保存相对 Workspace 路径；
- 用户原文件名只保存用于展示/追溯；
- 内部正式文件名统一为 `original.<安全扩展名>`；
- 扩展名/MIME 不是媒体真实性依据；
- ready 原片不得被后续 Feature 覆盖；
- Recovery 不得递归删除未知用户文件。

---

## 5. Database Contract

Migration：

```text
0002_create_source_videos
```

业务表：

```text
source_videos
```

状态只允许：

```text
importing
ready
```

冻结核心字段：

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

冻结约束：

```text
PRIMARY KEY(id)
FOREIGN KEY(project_id) → projects.id
UNIQUE(project_id)
UNIQUE(relative_path)
CHECK(status IN ('importing', 'ready'))
ready 时核心媒体 metadata 必须完整合法
```

`importing` 阶段允许尚未产生的 SHA / size / duration / codec / width / height 等字段为空；不得用伪造值满足 NOT NULL。

---

## 6. Time / Media Metadata Contract

F02 Source Timeline 权威时间固定：

```text
duration_us           integer microseconds
source_start_time_us  integer microseconds / nullable
```

FPS 固定保存 rational：

```text
fps_num
fps_den
```

例如：

```text
30000 / 1001
```

禁止后续把 float 秒或 `29.97` 单独替换成唯一权威值。

FFprobe 主流选择规则：

```text
video:
排除 attached_pic
→ 优先 default video stream
→ 否则第一个普通 video stream

audio:
优先 default audio stream
→ 否则第一个 audio stream
→ 无音频允许
```

---

## 7. Import / Recovery Contract

正常导入冻结流程：

```text
验证 F01 Project ready + Workspace/project.json
→ 确认项目无 Source
→ 生成 Source ID
→ DB importing 并提交恢复锚点
→ staging 分块写文件 + size/hash
→ FFprobe
→ publish staging → final
→ DB metadata + ready
```

Final 发布前失败：

```text
只清理本 Source 的 staging
+ 删除本次 importing row
```

Final 已发布但 DB ready 最终提交失败：

```text
保留 final 原片
保留 importing row
→ 下次启动 Recovery 补全
```

禁止为了数据库整洁删除已完整发布的 Source 原片。

Recovery 冻结规则：

```text
importing + 合法 final
→ 恢复 ready

importing + 仅系统明确拥有的 staging
→ 安全清理 staging + importing

importing + 无文件
→ 删除 importing

未知文件 / 无法确认归属 / 损坏 final
→ 保留现场，不递归删除
```

---

## 8. API Contract

F02 Additive API 固定为：

```text
GET  /api/projects/{project_id}/source-video
POST /api/projects/{project_id}/source-video
```

GET：

```text
无 Source → 200 null
ready Source → 200 SourceVideoDTO
```

POST：

```text
multipart/form-data
file=<视频>
成功 → 201 Created
```

同一 Project 已存在 importing / ready Source：

```text
409 SOURCE_VIDEO_ALREADY_EXISTS
```

Controller 继续遵守冻结边界：

```text
HTTP → Business → Response
```

Controller 不直接 SQL、mkdir、Hash、FFprobe、publish 或 Recovery。

---

## 9. Core Function Contract

F02 冻结核心函数保持 6 个：

```text
generate_source_video_id()
copy_upload_to_staging()
probe_source_video()
import_source_video()
get_source_video()
recover_source_video_imports()
```

Controller 保持 2 个：

```text
get_source_video_api()
import_source_video_api()
```

详细职责仍参考：

```text
docs/features/F02-function-contracts.md
```

以后内部 helper 可以重构，但不得改变这里冻结的业务行为和安全边界。

---

## 10. Frontend Contract

正式路由：

```text
/projects/:projectId/source-video
```

冻结交互：

```text
无 Source
→ 选择 / 拖拽

已选择未导入
→ 文件名 / 大小 / MIME提示
→ 重新选择
→ 开始导入

导入中
→ 上传百分比
→ 已发送字节 / 总字节
→ 100% 后“正在读取媒体信息”

Ready
→ 文件名 / Source ID / 大小 / 时长 / 分辨率 / 视频编码 / FPS
→ 容器 / 音频编码 / 采样率 / 声道
→ SHA-256 / 相对路径
→ 不显示替换/再次上传入口
```

沿用 F01 已冻结的深色 StudioShell 与桌面可读字号。

项目流程顺序固定至少包含：

```text
01 项目总览
02 视频导入
03 视频预处理
04 自动拉片
...
```

F03 未实现前不可把“视频预处理”伪装成已完成。

---

## 11. Migration Safety Contract

已有 `app.db` 且 Alembic revision 落后于代码 head：

```text
SQLite Connection.backup()
→ backups/app_<UTC>_<old-revision>.db
→ backup 成功后 Alembic upgrade
```

全新 DB 不制造无意义备份；已经是 head 不重复备份。

后续修改共享 `init_database()` 必须同时执行 F01 + F02 回归。

---

## 12. Accepted Verification Baseline

开发阶段自动验证记录：

```text
27 passed
```

覆盖 F01 回归和 F02 核心/API/Recovery/Migration。

同时完成真实媒体技术链路：

```text
视频文件
→ multipart
→ staging
→ FFprobe
→ final
→ DB ready
→ GET
```

用户随后在 Windows 本机完成实际测试，并于 2026-08-24 明确回复：

```text
测试通过
```

因此 User Acceptance Gate = PASS。

---

## 13. Frozen Change Rule

从本快照开始，以下变化不能直接修改 F02：

```text
一个项目一份 Source 的规则
Source ID 格式
source_videos 核心字段语义
Source 正式路径规则
ready 后只读/不覆盖规则
整数微秒 / rational FPS
2 个 F02 API 的既有语义
Recovery 的“不误删原片/未知文件”规则
```

若未来必须改变：

```text
Change Request
→ 影响分析
→ 数据迁移 / V2 设计
→ 用户明确批准
→ 实现
→ F01 + F02 回归
```

兼容性的新增字段、读取能力或 F03 下游派生资产可以正常扩展，但不得静默改变上述 Contract。
