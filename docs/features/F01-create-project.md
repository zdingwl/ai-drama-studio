# Feature 01 — 创建项目（Create Project）

> F01 正式 Contract 草案。
>
> 详细单函数职责以 `docs/features/F01-function-contracts.md` 为准。
>
> 当前状态仍为 `PLANNED`；用户确认 Contract 后才进入 `IN_PROGRESS`。
>
> Git：当前按用户要求直接维护 `main`，不得擅自新建/切换分支或 PR。

---

# 0. 基础信息

```text
Feature ID: F01
Name: 创建项目
Version: v1
Status: PLANNED
Working Branch: main
PR: N/A
Project Format Version: 1
Business Code: NOT_STARTED
```

## 一句话目标

让用户可以在本机创建一个 AI Drama Studio 项目，系统生成稳定 Project ID、应用级项目记录、独立 Workspace 与 `project.json`；关闭并重新启动应用后仍能从最近项目重新进入。

---

# 1. Scope

## 1.1 F01 必须完成

- Vue 3 + TypeScript + Vite 最小前端骨架；
- FastAPI 最小后端骨架；
- 应用级 SQLite `app.db`；
- Alembic 初始 Migration；
- 新建项目；
- 最近项目列表；
- 打开/进入已有项目；
- `/projects/:id` 刷新和直接访问可恢复；
- 自动创建 Project Workspace；
- 原子写入 `project.json`；
- 稳定 `project_id`；
- `project_format_version = 1`；
- 记录创建时 app/schema 基线；
- DB + 文件系统跨资源创建的安全事务边界；
- final 发布前失败回滚；
- final 发布后失败保留给 startup recovery；
- 启动时恢复 `creating` 项目；
- 业务代码/数据库/API Schema 简体中文说明；
- A/B 级函数对应测试；
- 用户可独立执行验收步骤。

## 1.2 F01 明确不做

- 视频上传；
- FFmpeg / FFprobe；
- Episode；
- Source Asset；
- Shot；
- Character；
- Dialogue；
- Scene；
- Actor Library；
- AI Model / Provider；
- GPU 检测；
- TTS / Lip Sync；
- 删除项目；
- 重命名项目；
- 项目归档；
- 项目导入/导出；
- Workspace relink；
- Electron 原生文件夹选择器；
- Electron 打包。

F02 前不得出现真实“上传原片”逻辑。

---

# 2. 核心架构决策（待用户确认后冻结）

## 2.1 数据库：应用级单 SQLite

```text
%LOCALAPPDATA%/AI Drama Studio/
└── app.db
    └── projects
```

V1 不采用“每项目一个 SQLite”。

原因：

- 最近项目天然需要应用级注册表；
- 后续 Actor Library 等存在跨项目共享可能；
- 一套连接/Migration/备份/事务更容易维护；
- 不在 F01 引入 Global DB + N Project DB 双数据库复杂度。

Project Workspace 仍通过 `project.json` 自描述，为未来 Import/Export/Package 保留能力。

## 2.2 应用数据目录

正式 Windows 默认：

```text
%LOCALAPPDATA%/AI Drama Studio/
```

开发/测试允许：

```text
AI_DRAMA_APP_DATA_DIR
```

测试必须指向临时目录，禁止污染真实用户数据。

## 2.3 默认 Workspace Root

```text
%USERPROFILE%/AI Drama Studio Projects/
```

用户可以创建项目时输入自定义根目录。

浏览器开发阶段只提供路径文本输入；Electron 后续只负责选择目录并填回同一 `workspace_root` 字段，不改变 API Contract。

## 2.4 Project ID

```text
PROJECT_<UUID4_HEX>
```

例如：

```text
PROJECT_86f767c94f2c4f96a1676ce36f615406
```

规则：

- 创建后永不改变；
- 不依赖项目名；
- 不依赖视频名；
- 不依赖 Provider/Model；
- Project Workspace 目录名直接使用 Project ID。

## 2.5 Project Workspace

F01 final 目录只有：

```text
<workspace_root>/
└── <project_id>/
    └── project.json
```

创建过程中使用：

```text
<workspace_root>/.ai-drama-staging/<project_id>/
```

F01 不提前创建：

```text
source/
proxy/
audio/
frames/
shots/
characters/
scenes/
generations/
voice/
lipsync/
exports/
```

