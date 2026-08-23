# F01 — 单函数职责字典 V2（审核后）

> 本文档是 `F01-create-project.md` 的函数级执行规范。
>
> 目标不是“函数越多越专业”，而是：**重要函数职责清楚、调用关系清楚、副作用清楚、出错后知道谁负责。**
>
> 当前仍为规划阶段，业务代码未开始。

---

# 1. 本轮审核结论

上一版最大的问题不是注释少，而是**拆得太机械**。审核后做以下调整。

## 1.1 删除 / 合并

### 删除 `build_database_url()`

原因：它只是把 `app.db` Path 拼成 SQLAlchemy URL，没有独立业务语义。

新方案：作为 `create_database_engine()` 内部 C 级 helper / 表达式，不单独进入正式 Function Contract。

### 删除 `serialize_project_manifest()`

原因：统一 JSON 编码属于 `write_project_manifest_atomic()` 的内部实现细节，没有必要让 Service 感知“序列化”这一步。

### 合并 `build_project_workspace_path()` + `build_project_staging_path()`

新函数：

```text
build_project_paths(root, project_id) -> ProjectPaths
```

一次返回 staging/final 路径，避免 Service 两次拼路径后出现规则漂移。

### 删除 `get_project()` 这一整条“只查详情”调用链

上一版有：

```text
GET /projects/{id}
→ get_project_endpoint()
→ get_project()
→ fetchProject()
→ loadCurrentProject()
```

审核后删除。

原因：F01 的 Workspace 页面本质上就是“进入项目”。无论用户从最近项目卡片点击，还是直接刷新 `/projects/:id`，都应该真正验证 Workspace + Manifest。

新方案统一为：

```text
POST /projects/{id}/open
```

浏览器刷新也调用 open。

因此：

```text
last_opened_at = 最近一次成功进入项目 Workspace 的时间
```

刷新页面更新该时间是符合语义的，不值得为了避免一次时间更新维护两套打开逻辑。

### 删除正式 Contract 中的简单 UI helper

以下不再作为项目级 Function Contract：

```text
resetCreateForm()
formatProjectLocale()
formatLastOpenedAt()
goBackToProjects()
```

它们属于 C 级展示/helper：代码命名清楚、必要时写注释即可。

---

## 1.2 重命名

### `validate_workspace_root()` → `prepare_workspace_root()`

原因：旧函数不仅“校验”，还会创建目录和写临时探针文件。

有副作用的函数继续叫 `validate_*` 会误导开发者。

### `ensure_database_schema()` → `run_database_migrations()`

原因：该函数会真实修改/创建 SQLite Schema，应把副作用写进名字。

### Repository 状态函数改成业务动词

```text
insert_creating_project()   → add_creating_project()
mark_project_ready()        → set_project_ready()
touch_project_opened_at()   → set_project_last_opened_at()
delete_creating_project()   → delete_incomplete_project()
list_creating_projects()    → list_incomplete_projects()
```

名字直接表达“改了什么业务状态”。

---

## 1.3 分层修正

### `health_check()` 移出 Backend Foundation

它本质是 HTTP Endpoint，应该与其它 API Controller 放在一起。

### `create_app()` 不再负责启动业务

上一版 `create_app()` 同时：

```text
创建 FastAPI
+ Migration
+ Recovery
```

职责过重。

现在拆为：

```text
application_lifespan()
    ├ run_database_migrations()
    └ recover_interrupted_project_creations()

create_app()
    └ 只组装 FastAPI / Router / Exception Handler / lifespan
```

---

## 1.4 DB 事务边界修正

Repository **不再 commit**。

Repository 只：

```text
SELECT / INSERT / UPDATE / DELETE / flush
```

Service 决定什么时候：

```text
session.commit()
session.rollback()
```

为什么：项目创建同时跨 SQLite 和文件系统，**commit 的时机本身就是业务流程的一部分**。如果隐藏在 Repository 里，后面很难看懂“为什么此时 DB 已经落盘、此时还没落盘”。

---

## 1.5 创建失败回滚边界修正

旧版 `rollback_failed_creation()` 有机会在 final Workspace 已发布后删除 final，风险太大。

现在明确“发布点”：

```text
staging rename → final
```

发布前失败：

```text
可以安全清理当前 Project staging
+ 删除 creating DB row
```

