# AI Drama Studio — Project State

> 新对话恢复当前项目状态的第一入口。历史过程放 `docs/sessions/`。

## 当前状态

```text
Project: AI Drama Studio
Official Baseline: main
Current Working Branch: main（用户未要求切换/新建其它分支）
Current Feature: F01 — 创建项目
Feature Status: IN_PROGRESS
F01 Contract: CONFIRMED
Stable Features: none
Frozen Features: none
Business Code: started
Business DB/Migration: not started
```

`main` 是唯一正式 Source of Truth。

## Git 操作权限

未经用户明确要求，AI / Codex / Agent 不得新建、切换、删除、重命名分支，也不得擅自创建/关闭/合并/重定向 PR。

当前继续直接维护 `main`，不创建新分支。

---

# F01 当前权威文档

```text
docs/features/F01-create-project.md
docs/features/F01-function-contracts.md
```

简化版 F01 已由用户确认，不再等待 Contract 确认。

---

# F01 范围

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

# F01 数据设计

应用级 SQLite：

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

Workspace：

```text
<workspace_root>/<project_id>/project.json
```

F01 只创建 `project.json`，不提前创建媒体目录。

---

# F01 API

```text
GET  /api/health
GET  /api/projects
POST /api/projects
POST /api/projects/{project_id}/open
```

Controller 只负责 HTTP → Service → Response，不直接 SQL、不 mkdir、不写 `project.json`。

---

# F01 核心函数

```text
1. get_app_data_path()             [TESTED / PASS]
2. init_database()                 [NEXT]
3. generate_project_id()           [PLANNED]
4. create_project_workspace()      [PLANNED]
5. create_project()                [PLANNED]
6. list_projects()                 [PLANNED]
7. open_project()                  [PLANNED]
8. recover_creating_projects()     [PLANNED]
9. create_app()                    [PLANNED]
```

前端主要动作：

```text
apiRequest()
loadProjects()
submitCreateProject()
openProject()
```

---

# 已完成：get_app_data_path()

实现：

```text
engine/app/core/paths.py
```

测试：

```text
engine/tests/unit/test_paths.py
```

pytest 配置：

```text
pyproject.toml
```

函数语义：

- 测试/开发可用 `AI_DRAMA_APP_DATA_DIR` 覆盖；
- 正式 Windows 默认 `%LOCALAPPDATA%/AI Drama Studio`；
- 只解析路径，不 mkdir；
- 无法确定位置时明确失败，不偷偷写到当前目录。

实际测试：

```text
4 passed
```

测试容器 Python 为 3.13.5，仅证明当前纯路径函数逻辑通过；项目正式环境基线仍是 Python 3.11，F01 完整验收前必须在目标环境再跑完整测试。

---

# 当前代码/数据状态

已存在：

```text
engine/app/core/paths.py
engine/tests/unit/test_paths.py
pyproject.toml
```

尚未存在：

```text
app.db
projects Model
Migration
FastAPI app
Vue frontend
```

没有任何 F02 代码。

---

# 开发纪律

继续严格按：

```text
当前核心函数说明
→ 实现
→ 对应测试
→ PASS
→ Feature 文档记录
→ 下一个函数
```

不一次堆完整 F01。

业务代码、数据库表/字段、API Schema 必须有简体中文业务解释。

AI / Agent 最多把 F01 推进到 `READY_FOR_REVIEW`；只有用户明确验收通过后才能 `STABLE/FROZEN`。

---

# 下一步唯一动作

> 开发 `init_database()`：只完成 F01 的应用级 SQLite 初始化和 `projects` 表，不创建 Project Workspace，不写 project.json，不创建 F02 以后才需要的表。

不擅自新建分支，不实现 F02。

## 最近更新时间

- 日期：2026-08-23 16:18 +08:00
- 状态：用户已确认简化版 F01 Contract；F01 正式进入 IN_PROGRESS；第一个核心函数 `get_app_data_path()` 已实现并通过 4 个单测。