谁首次使用，谁负责创建。

## 2.6 Project Manifest

V1：

```json
{
  "project_id": "PROJECT_86f767c94f2c4f96a1676ce36f615406",
  "project_format_version": 1,
  "name": "测试短剧",
  "source_language_code": "zh",
  "target_language_code": "en",
  "target_region_code": "US",
  "created_with_app_version": "0.1.0-dev",
  "created_with_schema_revision": "0001_create_projects",
  "created_at": "2026-08-23T07:00:00Z"
}
```

Manifest 不保存：

- API Key；
- Provider Secret；
- 未来 AI Result；
- 绝对媒体文件清单。

---

# 3. 用户操作流程

```text
打开应用
→ 首页加载最近项目
→ 点击“新建项目”
→ Dialog 按需加载默认 Workspace Root
→ 输入项目资料
→ 点击创建
→ UI creating
→ 后端创建 DB creating 记录
→ staging 写 project.json
→ 发布 final Workspace
→ DB ready
→ 返回 ProjectDTO
→ 自动进入 /projects/:id
```

已有项目：

```text
点击项目卡片
或刷新/直接访问 /projects/:id
→ 调用同一个 open API
→ 验证 DB ready + Workspace + Manifest
→ 更新 last_opened_at
→ 显示空 Workspace
```

F01 **不再维护“查项目详情但不打开”的第二套流程**。

---

# 4. UI Contract

## 4.1 `/` Project Home

```text
AI Drama Studio

[ + 新建项目 ]

最近项目
┌────────────────────────┐
│ 测试短剧                │
│ 中文 → 英语 / 美国       │
│ D:\AI Drama...          │
│ 最近进入：...            │
└────────────────────────┘
```

## 4.2 `/projects/:projectId`

F01 空 Workspace：

```text
项目名称
Project ID
目标语言 / 地区
Workspace 路径

项目已创建。
下一业务步骤：F02 上传原视频（本 Feature 不实现）。
```

禁止出现可工作的上传按钮。

## 4.3 Create Project Dialog

| UI 字段 | API/DB | 必填 | V1 |
|---|---|---:|---|
| 项目名称 | `name` | Yes | trim 后 1–100 字符 |
| 原片语言 | `source_language_code` | No | 空 = 尚未确认 |
| 目标语言 | `target_language_code` | Yes | 稳定 code，例如 `en` |
| 目标地区 | `target_region_code` | Yes | 稳定 code，例如 `US` |
| 存储位置 | `workspace_root` | No | 空 = 后端默认 Root |

Defaults 只在 Dialog 需要时加载，不随首页项目列表一起加载。

## 4.4 UI 状态

```text
idle
loading_projects
loading_defaults
creating
opening
error
```

创建中必须禁用重复提交。

---

# 5. Input Contract

## CreateProjectCommand

```json
{
  "name": "测试短剧",
  "source_language_code": "zh",
  "target_language_code": "en",
  "target_region_code": "US",
  "workspace_root": "D:\\AI Drama Studio Projects"
}
```

规则：

- `name` required；
- `source_language_code` nullable；
- `target_language_code` required；
- `target_region_code` required；
- `workspace_root` nullable；
- 项目名可以重复；
- 项目名不参与路径生成。

---

# 6. Output Contract

## ProjectDTO

```json
{
  "id": "PROJECT_86f767c94f2c4f96a1676ce36f615406",
  "name": "测试短剧",
  "source_language_code": "zh",
  "target_language_code": "en",
  "target_region_code": "US",
  "workspace_path": "D:\\AI Drama Studio Projects\\PROJECT_86f767c94f2c4f96a1676ce36f615406",
  "project_format_version": 1,
  "lifecycle_state": "ready",
  "created_with_app_version": "0.1.0-dev",
  "created_with_schema_revision": "0001_create_projects",
  "created_at": "2026-08-23T07:00:00Z",
  "updated_at": "2026-08-23T07:00:00Z",
  "last_opened_at": "2026-08-23T07:00:00Z",
  "workspace_available": true
}
```

`workspace_available` 只在响应时计算，不持久化。

`last_opened_at` 语义：

> 最近一次**成功进入 Project Workspace** 的时间。

因此项目卡片点击、刷新 `/projects/:id`、直接访问 `/projects/:id` 成功后都会更新。

