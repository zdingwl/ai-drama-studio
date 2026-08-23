# F01 — 单函数职责字典（Function Contracts）

> 本文档是 `F01-create-project.md` 的函数级补充说明。
>
> 目标：任何人不需要猜函数名，就能知道“这个函数为什么存在、谁调用、它调用谁、输入输出是什么、允许做什么、禁止做什么、失败怎么办、怎么测试”。
>
> 本文档仍属于规划阶段；不代表业务代码已经开始。

---

# 1. 先解释每一层到底干什么

## 1.1 API Controller / Endpoint（控制器）

**它是 HTTP 边界层，不是业务层。**

主要职责：

```text
浏览器 HTTP 请求
→ Pydantic / FastAPI 参数校验
→ 调用 Service
→ 把 Service 返回值转换成 Response DTO
→ 把 DomainError 映射成统一 HTTP Error
```

Controller **允许做**：

- 读取 path/query/body；
- 调用 Pydantic Schema 校验；
- 调用一个或少量 Service 用例；
- 返回 HTTP status + DTO；
- 调用统一错误映射。

Controller **禁止做**：

- 自己生成 Project ID；
- 自己拼 Workspace 路径；
- `mkdir`；
- 读写 `project.json`；
- 直接写 SQL / SQLAlchemy Query；
- 自己处理创建事务；
- 自己决定 recovery；
- 把业务逻辑写在路由函数里。

为什么：如果 Controller 也写业务逻辑，那么以后 Electron、CLI、测试或其它调用入口会被迫复制一套创建项目逻辑。

---

## 1.2 Service（业务服务层）

**Service 负责“一个完整业务动作怎么完成”。**

例如：`create_project()` 的职责不是亲自写每个文件，而是按正确顺序编排：

```text
校验输入
→ 生成 ID
→ 准备路径
→ 插入 creating DB row
→ 写 Manifest
→ 把 staging 转 final
→ 校验 final workspace
→ 标记 ready
```

Service 可以调用 Validation / Path / Repository / Manifest / Recovery 函数。

Service 禁止重新实现这些底层函数已经负责的细节。

---

## 1.3 Repository（数据库访问层）

**Repository 只负责 SQLite/SQLAlchemy。**

例如：

```text
insert_creating_project()
```

只负责插入一条项目记录。

Repository 禁止：

- `mkdir`；
- 读写 JSON；
- 调用 FastAPI；
- 返回 HTTPException；
- 判断 Workspace 是否存在。

---

## 1.4 Validation / Path Utility（校验和路径函数）

这些是小而稳定、无业务副作用的函数。

例如：

```text
normalize_project_name()
build_project_workspace_path()
```

它们应尽量是纯函数，方便单测和后续复用。

---

## 1.5 Manifest（project.json）

只负责：

- 构造 Manifest；
- 序列化；
- 原子写入；
- 读取；
- 校验。

不负责数据库状态流转。

---

## 1.6 Frontend API

只负责调用 HTTP API、解析统一响应，不管理页面状态。

---

## 1.7 Pinia Store

负责页面共享状态和前端用例编排：loading、creating、opening、currentProject、error。

Store 不直接操作 DOM，也不直接 `fetch()`；它调用 Frontend API 层。

---

## 1.8 Vue UI Handler

负责用户交互：点击、表单、导航、展示。

UI Handler 不直接知道 SQLite、Manifest、Workspace 创建细节。

---

# 2. Backend Foundation 单函数详细说明

## B01 `resolve_app_data_dir()`

**业务目的**  
确定 AI Drama Studio 自己的应用数据目录，后续 `app.db`、日志和应用级配置都从这里定位。

**谁调用**  
应用启动代码、数据库初始化函数。

**输入**  
- 环境变量 `AI_DRAMA_APP_DATA_DIR`；
- 当前 Windows 用户环境。

**输出**  
`Path`，例如：

```text
C:\Users\xxx\AppData\Local\AI Drama Studio
```