发布后失败：

```text
禁止删除 final Workspace
禁止删除 creating DB row
保留给 startup recovery
返回 PROJECT_CREATE_FINALIZATION_PENDING
```

这条规则比“尽量回滚干净”更安全，因为不能为了数据库整洁误删已经成功写到正式目录的用户项目。

---

# 2. 函数等级

使用 `templates/FUNCTION_CONTRACT_TEMPLATE.md` 的三级规则。

## A 级

完整 Contract：

- 业务用例；
- Controller；
- DB/File 状态变化；
- Recovery；
- 发布/回滚。

## B 级

简化 Contract：

- Repository；
- Manifest read/validate；
- Frontend API；
- Store Action；
- 有业务语义的路径函数。

## C 级

不单独占文档：

- JSON dumps 参数；
- 日期显示；
- 表单 reset；
- 私有路径小 helper；
- 简单 Router back。

---

# 3. F01 审核后的调用链

## 3.1 应用启动

```text
ASGI
→ create_app()
→ application_lifespan()
    → run_database_migrations()
    → recover_interrupted_project_creations()
→ API Ready
```

## 3.2 创建项目

```text
CreateProjectDialog
→ Store.create_new_project()
→ frontend createProject()
→ POST /api/v1/projects
→ create_project_endpoint()
→ Service.create_project()
    → normalize input
    → resolve / prepare workspace root
    → generate project id
    → build project paths
    → assert paths unused
    → Repository.add_creating_project()
    → DB COMMIT #1
    → write project.json in staging
    → validate staging manifest
    → publish staging → final
    → validate final workspace
    → Repository.set_project_ready()
    → DB COMMIT #2
→ ProjectDTO
→ Router 进入 /projects/:id
```

## 3.3 打开 / 刷新项目

统一：

```text
项目卡片点击
或
/projects/:id 页面刷新/直接访问
→ Store.open_project_by_id()
→ frontend openProject()
→ POST /api/v1/projects/{id}/open
→ open_project_endpoint()
→ Service.open_project()
    → DB ready
    → Workspace + Manifest 校验
    → set last_opened_at
    → COMMIT
→ ProjectDTO
→ 显示空 Workspace
```

不再存在第二套 `GET project detail` 逻辑。

---

# 4. Infrastructure / Application

## INF-01 `resolve_app_data_dir()` — B级

**业务作用**  
确定 AI Drama Studio 自己保存 `app.db`、日志和应用配置的根目录。

**谁调用**  
数据库初始化和应用 bootstrap。

**输入**  
`AI_DRAMA_APP_DATA_DIR` 环境覆盖值；否则 Windows LocalAppData。

**输出**  
`Path`。

**副作用**  
无，只解析路径。

**禁止**  
不 mkdir、不建 DB、不执行 migration。

**测试**  
env override、Windows fallback、测试环境不污染真实用户目录。

---

## INF-02 `resolve_default_workspace_root()` — B级

**业务作用**  
确定用户创建项目时如果不填写存储位置，后端默认放到哪里。

**输出**  
默认 `%USERPROFILE%/AI Drama Studio Projects` 对应 Path。

**副作用**  
无。

**禁止**  
不创建目录、不测试写权限。

---

## INF-03 `create_database_engine(app_data_dir)` — B级

**业务作用**  
创建整个应用唯一的 SQLAlchemy Engine，统一连接 `app.db`。

**输入**  
应用数据目录。

**输出**  
SQLAlchemy Engine。

**内部 C级细节**  
拼 SQLite URL、Windows Path 转换等不再单独建 Contract。

**副作用**  
建立数据库访问能力；不建业务表。

**禁止**  
不执行 Alembic、不创建 Project。

**测试**  
临时目录可创建/连接 SQLite；中文/空格路径可用。

---

## INF-04 `get_db_session()` — B级

**业务作用**  
为一次请求提供受控 Session，并确保结束时关闭。

**重要规则**  
它**不自动 commit 业务事务**。

**原因**  
commit 何时发生由 Service 决定。

**测试**  
正常/异常请求后 Session 均关闭。

---

## INF-05 `run_database_migrations()` — A级

**业务作用**  
应用启动时把 `app.db` 升到当前代码要求的 Alembic Head。