---

# 7. Data Access Contract

## F01 允许

```text
app.db
projects 表
Project Workspace Root
.ai-drama-staging/<project_id>
<project_id>/project.json
F01 日志/配置
```

## F01 禁止

```text
episodes
assets
shots
characters
dialogues
scenes
actors
bibles
generations
qc_results
voices
lipsync
renders
provider_jobs
```

禁止为了 F02/F03 方便提前建空表或空目录。

---

# 8. Database Contract

## 8.1 Database

```text
app.db
```

Alembic 首个 Revision：

```text
0001_create_projects
```

## 8.2 `projects`

| Field | Type | Null | Default | 中文业务作用 | 修改者 | Frozen |
|---|---|---:|---|---|---|---:|
| `id` | TEXT PK | No | - | 稳定 Project 业务 ID，创建后永不变化 | F01 create | Yes |
| `name` | TEXT | No | - | 用户看到的项目名称 | Future explicit rename | Semantic |
| `source_language_code` | TEXT | Yes | NULL | 原片语言；NULL=尚未确认 | Future explicit feature | Semantic |
| `target_language_code` | TEXT | No | - | 目标语言 code | Future explicit edit | Semantic |
| `target_region_code` | TEXT | No | - | 本土化目标地区 code | Future explicit edit | Semantic |
| `workspace_path` | TEXT | No | - | 应用定位 Project Workspace 的绝对路径 | Future relink only | Yes |
| `lifecycle_state` | TEXT | No | `creating` | 创建事务状态：`creating/ready` | F01/recovery | Yes |
| `project_format_version` | INTEGER | No | `1` | Workspace/Manifest 格式版本 | Project migration | Yes |
| `created_with_app_version` | TEXT | No | - | 创建该项目时应用版本 | Never | Yes |
| `created_with_schema_revision` | TEXT | No | - | 创建该项目时 app.db schema revision | Never | Yes |
| `created_at` | UTC DateTime | No | now | 创建时间 | Never | Yes |
| `updated_at` | UTC DateTime | No | now | 项目记录更新时间 | Service | No |
| `last_opened_at` | UTC DateTime | Yes | NULL | 最近成功进入 Workspace 时间 | open project | No |

Constraints：

```text
PRIMARY KEY(id)
UNIQUE(workspace_path)
INDEX(last_opened_at)
INDEX(lifecycle_state)
CHECK(lifecycle_state IN ('creating', 'ready'))
CHECK(project_format_version >= 1)
```

项目名不唯一。

## 8.3 Repository 事务规则

Repository：

```text
SELECT / INSERT / UPDATE / DELETE / flush
```

Repository **不得隐藏 `commit/rollback`**。

Service/Recovery 决定事务边界。

原因：创建项目横跨 DB + 文件系统，commit 时机是业务 Contract，不是 Repository 私有实现。

---

# 9. File / Recovery Contract

## 9.1 创建状态机

```text
Normalize Request
→ Resolve Workspace Root
→ prepare_workspace_root()       # 可能创建 root + 写权限 probe
→ Generate Project ID
→ Build ProjectPaths
→ Assert staging/final unused
→ DB add creating
→ COMMIT #1                       # 崩溃恢复锚点
→ Create staging
→ Atomic project.json write
→ Validate staging manifest
→ Rename staging → final          # FILE PUBLISH POINT
→ Validate final workspace
→ DB set ready + last_opened_at
→ COMMIT #2
→ Return ProjectDTO
```

## 9.2 发布前失败

如果还没有发生：

```text
staging → final
```

则允许：

```text
rollback current DB transaction
→ 安全清理当前 Project staging
→ 删除 creating row
→ commit cleanup
```

禁止递归删除用户 Workspace Root。

## 9.3 发布后失败

一旦 final Workspace 已发布：

```text
<root>/<project_id>/
```

则：

- 禁止自动删除 final；
- 禁止删除 creating DB row；
- 当前 DB transaction rollback；
- 保留 `creating + valid final` 给 startup recovery；
- 返回 `PROJECT_CREATE_FINALIZATION_PENDING`。

这是安全边界：**数据库整洁不能优先于用户已经发布成功的 Project 文件。**

## 9.4 Startup Recovery

查询所有 `creating`：

