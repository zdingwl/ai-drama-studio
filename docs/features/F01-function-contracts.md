# F01 — 核心函数职责说明（简化版）

> 目标：让人一眼看懂每个核心函数“为什么存在、做什么、不做什么”。
>
> F01 不再为简单 helper 建几十份 Function Contract。

---

# 1. 分层说明

## API / Controller

作用：

> 接收 HTTP 请求 → 调用业务函数 → 返回 HTTP 响应。

禁止：

- 直接写 SQL；
- 直接创建目录；
- 直接写 `project.json`；
- 在 Controller 里复制 `create_project()` 业务流程。

## Service / 业务函数

作用：

> 完成用户真正要做的一件事，例如“创建项目”“打开项目”。

允许协调数据库和文件系统，但必须把关键安全边界写清楚。

## 小 helper

例如字符串 trim、日期显示、JSON dumps、简单 Path 拼接。

这些函数：

- 名字清楚；
- 必要时写中文注释；
- 有逻辑风险时写单测；
- 不再单独占一大段项目规格。

---

# 2. 后端核心函数

## 2.1 `get_app_data_path()`

**它干嘛**

找到 AI Drama Studio 自己的应用数据目录，`app.db` 就保存在这里。

Windows 默认：

```text
%LOCALAPPDATA%/AI Drama Studio/
```

**谁调用**

`init_database()`。

**它不干嘛**

- 不创建项目；
- 不建表；
- 不创建 Workspace。

**主要测试**

- 默认 Windows 路径正确；
- 测试环境可以覆盖目录；
- 不污染真实用户数据。

---

## 2.2 `init_database()`

**它干嘛**

初始化应用 SQLite `app.db`，确保 `projects` 表存在且数据库可以正常使用。

**为什么需要**

项目列表、创建项目和打开项目都必须先有数据库。

**它负责**

- 创建应用数据目录；
- 建立 SQLAlchemy Engine / Session；
- 执行 F01 初始 Migration。

**它不负责**

- 创建任何具体 Project；
- 创建视频/Shot/人物表；
- 初始化 FFmpeg、CUDA 或 AI 模型。

**主要测试**

- 第一次运行可以创建数据库；
- 第二次运行不会重复破坏数据库；
- `projects` 表存在。

---

## 2.3 `generate_project_id()`

**它干嘛**

生成项目永久唯一 ID：

```text
PROJECT_<UUID4_HEX>
```

**为什么不使用项目名称**

因为项目可以重名、可以包含中文和特殊字符，后续还可能改名。

**它不负责**

- 查数据库；
- 创建目录；
- 保存项目。

**主要测试**

- 格式正确；
- 多次生成不重复。

---

## 2.4 `create_project_workspace()`

**它干嘛**

创建某个 Project 对应的本地文件夹，并写入 `project.json`。

输入至少包含：

```text
project_id
name
source_language
target_language
target_region
workspace_root
```

输出：

```text
workspace_path
```

生成：

```text
<workspace_root>/<project_id>/project.json
```

**安全边界**

如果写入失败，只允许清理由本次 `project_id` 新创建的半成品目录。

绝对禁止：

- 删除用户选择的 Workspace Root；
- 删除其它 Project；
- 覆盖已经存在的项目目录。

**主要测试**

- 默认路径成功；
- 中文路径成功；
- 无效/不可写路径失败；
- `project.json` 内容正确；
- 失败后不会误删其它目录。

---

## 2.5 `create_project()`

**它干嘛**

这是 F01 最核心的业务函数：真正完成一次“新建项目”。

流程：

```text
校验用户输入
→ generate_project_id()
→ 数据库写入 status=creating
→ create_project_workspace()
→ 成功后数据库改成 status=ready
→ 返回 Project
```

**为什么先写 `creating`**

如果软件创建到一半突然退出，下次启动能找到这条未完成记录并恢复/清理，而不是留下一个无法解释的半成品。

**它负责**

- 控制数据库事务；
- 调用 Workspace 创建；
- 创建失败时做安全清理；
- 最终只返回可用的 `ready` Project。

**它不负责**

- HTTP 状态码；
- 前端跳转；
- 视频上传；
- 未来业务目录。

**主要测试**

- 创建成功；
- 同名项目；
- 路径失败；
- Workspace 创建失败；
- 失败后没有 `ready` 假项目。

**正式代码中文注释示例**

```python
def create_project(data: CreateProjectRequest) -> Project:
    """
    创建一个新的 AI Drama Studio 项目。

    业务作用：
    - 生成稳定 Project ID；
    - 先保存 creating 状态；
    - 创建 Workspace 和 project.json；
    - 全部成功后才把项目标记为 ready。

    为什么先保存 creating：
    用于识别软件异常退出时留下的未完成项目，避免首页出现无法打开的假项目。

    安全边界：
    创建失败时只能清理由当前 project_id 新建的半成品，
    绝不能删除 Workspace Root 或其它项目目录。
    """
```