**为什么独立**  
Migration 会修改数据库，必须与 `create_app()` 的“应用组装”职责分离。

**调用方**  
`application_lifespan()`。

**副作用**  
首次运行创建 DB Schema；未来版本可能执行真实 migration。

**F01 特殊规则**  
首次 `0001_create_projects` 没有历史 DB 可备份；未来已有 DB migration 必须遵守 backup rule。

**失败**  
Migration 失败时不启动依赖 DB 的业务 API，不能假装成功。

**测试**  
fresh DB、已在 head、migration failure。

---

## INF-06 `read_schema_revision()` — B级

**业务作用**  
读取当前 `app.db` 实际 Alembic revision，用于写入 Project 创建基线。

**输出**  
revision string。

**副作用**  
只读。

---

## INF-07 `application_lifespan()` — A级

**业务作用**  
负责“应用启动前必须完成哪些基础准备”，而不是处理 HTTP 请求。

**启动顺序**

```text
准备 app data directory
→ run_database_migrations()
→ recover_interrupted_project_creations()
→ API 可以提供业务服务
```

**关闭阶段**  
释放数据库/基础资源；F01 没有 AI 模型需要卸载。

**禁止**  
不创建任何具体 Project。

**测试**  
启动成功、migration 失败、recovery 单项目失败的隔离策略。

---

## INF-08 `create_app()` — A级

**业务作用**  
组装 FastAPI Application。

**只负责**  
- 注册 Router；
- 注册 `domain_error_handler`；
- 挂载 `application_lifespan`；
- 应用基础设置。

**明确不负责**  
不直接执行 SQL、不直接 recovery、不直接 mkdir。

**输出**  
FastAPI app。

---

# 5. Project Input / ID / Path

## PRJ-01 `generate_project_id()` — B级

**业务作用**  
生成稳定项目主键：

```text
PROJECT_<UUID4_HEX>
```

**禁止**  
不使用项目名、不读取文件名、不依赖 Provider。

**测试**  
格式、前缀、批量唯一性。

---

## PRJ-02 `normalize_project_name(name)` — B级

**业务作用**  
把用户输入的名称变成数据库真正保存的项目名。

**规则**  
trim 后 1–100 字符；项目名允许重复。

**禁止**  
不把项目名拿去生成目录名。

**异常**  
`PROJECT_NAME_REQUIRED`、`PROJECT_NAME_TOO_LONG`。

---

## PRJ-03 `normalize_language_code(code, required)` — B级

**业务作用**  
统一语言代码格式。

**为什么合并旧函数语义**  
Source/Target 都是语言 code，不需要为“source/target”各造一套 normalize。

**输入**  
code + 是否必填。

**输出**  
小写 code 或 None。

**注意**  
F01 只做格式与必填校验，不在这个函数内维护一份庞大的全世界语言数据库。

---

## PRJ-04 `normalize_region_code(code)` — B级

**业务作用**  
统一地区 code，例如 `us → US`。

**规则**  
目标地区必填；只做 V1 需要的格式校验。

---

## PRJ-05 `resolve_workspace_root(requested_root)` — B级

**业务作用**  
决定本次 Project 真正使用哪个父目录。

**逻辑**  
- 空 → `resolve_default_workspace_root()`；
- 非空 → 规范化为绝对 Path。

**副作用**  
无。

---

## PRJ-06 `prepare_workspace_root(root)` — A级

**业务作用**  
确保本次用户选择的 Workspace Root 可以真实承载项目。

**为什么叫 prepare 而不是 validate**  
它会有文件系统副作用：目录不存在时创建，并用临时探针验证写权限。

**输入**  
Workspace Root Path。

**输出**  
确认可用的 Path。

**副作用**  
- 可能创建 root；
- 创建并删除随机 probe file。

**禁止**  
- 不创建具体 Project 目录；
- 不删除 root 中已有内容；
- probe 必须清理。

**异常**  
路径是文件、无法创建、无写权限、probe 无法删除。

**测试**  
不存在目录、已存在目录、file-as-dir、只读、probe cleanup。

---

## PRJ-07 `build_project_paths(root, project_id)` — B级

**业务作用**  
一次性得到本次创建过程需要的所有关键路径。

**输出**  
`ProjectPaths`：