```text
Case A: valid final
→ set ready → commit

Case B: no final + valid staging
→ publish final → validate → set ready → commit

Case C: no final + no staging
→ delete incomplete DB row → commit

Case D: invalid staging + no final
→ cleanup owned staging → delete incomplete row → commit

Case E: final exists but invalid / ID mismatch
→ 不删除 final
→ 不标 ready
→ 保留 creating row
→ 记录高优先级 recovery log
```

F01 不提供 Case E repair UI，这是 V1 已知限制。

---

# 10. API Contract

统一 Error Envelope：

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

## 10.1 Health

```text
GET /api/v1/health
```

只确认 FastAPI 可通信，不检测 FFmpeg/GPU/Model。

## 10.2 Defaults

```text
GET /api/v1/projects/defaults
```

返回：

```json
{
  "default_workspace_root": "C:\\Users\\User\\AI Drama Studio Projects",
  "project_format_version": 1
}
```

## 10.3 List

```text
GET /api/v1/projects
```

- 只返回 ready；
- `last_opened_at DESC`，再 `created_at DESC`；
- 轻量计算 `workspace_available`；
- 单个 Workspace 缺失不能让整个列表 500。

## 10.4 Create

```text
POST /api/v1/projects
```

成功：

```text
201 Created
```

Request = CreateProjectCommand  
Response = ProjectDTO

## 10.5 Open

```text
POST /api/v1/projects/{project_id}/open
```

所有“进入 Workspace”场景都使用它，包括页面刷新/直接 URL。

必须验证：

```text
DB project exists
+ lifecycle_state = ready
+ Workspace exists
+ project.json exists
+ Manifest valid
+ project_id matches
+ project_format_version supported
→ update last_opened_at
→ return ProjectDTO
```

### F01 删除的旧 API

```text
GET /api/v1/projects/{project_id}
```

不实现。

原因：F01 没有需要“只查详情但不验证 Workspace”的真实用户流程。

---

# 11. Error Contract

| Code | HTTP | 触发 | Retryable | UI |
|---|---:|---|---:|---|
| `PROJECT_NAME_REQUIRED` | 422 | 名称空 | No | 字段提示 |
| `PROJECT_NAME_TOO_LONG` | 422 | >100 | No | 字段提示 |
| `PROJECT_TARGET_LANGUAGE_REQUIRED` | 422 | 目标语言空 | No | 字段提示 |
| `PROJECT_TARGET_REGION_REQUIRED` | 422 | 目标地区空 | No | 字段提示 |
| `PROJECT_WORKSPACE_ROOT_INVALID` | 422 | 路径语义非法 | No | 路径提示 |
| `PROJECT_WORKSPACE_NOT_WRITABLE` | 409 | Root 无法写 | Maybe | 换目录/重试 |
| `PROJECT_CREATE_CONFLICT` | 409 | staging/final 冲突 | Yes | 允许重新创建 |
| `PROJECT_CREATE_FINALIZATION_PENDING` | 503 | final 已发布，但 DB 未成功转 ready | Yes | 提示项目文件已保留，将由恢复流程完成 |
| `PROJECT_CREATE_FAILED` | 500 | 未分类发布前创建失败 | Maybe | 展示 log id |
| `PROJECT_NOT_FOUND` | 404 | DB 不存在 | No | 返回首页 |
| `PROJECT_NOT_READY` | 409 | 仍为 creating | Maybe | 提示等待恢复 |
| `PROJECT_WORKSPACE_MISSING` | 409 | final 目录不存在 | No | 明确提示 |
| `PROJECT_MANIFEST_MISSING` | 409 | project.json 缺失 | No | 明确提示 |
| `PROJECT_MANIFEST_INVALID` | 409 | JSON/Schema 错误 | No | 明确提示 |
| `PROJECT_ID_MISMATCH` | 409 | DB/Manifest ID 不同 | No | 阻止打开 |
| `PROJECT_FORMAT_UNSUPPORTED` | 409 | Format 高于当前支持 | No | 提示升级/迁移 |

---

# 12. 单函数规划规则

详细：

```text
docs/features/F01-function-contracts.md
```

统一三级：