**副作用**  
无。只解析路径，不创建目录。

**禁止做**  
- 不创建 app.db；
- 不 mkdir；
- 不检查数据库版本。

**异常**  
环境变量存在但路径字符串无法规范化时抛出配置错误。

**测试**  
- env override；
- env 不存在时 Windows fallback；
- 测试环境不污染真实 LocalAppData。

---

## B02 `resolve_default_workspace_root()`

**业务目的**  
得到“用户不填写存储位置”时项目默认保存在哪。

**谁调用**  
`get_project_defaults()`、`resolve_requested_workspace_root()`。

**输入**  
环境变量覆盖值或 `%USERPROFILE%`。

**输出**  
例如：

```text
C:\Users\xxx\AI Drama Studio Projects
```

**副作用**  
无。

**禁止做**  
不验证是否可写；验证由 P06 负责。

**测试**  
override / default。

---

## B03 `ensure_directory(path)`

**业务目的**  
确保某个明确允许创建的目录存在。

**谁调用**  
数据库初始化、Workspace 创建、staging 创建等底层流程。

**输入**  
`Path`。

**输出**  
同一个 `Path` 或 `None`（实现时二选一并冻结）。

**副作用**  
可能创建目录。

**禁止做**  
- 不递归删除；
- 不判断该路径是否属于某项目；
- 不写测试文件。

**异常**  
权限不足、父路径是文件等 OS 错误，包装成明确基础设施异常。

**测试**  
目录已存在 / 创建成功 / 创建失败。

---

## B04 `probe_directory_writable(path)`

**业务目的**  
确认一个目录“理论存在”之外，是真的可以创建和删除文件，防止创建项目做到一半才发现没有写权限。

**谁调用**  
`validate_workspace_root()`。

**输入**  
待验证目录。

**输出**  
成功返回 `None` 或 `True`；失败抛明确错误。

**副作用**  
创建一个随机临时探针文件并立即删除。

**禁止做**  
不修改用户已有文件。

**测试**  
可写 / 只读 / 权限拒绝 / 临时文件最终被清理。

---

## B05 `build_database_url(app_data_dir)`

**业务目的**  
把应用数据目录转换成 SQLAlchemy 可用的 SQLite URL。

**谁调用**  
`create_db_engine()`。

**输入**  
应用数据目录。

**输出**  
SQLite URL，例如指向 `app.db`。

**副作用**  
无。

**禁止做**  
不连接数据库、不建表。

**测试**  
Windows 盘符、空格、中文路径。

---

## B06 `create_db_engine(database_url)`

**业务目的**  
统一创建整个应用使用的 SQLAlchemy Engine，避免各模块自己创建连接参数。

**谁调用**  
应用启动/数据库模块初始化。

**输入**  
SQLite URL。

**输出**  
SQLAlchemy `Engine`。

**副作用**  
建立数据库连接能力，但不主动建业务表。

**禁止做**  
不执行 Alembic migration。

**测试**  
临时 SQLite 可连接、关闭后无资源泄漏。

---

## B07 `get_db_session()`

**业务目的**  
为一次 FastAPI 请求提供一个受控 SQLAlchemy Session，并确保请求结束后关闭。

**谁调用**  
FastAPI Dependency Injection、Service/Repository 调用链。

**输入**  
Session factory。

**输出**  
一个 Session 生命周期。

**副作用**  
打开/关闭 DB session。

**禁止做**  
不自动提交业务事务；具体 commit 在明确 Repository/Service 边界执行。

**测试**  
正常请求关闭、异常请求也关闭。

---

## B08 `get_schema_revision()`

**业务目的**  
读取当前 `app.db` 已经应用到哪个 Alembic revision，用于 project metadata 和兼容诊断。

**谁调用**  
项目创建流程、环境诊断。

**输入**  
DB connection/session。

**输出**  
例如：`0001_create_projects`。

**副作用**  
只读。

