# AI Drama Studio — Project State

> 新对话恢复当前项目状态的第一入口。历史过程放 `docs/sessions/`。

## 当前状态

```text
Project: AI Drama Studio
Official Baseline: main
Current Working Branch: main（用户未要求切换/新建其它分支）
Current Feature: F01 — 创建项目
Feature Status: PLANNED
F01 Contract: SIMPLIFIED / WAITING_USER_CONFIRMATION
F01 Function Responsibilities: SIMPLIFIED / WAITING_USER_CONFIRMATION
Stable Features: none
Frozen Features: none
Business Code: not started
Business DB/Migration: not started
```

`main` 是唯一正式 Source of Truth。

## Git 操作权限

未经用户明确要求，AI / Codex / Agent 不得新建、切换、删除、重命名分支，也不得擅自创建/关闭/合并/重定向 PR。

当前继续维护 `main`，不创建新分支。

---

# F01 当前权威文档

```text
docs/features/F01-create-project.md
docs/features/F01-function-contracts.md
```

F01 已从上一版“几十个函数/复杂恢复状态”重新瘦身。

核心原则：

> 重要函数讲透；简单函数写清楚；不为了架构完整提前制造复杂度。

---

# F01 当前范围

第一阶段只解决：

```text
创建项目
→ 保存项目
→ 首页能看到
→ 重启后还在
→ 能重新打开
```

不涉及视频、AI、Shot、人物、对白、Scene、演员、TTS、Lip Sync。

---

# F01 当前数据设计

## 数据库

一个应用级 SQLite：

```text
%LOCALAPPDATA%/AI Drama Studio/app.db
```

只建一张业务表：

```text
projects
```

字段：

```text
id
name
source_language
target_language
target_region
workspace_path
project_format_version
status
created_at
last_opened_at
```

不再在 F01 保存 `created_with_app_version`、`created_with_schema_revision`、`updated_at` 等非必要字段。

## Workspace

```text
<workspace_root>/<project_id>/project.json
```

F01 只创建 `project.json`，不提前创建未来媒体目录。

`project.json` 只保存项目基础字段，不保存模型、API、视频清单或 AI 结果。

---

# F01 当前 API

项目业务只保留三个接口：

```text
GET  /api/projects
POST /api/projects
POST /api/projects/{project_id}/open
```

另有：

```text
GET /api/health
```

Controller 只负责 HTTP → Service → Response，不直接 SQL、不 mkdir、不写 `project.json`。

---

# F01 当前核心函数规模

后端约 9 个核心函数：

```text
get_app_data_path()
init_database()
generate_project_id()
create_project_workspace()
create_project()
list_projects()
open_project()
recover_creating_projects()
create_app()
```

Controller：

```text
list_projects_api()
create_project_api()
open_project_api()
health_api()
```

前端主要动作：

```text
apiRequest()
loadProjects()
submitCreateProject()
openProject()
```

日期显示、表单 reset、JSON dumps、简单路径拼接等不再单独做项目级 Function Contract。

---

# F01 简单恢复规则

Project 状态只有：

```text
creating
ready
```

创建：

```text
DB creating
→ 创建 Workspace + project.json
→ 成功改 ready
```

启动恢复：

```text
找到 creating
→ Workspace + project.json 完整且 ID 一致：改 ready
→ 否则安全清理 creating 记录和明确属于该 project_id 的半成品目录
```

F01 不建立复杂 Recovery Framework、Repair UI 或 orphan 管理后台。

无法确认归属的未知用户文件禁止自动删除。

---

# 代码和数据库注释仍然是强制要求

瘦身不等于减少可理解性。

正式代码仍必须：

- 核心业务函数写简体中文 docstring；
- 说明业务作用、为什么这样做、安全边界和主要异常；
- SQLAlchemy 表/字段写中文业务说明；
- Migration 写中文说明；
- F01 文档维护 Database Dictionary。

---

# F01 测试只围绕真实用户场景

必须覆盖：

```text
创建成功
重启后仍存在
重新打开成功
同名项目不冲突
非法/不可写路径失败且不产生假项目
creating 脏记录重启后恢复或安全清理
```

---

# 当前待用户确认的 8 项

```text
1. 应用级单 SQLite app.db。
2. 默认 Workspace Root = %USERPROFILE%/AI Drama Studio Projects。
3. Project ID = PROJECT_<UUID4_HEX>。
4. F01 只创建 project.json，不提前创建媒体目录。
5. projects 表只保留当前 10 个必要字段。
6. 项目业务 API 只保留 list / create / open 三个。
7. F01 只做 creating / ready 简单恢复，不做复杂 Recovery Framework。
8. project_format_version = 1。
```

用户确认前：

```text
不得把 F01 改为 IN_PROGRESS
不得开始业务代码
不得实现 F02
```

---

# 新对话最短恢复路径

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/features/F01-create-project.md
→ docs/features/F01-function-contracts.md
→ 最新 F01 Session Handoff
```

---

# 下一步唯一动作

> 用户审核并确认 F01 简化版 Contract 的 8 项关键决策。确认后将 F01 改为 `IN_PROGRESS`，再从最小运行骨架和 `get_app_data_path()` / `init_database()` 开始编码；不擅自新建分支，不实现 F02。

## 最近更新时间

- 日期：2026-08-23 16:02 +08:00
- 状态：F01 已从过度拆分方案瘦身为最小可验收方案，仍未开始业务代码。
