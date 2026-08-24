# AI Drama Studio — Project State

> 新对话恢复当前项目状态的第一入口。历史过程放 `docs/sessions/`。

## 当前状态

```text
Project: AI Drama Studio
Official Baseline: main
Current Working Branch: main（用户未要求切换/新建其它分支）
Current Feature: F02 — 上传原视频
Feature Status: IN_PROGRESS
F02 Contract: CONFIRMED
F02 Function Contracts: CONFIRMED
F02 Migration Backup Gate: IMPLEMENTED / ISOLATED TEST PASS
Business Code: STARTED
F01 — 创建项目: STABLE / FROZEN
Stable Features: F01
Frozen Features: F01
Next After F02: F03 — 视频预处理（NOT STARTED）
```

`main` 是唯一正式 Source of Truth。未经用户明确要求，不新建/切换/删除/重命名分支，不创建或操作 PR。

---

# F01 冻结基线

权威快照：

```text
docs/features/F01-stable-snapshot.md
```

F02 只能 Additive 扩展，不得静默改变 F01 的 Project ID、projects 既有字段语义、project.json V1、Workspace Root、F01 API、creating/ready 或正式 StudioShell UI 基线。

---

# F02 权威文档

```text
docs/features/F02-upload-source-video.md
docs/features/F02-function-contracts.md
```

用户已确认 F02 主 Contract、10 项关键设计、6 个核心函数和 2 个 Controller 的详细职责。

F02 目标：

```text
选择原视频
→ 流式写入 Project Workspace
→ SHA-256 / file size
→ FFprobe 验证 + 基础媒体元数据
→ source_videos ready
→ 重启后仍可读取
```

F02 不做转码、Proxy、WAV、Thumbnail、VFR 精确映射、自动拉片、ASR、人物/Scene/AI。

---

# F02 Source Contract

```text
1 Project → 0 或 1 个 Source Video
Source ID = SOURCE_<32位UUID4小写hex>
ready 后原片只读，不提供替换/删除
```

Workspace：

```text
<workspace>/
├── project.json
└── source/
    └── SOURCE_<UUID>/
        └── original.<ext>
```

Staging：

```text
<workspace>/source/.staging/SOURCE_<UUID>/original.<ext>
```

DB 保存相对路径，不覆盖 ready Source，不自动删除未知用户文件。

---

# F02 Database / Migration

新增：

```text
0002_create_source_videos
source_videos
```

状态：

```text
importing
ready
```

开发时发现并修正了一个 Contract 内部矛盾：

```text
DB importing 必须先于文件写入存在
→ 此时 SHA / size / FFprobe metadata 尚未知
```

因此 `file_size_bytes / sha256 / container_format / duration_us / video stream / codec / width / height` 等字段在 `importing` 阶段允许 NULL；数据库 CHECK 强制 `ready` 时核心媒体元数据必须完整合法。禁止为满足 NOT NULL 伪造未知值。

---

# Migration Backup Gate — 已实现

共享 `init_database()` 已增加：

```text
全新 DB
→ 直接 Alembic → 当前 head
→ 不创建无意义 backup

已有 app.db + current revision != head
→ SQLite Connection.backup()
→ <app-data>/backups/app_<UTC>_<old-revision>.db
→ backup 成功后 Alembic upgrade

已有 DB 已是 head
→ 不重复 backup
```

代码：

```text
engine/app/core/database.py
engine/migrations/versions/0002_create_source_videos.py
engine/tests/unit/test_database.py
engine/tests/unit/test_database_migration_f02.py
```

隔离工作副本实际验证：

```text
fresh DB → 0002，无 backup                  PASS
0001 → backup → 0002                       PASS
backup 保留 F01 Project 数据               PASS
backup revision = 0001                     PASS
升级后 F01 Project 数据仍存在              PASS
再次 init 不重复 backup                    PASS
importing 可先保存空 metadata              PASS
ready 缺核心 metadata 被 DB CHECK 拒绝     PASS
```

另执行针对性 pytest：

```text
3 passed
```

完整仓库 F01+F02 pytest 仍需在后续整体验证 Gate 执行。

---

# F02 核心函数

只保留 6 个：

```text
generate_source_video_id()
copy_upload_to_staging()
probe_source_video()
import_source_video()
get_source_video()
recover_source_video_imports()
```

Controller 只有：

```text
get_source_video_api()
import_source_video_api()
```

详细业务职责见 `docs/features/F02-function-contracts.md`，禁止 Controller 复制 SQL/文件/hash/FFprobe/Recovery 逻辑。

---

# F02 API Draft

```text
GET  /api/projects/{project_id}/source-video
POST /api/projects/{project_id}/source-video
```

GET 无 Source → `200 null`；POST multipart file 成功 → `201 Created`。

---

# Environment Gate

F02 首次正式依赖 Native FFprobe。目标 Windows 验收必须记录：

```text
ffprobe -version
```

并更新 `docs/ENVIRONMENT_BASELINE.md`。

Python 只新增 multipart 上传必需依赖；不提前安装 OpenCV/PyTorch/Whisper。

---

# 当前下一步

```text
Migration Backup Gate       DONE / isolated PASS
→ generate_source_video_id()
→ copy_upload_to_staging()
→ probe_source_video()
→ import / get / recovery
→ 2 个 API
→ Vue 视频导入页面
→ F02 自动测试 + F01 Regression
→ Windows 真实短剧视频验收
→ READY_FOR_REVIEW
→ 用户验收
```

F02 未通过用户验收前不得进入 F03。

## 最近更新时间

- 日期：2026-08-24 09:40 +08:00
- 状态：用户确认 F02 Contract；F02 已进入 IN_PROGRESS；0002 + Migration 前 SQLite 安全备份已实现并完成隔离验证，下一步开发 Source ID。
