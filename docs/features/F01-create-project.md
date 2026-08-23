# Feature 01 — 创建项目（Create Project）

> F01 简化版正式 Contract 草案。
>
> 原则：第一阶段只解决“创建项目、保存项目、重启后还能看到、还能打开”。
>
> 不为了后续 34 个 Feature 提前设计复杂架构。
>
> Git：当前按用户要求直接维护 `main`，不得擅自创建/切换分支或 PR。

---

# 0. 当前状态

```text
Feature: F01 创建项目
Status: PLANNED
Business Code: NOT_STARTED
Project Format Version: 1
Working Branch: main
```

## 一句话目标

用户填写项目基础信息后，系统把项目保存到 SQLite，并创建一个独立项目文件夹和 `project.json`；软件关闭重启后，项目仍能在首页看到并重新打开。

---

# 1. F01 只做这些

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
- 简单处理创建到一半异常退出的脏记录；
- 所有业务代码、表、字段都有简体中文注释；
- 完整测试后由用户验收。

---

# 2. F01 明确不做

```text
视频上传
FFmpeg / FFprobe
Episode
Asset
Shot
人物
对白
Scene
演员库
AI / Provider
GPU
TTS
Lip Sync
项目删除
项目重命名
项目归档
项目导入/导出
复杂项目修复工具
Electron
```

F02 之前不写任何“上传原视频”的真实逻辑。

---

# 3. 用户操作流程

```text
打开软件
→ 首页显示“最近项目”
→ 点击“新建项目”
→ 填写项目名称、语言、地区、保存位置
→ 点击创建
→ 系统保存数据库
→ 系统创建项目目录和 project.json
→ 创建成功
→ 自动进入空项目工作区
```

重新启动：

```text
关闭前端/后端
→ 再次启动
→ 首页仍然显示之前的项目
→ 点击项目
→ 检查项目目录和 project.json 仍存在
→ 成功进入项目工作区
```

---

# 4. 页面

## 4.1 项目首页 `/`

```text
AI Drama Studio

[ + 新建项目 ]

最近项目
┌────────────────────────────┐
│ 项目名称                    │
│ 中文 → 英语 / 美国           │
│ 保存位置                    │
│ 最近打开时间                │
└────────────────────────────┘
```

## 4.2 新建项目弹窗

| 字段 | 必填 | 说明 |
|---|---:|---|
| 项目名称 | 是 | 用户看到的项目名称 |
| 原片语言 | 否 | 可以为空，后续再识别 |
| 目标语言 | 是 | 例如 `en` |
| 目标地区 | 是 | 例如 `US` |
| 存储位置 | 否 | 留空使用默认路径 |

开发阶段浏览器不能稳定获得 Windows 原生目录选择结果，所以 F01 先使用文本路径输入；Electron 阶段再增加“选择文件夹”。

## 4.3 空项目工作区 `/projects/:projectId`

只显示：

```text
项目名称
Project ID
目标语言 / 地区
Workspace 路径

项目已创建。
```

F01 不显示可工作的“上传视频”按钮。

---

# 5. 项目保存方式

## 5.1 应用数据库

```text
%LOCALAPPDATA%/AI Drama Studio/app.db
```

开发/测试允许通过环境变量改变位置，避免污染真实数据。

## 5.2 默认项目目录

```text
%USERPROFILE%/AI Drama Studio Projects/
```

用户可以填写其它目录。

## 5.3 Project ID

```text
PROJECT_<UUID4_HEX>
```

例如：

```text
PROJECT_86f767c94f2c4f96a1676ce36f615406
```

Project ID：

- 创建后不改变；
- 不使用项目名称生成；
- 同名项目可以同时存在；
- 项目文件夹直接使用 Project ID。

## 5.4 Workspace

```text
<workspace_root>/
└── PROJECT_xxx/
    └── project.json
```

F01 只创建 `project.json`。

不要提前创建：

```text
source/
proxy/
shots/
characters/
scenes/
generations/
```

后面哪个 Feature 真正使用，哪个 Feature 再创建。

---

# 6. `project.json`

V1 只保存真正需要的基础信息：

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

暂时不保存：

- API Key；
- 模型配置；
- 视频清单；
- AI 结果；
- Alembic revision；
- 应用构建版本。

这些不是“创建项目”完成所必需的信息。

---

# 7. 数据库：只建一张表

表名：`projects`

