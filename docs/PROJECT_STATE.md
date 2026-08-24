# AI Drama Studio — Project State

> 新对话恢复当前项目状态的第一入口。历史过程放 `docs/sessions/`。

## 当前状态

```text
Project: AI Drama Studio
Official Baseline: main
Current Working Branch: main（用户未要求切换/新建其它分支）
Current Feature: F02 — 上传原视频
Feature Status: PLANNED
F02 Contract: DRAFTED / WAITING_USER_CONFIRMATION
F02 Function Contracts: DETAILED / WAITING_USER_CONFIRMATION
Business Code: NOT STARTED
F01 — 创建项目: STABLE / FROZEN
Stable Features: F01
Frozen Features: F01
Next After F02: F03 — 视频预处理（NOT STARTED）
```

`main` 是唯一正式 Source of Truth。

## Git 操作权限

未经用户明确要求，AI / Codex / Agent 不得新建、切换、删除、重命名分支，也不得擅自创建/关闭/合并/重定向 PR。

当前继续直接维护 `main`，不创建新分支。

---

# F01 冻结基线

F01 已由用户在 Windows 本机验收通过：

```text
F01 = STABLE / FROZEN
```

权威冻结快照：

```text
docs/features/F01-stable-snapshot.md
```

F02 可以 Additive 扩展，但不得静默改变 F01 的：

```text
Project ID
projects 既有字段语义
project.json V1
Workspace Root
F01 API
creating/ready
正式 StudioShell UI 基线
```

---

# F02 权威规划文档

```text
docs/features/F02-upload-source-video.md
docs/features/F02-function-contracts.md
```

其中：

```text
F02-upload-source-video.md
→ 负责 Feature 范围、数据、文件、API、UI、Recovery、测试和验收

F02-function-contracts.md
→ 负责把 6 个核心后端函数 + 2 个 Controller 的真实业务职责讲透
```

当前只完成 Contract 规划，没有写 F02 业务代码。

---

# F02 一句话目标

```text
选择原视频
→ 流式复制进 Project Workspace
→ SHA-256 / Size
→ FFprobe 验证并读取基础媒体信息
→ source_videos ready
→ 重启后仍可读取
```

F02 不做：

```text
转码
proxy.mp4
audio.wav
thumbnail.jpg
VFR 精确分析
自动拉片
ASR
人物/Scene/AI
```

这些属于 F03 或以后。

---

# F02 当前拟定 Source Contract

## Source ID

```text
SOURCE_<32位UUID4小写hex>
```

## V1 数量

```text
1 Project → 0 或 1 个 ready Source Video
```

一旦导入成功，Source 原片只读；F02 不提供替换/删除。

## Workspace

```text
<workspace>/
├── project.json
└── source/
    └── SOURCE_<UUID>/
        └── original.<ext>
```

导入 staging：

```text
<workspace>/source/.staging/SOURCE_<UUID>/original.<ext>
```

DB 只保存相对 Workspace 的媒体路径。

---

# F02 Database Draft

新增：

```text
0002_create_source_videos
source_videos
```

核心内容：

```text
Source ID / Project ID
原文件名
relative_path
file_size_bytes
sha256
importing / ready
container / duration_us / source_start_time_us
主 video stream / codec / width / height / fps rational
主 audio stream / codec / sample rate / channels
created_at
```

V1 使用 `UNIQUE(project_id)` 保证一项目一 Source。

---

# F02 API Draft

Additive 新增：

```text
GET  /api/projects/{project_id}/source-video
POST /api/projects/{project_id}/source-video
```

POST：`multipart/form-data` + `file`，成功 `201 Created`。

GET 无 Source：`200 null`。

Controller 继续遵守 F01 冻结职责：HTTP → Schema → Business → Response，不直接 SQL/文件/FFprobe/hash。

详细 Controller 职责见：

```text
docs/features/F02-function-contracts.md
```

---

# F02 核心函数 Draft

只保留真正影响文件/DB/媒体边界的 6 个核心函数：

```text
generate_source_video_id()
copy_upload_to_staging()
probe_source_video()
import_source_video()
get_source_video()
recover_source_video_imports()
```

并且只新增 2 个 Controller：

```text
get_source_video_api()
import_source_video_api()
```

用户已指出“仅列函数名和路由仍然看不懂”。因此当前正式要求是：

> 每个核心函数和 Controller 必须明确解释：真实业务作用、为什么存在、谁调用、输入、输出、DB/文件副作用、失败边界、明确禁止行为、测试。

上述 8 个入口的完整说明已写入：

```text
docs/features/F02-function-contracts.md
```

不再把简单格式化/helper 拆成大量正式 Contract。

---

# F02 文件安全 / Recovery Draft

```text
DB importing
→ staging 分块写文件 + SHA-256
→ close/flush
→ FFprobe
→ publish staging → final
→ DB ready
```

Final 未发布失败：清理本 Source staging + importing row。

Final 已发布但 DB ready 失败：保留 final + importing，启动 Recovery 完成，不删除已经落盘的原片。

Ready Source 不覆盖、不由缓存清理、不因后续 Feature 重跑替换。

---

# F02 Migration Safety Gate

F02 首次新增 `0002`，按 P0-04 / `DATA_RECOVERY_AND_MIGRATION_RULES.md`：

```text
检测 app.db 存在且有 pending migration
→ SQLite safe backup
→ %LOCALAPPDATA%/AI Drama Studio/backups/
→ Alembic upgrade
```

只在确实升级 Schema 时备份，不每次启动都备份。

这会修改共享 `init_database()` 内部安全实现，因此编码时必须完整跑 F01 Regression。

---

# F02 Environment Gate

F02 首次正式依赖 Native FFprobe。

编码/验收需要在目标 Windows 记录：

```text
ffprobe -version
```

并更新 `docs/ENVIRONMENT_BASELINE.md`。

Python 只计划新增 F02 必需的 multipart 支持依赖；不提前安装 OpenCV/PyTorch/Whisper。

---

# 当前等待用户确认的 10 项

```text
1. F02 V1 一个 Project 只允许一个 Source Video
2. 导入成功后原片只读，不提供替换/删除
3. 原片复制进 Workspace，不只记录外部电脑路径
4. Source ID = SOURCE_<UUID4_HEX>
5. 正式路径 = source/<source_id>/original.<ext>
6. 浏览器开发阶段使用 multipart + 流式后端写入
7. F02 使用 FFprobe，只读取基础媒体信息，不转码
8. duration/start_time 使用整数微秒，FPS 使用 rational
9. F02 新增 source_videos 表和 0002 Migration
10. 0002 执行前先做安全 app.db backup
```

用户确认后：

```text
F02 → IN_PROGRESS
→ Migration Backup Gate
→ Source ID / streaming / FFprobe
→ import/get/recovery
→ API
→ Vue 视频导入页
→ 自动测试 + F01 Regression
→ 真实短剧视频测试
→ READY_FOR_REVIEW
→ 用户验收
```

未经确认不开始 F02 业务编码，不进入 F03。

## 最近更新时间

- 日期：2026-08-24 09:10 +08:00
- 状态：F02 主 Contract 已起草；根据用户反馈补充了 6 个核心函数 + 2 个 Controller 的详细职责 Contract；仍等待用户审核确认后再编码。