**异常**  
数据库未初始化或 alembic_version 缺失。

**测试**  
初始化后返回准确 revision。

---

## B09 `ensure_database_schema()`

**业务目的**  
应用启动时确保 `app.db` schema 已达到当前应用要求。

**谁调用**  
startup/bootstrap。

**输入**  
DB path + Alembic config。

**输出**  
schema ready。

**副作用**  
首次启动可能创建数据库并执行 migration。

**禁止做**  
不创建 Project Workspace。

**异常**  
Migration 失败时停止进入需要 DB 的业务功能，不能忽略。

**测试**  
fresh DB / 已是最新 / revision 异常。

---

## B10 `create_app()`

**业务目的**  
创建 FastAPI Application 对象，注册 Router、异常处理器和 startup/recovery 生命周期。

**谁调用**  
ASGI Server。

**输入**  
应用配置。

**输出**  
`FastAPI` 实例。

**副作用**  
组装应用；启动阶段会触发 schema 检查和 interrupted project recovery。

**禁止做**  
不在函数体里写具体 Project 创建业务。

**测试**  
TestClient 能启动、路由存在、startup 失败可见。

---

## B11 `health_check()`

**业务目的**  
给前端判断“本地 FastAPI Engine 是否在线”。

**谁调用**  
前端启动探测、人工诊断。

**输入**  
无。

**输出**  
最小 JSON，例如：

```json
{"status":"ok"}
```

**副作用**  
无。

**禁止做**  
不做 FFmpeg/GPU/模型检测；F01 只确认 API 存活。

**测试**  
HTTP 200 + schema。

---

# 3. Project Validation / ID / Paths

## P01 `generate_project_id()`

**业务目的**  
生成永不依赖项目名、文件名或模型的稳定 Project 主键。

**调用方**  
`create_project()`。

**输出**  
`PROJECT_<32位UUID4 hex>`。

**副作用**  
无。

**禁止做**  
不访问 DB；唯一冲突最终仍由 DB PK 保底。

**测试**  
prefix、长度、格式、批量唯一性。

---

## P02 `normalize_project_name(name)`

**业务目的**  
把用户输入的项目名变成合法的业务值。

**输入**  
原始字符串。

**输出**  
trim 后名称。

**规则**  
1–100 字符；重复名称允许。

**异常**  
`PROJECT_NAME_REQUIRED` / `PROJECT_NAME_TOO_LONG`。

**禁止做**  
不把项目名转成文件夹名。

---

## P03 `normalize_language_code(code)`

**业务目的**  
统一语言代码大小写和空值语义，避免数据库出现 `EN/en/English` 三套值。

**输入**  
字符串或 `None`。

**输出**  
如 `zh`、`en` 或 `None`。

**注意**  
Source Language 可以为空；Target Language 由更高层 Schema/Service 保证必填。

---

## P04 `normalize_region_code(code)`

**业务目的**  
统一目标地区代码。

**输入**  
如 `us`。

**输出**  
`US`。

**异常**  
非法地区代码。

---

## P05 `resolve_requested_workspace_root(value)`

**业务目的**  
决定本次创建项目具体使用哪个根目录。

**输入**  
用户输入路径或空值。

**输出**  
规范化绝对 `Path`。

**逻辑**  
空 → B02 默认路径；非空 → 规范成绝对路径。

**禁止做**  
这里不执行写权限探测；交给 P06。

---

## P06 `validate_workspace_root(path)`

**业务目的**  
确认 Workspace Root 可以作为项目父目录。

**调用**  
B03 `ensure_directory()` + B04 `probe_directory_writable()`。

**输出**  
验证后的 Path。

**异常**  
路径非法、父路径冲突、不可写。

**禁止做**  
不创建具体 Project 目录。

---

## P07 `build_project_workspace_path(root, project_id)`

**业务目的**  
唯一、统一地生成正式项目目录。

**输出**  
`<root>/<project_id>`。