```text
staging_dir = <root>/.ai-drama-staging/<project_id>
final_dir   = <root>/<project_id>
manifest    = <final_or_staging>/project.json（由调用阶段选择）
```

实现时建议 `ProjectPaths` 只保存目录级路径，Manifest 文件名由 Manifest 模块统一定义，避免重复来源。

**副作用**  
无。

---

## PRJ-08 `assert_project_paths_unused(paths)` — B级

**业务作用**  
创建前保证同一 Project ID 对应的 staging/final 没有已有目录，避免覆盖。

**副作用**  
只读。

**禁止**  
发现冲突时绝不自动删除。

**异常**  
`PROJECT_CREATE_CONFLICT`。

---

# 6. Project Manifest

## MAN-01 `build_project_manifest(project_data)` — B级

**业务作用**  
从已经确定的 Project 数据构造 Project Format V1 的 `project.json` 内容。

**副作用**  
无。

**禁止**  
不读磁盘、不写 DB。

---

## MAN-02 `write_project_manifest_atomic(staging_dir, manifest)` — A级

**业务作用**  
把 `project.json` 安全写入 staging，确保中断时不会把半截 JSON 当正式 Manifest。

**流程**

```text
project.json.tmp
→ UTF-8 JSON write
→ flush/fsync/close
→ os.replace(tmp, project.json)
```

JSON 序列化是本函数内部 C 级实现，不再单独暴露 `serialize_*()`。

**副作用**  
写文件 / replace。

**失败保证**  
不能留下一个被正常读取逻辑接受的半文件。

**测试**  
中文、正常写入、写中断、replace failure、tmp cleanup。

---

## MAN-03 `read_project_manifest(workspace_dir)` — B级

**业务作用**  
读取 Workspace 的 `project.json`。

**输出**  
原始/typed Manifest。

**异常**  
missing / invalid JSON。

**副作用**  
只读。

---

## MAN-04 `validate_project_manifest(manifest, expected_project_id)` — B级

**业务作用**  
确认这个 Manifest 确实属于 DB 里的同一个 Project，并且格式版本可支持。

**检查**  
- 必填字段；
- Project ID；
- Project Format Version；
- 基本类型。

**副作用**  
无。

---

## MAN-05 `validate_project_workspace(workspace_dir, project_id)` — A级

**业务作用**  
提供“Project Workspace 是否真的可打开”的统一检查入口。

**调用**

```text
目录 exists/is_dir
→ read_project_manifest()
→ validate_project_manifest()
```

**调用方**  
- 创建完成发布后的最终确认；
- 打开项目；
- startup recovery。

**禁止**  
不更新 `last_opened_at`，不自动修改 Manifest。

---

# 7. Repository — 只负责 DB，不负责事务提交

> 统一规则：Repository 可以 `flush`，**不得隐藏 `commit/rollback`**。事务边界由 Service/Recovery 决定。

## DB-01 `add_creating_project(session, project)` — B级

**业务作用**  
把新项目以 `creating` 状态加入当前 DB transaction。

**DB 副作用**  
INSERT / flush；不 commit。

**为什么**  
Service 必须先把 `creating` 状态 commit 落盘，再开始写文件，崩溃后 recovery 才有线索。

---

## DB-02 `find_project_by_id(session, project_id)` — B级

**业务作用**  
按 Project ID 查一条项目记录。

**输出**  
Project | None。

**副作用**  
只读。

---

## DB-03 `list_ready_projects(session)` — B级

**业务作用**  
给首页查询创建完成的最近项目。

**规则**  
只查 ready，并按 `last_opened_at` / `created_at` 排序。

**禁止**  
不检查磁盘。

---

## DB-04 `set_project_ready(session, project_id, opened_at)` — B级

**业务作用**  
在 final Workspace 已经验证成功后，把 DB 项目状态改成 ready。

**DB 副作用**  
UPDATE / flush；不 commit。

**保护**  
只允许 `creating → ready`。

---

## DB-05 `set_project_last_opened_at(session, project_id, opened_at)` — B级

**业务作用**  
记录最近一次成功进入 Workspace 的时间。

**DB 副作用**  
UPDATE / flush；不 commit。

---

## DB-06 `delete_incomplete_project(session, project_id)` — B级

**业务作用**  
仅在“项目尚未发布到 final Workspace”且创建失败时清理 `creating` DB row。