```text
A级：核心业务/Controller/DB-File状态变化/Recovery
→ 完整 Function Contract

B级：Repository/Manifest/Frontend API/Store/有业务语义的 helper
→ 简化 Contract

C级：日期格式化/JSON小helper/reset/router back 等
→ 代码注释 + 必要测试，不单独写大段 Contract
```

禁止再次出现“为了单函数而把每个一行 helper 都升成正式 Function”。

---

# 13. 审核后的正式函数清单

## Infrastructure

```text
INF-01 resolve_app_data_dir()
INF-02 resolve_default_workspace_root()
INF-03 create_database_engine()
INF-04 get_db_session()
INF-05 run_database_migrations()
INF-06 read_schema_revision()
INF-07 application_lifespan()
INF-08 create_app()
```

## Project / Path

```text
PRJ-01 generate_project_id()
PRJ-02 normalize_project_name()
PRJ-03 normalize_language_code()
PRJ-04 normalize_region_code()
PRJ-05 resolve_workspace_root()
PRJ-06 prepare_workspace_root()
PRJ-07 build_project_paths()
PRJ-08 assert_project_paths_unused()
```

## Manifest

```text
MAN-01 build_project_manifest()
MAN-02 write_project_manifest_atomic()
MAN-03 read_project_manifest()
MAN-04 validate_project_manifest()
MAN-05 validate_project_workspace()
```

## Repository

```text
DB-01 add_creating_project()
DB-02 find_project_by_id()
DB-03 list_ready_projects()
DB-04 set_project_ready()
DB-05 set_project_last_opened_at()
DB-06 delete_incomplete_project()
DB-07 list_incomplete_projects()
```

Repository 不 commit。

## Recovery

```text
REC-01 cleanup_owned_staging_directory()
REC-02 rollback_unpublished_project_creation()
REC-03 recover_incomplete_project()
REC-04 recover_interrupted_project_creations()
```

## Service

```text
SVC-01 create_project()
SVC-02 list_projects()
SVC-03 open_project()
SVC-04 get_project_defaults()
```

## API

```text
API-01 health_endpoint()
API-02 project_defaults_endpoint()
API-03 list_projects_endpoint()
API-04 create_project_endpoint()
API-05 open_project_endpoint()
API-06 domain_error_handler()
```

## Frontend API

```text
FEAPI-01 request<T>()
FEAPI-02 getProjectDefaults()
FEAPI-03 fetchProjects()
FEAPI-04 createProject()
FEAPI-05 openProject()
```

## Store

```text
STORE-01 loadRecentProjects()
STORE-02 loadCreateProjectDefaults()
STORE-03 createNewProject()
STORE-04 openProjectById()
```

`clearProjectError()` 为 C 级 helper。

## UI

```text
UI-01 handleOpenCreateDialog()
UI-02 validateCreateProjectForm()
UI-03 handleCreateSubmit()
UI-04 handleProjectCardClick()
UI-05 bootstrapProjectWorkspace()
```

表单 reset、locale/time formatting、back navigation 为 C 级，不进入正式 Function Contract。

---

# 14. 推荐目录

Backend：

```text
engine/
├── requirements / lock
├── alembic.ini
├── migrations/
│   └── versions/0001_create_projects.py
├── app/
│   ├── main.py
│   ├── core/
│   │   ├── config.py
│   │   ├── paths.py
│   │   ├── database.py
│   │   └── errors.py
│   ├── api/v1/
│   │   ├── router.py
│   │   ├── health.py
│   │   └── projects.py
│   ├── models/project.py
│   ├── schemas/project.py
│   ├── repositories/projects.py
│   ├── services/
│   │   ├── project_validation.py
│   │   ├── project_paths.py
│   │   ├── project_manifest.py
│   │   ├── project_recovery.py
│   │   └── project_service.py
│   └── utils/ids.py
└── tests/
    ├── unit/
    └── integration/
```

Frontend：

```text
frontend/
├── package.json + lock
├── src/
│   ├── main.ts
│   ├── App.vue
│   ├── router/index.ts
│   ├── api/http.ts
│   ├── api/projects.ts
│   ├── types/project.ts
│   ├── stores/project.ts
│   ├── views/ProjectHome.vue
│   ├── views/ProjectWorkspace.vue
│   └── components/projects/
│       ├── CreateProjectDialog.vue
│       └── ProjectCard.vue
└── tests/
```

只创建 F01 真正使用的模块。