**副作用**  
无。

---

## P08 `build_project_staging_path(root, project_id)`

**业务目的**  
生成创建项目时的临时 staging 路径，使写入成功后可以原子移动到正式目录。

**输出**  
`<root>/.ai-drama-staging/<project_id>`。

**副作用**  
无。

---

## P09 `assert_project_path_available(final_path, staging_path)`

**业务目的**  
创建前防止误覆盖已经存在的目录或残留 staging。

**输入**  
正式路径、staging 路径。

**输出**  
可用时无返回。

**异常**  
`PROJECT_CREATE_CONFLICT`。

**禁止做**  
不自动删除冲突目录；因为无法确定它是否包含用户数据。

---

# 4. Manifest 单函数详细说明

## M01 `build_project_manifest(project)`

**业务目的**  
从已经确定的 Project 数据构造 `project.json` 的稳定 V1 结构。

**输入**  
Project 创建数据。

**输出**  
Manifest dict/typed object。

**禁止做**  
不读取磁盘、不写文件。

---

## M02 `serialize_project_manifest(manifest)`

**业务目的**  
保证所有 project.json 采用统一 UTF-8、缩进、换行和中文策略。

**输入**  
Manifest。

**输出**  
JSON text/bytes。

**测试**  
中文不乱码、反序列化等价。

---

## M03 `write_manifest_atomic(staging_dir, manifest)`

**业务目的**  
保证 `project.json` 不会因为断电/异常只写了一半。

**流程**  
`project.json.tmp` → flush/fsync/close → `os.replace()` → `project.json`。

**副作用**  
写文件。

**失败要求**  
不允许留下被当正式 Manifest 使用的半文件。

---

## M04 `read_project_manifest(workspace_path)`

**业务目的**  
读取现有项目的 `project.json`。

**输出**  
原始/typed manifest。

**异常**  
`PROJECT_MANIFEST_MISSING`、JSON decode error → `PROJECT_MANIFEST_INVALID`。

**禁止做**  
不修改 Manifest。

---

## M05 `validate_project_manifest(manifest, expected_id)`

**业务目的**  
确认 Manifest 属于当前 DB 项目，而且格式版本是当前应用能理解的。

**检查**  
- 必填字段；
- `project_id == expected_id`；
- `project_format_version` 支持；
- 字段基本类型。

**异常**  
ID mismatch / unsupported format / invalid manifest。

---

## M06 `validate_final_workspace(workspace_path, project_id)`

**业务目的**  
给“打开项目”和“创建完成前最终检查”提供同一套 Workspace 完整性入口。

**调用**  
M04 + M05。

**输出**  
Validated Manifest。

**禁止做**  
不更新 `last_opened_at`；那是 open_project() 的业务动作。

---

# 5. Repository 单函数详细说明

## R01 `insert_creating_project(session, data)`

**业务目的**  
在开始写文件前，先留下“这个 Project ID 正在创建”的 DB 记录，便于异常后恢复。

**输入**  
已经校验好的创建数据。

**DB 副作用**  
INSERT，`lifecycle_state='creating'`。

**为什么先 commit**  
如果随后进程崩溃，startup recovery 才能知道有一笔创建任务没完成。

**禁止做**  
不创建目录、不写 Manifest。

---

## R02 `get_project_by_id(session, id)`

**业务目的**  
按稳定 Project ID 读取项目记录。

**输出**  
Project / None。

**副作用**  
无。

---

## R03 `list_ready_projects(session)`

**业务目的**  
给“最近项目”首页读取已经完成创建的项目。

**规则**  
只返回 `ready`；按 `last_opened_at`、`created_at` 排序。

**禁止做**  
不检查磁盘；磁盘可用性由 Service 计算，避免 Repository 混入文件系统逻辑。

---

## R04 `mark_project_ready(session, id, opened_at)`

**业务目的**  
只有正式 Workspace 和 Manifest 全部验证成功后，才把项目从 `creating` 变成 `ready`。

