# Feature 01 — 创建项目（Create Project）

> F01 已由用户确认，当前正式开发中。
>
> 原则：第一阶段只解决“创建项目、保存项目、重启后还能看到、还能打开”。
>
> Git：按用户要求直接维护 `main`，不得擅自新建/切换分支或 PR。

---

## 0. 当前状态

```text
Feature: F01 创建项目
Status: IN_PROGRESS
Contract: CONFIRMED
Business Code: STARTED
Project Format Version: 1
Working Branch: main
```

当前核心函数进度：

```text
[PASS] get_app_data_path()
[PASS] init_database()
[PASS] generate_project_id()
[NEXT] create_project_workspace()
```

---

# 1. F01 一句话目标

用户填写项目基础信息后，系统把项目保存到 SQLite，并创建独立项目文件夹和 `project.json`；软件关闭重启后，项目仍能在首页看到并重新打开。

---

# 2. F01 范围

必须完成：最小 Vue 3 前端、最小 FastAPI 后端、应用级 `app.db`、唯一 `projects` 表、创建项目、项目列表、打开项目、Workspace、`project.json`、简单 `creating` 恢复、中文业务注释和完整验收测试。

明确不做：视频上传、FFmpeg/FFprobe、Episode、Asset、Shot、人物、对白、Scene、演员库、AI/Provider、GPU、TTS、Lip Sync、项目删除/重命名/归档/导入导出、复杂 Repair UI、Electron。

F02 前不写任何“上传原视频”的真实业务逻辑。

---

# 3. 用户操作流程

```text
打开软件
→ 首页显示最近项目
→ 点击“新建项目”
→ 填写项目名称、语言、地区、保存位置
→ 点击创建
→ 保存 projects 记录
→ 创建 <workspace_root>/<project_id>/
→ 写 project.json
→ 状态改为 ready
→ 自动进入空项目工作区
```

重新启动后，首页仍显示之前项目；点击项目时验证 Workspace + `project.json` 后重新进入。

---

# 4. 页面范围

- `/`：最近项目 + `+ 新建项目`；
- 新建项目弹窗：项目名称、原片语言（可空）、目标语言、目标地区、存储位置（可空）；
- `/projects/:projectId`：只显示项目基础信息和“项目已创建”，F01 不提供真实上传按钮。

浏览器开发阶段存储位置使用文本路径输入；Electron 后续再接原生目录选择器。

---

# 5. 保存方式

应用数据库：

```text
%LOCALAPPDATA%/AI Drama Studio/app.db
```

测试可用 `AI_DRAMA_APP_DATA_DIR` 覆盖。

默认 Workspace Root：

```text
%USERPROFILE%/AI Drama Studio Projects/
```

Project ID：

```text
PROJECT_<UUID4_HEX>
```

Workspace：

```text
<workspace_root>/PROJECT_xxx/project.json
```

F01 只创建 `project.json`，不提前创建后续媒体目录。

---

# 6. `project.json` V1

```json
{
  "project_id": "PROJECT_86f767c94f2c4f96a1676ce36f615406",
  "project_format_version": 1,
  "name": "测试短剧",
  "source_language": "zh",
  "target_language": "en",
  "target_region": "US"
}
```

不保存 API Key、模型配置、视频清单、AI 结果、Alembic revision 或应用构建版本。

---

# 7. Database Dictionary

F01 只建一张业务表：`projects`。

| Field | Type | Nullable | Default | 业务作用 | Mutable By | Frozen |
|---|---|---:|---|---|---|---:|
| `id` | TEXT PK | No | - | 项目唯一业务 ID，创建后永久不变 | 创建项目 | Yes |
| `name` | TEXT | No | - | 用户看到的项目名称 | 未来显式改名功能 | Semantic |
| `source_language` | TEXT | Yes | NULL | 原片语言；空表示尚未确认 | 未来显式功能 | Semantic |
| `target_language` | TEXT | No | - | 目标语言 | 未来显式功能 | Semantic |
| `target_region` | TEXT | No | - | 本土化目标地区 | 未来显式功能 | Semantic |
| `workspace_path` | TEXT | No | - | 项目文件夹绝对路径 | 未来 relink 功能 | Yes |
| `project_format_version` | INTEGER | No | `1` | Workspace/project.json 格式版本 | Project migration | Yes |
| `status` | TEXT | No | `creating` | 创建状态，只允许 `creating/ready` | F01/recovery | Yes |
| `created_at` | DATETIME | No | now | 项目创建时间 | Never | Yes |
| `last_opened_at` | DATETIME | Yes | NULL | 最近一次成功打开项目时间 | open_project | No |