---

## 2.6 `list_projects()`

**它干嘛**

读取首页“最近项目”列表。

只返回：

```text
status = ready
```

排序：

```text
最近打开优先
→ 创建时间兜底
```

**它不负责**

- 自动修复项目；
- 删除找不到目录的项目；
- 创建 Workspace。

**主要测试**

- 空列表；
- 多项目排序；
- `creating` 不显示。

---

## 2.7 `open_project()`

**它干嘛**

用户真正进入一个已有项目之前，确认它现在仍然可以打开。

流程：

```text
数据库找到 Project
→ status 必须 ready
→ Workspace 存在
→ project.json 存在且能解析
→ project_id 一致
→ project_format_version 支持
→ 更新 last_opened_at
→ 返回 Project
```

**为什么不能只查数据库**

用户可能在 Windows 资源管理器里移动、删除或改坏项目文件夹。

**它不负责**

- 自动重建损坏项目；
- 修改 `project.json`；
- 删除损坏目录。

**主要测试**

- 正常打开；
- DB 无项目；
- Workspace 丢失；
- `project.json` 损坏；
- Project ID 不一致；
- 成功后 `last_opened_at` 更新。

---

## 2.8 `recover_creating_projects()`

**它干嘛**

软件启动时处理上次异常退出留下的 `status=creating` 项目。

简单规则：

```text
Workspace 存在
+ project.json 合法
+ project_id 一致
→ 改成 ready

否则
→ 删除 creating DB 记录
→ 只有明确属于当前 project_id 的半成品目录才允许清理
```

**为什么保持简单**

F01 只需要避免“假项目”和明显半成品，不建立完整项目修复系统。

**它不负责**

- orphan 管理后台；
- Repair UI；
- 猜测未知文件属于哪个项目。

**主要测试**

- 完整 creating 项目恢复 ready；
- 不完整项目清理；
- 不误删未知目录。

---

## 2.9 `create_app()`

**它干嘛**

创建 FastAPI 应用并注册 F01 的路由和启动逻辑。

启动时：

```text
init_database()
→ recover_creating_projects()
→ API Ready
```

**它不负责**

- 创建具体 Project；
- 视频处理；
- GPU/AI 模型初始化。

---

# 3. Controller / API

Controller 不需要复杂抽象，F01 项目业务只保留三个入口。

## 3.1 `list_projects_api()`

```text
GET /api/projects
```

**作用**

接收首页请求，调用 `list_projects()`，把结果返回前端。

**明确不做**

- 不写 SQL；
- 不检查/修复磁盘；
- 不创建项目。

---

## 3.2 `create_project_api()`

```text
POST /api/projects
```

**作用**

接收新建项目表单，调用 `create_project()`，成功后返回新项目。

成功：

```text
HTTP 201 Created
```

**明确不做**

- 不生成 Project ID；
- 不创建 Workspace；
- 不写 `project.json`；
- 不执行 SQL；
- 不做创建失败清理。

这些全部属于 `create_project()` 及其内部业务逻辑。

**代码注释示例**

```python
@router.post("/api/projects", status_code=201)
def create_project_api(request: CreateProjectRequest):
    """
    新建项目 HTTP 入口。

    只负责接收前端请求、调用 create_project() 并返回结果。
    Project ID、数据库、Workspace、project.json 和失败清理都不在 Controller 中实现。
    """
```

---

## 3.3 `open_project_api()`

```text
POST /api/projects/{project_id}/open
```

**作用**

接收“进入项目”的请求，调用 `open_project()`。

**明确不做**

- 不自己 `Path.exists()`；
- 不读 JSON；
- 不更新数据库。

---

## 3.4 `health_api()`

```text
GET /api/health
```

只用于确认后端在线，不做 FFmpeg/GPU/模型检查。

---

# 4. 前端核心动作

## 4.1 `apiRequest()`

统一调用 FastAPI、解析 JSON 和错误格式。

不负责页面跳转。

## 4.2 `loadProjects()`

首页加载时调用 `GET /api/projects`，保存项目列表和 loading/error 状态。

## 4.3 `submitCreateProject()`

用户点击“创建项目”：

```text
前端基础校验
→ POST /api/projects
→ 成功保存 currentProject
→ 进入 /projects/:id
```

创建中禁止重复点击。

## 4.4 `openProject()`

项目卡片点击或 `/projects/:id` 页面进入时：

```text
POST /api/projects/{id}/open
→ 成功才显示 Workspace
```

如果项目目录已经丢失，显示明确错误，不假装打开成功。

---

# 5. 不再单独规划的函数

以下类型以后可以自然写成小 helper，不需要项目级文档：

```text
trimProjectName()
formatLastOpenedAt()
resetForm()
jsonDumps()
buildPath()
closeDialog()
goBack()
```

原则：

> 重要函数讲透；简单函数写清楚；不要为了“单函数开发”人为制造几十层抽象。
