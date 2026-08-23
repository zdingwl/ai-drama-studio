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

文件：`engine/app/core/paths.py`

**业务作用**：确定 AI Drama Studio 的应用级数据目录。后续 `app.db`、应用日志和应用级配置都从这里定位。

**输入来源**：`AI_DRAMA_APP_DATA_DIR`（开发/测试覆盖）或 Windows `LOCALAPPDATA`。

**副作用**：无，只解析路径。

**明确不做**：不 mkdir、不创建 `app.db`、不初始化数据库、不创建 Project Workspace。

**测试结果**：`4 passed`。

---

# 3. `init_database()` — 已完成 / TESTED

文件：

```text
engine/app/core/database.py
engine/migrations/env.py
engine/migrations/versions/0001_create_projects.py
engine/tests/unit/test_database.py
```

**业务作用**：初始化 `<get_app_data_path()>/app.db`，并通过 Alembic `0001_create_projects` 创建 F01 唯一的业务表 `projects`。

**为什么使用 Alembic**：数据库从第一版就需要可追踪升级历史，开发期初始化和以后正式升级统一走 Migration，不维护第二套 `create_all()` 建表逻辑。

**明确不做**：不创建具体 Project、不创建 Workspace、不写 `project.json`、不插入项目记录、不创建后续 Feature 表。

**依赖**：

```text
SQLAlchemy==2.0.50
alembic==1.18.4
pytest==9.0.2
```

**测试结果**：`6 passed`。

覆盖 app.db 创建、字段一致、Alembic revision、重复初始化、非法 status、重复 workspace_path。

---

# 4. `generate_project_id()` — 已完成 / TESTED

文件：

```text
engine/app/core/ids.py
engine/tests/unit/test_ids.py
```

**业务作用**

为每个新项目生成一个稳定、与项目名称和路径无关的业务主键：

```text
PROJECT_<32位UUID4小写hex>
```

示例：

```text
PROJECT_86f767c94f2c4f96a1676ce36f615406
```

**为什么独立存在**

Project ID 后续会同时用于：

- `projects.id`；
- Workspace 目录名；
- 后续 Episode / Shot / Character 等数据归属的上游项目身份。

把 ID 规则集中在一个函数里，可以保证项目改名、素材变化、模型切换都不会改变项目身份。

**为什么使用 UUID4**

F01 是本地单用户工具，不需要为了排序能力引入 ULID、雪花算法等额外依赖。Python 标准库 UUID4 已足够简单，碰撞概率极低；SQLite `projects.id` 主键仍是最终冲突保护。

**输入**：无。

**输出**：字符串 `PROJECT_<UUID4_HEX>`。

**副作用**：无。

**明确不做**

- 不访问数据库；
- 不检查 ID 是否已存在；
- 不创建 Workspace；
- 不读写 `project.json`；
- 不使用项目名称、视频名称、时间戳或保存路径参与 ID 计算。

**测试结果**：

```text
3 passed
```

覆盖：

- 固定 `PROJECT_` 前缀；
- 后缀固定 32 位小写十六进制；
- 可解析且版本为 UUID4；
- 连续生成 5000 个 ID 无重复。

该函数没有新增第三方依赖。

---

# 5. `create_project_workspace()` — 下一函数 / PLANNED

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

**业务作用**：把用户的“新建项目”操作变成一个真正可以重新打开的 `ready` 项目。

流程：

```text
校验输入
→ generate_project_id()
→ DB 写 creating
→ create_project_workspace()
→ DB 改 ready
→ 返回项目
```

Workspace/project.json 创建失败时，不允许首页留下一个可正常显示和打开的假项目。

---

# 7. `list_projects()` — PLANNED

查询所有 `ready` 项目，供首页最近项目列表使用。只读数据库，不创建/修改 Workspace。

---

# 8. `open_project()` — PLANNED

**业务作用**：真正进入一个已有项目。

必须验证：

```text
DB 有项目
status = ready
Workspace 存在
project.json 存在且合法
manifest project_id == DB id
```

全部成功后更新 `last_opened_at`。禁止自动修改或删除损坏的用户 Workspace。

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

Controller 只负责 HTTP → Service → Response，不负责 Project ID、SQL、目录或 Manifest。

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

```text
先解释当前函数
→ 实现
→ 对应测试
→ PASS
→ 在 Feature 文档记录结果
→ 再进入下一个函数
```

不能因为“后面反正要用”就一次把 F01 所有函数提前写完。