**保护**  
ready Project 必须拒绝删除。

**DB 副作用**  
DELETE / flush；不 commit。

---

## DB-07 `list_incomplete_projects(session)` — B级

**业务作用**  
应用启动时找出所有 `creating` 项目，交给 recovery 判断。

**副作用**  
只读。

---

# 8. Recovery / Create Transaction

## REC-01 `cleanup_owned_staging_directory(staging_dir, project_id)` — A级

**业务作用**  
安全清理一个明确属于当前 Project ID 的 staging 目录。

**安全边界**  
删除前必须确认实际路径满足：

```text
.../.ai-drama-staging/<same project_id>
```

**禁止**  
不允许删除 Workspace Root、final Project、其它 Project、任意用户路径。

---

## REC-02 `rollback_unpublished_project_creation(session, project_id, paths)` — A级

**业务作用**  
只处理 **final 发布前** 的同步创建失败。

**调用**

```text
cleanup_owned_staging_directory()
→ delete_incomplete_project()
→ session.commit()
```

**为什么叫 unpublished**  
函数名直接声明安全边界：只有 staging 还没有 rename 到 final 才能调用。

**绝对禁止**  
如果 final Workspace 已经发布，本函数不得删除 final，也不得删除 creating DB row。

---

## REC-03 `recover_incomplete_project(session, project)` — A级

**业务作用**  
恢复一个上次中断、DB 仍为 `creating` 的项目。

**状态判断**

```text
Case A: final 存在 + Manifest valid
→ set ready → commit

Case B: final 不存在 + staging valid
→ publish staging → final
→ validate final
→ set ready → commit

Case C: staging/final 都不存在
→ delete incomplete row → commit

Case D: staging invalid + final 不存在
→ 安全删除本项目 staging
→ delete incomplete row → commit

Case E: final 存在但 invalid / ID mismatch
→ 不删除 final
→ 不把它标 ready
→ 为 V1 记录高优先级 recovery error
→ creating row 保留，等待人工/未来 repair 能力
```

**为什么 Case E 不删除 DB row**  
删除 row 会让应用彻底失去“这个目录曾属于哪个 Project ID”的追踪线索。

**V1 已知限制**  
F01 不提供 repair UI。Case E 会继续保持 `creating`，项目不会出现在 ready 列表；日志必须明确说明原因。

---

## REC-04 `recover_interrupted_project_creations()` — A级

**业务作用**  
应用启动时恢复所有 incomplete Project。

**调用链**

```text
list_incomplete_projects()
→ 每条独立 session/transaction 调 recover_incomplete_project()
```

**故障隔离**  
一个 Project recovery 失败不能阻断其它 Project recovery。

**严重基础设施异常**  
如果 DB 本身不可用，则应用启动失败；这与某条 Project 数据损坏要区分。

---

# 9. Project Service

## SVC-01 `create_project(command, session, settings)` — A级

**业务作用**  
把用户的一次“创建项目”请求完整变成一个可打开的 ready Project。

**调用方**  
`create_project_endpoint()`。

**输入**  
CreateProjectCommand + DB Session + Settings。

**主流程**

```text
1. normalize name/language/region
2. resolve workspace root
3. prepare workspace root
4. generate project id
5. build project paths
6. assert paths unused
7. 构造 Project creating record
8. add_creating_project()
9. session.commit()                     ← DB 持久化恢复点
10. build manifest
11. 创建 staging
12. write_project_manifest_atomic()
13. validate staging manifest
14. publish staging dir → final dir      ← FILE PUBLISH POINT
15. validate final workspace
16. set_project_ready()
17. session.commit()                     ← ready 持久化
18. return ProjectDTO
```

**事务原则**

### 发布前失败

```text
session.rollback() 当前未提交 DB 变更
→ rollback_unpublished_project_creation()
→ 返回明确错误
```

### 发布后、ready commit 前失败

```text
session.rollback()
→ 保留 final Workspace
→ 保留 DB creating row
→ 返回 PROJECT_CREATE_FINALIZATION_PENDING
→ startup recovery 后续完成
```

**禁止**  
- 不直接写 SQL；
- 不自己 JSON dumps；
- 不在发布后删除 final；
- 不创建 F02 的 source/等目录。