**DB 副作用**  
UPDATE lifecycle + timestamps。

**保护**  
必须只允许合法状态转换，不能无条件把任意项目改 ready。

---

## R05 `touch_project_opened_at(session, id, now)`

**业务目的**  
记录用户最近一次真正成功打开项目的时间，用于最近项目排序。

**调用时机**  
必须在 Workspace/Manifest 验证成功之后。

**禁止做**  
`GET project detail` 不调用它，避免页面刷新查询就被错误算成“打开”。

---

## R06 `delete_creating_project(session, id)`

**业务目的**  
创建失败或无法恢复时，只清理未完成的 `creating` DB row。

**保护**  
如果项目已经 `ready`，必须拒绝删除。

**为什么**  
F01 不提供删除正式项目功能。

---

## R07 `list_creating_projects(session)`

**业务目的**  
应用启动时查出所有上次崩溃留下的未完成创建项目。

**调用方**  
S04 startup recovery。

**副作用**  
无。

---

# 6. Recovery / Service 单函数详细说明

## S01 `cleanup_owned_staging(path, project_id)`

**业务目的**  
安全删除“明确属于当前 Project ID”的 staging 目录。

**安全边界**  
必须校验路径位于 `.ai-drama-staging/<project_id>`，不能对用户 workspace_root 做递归删除。

**调用方**  
rollback / recovery。

---

## S02 `rollback_failed_creation(project, paths)`

**业务目的**  
同步创建项目失败时执行补偿，避免 DB/文件留下半成品。

**调用**  
S01 + R06。

**允许清理**  
当前 Project ID 的 staging；必要时只在 Final Manifest ID 明确匹配时清理本次刚创建的 final。

**禁止清理**  
用户 root、未知目录、其它 Project。

---

## S03 `recover_one_creating_project(project)`

**业务目的**  
处理一个因为崩溃停在 `creating` 状态的项目。

**核心判断**  
- valid final → mark ready；
- valid staging + no final → rename → validate → ready；
- neither → 删除 creating row；
- invalid staging → 安全清理 + 删除 row；
- final 冲突/invalid → 不删 final，记录冲突并清理 DB creating row。

**为什么单独一个函数**  
每个项目恢复互不影响，某一个坏项目不能阻塞其它 creating 项目的恢复。

---

## S04 `recover_interrupted_project_creations()`

**业务目的**  
应用启动时统一恢复所有上次未完成的项目创建。

**调用**  
R07 → 对每条调用 S03。

**失败隔离**  
一个项目 recovery 出错只记录错误，不导致整个应用无法处理其它记录；是否阻断启动需在实现时按严重程度区分。

---

## S05 `create_project(command)`

**业务目的**  
这是 F01 的核心业务用例：把“用户点击创建项目”完整变成一个 `ready` Project。

**谁调用**  
A03 `create_project_endpoint()`；集成测试也可以直接调用。

**它调用谁**  
P02/P03/P04 → P05/P06 → P01/P07/P08/P09 → R01 → M01/M03/M06 → R04；异常时 S02。

**输入**  
`CreateProjectCommand`。

**输出**  
`ProjectDTO` / Project domain object。

**副作用**  
DB + staging + final workspace + project.json。

**关键原则**  
它是 orchestration，不重新写 SQL、JSON、path 算法。

**测试**  
happy path、manifest 写失败、rename 失败、DB ready 更新失败、rollback 安全性。

---

## S06 `list_projects()`

**业务目的**  
给首页提供可展示的最近项目列表。

**调用**  
R03，并逐条只做轻量 Workspace 可用性检查。

**输出**  
`ProjectDTO[]`。

**重要行为**  
某个 Workspace 被用户移动/删除时，该项目仍返回，但 `workspace_available=false`；不能因为一条坏记录让整个首页 500。

---

## S07 `get_project(project_id)`

**业务目的**  
给 `/projects/:id` 页面刷新时读取项目基础信息。