| 字段 | 类型 | 可空 | 中文业务作用 |
|---|---|---:|---|
| `id` | TEXT PK | 否 | 项目唯一 ID，创建后不变 |
| `name` | TEXT | 否 | 用户看到的项目名称 |
| `source_language` | TEXT | 是 | 原片语言；空表示暂未确认 |
| `target_language` | TEXT | 否 | 目标语言 |
| `target_region` | TEXT | 否 | 本土化目标地区 |
| `workspace_path` | TEXT | 否 | 项目文件夹完整路径 |
| `project_format_version` | INTEGER | 否 | 当前项目文件格式版本，F01 固定为 `1` |
| `status` | TEXT | 否 | 创建状态，只用 `creating` / `ready` |
| `created_at` | DATETIME | 否 | 项目创建时间 |
| `last_opened_at` | DATETIME | 是 | 最近一次成功打开项目的时间 |

约束：

```text
PRIMARY KEY(id)
UNIQUE(workspace_path)
CHECK(status IN ('creating', 'ready'))
```

项目名称不唯一。

## 数据库注释要求

正式代码中的 SQLAlchemy Model 和 Migration 必须给表、字段写简体中文业务说明。

例如：

```python
class Project(Base):
    """项目基础信息表。只保存项目级基础资料，不保存视频、Shot、人物等后续业务数据。"""

    id = Column(
        String,
        primary_key=True,
        comment="项目唯一业务 ID。创建后永久不变，不使用项目名称生成。",
    )
```

SQLite 本身不能完整依赖数据库原生 COMMENT，所以本文件的字段字典 + SQLAlchemy 注释 + Migration 注释共同作为字段说明。

---

# 8. 创建项目的简单状态

只使用：

```text
creating
ready
```

流程：

```text
收到创建请求
→ 生成 Project ID
→ 数据库插入 status=creating
→ 创建 Workspace
→ 写 project.json
→ 全部成功
→ status=ready
```

如果创建目录或写 `project.json` 失败：

```text
删除本次创建的半成品项目目录（仅限系统刚生成的 project_id 目录）
→ 删除对应 creating 记录
→ 返回创建失败
```

禁止删除用户自己选择的 Workspace Root。

---

# 9. 简单异常恢复

软件启动时调用：

```text
recover_creating_projects()
```

只处理数据库里 `status=creating` 的项目。

规则：

```text
项目目录存在
+ project.json 合法
+ project_id 一致
→ 改成 ready

否则
→ 清理本次未完成项目记录
→ 如果存在明确属于该 project_id 的半成品目录，则清理该目录
```

F01 不做复杂 Repair UI、orphan 管理、恢复状态机。

如果发现无法确认是否属于本项目的未知用户文件：

> 不自动删除，记录错误并保留现场。

---

# 10. API：项目只需要 3 个业务接口

另有一个基础健康检查。

## 10.1 后端健康检查

```text
GET /api/health
```

作用：

> 前端确认 FastAPI 是否已经启动。

## 10.2 获取项目列表

```text
GET /api/projects
```

作用：

> 首页获取所有已经 `ready` 的项目，按最近打开时间排序。

## 10.3 创建项目

```text
POST /api/projects
```

作用：

> 接收新建项目表单，调用 `create_project()`，成功后返回新项目。

成功使用：

```text
HTTP 201 Created
```

## 10.4 打开项目

```text
POST /api/projects/{project_id}/open
```

作用：

> 用户点击项目卡片或进入 `/projects/:id` 时，检查数据库、项目目录和 `project.json` 是否正常；成功后更新 `last_opened_at`。

---

# 11. 统一错误格式

```json
{
  "error": {
    "code": "PROJECT_WORKSPACE_NOT_WRITABLE",
    "message": "项目存储位置不可写"
  }
}
```

F01 只需要这些主要错误：

| Code | 说明 |
|---|---|
| `PROJECT_NAME_REQUIRED` | 项目名称为空 |
| `PROJECT_TARGET_LANGUAGE_REQUIRED` | 目标语言为空 |
| `PROJECT_TARGET_REGION_REQUIRED` | 目标地区为空 |
| `PROJECT_WORKSPACE_INVALID` | 保存路径非法或不可写 |
| `PROJECT_CREATE_FAILED` | 创建项目失败 |
| `PROJECT_NOT_FOUND` | 数据库中没有这个项目 |
| `PROJECT_WORKSPACE_MISSING` | 项目文件夹不存在 |
| `PROJECT_MANIFEST_INVALID` | `project.json` 不存在、损坏或 ID 不一致 |

先保持简单，真实开发发现必须区分的新错误再增加。

---

# 12. F01 核心函数

详细说明见：

```text
docs/features/F01-function-contracts.md
```

后端核心函数控制在约 9 个：