**关键测试**  
happy path、DB commit#1 failure、Manifest failure、publish failure、final validation failure、ready commit failure。

---

## SVC-02 `list_projects(session)` — A级

**业务作用**  
给首页返回最近项目，同时告诉 UI 每个 Workspace 是否还“基本存在”。

**流程**

```text
list_ready_projects()
→ 对每条检查 final directory + project.json 是否存在
→ 构造 ProjectDTO(workspace_available)
```

**注意**  
列表阶段只做轻量检查，不解析所有 Manifest，避免一个损坏项目让首页加载变重或报 500。

**规则**  
某一个 Workspace 缺失仍返回该项目，`workspace_available=false`。

---

## SVC-03 `open_project(project_id, session)` — A级

**业务作用**  
真正进入一个已有项目 Workspace。

**适用场景**  
- 用户点击最近项目卡片；
- 浏览器刷新 `/projects/:id`；
- 用户直接输入 `/projects/:id`。

**流程**

```text
find_project_by_id()
→ 必须 ready
→ validate_project_workspace()
→ set_project_last_opened_at()
→ session.commit()
→ return ProjectDTO
```

**为什么没有 get_project()**  
F01 没有需要“只查详情但不验证 Workspace”的真实用户动作。维护第二套入口只会产生状态语义差异。

**失败**  
not found、not ready、workspace missing、manifest missing/invalid、ID mismatch、format unsupported。

**禁止**  
不自动修复、不修改 Manifest、不静默重建 Workspace。

---

## SVC-04 `get_project_defaults(settings)` — B级

**业务作用**  
新建项目 Dialog 真正打开时，返回后端当前默认 Workspace Root 和 `project_format_version`。

**为什么保留这个 API**  
UI 可以明确告诉用户“留空会保存在哪里”，同时默认值不在 Vue 写死。

---

# 10. API Controller / HTTP Boundary

> Controller 的中文定义：**HTTP 接待层**。它负责“接请求、交给 Service、返回结果”，不负责真正创建项目。

## API-01 `health_endpoint()` — B级

**HTTP**  
`GET /api/v1/health`

**业务作用**  
前端/人工确认本地 FastAPI 进程可通信。

**输出**  
`{"status":"ok"}`。

**禁止**  
不做 GPU/FFmpeg/模型检测。

---

## API-02 `project_defaults_endpoint()` — A级

**HTTP**  
`GET /api/v1/projects/defaults`

**用户场景**  
打开“新建项目”Dialog 时获取默认存储位置。

**调用**  
只调用 `get_project_defaults()`。

**禁止**  
不自己解析 Windows 用户目录。

---

## API-03 `list_projects_endpoint()` — A级

**HTTP**  
`GET /api/v1/projects`

**用户场景**  
首页加载最近项目卡片。

**调用**  
只调用 `list_projects()`。

**禁止**  
不自己 SQL、不自己扫描 Workspace。

---

## API-04 `create_project_endpoint()` — A级

**HTTP**  
`POST /api/v1/projects`

**用户场景**  
用户点击“创建项目”。

**Controller 实际只做**

```text
HTTP body / Pydantic结构校验
→ create_project(command, session, settings)
→ ProjectDTO
```

**明确不做**  
Project ID、目录、Manifest、SQL、commit、rollback、recovery。

**HTTP 成功状态**  
建议冻结为 `201 Created`，比 200 更符合“新资源已创建”。

**测试**  
201、请求结构 422、Domain 409/503、未知 500 envelope。

---

## API-05 `open_project_endpoint()` — A级

**HTTP**  
`POST /api/v1/projects/{project_id}/open`

**用户场景**  
任何“进入 Project Workspace”的动作。

**为什么 POST**  
成功后更新 `last_opened_at`，存在状态变化。

**调用**  
只调用 `open_project()`。

**删除的旧设计**  
不再提供 F01 `GET /projects/{id}`。

---

## API-06 `domain_error_handler(request, exc)` — A级

**业务作用**  
统一把 DomainError 变成稳定 HTTP Error Envelope。

**示例**

```json
{
  "error": {
    "code": "PROJECT_WORKSPACE_NOT_WRITABLE",
    "message": "项目存储位置不可写",
    "retryable": false,
    "details": {}
  }
}
```

**为什么不是每个 Controller try/except**  
否则各接口会出现不同错误格式。