约束：

```text
PRIMARY KEY(id)
UNIQUE(workspace_path)
CHECK(status IN ('creating', 'ready'))
```

项目名称不唯一。

---

# 8. 创建与简单恢复

创建：

```text
收到创建请求
→ generate_project_id()
→ DB 写 status=creating
→ create_project_workspace()
→ 成功后 status=ready
```

失败时只能清理由本次函数刚创建且明确属于当前 `project_id` 的半成品目录，禁止删除 Workspace Root 或其它项目目录。

启动时 `recover_creating_projects()`：完整且 ID 一致则转 `ready`；明确不完整且归属可确认则安全清理；未知文件不自动删除。

F01 不做复杂 Recovery Framework、orphan 管理或 Repair UI。

---

# 9. API Contract

```text
GET  /api/health
GET  /api/projects
POST /api/projects
POST /api/projects/{project_id}/open
```

Controller 只负责 HTTP → 业务函数 → Response，禁止直接 SQL、mkdir、写 `project.json` 或生成 Project ID。

`POST /api/projects` 成功返回 `201 Created`。

初始错误码：

```text
PROJECT_NAME_REQUIRED
PROJECT_TARGET_LANGUAGE_REQUIRED
PROJECT_TARGET_REGION_REQUIRED
PROJECT_WORKSPACE_INVALID
PROJECT_CREATE_FAILED
PROJECT_NOT_FOUND
PROJECT_WORKSPACE_MISSING
PROJECT_MANIFEST_INVALID
```

---

# 10. 核心函数进度

```text
1. get_app_data_path()             [PASS]
2. init_database()                 [PASS]
3. generate_project_id()           [PASS]
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

详细职责见 `docs/features/F01-function-contracts.md`。

---

# 11. 中文注释要求

核心业务函数必须用简体中文 docstring 说明业务作用、为什么存在、主要输入/输出、副作用、安全边界和主要异常。

数据库 Migration 必须为表和字段写简体中文业务解释。Controller 必须明确写出“不负责什么”。

---

# 12. 测试与用户验收

最终至少覆盖：创建成功、重启仍存在、重新打开、同名项目、非法路径、`creating` 异常恢复。

Agent 完成开发后只能标记 `READY_FOR_REVIEW`；只有用户明确验收通过后才能 `STABLE/FROZEN`。

---

# 13. P0 / Freeze

- Dependency/Invalidation：F01 无上游业务 Feature；`project_id`、Workspace、Project Format 是未来下游 Contract；
- Media Timebase：N/A；
- Environment：适用；
- DB + File Recovery：适用，采用 F01 简化恢复；
- Provider Job：N/A。

F01 验收后冻结 Project ID 格式、projects 字段语义、`project_format_version=1`、Workspace 规则、`project.json` V1 基础字段、三个 Project API 基本语义、`creating/ready` 状态含义。

---

# 14. 当前实现记录

## `get_app_data_path()`

实现：`engine/app/core/paths.py`  
测试：`engine/tests/unit/test_paths.py`  
结果：`4 passed`。

## `init_database()`

实现：

```text
engine/app/core/database.py
engine/migrations/env.py
engine/migrations/versions/0001_create_projects.py
```

测试：`engine/tests/unit/test_database.py`。  
依赖：`SQLAlchemy==2.0.50`、`alembic==1.18.4`、`pytest==9.0.2`。  
结果：`6 passed`。

## 2026-08-23 — `generate_project_id()`

实现：

```text
engine/app/core/ids.py
```

测试：

```text
engine/tests/unit/test_ids.py
```

规则：

```text
PROJECT_<32位UUID4小写hex>
```

函数只生成 ID，不访问数据库、不创建 Workspace、不写 `project.json`，也不使用项目名称或路径参与 ID 计算。

实际测试：

```text
3 passed
```

覆盖格式、UUID4 版本、连续 5000 次生成无重复。

该函数未新增第三方依赖。

下一函数：

```text
create_project_workspace()
```