**输出**  
ProjectDTO。

**重要区别**  
这只是“查看详情”，**不代表用户成功打开 Workspace**，因此不更新 `last_opened_at`。

---

## S08 `open_project(project_id)`

**业务目的**  
用户点击历史项目时，真正确认这个项目现在还可以使用。

**步骤**  
DB 项目存在且 ready → M06 验证 Workspace/Manifest → format 支持 → R05 更新 last_opened_at → 返回 ProjectDTO。

**失败**  
Workspace missing、Manifest missing/invalid、ID mismatch、format unsupported。

**禁止做**  
不自动“修复”未知用户文件；F01 只阻止打开并给明确错误。

---

## S09 `get_project_defaults()`

**业务目的**  
前端打开“新建项目”窗口前，获取后端实际使用的默认 Workspace Root 和 Project Format Version。

**为什么不用前端写死**  
以后 Electron/配置变化时，只改后端设置，不让前后端默认值漂移。

---

# 7. API Controller / Endpoint 单函数详细说明

> 这一节就是你指出最不清楚的“控制器”。Controller 只负责 HTTP 边界，不负责真正创建项目。

## A01 `get_project_defaults_endpoint()`

**HTTP**  
`GET /api/v1/projects/defaults`

**业务作用**  
前端准备打开新建项目 Dialog 时，询问后端：“默认存储目录是什么？当前 Project Format Version 是多少？”

**谁调用**  
Frontend `getProjectDefaults()`。

**内部调用**  
只调用 S09 `get_project_defaults()`。

**成功输出**  
Defaults DTO。

**禁止做**  
不自己解析 `%USERPROFILE%`；那是底层 path/service 的职责。

**测试**  
200 + 返回字段完整。

---

## A02 `list_projects_endpoint()`

**HTTP**  
`GET /api/v1/projects`

**业务作用**  
项目首页加载“最近项目”卡片列表。

**谁调用**  
Frontend `fetchProjects()`。

**内部调用**  
S06 `list_projects()`。

**成功输出**  
`ProjectDTO[]`。

**禁止做**  
Controller 不写 SQL，不自己遍历磁盘。

**测试**  
空数组、多个项目排序、某项目 workspace 缺失仍整体 200。

---

## A03 `create_project_endpoint()`

**HTTP**  
`POST /api/v1/projects`

**业务作用**  
这是“用户点击创建项目”对应的 HTTP 入口。

**谁调用**  
Frontend `createProject(payload)`。

**Controller 实际做什么**  
1. FastAPI/Pydantic 读取并做结构级请求校验；
2. 构造/接收 `CreateProjectCommand`；
3. 调用 S05 `create_project(command)`；
4. 把成功结果转换成 `ProjectDTO`；
5. 把 DomainError 交给 A06 映射成统一 HTTP Error。

**Controller 明确不做什么**  
- 不生成 Project ID；
- 不 trim 项目名业务规则；
- 不决定默认目录；
- 不检查目录权限；
- 不 mkdir；
- 不写 `project.json`；
- 不执行 SQL；
- 不做 rollback。

**为什么**  
真正创建项目只能存在 S05 一份逻辑，避免 API/未来 Electron/测试各写一套。

**测试**  
成功 200/201（实现前冻结其一）、Schema 错误、Domain 422/409、未知 500 envelope。

---

## A04 `get_project_endpoint()`

**HTTP**  
`GET /api/v1/projects/{project_id}`

**业务作用**  
用户已经在 `/projects/:id` 页面，浏览器刷新后重新拿到当前项目基本资料。

**内部调用**  
S07 `get_project()`。

**重要规则**  
这不是“打开项目动作”，所以不能更新 `last_opened_at`。

**测试**  
存在 200、不存在 404、调用后 opened_at 不变。

---

## A05 `open_project_endpoint()`

**HTTP**  
`POST /api/v1/projects/{project_id}/open`

