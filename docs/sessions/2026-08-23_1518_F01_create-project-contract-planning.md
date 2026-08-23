# Session Handoff — F01 创建项目 Contract 规划

## 会话时间

```text
2026-08-23 15:18 +08:00
```

## 当前 Feature

```text
F01 — 创建项目
Status: PLANNED
Contract: DRAFTED / WAITING_USER_CONFIRMATION
Business Code: NOT_STARTED
Working Branch: main
```

## 本次目标

用户要求开始详细规划第一阶段开发，并明确需要“单函数”粒度。

本次没有开始写业务代码，没有创建新分支，没有实现 F02。

## 本次完成

创建：

```text
docs/features/F01-create-project.md
```

该文档已经把 F01 从业务目标拆到单函数级实现顺序，包括：

```text
Backend Foundation B01–B11
Project Validation / ID / Paths P01–P09
Manifest M01–M06
Repository R01–R07
Recovery / Service S01–S09
API A01–A06
Frontend API / Store F01–F11
Frontend UI U01–U09
```

每一个核心函数均定义：

- 单一职责；
- 文件建议位置；
- 输入；
- 输出/副作用；
- 对应测试。

## 本次核心架构建议

### 1. Global app.db

推荐使用应用级单 SQLite：

```text
%LOCALAPPDATA%/AI Drama Studio/app.db
```

F01 不采用“每个项目独立 project.db”。

理由：全局项目列表、未来共享 Actor Library、Migration/连接管理更简单；Workspace 通过 `project.json` 自描述，为未来导入/迁移保留能力。

### 2. Workspace

默认：

```text
%USERPROFILE%/AI Drama Studio Projects
```

项目目录：

```text
<workspace_root>/<project_id>/project.json
```

F01 只创建 `project.json`，不提前创建 source/proxy/shots 等目录。

### 3. Project ID

```text
PROJECT_<UUID4_HEX>
```

使用 Python 标准库，避免为 ID 增加第三方依赖。

### 4. Project Format

```text
project_format_version = 1
```

与 Alembic schema revision 分开。

### 5. Project Lifecycle

```text
creating → ready
```

创建同时写 DB + 文件系统，因此设计 startup recovery。

### 6. Atomic creation

```text
validate
→ DB creating commit
→ staging dir
→ project.json.tmp
→ atomic file replace
→ validate manifest
→ atomic staging→final rename
→ DB ready commit
```

进程中断后，启动时对 `creating` row 做恢复。

### 7. Browser development path selection

Electron 尚未接入，因此 F01 浏览器阶段不实现 native folder picker。

UI 允许：

```text
workspace_root 文本路径
```

空值使用后端默认；Electron 后续只负责填充同一字段，不改变 F01 API。

## Database 草案

`projects` 表字段：

```text
id
name
source_language_code
target_language_code
target_region_code
workspace_path
lifecycle_state
project_format_version
created_with_app_version
created_with_schema_revision
created_at
updated_at
last_opened_at
```

完整业务字段说明见 F01 文档 Database Dictionary。

## API 草案

```text
GET  /api/v1/health
GET  /api/v1/projects/defaults
GET  /api/v1/projects
POST /api/v1/projects
GET  /api/v1/projects/{project_id}
POST /api/v1/projects/{project_id}/open
```

不包含删除、重命名、归档、导入/导出。

## F01 明确不做

```text
Upload Video
FFprobe/FFmpeg
Episode
Asset
Shot
Character
Dialogue
Scene
Actor
Bible
Provider
AI/GPU
TTS/LipSync
Project Delete/Rename/Archive/Import/Export
Electron native folder picker
```

## P0 结论

```text
P0 Dependency: 部分适用
P0 Media Timebase: N/A
P0 Environment: Yes
P0 DB + File Recovery: Yes / 强适用
P0 Provider Job: N/A
```

## 当前用户需要确认的 9 个决策

```text
1. app.db 采用应用级单 SQLite，而不是每项目独立 DB。
2. 默认 Workspace Root = %USERPROFILE%/AI Drama Studio Projects。
3. Project ID = PROJECT_<UUID4_HEX>。
4. Workspace Final = <root>/<project_id>/。
5. F01 只创建 project.json，不提前创建媒体目录。
6. 浏览器开发阶段存储位置使用文本路径，不做原生目录选择器。
7. F01 暂不做删除/重命名/归档/导入导出。
8. project_format_version 初始值 = 1。
9. 生命周期仅 creating/ready，创建中断通过 startup recovery 解决。
```

## 当前状态

- `docs/PROJECT_STATE.md` 已更新；
- F01 尚未进入 IN_PROGRESS；
- 尚未安装依赖；
- 尚未创建 frontend/engine 业务代码；
- 尚未创建 app.db；
- 尚未创建 Alembic migration。

## 下一步唯一动作

> 用户审核并确认 `docs/features/F01-create-project.md` 第 31 节九个关键决策。
>
> 用户确认后，把 F01 改为 `IN_PROGRESS`，然后严格从 `B01 resolve_app_data_dir()` 开始，一函数一测试推进。

## Git 约束

用户已经明确：不要擅自新建分支。

因此后续除非用户另行明确要求：

```text
不创建分支
不切换分支
不创建 PR
不重定向 PR
```

当前继续使用 `main`。