# Feature 01 — 创建项目（Create Project）

> F01 已由用户确认，当前正式进入开发。
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

当前实现进度：

```text
[PASS] get_app_data_path()
[PASS] init_database()
[NEXT] generate_project_id()
```

---

# 1. F01 一句话目标

用户填写项目基础信息后，系统把项目保存到 SQLite，并创建独立项目文件夹和 `project.json`；软件关闭重启后，项目仍能在首页看到并重新打开。

---

# 2. F01 只做这些

```text
创建项目
→ 保存项目
→ 首页显示项目列表
→ 打开项目
→ 重启后仍然存在
```

必须完成：

- 最小 Vue 3 前端；
- 最小 FastAPI 后端；
- 一个应用级 SQLite：`app.db`；
- 一张 `projects` 表；
- 创建项目；
- 项目列表；
- 打开项目；
- 一个项目对应一个 Workspace；
- Workspace 中写 `project.json`；
- 简单处理创建到一半异常退出的 `creating` 记录；
- 所有业务代码、数据库表和字段有简体中文业务说明；
- 完整测试后交给用户验收。

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

重新启动：

```text
关闭前端/后端
→ 再次启动
→ 首页仍显示之前项目
→ 点击项目
→ 检查 Workspace + project.json
→ 成功进入项目工作区
```

---

# 4. 页面范围

## `/` 项目首页

- 最近项目；
- `+ 新建项目`；
- 项目卡片显示名称、语言/地区、保存位置、最近打开时间。

## 新建项目弹窗

| 字段 | 必填 | 说明 |
|---|---:|---|
| 项目名称 | 是 | 用户看到的名称 |
| 原片语言 | 否 | 空表示尚未确认 |
| 目标语言 | 是 | 如 `en` |
| 目标地区 | 是 | 如 `US` |
| 存储位置 | 否 | 空使用默认路径 |

浏览器开发阶段使用文本路径输入；Electron 后续再加原生目录选择器。

## `/projects/:projectId` 空工作区

只显示项目名称、Project ID、目标语言/地区、Workspace 路径和“项目已创建”。

F01 不显示可工作的上传按钮。

---

# 5. 保存方式

## 应用数据库

```text
%LOCALAPPDATA%/AI Drama Studio/app.db
```

测试允许通过：

```text
AI_DRAMA_APP_DATA_DIR
```

覆盖应用数据目录，避免污染真实用户数据。

## 默认 Workspace Root

```text
%USERPROFILE%/AI Drama Studio Projects/
```

## Project ID

```text
PROJECT_<UUID4_HEX>
```

规则：创建后不改变；不使用项目名称生成；同名项目允许；项目文件夹直接使用 Project ID。

## Workspace

```text
<workspace_root>/
└── PROJECT_xxx/
    └── project.json
```

F01 只创建 `project.json`，不提前创建 source/proxy/shots/characters/scenes/generations 等后续目录。

---

# 6. project.json V1

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

SQLite 原生 COMMENT 能力有限，因此 Migration 中文说明 + 本 Database Dictionary 共同构成字段说明；后续增加 SQLAlchemy Model 时必须继续保持一致。

---

# 8. 创建与简单恢复

项目状态只使用：

```text
creating
ready
```

创建：

```text
收到创建请求
→ 生成 Project ID
→ DB 写 status=creating
→ 创建 Workspace
→ 写 project.json
→ 成功后 status=ready
```

如果创建目录或写 `project.json` 失败，只允许清理由本次函数刚创建且明确属于当前 `project_id` 的半成品目录，并删除对应 `creating` 记录；禁止删除用户选择的 Workspace Root 或其它项目目录。

启动时 `recover_creating_projects()`：

```text
Workspace 存在
+ project.json 合法
+ project_id 一致
→ 改 ready

否则
→ 清理未完成 DB 记录
→ 仅在明确属于该 project_id 时清理半成品目录
```

无法确认归属的未知用户文件不自动删除，只记录错误并保留现场。

F01 不做复杂 Recovery Framework、orphan 管理或 Repair UI。

---

# 9. API Contract

基础健康检查：

```text
GET /api/health
```

项目业务只保留三个接口：

```text
GET  /api/projects
POST /api/projects
POST /api/projects/{project_id}/open
```

- `GET /api/projects`：首页读取 `ready` 项目列表；
- `POST /api/projects`：接收新建项目表单，调用 `create_project()`；成功返回 `201 Created`；
- `POST /api/projects/{project_id}/open`：验证 DB、Workspace、project.json 后更新 `last_opened_at`。