---

# 15. Dependencies

F01 Backend 只引入实际需要的：

```text
FastAPI
Uvicorn
SQLAlchemy
Alembic
Pydantic / pydantic-settings（需要配置时）
pytest
httpx（测试需要时）
```

Frontend：

```text
Vue 3
TypeScript
Vite
Vue Router
Pinia
Vitest
Vue Test Utils
```

F01 不安装：

```text
PyTorch
CUDA Python packages
OpenCV
Whisper
DINO
TransNetV2
视频 Provider SDK
```

正式编码时锁定精确版本并同步 `docs/ENVIRONMENT_BASELINE.md`。

---

# 16. P0 Checklist

## P0-01 Dependency / Invalidation

部分适用。

F01 无上游派生数据，但以下内容验收后成为未来 Stable Contract：

```text
Project ID
project_format_version
Workspace path rule
Manifest v1
projects 字段语义
```

## P0-02 Media Timebase

```text
N/A
```

## P0-03 Environment Baseline

```text
PASS 前置要求：实际版本锁定 + 新环境安装验证
```

## P0-04 DB + File Recovery

强适用。

必须覆盖：

```text
creating DB anchor
staging
atomic Manifest
file publish point
pre-publish rollback
post-publish preserve
startup recovery
```

## P0-05 Provider Job

```text
N/A
```

---

# 17. 测试计划

## 17.1 Backend Unit

至少：

```text
Project ID format/uniqueness
Project name boundaries
Language/Region normalization
Default/custom Workspace resolution
prepare_workspace_root 创建/写权限/probe cleanup
ProjectPaths 构造
Path conflict
Manifest build/write/read/validate
Manifest ID mismatch
Unsupported format
Repository creating/ready transition（验证 Repository 不自行 commit）
Ready list order
Delete incomplete safety
Pre-publish rollback
Post-publish final preservation
Recovery valid final
Recovery valid staging
Recovery no files
Recovery invalid staging
Recovery invalid final preservation
create_project happy path
create_project DB commit#1 failure
create_project manifest failure
create_project publish failure
create_project ready commit failure → FINALIZATION_PENDING
open missing workspace
open missing/invalid manifest
open ID mismatch
open unsupported format
```

## 17.2 API Integration

```text
GET health → 200
GET defaults → 200
GET projects → []
POST project → 201
POST invalid name → 422
POST invalid root → 422/409
POST open success
POST open not found
POST open missing workspace
确认不存在 GET /projects/{id} F01 detail API
Restart backend → 已创建项目仍存在
```

## 17.3 Frontend

```text
首页 empty state
loadRecentProjects 不请求 defaults
打开 Dialog 才加载 defaults
Dialog validation
creating 禁止重复 submit
创建成功导航 Workspace
卡片点击先 open 成功再导航
直接访问 /projects/:id 调用 open
刷新 /projects/:id 仍调用 open 并恢复
Workspace 缺失时不展示假 Workspace
Error Envelope 正确显示
```

---

# 18. 用户验收

F01 不需要短剧素材。

```text
1. 启动 FastAPI + Vue。
2. 首页为空项目状态。
3. 打开新建 Dialog，能看到默认保存位置。
4. 创建项目 A：中文 → 英语 / 美国，默认 Root。
5. POST create 返回 201。
6. app.db 中项目为 ready。
7. Workspace 只有 project.json。
8. Manifest ID/format/locale/app/schema 正确。
9. 自动进入 /projects/:id。
10. 返回首页，A 出现在最近项目。
11. 关闭前后端并重新启动。
12. A 仍存在。
13. 点击 A，open 成功并更新时间。
14. 刷新 Workspace，仍通过 open 校验并恢复。
15. 创建自定义 Root 项目 B。
16. 创建同名项目 C，允许成功且 ID 不同。
17. 非法/不可写 Root 创建失败，不残留 ready 项目。
18. 手工删除 A Workspace，进入时明确提示缺失，不能假装成功。
```

Recovery 集成测试：

```text
creating + valid staging → restart → final + ready
creating + valid final → restart → ready
creating + no files → restart → DB incomplete row cleanup
creating + invalid staging → safe cleanup
creating + invalid final → final 不删、creating 保留、日志明确
```

---

# 19. Definition of Done

