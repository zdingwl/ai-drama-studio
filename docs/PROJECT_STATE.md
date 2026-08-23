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
Business DB/Migration: started
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

简化版 F01 已由用户确认。

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

只建一张业务表：`projects`。

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

# F01 核心函数进度

```text
1. get_app_data_path()             [TESTED / PASS]
2. init_database()                 [TESTED / PASS]
3. generate_project_id()           [TESTED / PASS]
4. create_project_workspace()      [NEXT]
5. create_project()                [PLANNED]
6. list_projects()                 [PLANNED]
7. open_project()                  [PLANNED]
8. recover_creating_projects()     [PLANNED]
9. create_app()                    [PLANNED]
```

前端主要动作尚未开始：

```text
apiRequest()
loadProjects()
submitCreateProject()
openProject()
```

---

# 已完成函数

## 1. `get_app_data_path()`

实现：`engine/app/core/paths.py`  
测试：`engine/tests/unit/test_paths.py`  
结果：`4 passed`。

## 2. `init_database()`

实现：

```text
engine/app/core/database.py
engine/migrations/env.py
engine/migrations/versions/0001_create_projects.py
```

测试：`engine/tests/unit/test_database.py`。  
结果：`6 passed`。

依赖：

```text
SQLAlchemy==2.0.50
alembic==1.18.4
pytest==9.0.2
```

## 3. `generate_project_id()`

实现：

```text
engine/app/core/ids.py
```

测试：

```text
engine/tests/unit/test_ids.py
```

业务规则：

```text
PROJECT_<32位UUID4小写hex>
```

函数只生成稳定 Project ID：

- 不访问数据库；
- 不创建目录；
- 不读写 `project.json`；
- 不使用项目名称、视频名称、路径或模型信息参与 ID 计算。

实际测试：

```text
3 passed
```

覆盖固定格式、UUID4 版本、连续 5000 次生成无重复。

该函数没有新增第三方依赖。

---

# 当前测试环境说明

当前工具执行环境为 Python 3.13.5；项目正式基线仍为 Python 3.11。当前单函数测试结果可以证明逻辑正确，但 F01 完整验收前必须在目标 Python 3.11 环境重跑全部测试。

---

# 当前代码/数据状态

已存在：

```text
engine/app/core/paths.py
engine/app/core/database.py
engine/app/core/ids.py
engine/migrations/env.py
engine/migrations/versions/0001_create_projects.py
engine/tests/unit/test_paths.py
engine/tests/unit/test_database.py
engine/tests/unit/test_ids.py
engine/requirements.txt
pyproject.toml
```

尚未实现：

```text
Project Workspace / project.json
Project create/list/open 业务
FastAPI app / Controller
Vue frontend
```

没有任何 F02 代码。

---

# 开发纪律

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

> 开发 `create_project_workspace()`：只负责根据已经确定的 Project ID 和项目基础信息创建 `<workspace_root>/<project_id>/project.json`，重点测试路径安全、Manifest 内容和失败清理；不写 projects 业务记录、不实现 create/list/open API。

不擅自新建分支，不实现 F02。

## 最近更新时间

- 日期：2026-08-23 17:47 +08:00
- 状态：F01 持续 IN_PROGRESS；前三个核心函数已通过测试；下一函数 `create_project_workspace()`。
