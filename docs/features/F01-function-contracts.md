# F01 — 核心函数职责说明（简化版）

> 目标：让人一眼看懂每个核心函数“为什么存在、做什么、不做什么”。
>
> F01 不为简单 helper 建几十份 Function Contract。

---

## 1. 分层规则

### API / Controller

作用：HTTP Request → 调用业务函数 → HTTP Response。

禁止直接 SQL、mkdir、写 `project.json`、生成 Project ID，禁止把 `create_project()` 业务流程复制到 Controller。

### Service / 核心业务函数

完成用户真正需要的一件事，例如创建项目、打开项目。涉及 DB/文件时必须写清安全边界。

### 小 helper

trim、日期显示、JSON dumps、简单 Path 拼接等只要求名字清楚、必要中文注释和必要测试，不单独写大篇 Contract。

---

# 2. `get_app_data_path()` — 已完成 / TESTED

文件：

```text
engine/app/core/paths.py
```

**业务作用**

确定 AI Drama Studio 的应用级数据目录。后续 `app.db`、应用日志和应用级配置都从这里定位。

**为什么独立存在**

应用数据目录是全局基础路径，同时测试必须能改到临时目录。把这条规则集中在一个函数里，可以避免数据库、日志等模块各自猜路径。

**输入来源**

```text
AI_DRAMA_APP_DATA_DIR  # 开发/测试覆盖
LOCALAPPDATA            # Windows 正式默认
```

**输出**

`Path`，例如：

```text
C:\Users\xxx\AppData\Local\AI Drama Studio
```

**副作用**

无。只解析路径，不创建目录。

**明确不做**

- 不 mkdir；
- 不创建 `app.db`；
- 不初始化数据库；
- 不创建 Project Workspace。

**异常**

没有覆盖值且缺少 `LOCALAPPDATA` 时抛出明确 `RuntimeError`，不偷偷回退到当前工作目录。

**测试结果**

```text
4 passed
```

---

# 3. `init_database()` — 已完成 / TESTED

文件：

```text
engine/app/core/database.py
engine/migrations/env.py
engine/migrations/versions/0001_create_projects.py
engine/tests/unit/test_database.py
```

**业务作用**

初始化 F01 唯一的应用级 SQLite：

```text
<get_app_data_path()>/app.db
```

并通过 Alembic `0001_create_projects` 创建 F01 唯一的业务表 `projects`。

**为什么使用 Alembic，而不是临时 `create_all()`**

数据库从第一版开始就需要可追踪升级历史。开发期初始化和以后正式升级统一走 Migration，避免同一个 `app.db` 同时存在两套建表方式。

**实际职责**

- 应用数据目录不存在时创建；
- 固定数据库文件名为 `app.db`；
- 调用 Alembic 升级到当前 `head`；
- 重复调用保持幂等；
- 返回已经初始化完成的 `app.db` 路径。

**明确不做**

- 不创建具体 Project；
- 不创建 Project Workspace；
- 不写 `project.json`；
- 不插入项目记录；
- 不创建 Episode、Shot、Character 等后续 Feature 表。

**数据库注释**

`0001_create_projects.py` 已为表用途、字段意义、状态约束和 downgrade 边界写简体中文说明。

当前 `projects` 字段与 F01 Database Dictionary 一致：

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

**依赖**

```text
SQLAlchemy==2.0.50
alembic==1.18.4
pytest==9.0.2
```

记录在：

```text
engine/requirements.txt
```

**实际测试结果**

```text
6 passed
```

覆盖：

- 全新临时目录创建 `app.db`；
- 只出现 `alembic_version + projects`；
- projects 10 个字段完全一致；
- Alembic revision=`0001_create_projects`；
- 重复初始化安全；
- 非法 `status` 被数据库拒绝；
- 重复 `workspace_path` 被数据库拒绝。

当前测试容器 Python 为 3.13.5；项目正式基线仍是 Python 3.11，F01 完整验收前必须在目标 Python 3.11 环境再跑一次完整测试。

---

# 4. `generate_project_id()` — 下一函数 / PLANNED

生成：

```text
PROJECT_<UUID4_HEX>
```

不使用项目名称、视频名称或模型信息。测试格式和批量唯一性。

---

# 5. `create_project_workspace()` — PLANNED

**业务作用**

为一个已经确定 `project_id` 的项目创建：

```text
<workspace_root>/<project_id>/project.json
```

**输入**

项目 ID、项目名称、语言/地区、Workspace Root。

**副作用**

创建项目目录并写 `project.json`。

**安全边界**

失败时只能清理由本函数本次创建且明确属于当前 `project_id` 的目录；绝不能删除 Workspace Root 或其它项目目录。

---

# 6. `create_project()` — PLANNED

这是 F01 的核心业务函数。

**业务作用**

把用户的“新建项目”操作变成一个真正可以重新打开的 `ready` 项目。

**流程**

```text
校验输入
→ generate_project_id()
→ DB 写 creating
→ create_project_workspace()
→ DB 改 ready
→ 返回项目
```

**失败**

Workspace/project.json 创建失败时，不允许首页留下一个可正常显示和打开的假项目。

---

# 7. `list_projects()` — PLANNED

查询所有 `ready` 项目，供首页最近项目列表使用。只读数据库，不创建/修改 Workspace。

---

# 8. `open_project()` — PLANNED

**业务作用**

真正进入一个已有项目。

必须验证：

```text
DB 有项目
status = ready
Workspace 存在
project.json 存在且合法
manifest project_id == DB id
```

全部成功后更新 `last_opened_at`。

禁止自动修改或删除损坏的用户 Workspace。

---

# 9. `recover_creating_projects()` — PLANNED

应用启动时处理上次异常退出留下的 `status=creating` 项目。

V1 只做简单规则：完整则转 `ready`，明确不完整且目录归属可确认则清理；未知文件不自动删除。

不建立复杂 Recovery Framework 或 Repair UI。

---

# 10. `create_app()` — PLANNED

创建 FastAPI 应用，注册 `/api/health` 和三个 Project API，并在启动阶段调用数据库初始化和简单 `creating` 恢复。

不在本函数里实现创建项目业务。

---

# 11. Controller

Controller 只保留：

```text
health_api()
list_projects_api()
create_project_api()
open_project_api()
```

示例注释标准：

```python
@router.post("/api/projects", status_code=201)
def create_project_api(request: CreateProjectRequest):
    """
    新建项目 HTTP 入口。

    只负责接收前端请求、调用 create_project() 并返回结果。
    不负责生成 Project ID、创建目录、写 project.json 或执行 SQL。
    """
```

---

# 12. 前端主要动作

只要求：

```text
apiRequest()
loadProjects()
submitCreateProject()
openProject()
```

简单日期格式化、表单 reset 和 Router 返回不建立单独项目级 Contract。

---

# 13. 单函数开发纪律

当前核心函数按下面方式推进：

```text
先解释当前函数
→ 实现
→ 对应测试
→ PASS
→ 在 Feature 文档记录结果
→ 再进入下一个函数
```

不能因为“后面反正要用”就一次把 F01 所有函数提前写完。