**业务作用**  
用户从最近项目列表点击一个项目时，真正尝试打开它。

**为什么必须 POST 而不是 GET**  
因为成功打开后会更新 `last_opened_at`，存在状态变化。

**内部调用**  
S08 `open_project()`。

**成功条件**  
DB ready + Workspace 存在 + Manifest 有效 + ID 相符 + Format 支持。

**成功副作用**  
更新 `last_opened_at`。

**Controller 禁止做**  
不能自行 `Path.exists()`、读 JSON 或 UPDATE DB。

**测试**  
成功、workspace missing、manifest invalid、ID mismatch、unsupported format。

---

## A06 `map_domain_error_to_http()`

**业务作用**  
把后端业务层统一领域错误转换成前端稳定可识别的 HTTP 错误格式。

**输入示例**  
`ProjectWorkspaceNotWritableError`。

**输出示例**

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

**为什么单独做**  
避免每个 Controller 自己 `try/except` 后返回不同格式。

**禁止做**  
不吞掉未知异常；未知异常应记录日志 ID，并返回统一 500，不能把 Python stack 暴露给 UI。

**测试**  
F01 每个 Domain Error 都有唯一 HTTP status/code；未知错误不会泄漏敏感内部信息。

---

# 8. Frontend API 单函数详细说明

## F01 `request<T>()`

**业务目的**  
统一浏览器请求 FastAPI 的底层 HTTP 客户端。

**职责**  
拼 base URL、JSON headers、解析 JSON、识别统一 error envelope、抛统一 FrontendApiError。

**禁止做**  
不更新 Pinia，不导航页面。

---

## F02 `getProjectDefaults()`

调用 `GET /projects/defaults`，返回 typed defaults。

不负责 Dialog 状态。

---

## F03 `fetchProjects()`

调用 `GET /projects`，返回 typed ProjectDTO[]。

---

## F04 `createProject(payload)`

调用 `POST /projects`。

只负责 HTTP，不决定创建成功后跳哪个页面。

---

## F05 `fetchProject(id)`

调用 `GET /projects/{id}`，用于页面刷新恢复详情。

---

## F06 `openProject(id)`

调用 `POST /projects/{id}/open`，表示一次真实打开动作。

---

# 9. Pinia Store 单函数详细说明

## F07 `loadProjectHome()`

**业务目的**  
项目首页初始化。

**动作**  
加载 defaults + recent projects；管理 `loading_projects` 和 error。

**禁止做**  
不直接 fetch，不操作 DOM。

---

## F08 `createNewProject(payload)`

**业务目的**  
前端“创建项目”用例编排。

**动作**  
检查 `creating` 防重复 → 调 F04 → 保存 currentProject → 刷新/插入最近项目 → 返回新项目供 UI 导航。

**状态**  
`creating=true/false`。

**失败**  
保存统一错误，但不能把失败项目放入 currentProject。

---

## F09 `openExistingProject(id)`

**业务目的**  
从最近项目卡片打开一个项目。

**动作**  
`opening=true` → F06 → currentProject → 返回成功对象。

**失败**  
保持当前页面并显示 Workspace/Manifest 等明确错误。

---

## F10 `loadCurrentProject(id)`

**业务目的**  
直接刷新 `/projects/:id` 时恢复 currentProject。

**调用**  
F05 `fetchProject()`，不是 F06 open。

**原因**  
页面刷新不应每次都修改 last_opened_at。

---

## F11 `clearProjectError()`

**业务目的**  
用户关闭错误提示或重新操作前清除 Store 中的旧错误。

**副作用**  
只修改前端 error state。

---

# 10. Vue UI Handler 单函数详细说明

## U01 `validateCreateProjectForm()`

**业务目的**  
用户点击提交前给即时 UI 提示。

**检查**  
项目名、目标语言、目标地区、长度等可在前端快速判断的规则。

**注意**  
前端校验不能代替后端校验。

---