**未知异常**  
由通用 500 handler 记录 log id；不能向 UI 返回 Python stack。

---

# 11. Frontend API — B级边界适配

这些函数很薄，不需要像 `create_project()` 一样写几十行 Contract，但职责必须清楚。

## FEAPI-01 `request<T>()`

统一 base URL、JSON、Error Envelope → `FrontendApiError`。

禁止修改 Pinia/Router。

## FEAPI-02 `getProjectDefaults()`

`GET /api/v1/projects/defaults`。

只返回 typed Defaults。

## FEAPI-03 `fetchProjects()`

`GET /api/v1/projects`。

只返回 typed ProjectDTO[]。

## FEAPI-04 `createProject(payload)`

`POST /api/v1/projects`。

只负责 HTTP，不导航。

## FEAPI-05 `openProject(projectId)`

`POST /api/v1/projects/{id}/open`。

卡片点击与 Workspace route bootstrap 共用。

---

# 12. Pinia Store

## STORE-01 `load_recent_projects()` — B级

> TypeScript 实际命名使用 camelCase：`loadRecentProjects()`。

**业务作用**  
首页只加载最近项目。

**审核修正**  
不再同时加载 defaults。首页没有打开创建 Dialog 时，不需要额外请求默认目录。

**状态**  
`loadingProjects / projects / error`。

---

## STORE-02 `load_create_project_defaults()` — B级

实际命名：`loadCreateProjectDefaults()`。

**业务作用**  
新建项目 Dialog 第一次打开时懒加载 defaults。

**优化**  
同一前端会话已经加载过可缓存，不必每次开 Dialog 都请求。

---

## STORE-03 `create_new_project(payload)` — A级

实际命名：`createNewProject()`。

**业务作用**  
前端创建项目用例。

**流程**

```text
creating guard
→ createProject()
→ currentProject = result
→ 把新项目加入/刷新最近项目
→ return project 给 UI 导航
```

**失败**  
不能把失败项目写入 currentProject。

---

## STORE-04 `open_project_by_id(projectId)` — A级

实际命名：`openProjectById()`。

**业务作用**  
统一处理卡片点击、直接 URL、刷新三种进入项目方式。

**流程**

```text
opening = true
→ openProject(id)
→ currentProject = result
→ opening = false
```

**审核删除**  
不再有 `openExistingProject()` + `loadCurrentProject()` 两套 Store action。

---

## STORE-05 `clearProjectError()` — C级

仅清空前端错误状态；不再写正式大段 Contract。

---

# 13. Vue UI — 只保留真正有业务交互的 Handler

## UI-01 `handleOpenCreateDialog()` — B级

**业务作用**  
用户点“新建项目”时打开 Dialog，并在需要时加载后端默认目录。

**调用**  
`loadCreateProjectDefaults()`。

---

## UI-02 `validateCreateProjectForm()` — B级

**业务作用**  
在请求前给用户即时表单反馈。

**检查**  
项目名、目标语言、目标地区等明显错误。

**禁止**  
不能替代后端校验。

---

## UI-03 `handleCreateSubmit()` — A级

**用户动作**  
点击“创建项目”。

**流程**

```text
validateCreateProjectForm()
→ store.createNewProject()
→ 成功关闭 Dialog
→ router.push('/projects/:id')
```

**禁止**  
不直接 fetch、不理解 DB/Manifest。

---

## UI-04 `handleProjectCardClick(projectId)` — A级

**用户动作**  
点击最近项目。

**流程**

```text
store.openProjectById(id)
→ 成功后 router.push('/projects/:id')
```

后端 open 失败时不导航。

---

## UI-05 `bootstrapProjectWorkspace(projectId)` — A级

**用户场景**  
浏览器刷新或直接访问 `/projects/:id`。

**流程**

```text
store.openProjectById(id)
→ 成功显示 Workspace
→ 失败显示明确错误 / 返回项目首页入口
```

**关键修正**  
它现在调用真正的 open，不再只“查详情”。因此直接 URL 也会验证 Workspace + Manifest。

---

# 14. 不再列为正式 Function Contract 的 C 级 helper

允许实现，但不要为了它们单独写一页文档：

```text
_build_sqlite_url(...)
_json_dumps_manifest(...)
_resetCreateForm()
formatProjectLocale(...)
formatLastOpenedAt(...)
goBackToProjects()
简单 computed / mapper / CSS helper
```