```text
1. get_app_data_path()
2. init_database()
3. generate_project_id()
4. create_project_workspace()
5. create_project()
6. list_projects()
7. open_project()
8. recover_creating_projects()
9. create_app()
```

Controller/API 只是把 HTTP 请求转给这些业务函数，不自己写 SQL 或文件业务。

前端主要动作：

```text
1. apiRequest()
2. loadProjects()
3. submitCreateProject()
4. openProject()
```

简单格式化、表单 reset、日期显示等 helper 不进入项目级 Function Contract。

---

# 13. 代码注释标准

“单函数开发”重点是**看得懂**，不是拆得多。

核心业务函数必须有简体中文 docstring，例如：

```python
def create_project(data: CreateProjectRequest) -> Project:
    """
    创建一个新的 AI Drama Studio 项目。

    业务作用：
    1. 生成稳定 Project ID；
    2. 先在 projects 表记录 creating 状态；
    3. 创建项目 Workspace；
    4. 写入 project.json；
    5. 全部成功后把项目状态改为 ready。

    为什么先写 creating：
    如果软件在创建过程中异常退出，下次启动可以找到未完成项目并清理或恢复，
    避免首页出现一个实际上无法打开的“假项目”。

    安全边界：
    失败时只能清理由本函数刚创建、且明确属于当前 project_id 的目录，
    绝不能删除用户选择的 Workspace Root 或其它项目目录。
    """
```

Controller 示例：

```python
@router.post("/api/projects", status_code=201)
def create_project_api(request: CreateProjectRequest):
    """
    新建项目 HTTP 入口。

    本函数只负责接收前端请求、调用 create_project() 并返回结果。
    不负责生成 Project ID、创建目录、写 project.json 或执行 SQL。
    """
```

---

# 14. 测试：只围绕用户真正会遇到的问题

## 14.1 创建成功

```text
创建项目
→ projects 有 ready 记录
→ Workspace 存在
→ project.json 正确
→ 前端进入工作区
```

## 14.2 重启仍存在

```text
创建项目
→ 关闭前后端
→ 再启动
→ 项目列表仍存在
```

## 14.3 可以重新打开

```text
点击历史项目
→ Workspace/Manifest 正常
→ 打开成功
→ last_opened_at 更新
```

## 14.4 同名项目

```text
创建两个同名项目
→ 都成功
→ Project ID 不同
→ Workspace 不冲突
```

## 14.5 非法路径

```text
不可写/非法路径
→ 创建失败
→ 不出现 ready 项目
→ 不留下可被误认为正常项目的半成品
```

## 14.6 异常中断恢复

```text
模拟 DB status=creating
→ 重启
→ 完整项目恢复 ready
或
→ 不完整项目安全清理
```

---

# 15. 用户验收步骤

1. 启动前端和后端。
2. 首页能看到“最近项目”和“新建项目”。
3. 使用默认路径创建项目 A。
4. 确认进入空项目工作区。
5. 检查 `app.db` 中项目 A 为 `ready`。
6. 检查项目目录中存在 `project.json`。
7. 关闭前端和后端，再启动。
8. 项目 A 仍显示在首页。
9. 点击项目 A，可以重新打开。
10. 创建一个与项目 A 同名的项目，确认可以成功且 ID 不同。
11. 使用无效路径创建，确认给出明确错误且没有假项目。
12. 模拟一条 `creating` 脏记录，确认重启后可以恢复或安全清理。

Agent 完成开发测试后只能标记：

```text
READY_FOR_REVIEW
```

只有用户明确验收通过后才能：

```text
STABLE / FROZEN
```

---

# 16. F01 验收后冻结什么

只冻结真正会被 F02 依赖的内容：

```text
Project ID 格式
projects 表字段语义
project_format_version = 1
Workspace = <root>/<project_id>/
project.json V1 基础字段
3 个 Project API 的基本语义
creating / ready 状态含义
```

不冻结未来还没做的项目删除、改名、导入导出、缩略图等能力。

---

# 17. 当前待确认

当前简化方案的关键决策：

1. 使用应用级单 SQLite `app.db`。
2. 默认 Workspace Root = `%USERPROFILE%/AI Drama Studio Projects`。
3. Project ID = `PROJECT_<UUID4_HEX>`。
4. F01 只创建 `project.json`，不提前创建媒体目录。
5. `projects` 只保留本 Contract 的 10 个字段。
6. 项目业务 API 只保留 `list / create / open` 三个。
7. F01 只做 `creating / ready` 简单恢复，不做复杂 Recovery Framework。
8. `project_format_version = 1`。

确认后再把 F01 从 `PLANNED` 改为 `IN_PROGRESS` 并开始编码。