F01 只有满足全部适用项才能 `READY_FOR_REVIEW`：

```text
[ ] A/B级 Function Contract 与代码一致
[ ] C级 helper 未被过度文档化但有必要注释/测试
[ ] Model + 0001 Migration 完成
[ ] Database Dictionary 与代码字段一致
[ ] Repository 不隐藏 commit/rollback
[ ] create_project 两阶段 DB commit + file publish 实现正确
[ ] pre-publish rollback 安全
[ ] post-publish final 永不自动删除
[ ] startup recovery 完成
[ ] Project ID / Manifest / Format 正确
[ ] API Create=201
[ ] F01 不存在 GET project detail 双逻辑
[ ] Frontend 统一 openProjectById
[ ] defaults lazy load
[ ] 中文业务注释 Review PASS
[ ] Backend Unit PASS
[ ] API Integration PASS
[ ] Frontend Tests PASS
[ ] Regression N/A（无 Stable 上游）
[ ] P0 PASS/N/A
[ ] Feature Doc / Function Contract / Session / PROJECT_STATE 同步
```

Agent 只能推进到：

```text
READY_FOR_REVIEW
```

用户明确验收后才能：

```text
STABLE / FROZEN
```

---

# 20. F01 预计冻结项

```text
Project ID format
project_format_version = 1
projects table 字段语义
Workspace Root/Final/Staging 路径规则
project.json v1
CreateProjectCommand
ProjectDTO
Create/List/Defaults/Open API
Create 201 status
Error Envelope / F01 error codes
creating → ready lifecycle
file publish point
startup recovery behavior
last_opened_at 语义
```

F02 不允许为了上传视频方便改变这些语义。

---

# 21. 不冻结 / 后续可扩展

```text
删除项目
重命名
归档
Import/Export
Workspace relink
Electron folder picker
Project thumbnail
Project tags
Search/filter
Recovery repair UI
```

---

# 22. 审核后的正式编码顺序

```text
Step 01 INF-01~04 基础路径/DB runtime
Step 02 INF-05~06 Migration / schema revision
Step 03 PRJ-01~08 Project输入/路径
Step 04 MAN-01~05 Manifest
Step 05 Project Model + 0001 Migration + Database Dictionary
Step 06 DB-01~07 Repository
Step 07 REC-01~02 安全清理/发布前回滚
Step 08 SVC-01 create_project
Step 09 REC-03~04 startup recovery
Step 10 SVC-02~04 list/open/defaults
Step 11 API-01~06
Step 12 INF-07~08 lifespan/create_app 最终接入
Step 13 Vue/Router/Pinia 最小骨架
Step 14 FEAPI-01~05
Step 15 STORE-01~04
Step 16 UI-01~05
Step 17 前后端联调
Step 18 Crash/Restart/Recovery 集成测试
Step 19 READY_FOR_REVIEW 验收包
```

注意：`application_lifespan()` 虽属于 Infrastructure，但必须等 Recovery 函数已经存在后再最终接入，避免先写空壳后返工。

---

# 23. 用户确认前的关键决策

审核后仍需用户确认：

```text
1. 应用级单 SQLite app.db。
2. 默认 Workspace Root = %USERPROFILE%/AI Drama Studio Projects。
3. Project ID = PROJECT_<UUID4_HEX>。
4. Final Workspace = <root>/<project_id>/。
5. F01 只创建 project.json，不提前创建媒体目录。
6. 浏览器开发期自定义路径使用文本输入。
7. F01 暂不做删除/重命名/归档/导入导出。
8. project_format_version = 1。
9. 生命周期仍使用 creating/ready；无法自动恢复的 invalid-final 情况保留 creating + 日志，不在 F01 做 repair UI。
10. 所有进入 Workspace 的动作（卡片、刷新、直接 URL）统一走 POST /open，并允许更新 last_opened_at。
11. Create Project 成功 HTTP Status = 201 Created。
12. final Workspace 一旦发布，后续失败不得自动删除；由 startup recovery 完成 DB finalization。
```

用户确认后：

```text
F01 PLANNED → IN_PROGRESS
```

然后才开始正式业务代码。

---

# 24. Next Action

> 继续审核并确认本 Contract 第 23 节 12 项决策。
>
> 未确认前不编码、不实现 F02、不擅自创建分支。