## U02 `handleCreateSubmit()`

**业务目的**  
处理用户点击“创建项目”。

**动作**  
U01 校验 → Store F08 → 成功关闭 Dialog → Router 导航 `/projects/:id`。

**禁止做**  
不直接调用 fetch、不写 localStorage 作为项目真相。

---

## U03 `resetCreateForm()`

关闭或重新打开 Dialog 时清理表单草稿/字段错误。

不修改已经创建的 Project。

---

## U04 `handleProjectCardClick(project)`

**业务目的**  
用户点击最近项目卡片。

**动作**  
调用 Store F09；只有后端 open 成功才导航。

**为什么**  
避免 Workspace 已丢失时仍进入一个假工作区。

---

## U05 `handleRetryLoad()`

首页项目列表加载失败时重新调用 `loadProjectHome()`。

---

## U06 `formatProjectLocale(project)`

把 `zh → en / US` 这样的稳定代码转换成 UI 可读文本。

**副作用**  
无。

**禁止做**  
不改变数据库 code。

---

## U07 `formatLastOpenedAt(value)`

只负责日期展示格式，不回写业务时间。

---

## U08 `bootstrapWorkspace(projectId)`

**业务目的**  
`/projects/:id` 页面首次挂载时恢复当前项目详情。

**动作**  
调用 Store F10；加载成功后展示空 Workspace。

**注意**  
这里不调用 `openProject()`，因为真正点击打开动作已经在项目首页发生；浏览器直接刷新只恢复详情。

---

## U09 `goBackToProjects()`

从空 Workspace 返回项目首页。

只负责 Router 导航，不修改项目状态。

---

# 11. 单函数代码注释最低标准

正式编码时，每个非显而易见的业务函数至少使用以下格式的简体中文 docstring：

```python
def open_project(project_id: str) -> ProjectDTO:
    """
    打开一个已经创建完成的项目。

    业务作用：
    - 验证 projects 表中的项目必须处于 ready；
    - 验证 Workspace 和 project.json 仍然存在且属于同一个 project_id；
    - 验证 project_format_version 为当前应用支持版本；
    - 只有全部验证通过后才更新 last_opened_at。

    为什么不能只查数据库：
    用户可能在系统外移动、删除或修改项目目录，因此 DB 有记录并不等于项目真实可打开。

    禁止行为：
    - 不自动删除损坏 Workspace；
    - 不偷偷修改 project.json；
    - 不把缺失 Workspace 当成功打开。

    Raises:
        ProjectNotFoundError: 数据库不存在项目。
        ProjectWorkspaceMissingError: Workspace 已丢失。
        ProjectManifestInvalidError: project.json 损坏。
        ProjectIdMismatchError: DB 与 Manifest 指向不同项目。
        ProjectFormatUnsupportedError: 项目格式高于当前应用支持版本。
    """
```

Controller 示例：

```python
@router.post("/projects", response_model=ProjectDTO)
def create_project_endpoint(command: CreateProjectCommand):
    """
    新建项目 HTTP 入口。

    本函数只负责把 HTTP Request 转换成 create_project() 业务调用，
    再把成功结果返回给前端。

    它不负责：Project ID、路径、mkdir、SQL、Manifest、rollback。
    这些行为全部属于 Service/Repository/Manifest 层。
    """
```

---

# 12. 每开发一个函数时必须同时回答的问题

以后开发 B01、B02……U09，每次开始当前函数前必须在开发记录里回答：

```text
1. 这个函数解决什么真实业务问题？
2. 为什么需要独立成一个函数？
3. 谁调用它？
4. 它调用哪些下层函数？
5. 输入是什么，谁保证输入合法？
6. 输出是什么？
7. 它会修改 DB/文件/前端状态吗？
8. 它明确禁止修改什么？
9. 会抛哪些业务异常？
10. 对应哪几个测试？
```

如果这 10 项解释不清，说明函数边界还没有设计清楚，不开始编码。