Controller 只负责 HTTP → 业务函数 → Response，禁止直接 SQL、mkdir 或写 project.json。

统一错误格式：

```json
{
  "error": {
    "code": "PROJECT_WORKSPACE_INVALID",
    "message": "项目存储位置不可用"
  }
}
```

F01 初始错误码：

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

真实开发发现确有必要时再增加，不预建复杂错误体系。

---

# 10. 核心函数

后端控制在约 9 个核心函数：

```text
1. get_app_data_path()             [PASS]
2. init_database()                 [PASS]
3. generate_project_id()           [NEXT]
4. create_project_workspace()      [PLANNED]
5. create_project()                [PLANNED]
6. list_projects()                 [PLANNED]
7. open_project()                  [PLANNED]
8. recover_creating_projects()     [PLANNED]
9. create_app()                    [PLANNED]
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

日期显示、表单 reset、JSON dumps、简单路径拼接等 helper 不进入项目级 Function Contract。

详细职责见 `docs/features/F01-function-contracts.md`。

---

# 11. 中文注释要求

“单函数开发”重点是看得懂，不是拆得多。

核心业务函数必须用简体中文 docstring 说明：

- 这个函数解决什么业务问题；
- 为什么存在；
- 主要输入/输出；
- 是否修改 DB/文件；
- 安全边界；
- 主要异常。

Controller 必须明确写出“不负责什么”。

数据库 Migration 必须为表和字段写简体中文业务解释，不能只翻译字段名。

---

# 12. 测试与验收

F01 必须覆盖：

```text
创建成功
重启后仍存在
重新打开成功
同名项目不冲突
非法/不可写路径失败且不产生假项目
creating 脏记录重启后恢复或安全清理
```

用户最终验收步骤：

1. 启动前端和后端；
2. 首页能看到最近项目和新建项目；
3. 使用默认路径创建项目 A；
4. 自动进入空项目工作区；
5. 检查 app.db 中项目 A 为 ready；
6. 检查项目目录存在 project.json；
7. 关闭前后端再启动，项目 A 仍在；
8. 点击项目 A 能重新打开，last_opened_at 更新；
9. 创建同名项目，确认 ID 不同；
10. 使用无效路径创建，确认明确报错且不产生假项目；
11. 模拟 creating 记录，确认启动恢复或安全清理。

Agent 开发完成后只能标记 `READY_FOR_REVIEW`；只有用户明确验收通过后才能 `STABLE/FROZEN`。

---

# 13. P0 / Freeze

- Dependency/Invalidation：F01 无上游业务 Feature；`project_id`、Workspace、Project Format 是未来下游 Contract；
- Media Timebase：N/A；
- Environment：适用，正式验收前锁定 Python/Node/FastAPI/Vue/SQLAlchemy 等版本；
- DB + File Recovery：适用，但 F01 采用上述简化恢复，不建立复杂 Framework；
- Provider Job：N/A。

F01 验收后只冻结：

```text
Project ID 格式
projects 表字段语义
project_format_version = 1
Workspace = <root>/<project_id>/
project.json V1 基础字段
list/create/open 三个 Project API 的基本语义
creating / ready 状态含义
```

---

# 14. 当前实现记录

## 2026-08-23 — `get_app_data_path()`

实现：`engine/app/core/paths.py`  
测试：`engine/tests/unit/test_paths.py`

结果：

```text
4 passed
```

覆盖测试/开发覆盖路径、Windows 默认路径、空白覆盖值、缺少环境路径时明确失败，并确认函数本身不创建目录。

## 2026-08-23 — `init_database()`

实现：

```text
engine/app/core/database.py
engine/migrations/env.py
engine/migrations/versions/0001_create_projects.py
```

测试：

```text
engine/tests/unit/test_database.py
```

新增最小依赖：

```text
SQLAlchemy==2.0.50
alembic==1.18.4
pytest==9.0.2
```

记录：`engine/requirements.txt`。

数据库初始化统一走 Alembic，不使用临时 `create_all()`。

本地实际测试：

```text
6 passed
```

测试覆盖：

- 全新目录能创建 `app.db`；
- 只创建 `alembic_version` 和 `projects`；
- projects 10 个字段与 Database Dictionary 一致；
- revision=`0001_create_projects`；
- 重复调用安全；
- 非法 status 被拒绝；
- 重复 workspace_path 被拒绝。

当前测试容器为 Python 3.13.5；项目正式基线仍为 Python 3.11，F01 完整验收前必须在目标 Python 3.11 环境重跑全部测试。

下一函数：

```text
generate_project_id()
```