这些函数如果以后开始承担 DB、文件、业务状态或复杂异常，则升级为 A/B 级。

---

# 15. 审核后的函数数量与开发重点

上一版把大量 helper 都视为“正式单函数任务”。

审核后正式关注：

```text
Infrastructure: 8
Project/Path:   8
Manifest:       5
Repository:     7
Recovery:       4
Service:        4
API:            6
Frontend API:   5（B级薄适配）
Store:          4 个正式 + 1 个C级
UI:             5
```

真正 A 级函数远少于这个数字，开发时优先围绕 A 级业务闭环测试。

---

# 16. 推荐正式编码顺序

不是按“文件夹写完”推进，而按依赖关系推进：

```text
INF-01/02/03/04
→ INF-05/06
→ PRJ-01~08
→ MAN-01~05
→ DB Model + Migration
→ DB-01~07
→ REC-01/02
→ SVC-01 create_project
→ REC-03/04 startup recovery
→ SVC-02 list_projects
→ SVC-03 open_project
→ SVC-04 defaults
→ API-01~06
→ INF-07/08 lifespan + app assembly integration
→ FEAPI
→ STORE
→ UI
→ Restart / Crash / Integration tests
→ READY_FOR_REVIEW
```

注意：`application_lifespan()` 最终集成虽然属于 Infrastructure，但要等 Recovery 函数存在后再接入，避免先写空壳启动逻辑后反复修改。

---

# 17. 每个 A 级函数正式编码前必须写的中文注释

示例：

```python
def create_project(command, session, settings) -> ProjectDTO:
    """
    创建一个新的 AI Drama Studio 项目，并在成功后返回可直接进入的 ProjectDTO。

    业务作用：
    把用户的一次“创建项目”操作安全地转换成数据库记录、Project Workspace
    和 project.json。创建过程跨 SQLite 和文件系统，因此采用 creating 状态 +
    staging + final 发布点，保证程序中断后仍然可以恢复。

    事务边界：
    1. creating 记录必须先 commit，作为崩溃恢复线索；
    2. staging 发布为 final 后，不再允许自动删除 final；
    3. ready commit 失败时保留 creating + final，交给 startup recovery。

    禁止行为：
    - 不创建 F02 的 source/proxy/audio 等目录；
    - 不在发布 final 后为了回滚而删除用户 Project Workspace；
    - 不直接实现 Repository / Manifest 已负责的底层细节。

    Raises:
        ProjectWorkspaceNotWritableError: Workspace Root 不可写。
        ProjectCreateConflictError: staging/final 路径冲突。
        ProjectCreateFinalizationPendingError: final 已发布但 DB 尚未成功转 ready。
    """
```

Controller 示例：

```python
@router.post('/projects', status_code=201, response_model=ProjectDTO)
def create_project_endpoint(...):
    """
    新建项目的 HTTP 接待入口。

    本函数只把 HTTP Request 交给 create_project() Service，并返回 ProjectDTO。
    它不生成 Project ID、不创建目录、不写 SQL、不写 project.json、也不负责回滚。
    """
```

---

# 18. 本轮审核后还需要同步到 F01 主 Contract 的变化

以下变化属于 F01 Contract 修订项，必须以本文件 V2 为准，并同步回主 Contract：

```text
1. 删除 GET /api/v1/projects/{id}
2. /projects/:id 刷新也使用 POST /open
3. last_opened_at 定义为“最近一次成功进入 Workspace 的时间”
4. validate_workspace_root → prepare_workspace_root
5. build final/staging path → build_project_paths
6. 删除 serialize_project_manifest
7. Repository 不 commit，Service 管事务
8. create_app 与 application_lifespan 分离
9. health_endpoint 归 API 层
10. loadRecentProjects 不再顺带加载 defaults
11. defaults 仅 Dialog 懒加载
12. openExistingProject + loadCurrentProject 合并为 openProjectById
13. final 发布后失败不得自动删除 final
14. 增加 PROJECT_CREATE_FINALIZATION_PENDING 错误语义
15. C级 helper 不再强制独立 Function Contract
```

F01 仍保持 `PLANNED`，这些设计在用户确认前都还不是 Frozen Contract。
