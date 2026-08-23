# Feature 01 — 创建项目（Create Project）

> 本文档是 F01 的正式 Contract 草案与单函数开发计划。
>
> 当前只做规划，不代表已开始业务编码；用户确认本 Contract 后，F01 才进入 `IN_PROGRESS`。
>
> Git 规则：本次直接维护用户指定的 `main`，不得擅自创建/切换任何分支或 PR。

---

## 0. 基础信息

```text
Feature ID: F01
Name: 创建项目
Version: v1
Status: PLANNED
Working Branch: main（用户未要求其它分支）
PR: N/A
Project Format Version: 1
Business Code: NOT_STARTED
```

### F01 一句话目标

让用户能够在本机创建一个 AI Drama Studio 项目，系统生成稳定 Project ID、全局项目记录、独立 Workspace 与 `project.json` Manifest；关闭/重启后仍可从项目列表打开并恢复该项目。

---

# 1. F01 的边界

## 1.1 必须完成

- 建立最小可运行 Vue 3 + TypeScript + Vite 前端骨架；
- 建立最小可运行 FastAPI 后端骨架；
- 建立应用级 SQLite `app.db`；
- 建立 Alembic 初始 migration；
- 新建项目；
- 最近项目列表；
- 打开已有项目；
- 进入空项目工作区；
- 自动创建 Project Workspace；
- 自动写 `project.json`；
- 稳定 Project ID；
- `project_format_version = 1`；
- 保存创建时 app/schema 基线；
- 创建过程中 DB + 文件系统失败回滚；
- 应用重启时恢复 interrupted project creation；
- 代码/表/字段/API Schema 使用简体中文业务说明；
- 单函数单测、API 集成测试、前端交互测试；
- 用户可按验收步骤独立验证。

## 1.2 明确不做

F01 禁止实现：

- 上传视频；
- FFprobe / FFmpeg 媒体分析；
- Episode；
- Asset / Source Video；
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
- 项目路径重新绑定；
- 原生 Windows 文件夹选择器；
- Electron。

F02 之前不得出现“导入原片”的真实业务逻辑。

---

# 2. F01 核心架构决策（待用户确认后冻结）

## 2.1 数据库：应用级 `app.db`

F01 推荐：

```text
Application Data
└── app.db
    └── projects
```

而不是：

```text
每个 Project 一个独立 SQLite
```

原因：

- 最近项目列表需要全局注册表；
- 后续 Actor Library 等天然存在跨项目共享需求；
- 单应用级 DB 的连接、Migration、备份、事务更简单；
- 避免第一版同时维护“global DB + N 个 project DB”；
- Project Workspace 仍通过 `project.json` 自描述，为未来导入/迁移保留能力。

如果未来确认必须“整个项目文件夹复制到另一台电脑即完全独立运行”，再设计 Project Export / Import 或 Project Package，不在 F01 引入双数据库复杂度。

## 2.2 应用数据目录

Windows 正式默认：

```text
%LOCALAPPDATA%/AI Drama Studio/
├── app.db
└── logs/
```

开发/测试允许环境变量覆盖：

```text
AI_DRAMA_APP_DATA_DIR
```

测试必须使用 pytest 临时目录，禁止污染真实用户目录。

## 2.3 默认项目 Workspace 根目录

默认建议：

```text
%USERPROFILE%/AI Drama Studio Projects/
```

允许创建项目时输入自定义根路径。

开发阶段由于前端运行在浏览器，不实现原生目录选择器；UI 提供路径文本输入，留空则使用后端默认路径。以后 Electron 只负责把原生目录选择结果填回同一个 `workspace_root` 字段，不改变 F01 API Contract。

## 2.4 Project ID

使用 Python 标准库，不新增第三方 ID 依赖：

```text
PROJECT_<UUID4_HEX>
```

示例：

```text
PROJECT_86f767c94f2c4f96a1676ce36f615406
```

规则：

- 创建后永不改变；
- 与项目名称无关；
- 与目录名称一致；
- 不能因重命名、复制媒体、模型切换改变；
- 后续 Episode / Shot / Character 等继续采用各自稳定业务 ID。

## 2.5 Project Workspace

F01 只创建最小目录：

```text
<workspace_root>/
└── PROJECT_<UUID>/
    └── project.json
```

禁止 F01 提前创建：

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

这些目录由首次真正需要它们的 Feature 创建。

## 2.6 Project Manifest

`project.json` 是 Workspace 的自描述入口，不代替数据库。

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
  "created_with_schema_revision": "0001",
  "created_at": "2026-08-23T07:00:00Z"
}
```

Manifest 不保存 API Key、绝对媒体文件清单或未来 AI 结果。

---

# 3. 用户操作流程

```text
打开 AI Drama Studio
→ 进入项目首页
→ 查看最近项目
→ 点击“新建项目”
→ 填写项目名称
→ 原片语言（可选；默认自动/未知）
→ 选择目标语言
→ 选择目标地区
→ 存储根目录可选，留空使用默认
→ 点击“创建项目”
→ UI 进入 creating 状态
→ 后端创建 DB + Workspace + Manifest
→ 成功
→ 自动进入空项目工作区
→ 关闭前端/后端
→ 再次启动
→ 最近项目仍存在
→ 点击项目
→ 校验 Workspace + Manifest
→ 更新 last_opened_at
→ 重新进入空工作区
```

---

# 4. UI Contract

## 4.1 页面

### `/`

Project Home：

```text
AI Drama Studio

[ + 新建项目 ]

最近项目
┌────────────────────────┐
│ 测试短剧                │
│ 中文 → 英语 / 美国       │
│ D:\AI Drama...          │
│ 最近打开：...            │
└────────────────────────┘
```

### `/projects/:projectId`

F01 空 Workspace：

```text
项目名称
Project ID
目标语言 / 目标地区
Workspace 路径

项目已创建。
下一步业务功能：F02 上传原视频（当前不实现）。
```

不出现可工作的上传按钮。

## 4.2 新建项目 Dialog

字段：

| UI 字段 | DB/API | 必填 | V1 行为 |
|---|---|---:|---|
| 项目名称 | `name` | Yes | trim 后 1–100 字符 |
| 原片语言 | `source_language_code` | No | 空 = 未确认/后续自动识别 |
| 目标语言 | `target_language_code` | Yes | 存稳定代码，如 `en` |
| 目标地区 | `target_region_code` | Yes | 存稳定代码，如 `US` |
| 存储位置 | `workspace_root` | No | 空 = 后端默认 Workspace Root |

## 4.3 UI 状态

```text
idle
loading_projects
creating
opening
success
error
```

创建中必须禁止重复点击“创建项目”。

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

- `name`: required, trim 后 1–100；
- `source_language_code`: nullable；
- `target_language_code`: required；
- `target_region_code`: required；
- `workspace_root`: nullable；
- 项目名重复允许；
- Workspace 最终目录不使用项目名，避免中文、特殊字符、重命名引起路径变化。

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
  "created_with_schema_revision": "0001",
  "created_at": "2026-08-23T07:00:00Z",
  "updated_at": "2026-08-23T07:00:00Z",
  "last_opened_at": "2026-08-23T07:00:00Z",
  "workspace_available": true
}
```

`workspace_available` 是响应时计算字段，不持久化。

---

# 7. Data Access Contract

## F01 允许新增/修改

```text
projects 表
app.db
Project Workspace 根目录
project.json
F01 自己的日志/配置
```

## F01 明确禁止新增/修改

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

F01 不能为了“以后方便”提前创建这些业务表。

---

# 8. Database Contract

## 8.1 Database

```text
app.db
```

应用级 SQLite。

初始 Alembic Revision：

```text
0001_create_projects
```

初始 DB 不存在时无需备份；未来对已有数据库做 schema migration 时必须遵守 Migration Backup 规则。

## 8.2 projects 表

| Field | Type | Nullable | Default | Business Meaning | Source | Mutable By | Frozen |
|---|---|---:|---|---|---|---|---:|
| `id` | TEXT PK | No | - | 项目稳定业务 ID，创建后永不变化 | F01 | Never | Yes |
| `name` | TEXT | No | - | 用户可读项目名称；V1 创建后暂不提供修改入口 | User | Future rename feature | Yes semantic |
| `source_language_code` | TEXT | Yes | NULL | 原片语言；NULL 表示尚未确认/后续识别 | User/F08 future | Future feature | Yes semantic |
| `target_language_code` | TEXT | No | - | 重制目标语言代码 | User | Future explicit edit | Yes semantic |
| `target_region_code` | TEXT | No | - | 本土化目标地区代码 | User | Future explicit edit | Yes semantic |
| `workspace_path` | TEXT | No | - | 项目 Workspace 绝对路径；全局 DB 用于定位项目 | F01 | Future relink only | Yes |
| `lifecycle_state` | TEXT | No | `creating` | F01 创建事务状态，仅允许 `creating/ready` | F01 | F01 recovery | Yes |
| `project_format_version` | INTEGER | No | `1` | Workspace/Manifest/持久化格式版本 | F01 | Project migration only | Yes |
| `created_with_app_version` | TEXT | No | - | 创建项目时应用版本，便于兼容追踪 | F01 | Never | Yes |
| `created_with_schema_revision` | TEXT | No | - | 创建项目时 app.db Alembic revision | F01 | Never | Yes |
| `created_at` | UTC DateTime | No | now | 项目创建时间 | F01 | Never | Yes |
| `updated_at` | UTC DateTime | No | now | 项目记录最后更新时间 | System | Project service | No |
| `last_opened_at` | UTC DateTime | Yes | NULL | 最近真正成功打开 Workspace 的时间 | F01 | Open project | No |

### Constraints / Indexes

```text
PRIMARY KEY(id)
UNIQUE(workspace_path)
INDEX(last_opened_at)
INDEX(lifecycle_state)
CHECK(lifecycle_state IN ('creating', 'ready'))
CHECK(project_format_version >= 1)
```

项目名称不唯一。

---

# 9. File / Workspace Contract

## 9.1 Staging

所有创建先进入同一 Workspace Root 下：

```text
<workspace_root>/.ai-drama-staging/<project_id>/
```

这样 staging → final 处于同一文件系统，才能使用 atomic rename/move。

## 9.2 Final

```text
<workspace_root>/<project_id>/project.json
```

## 9.3 创建状态机

```text
Validate Request
↓
Resolve Workspace Root
↓
Writable Probe
↓
Generate Project ID
↓
DB insert lifecycle_state=creating + COMMIT
↓
Create staging directory
↓
Write project.json.tmp
↓
fsync/close
↓
os.replace(project.json.tmp, project.json)
↓
Validate Manifest
↓
Atomic rename staging directory → final project directory
↓
Validate Final Workspace
↓
DB update lifecycle_state=ready + last_opened_at + COMMIT
↓
Return ProjectDTO
```

## 9.4 同步异常回滚

异常发生后：

```text
仅清理本次 generated project_id 对应 staging
↓
若 final 已出现，只在 manifest project_id 完全匹配时才允许清理
↓
删除 lifecycle_state=creating 的 DB row
↓
返回标准错误
```

禁止对用户提供的 `workspace_root` 做递归删除。

## 9.5 应用启动恢复

启动时查询所有 `creating` 项目：

```text
Case A: final dir + valid manifest
→ mark ready

Case B: staging dir + valid manifest + final missing
→ atomic rename → final
→ mark ready

Case C: DB creating，但 staging/final 都不存在
→ 删除 creating row

Case D: staging 存在但 manifest 无效
→ 仅清理已确认属于本 project_id 的 staging
→ 删除 creating row
→ 记录 recovery log

Case E: final 存在但 manifest 无效/ID 不一致
→ 不删除 final
→ 删除 creating row
→ 记录 orphan/conflict log
```

F01 不提供 orphan repair UI。

---

# 10. API Contract

统一错误格式：

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

用途：前端启动确认 FastAPI 正常。

## 10.2 Project Defaults

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

## 10.3 List Projects

```text
GET /api/v1/projects
```

规则：

- 只返回 `ready`；
- `last_opened_at DESC NULLS LAST`，再 `created_at DESC`；
- 计算 `workspace_available`；
- 不因某一个 Workspace 缺失导致整个列表 500。

## 10.4 Create Project

```text
POST /api/v1/projects
```

Request = `CreateProjectCommand`。

Response = `ProjectDTO`。

## 10.5 Get Project

```text
GET /api/v1/projects/{project_id}
```

用于 `/projects/:projectId` 页面刷新恢复，不修改 `last_opened_at`。

## 10.6 Open Project

```text
POST /api/v1/projects/{project_id}/open
```

必须：

```text
DB ready
+ Workspace exists
+ project.json exists
+ manifest valid
+ project_id match
+ project_format_version supported
→ update last_opened_at
→ return ProjectDTO
```

---

# 11. Error Contract

| Code | HTTP | Trigger | Retryable | UI 行为 |
|---|---:|---|---:|---|
| `PROJECT_NAME_REQUIRED` | 422 | 项目名为空 | No | 表单字段提示 |
| `PROJECT_NAME_TOO_LONG` | 422 | >100 | No | 表单字段提示 |
| `PROJECT_TARGET_LANGUAGE_REQUIRED` | 422 | 目标语言为空 | No | 表单字段提示 |
| `PROJECT_TARGET_REGION_REQUIRED` | 422 | 目标地区为空 | No | 表单字段提示 |
| `PROJECT_WORKSPACE_ROOT_INVALID` | 422 | 路径非法 | No | 存储位置提示 |
| `PROJECT_WORKSPACE_NOT_WRITABLE` | 409 | 无写权限/磁盘路径不可写 | Maybe | 提示换目录/重试 |
| `PROJECT_CREATE_CONFLICT` | 409 | 生成目标目录意外已存在 | Yes | 允许重新创建 |
| `PROJECT_CREATE_FAILED` | 500 | 未分类创建失败 | Maybe | 显示错误并保留日志 ID |
| `PROJECT_NOT_FOUND` | 404 | DB 无该项目 | No | 返回首页 |
| `PROJECT_NOT_READY` | 409 | lifecycle 非 ready | Maybe | 提示项目仍在恢复 |
| `PROJECT_WORKSPACE_MISSING` | 409 | 项目目录不存在 | No | 卡片显示路径缺失 |
| `PROJECT_MANIFEST_MISSING` | 409 | project.json 不存在 | No | 提示 Workspace 损坏 |
| `PROJECT_MANIFEST_INVALID` | 409 | JSON/字段错误 | No | 提示项目清单损坏 |
| `PROJECT_ID_MISMATCH` | 409 | DB ID != manifest ID | No | 阻止打开 |
| `PROJECT_FORMAT_UNSUPPORTED` | 409 | 格式版本高于当前支持 | No | 提示应用升级/迁移 |

---

# 12. 单函数开发原则

F01 不采用“先把整个后端写完再测”。

规则：

```text
写函数
→ 写该函数测试
→ 测试通过
→ Commit/记录
→ 下一个函数
```

如果函数依赖前一个函数，前一个函数测试未通过不得继续。

---

# 13. 单函数开发顺序 — Backend Foundation

| No. | Function | 文件建议 | 单一职责 | 输入 | 输出/副作用 | 对应测试 |
|---:|---|---|---|---|---|---|
| B01 | `resolve_app_data_dir()` | `engine/app/core/paths.py` | 解析应用数据根目录 | env + OS | `Path` | env override / Windows fallback |
| B02 | `resolve_default_workspace_root()` | `core/paths.py` | 解析默认项目根目录 | env + home | `Path` | override / default |
| B03 | `ensure_directory(path)` | `core/paths.py` | 只确保指定目录存在 | Path | mkdir | exists / create / failure |
| B04 | `probe_directory_writable(path)` | `core/paths.py` | 用临时文件确认目录真的可写 | Path | bool/exception | writable / denied |
| B05 | `build_database_url(app_data_dir)` | `core/database.py` | 构造 SQLite URL | Path | str | Windows path escaping |
| B06 | `create_db_engine(database_url)` | `core/database.py` | 创建 SQLAlchemy Engine | URL | Engine | connection smoke test |
| B07 | `get_db_session()` | `core/database.py` | FastAPI request DB session | Engine/sessionmaker | Session | session closes |
| B08 | `get_schema_revision()` | `core/database.py` | 读取当前 Alembic revision | DB | revision string | initial revision |
| B09 | `ensure_database_schema()` | `core/database.py` | 首次启动执行 initial migration/校验 schema | DB path | schema ready | fresh DB / mismatch |
| B10 | `create_app()` | `engine/app/main.py` | 组装 FastAPI、router、startup | settings | FastAPI app | TestClient starts |
| B11 | `health_check()` | `api/v1/health.py` | 返回后端健康状态 | none | JSON | 200 response |

说明：B01–B11 是 F01 必需的最小工程骨架；不得顺手初始化 FFmpeg、CUDA、模型或 Provider。

---

# 14. 单函数开发顺序 — Project Validation / ID / Paths

| No. | Function | 文件建议 | 单一职责 | 输入 | 输出 | 对应测试 |
|---:|---|---|---|---|---|---|
| P01 | `generate_project_id()` | `utils/ids.py` | 生成稳定 Project ID | none | `PROJECT_<uuidhex>` | prefix/format/1000次唯一性 |
| P02 | `normalize_project_name(name)` | `services/project_validation.py` | trim + 长度校验 | string | normalized string | empty/space/100/101 |
| P03 | `normalize_language_code(code)` | `project_validation.py` | 规范语言 code；NULL 允许给 source | string/null | normalized/null | `ZH`→`zh`, invalid |
| P04 | `normalize_region_code(code)` | `project_validation.py` | 规范地区 code | string | uppercase | `us`→`US`, invalid |
| P05 | `resolve_requested_workspace_root(value)` | `project_paths.py` | 用户空值→默认，非空→绝对规范路径 | str/null | Path | relative/absolute/default |
| P06 | `validate_workspace_root(path)` | `project_paths.py` | 确认根路径可创建/可写 | Path | Path | not writable/file-as-dir |
| P07 | `build_project_workspace_path(root, project_id)` | `project_paths.py` | 构造最终项目目录 | root,id | Path | exact path |
| P08 | `build_project_staging_path(root, project_id)` | `project_paths.py` | 构造 staging | root,id | Path | same filesystem parent |
| P09 | `assert_project_path_available(final_path, staging_path)` | `project_paths.py` | 防止目标目录冲突 | Paths | none | existing conflict |

---

# 15. 单函数开发顺序 — Manifest

| No. | Function | 文件建议 | 单一职责 | 输入 | 输出/副作用 | 对应测试 |
|---:|---|---|---|---|---|---|
| M01 | `build_project_manifest(project)` | `services/project_manifest.py` | Project→稳定 Manifest dict | Project | dict | schema exact |
| M02 | `serialize_project_manifest(manifest)` | 同上 | 统一 UTF-8/缩进/JSON 序列化 | dict | str | 中文不转义/可解析 |
| M03 | `write_manifest_atomic(staging_dir, manifest)` | 同上 | tmp→fsync→replace 写 Manifest | Path,dict | project.json | tmp cleanup / failure |
| M04 | `read_project_manifest(workspace_path)` | 同上 | 读取 JSON | Path | dict | missing/invalid JSON |
| M05 | `validate_project_manifest(manifest, expected_id)` | 同上 | 校验必填字段、ID、format | dict,id | typed manifest | mismatch/unsupported |
| M06 | `validate_final_workspace(workspace_path, project_id)` | 同上 | 组合 exists + read + validate | Path,id | manifest | missing dir/file/bad id |

---

# 16. 单函数开发顺序 — Repository

| No. | Function | 文件建议 | 单一职责 | 输入 | DB 修改 | 对应测试 |
|---:|---|---|---|---|---|---|
| R01 | `insert_creating_project(session, data)` | `repositories/projects.py` | 插入 `creating` 项目并 commit | create data | INSERT | row fields/state |
| R02 | `get_project_by_id(session, id)` | 同上 | 只查项目 | id | none | found/not found |
| R03 | `list_ready_projects(session)` | 同上 | 最近项目排序查询 | none | none | ready only/order |
| R04 | `mark_project_ready(session, id, opened_at)` | 同上 | 完成项目创建 | id,time | UPDATE state/time | state transition |
| R05 | `touch_project_opened_at(session, id, now)` | 同上 | 成功打开后更新时间 | id,time | UPDATE | timestamp only |
| R06 | `delete_creating_project(session, id)` | 同上 | 回滚未完成项目 row | id | DELETE creating only | refuses ready delete |
| R07 | `list_creating_projects(session)` | 同上 | 启动恢复查询 | none | none | creating only |

Repository 禁止直接写文件系统。

---

# 17. 单函数开发顺序 — Recovery / Service

| No. | Function | 文件建议 | 单一职责 | 输入 | 输出/副作用 | 对应测试 |
|---:|---|---|---|---|---|---|
| S01 | `cleanup_owned_staging(path, project_id)` | `services/project_recovery.py` | 只清理由本次项目拥有的 staging | path,id | remove known staging | path safety |
| S02 | `rollback_failed_creation(project, paths)` | 同上 | 同步失败补偿 DB + staging | project,paths | cleanup + delete creating row | file fail rollback |
| S03 | `recover_one_creating_project(project)` | 同上 | 恢复单个 interrupted create | Project | ready/remove/log | final-valid/staging-valid/missing |
| S04 | `recover_interrupted_project_creations()` | 同上 | 启动时逐条恢复 | none | DB/files | multiple rows isolation |
| S05 | `create_project(command)` | `services/project_service.py` | F01 核心 orchestration，只编排不重复底层逻辑 | command | ready Project | full happy/failure paths |
| S06 | `list_projects()` | 同上 | 读取 ready 列表并计算 workspace_available | none | ProjectDTO[] | missing workspace not 500 |
| S07 | `get_project(project_id)` | 同上 | 获取项目详情，不更新 open time | id | ProjectDTO | 404 |
| S08 | `open_project(project_id)` | 同上 | 验证 Workspace/Manifest 后 touch open time | id | ProjectDTO | missing/mismatch/format |
| S09 | `get_project_defaults()` | 同上 | 返回 Workspace 默认值 + format version | none | defaults DTO | exact defaults |

核心要求：`create_project()` 不允许包含几十行直接 SQL/文件操作；它只能调用已经单测通过的 P/R/M/S 小函数。

---

# 18. 单函数开发顺序 — API

| No. | Function | Endpoint | 单一职责 | 对应测试 |
|---:|---|---|---|---|
| A01 | `get_project_defaults_endpoint()` | `GET /api/v1/projects/defaults` | DTO→HTTP | status/schema |
| A02 | `list_projects_endpoint()` | `GET /api/v1/projects` | list service→HTTP | empty/list |
| A03 | `create_project_endpoint()` | `POST /api/v1/projects` | request validate→service→DTO | happy/all error mapping |
| A04 | `get_project_endpoint()` | `GET /api/v1/projects/{id}` | detail no touch | 200/404 |
| A05 | `open_project_endpoint()` | `POST /api/v1/projects/{id}/open` | validated open | 200/missing/manifest error |
| A06 | `map_domain_error_to_http()` | shared error layer | DomainError→统一 JSON error | every error code mapping |

API 层禁止自己创建目录/写 SQL。

---

# 19. 单函数开发顺序 — Frontend API / Store

| No. | Function | 文件建议 | 单一职责 | 对应测试 |
|---:|---|---|---|---|
| F01 | `request<T>()` | `frontend/src/api/http.ts` | 统一 fetch + error envelope | 2xx/json/error |
| F02 | `getProjectDefaults()` | `api/projects.ts` | 调 defaults API | typed result |
| F03 | `fetchProjects()` | 同上 | 调 list API | typed list |
| F04 | `createProject(payload)` | 同上 | 调 create API | request/response |
| F05 | `fetchProject(id)` | 同上 | 调 get API | correct URL |
| F06 | `openProject(id)` | 同上 | 调 open API | correct POST |
| F07 | `loadProjectHome()` | `stores/project.ts` | 并行/顺序加载 defaults+projects | loading/error |
| F08 | `createNewProject(payload)` | 同上 | 防重复 submit + create + current project | creating state |
| F09 | `openExistingProject(id)` | 同上 | opening + current project | opening/error |
| F10 | `loadCurrentProject(id)` | 同上 | 页面刷新恢复 project detail | success/404 |
| F11 | `clearProjectError()` | 同上 | 清理显示错误 | state only |

---

# 20. 单函数开发顺序 — Frontend UI

| No. | Function | Component | 单一职责 | 对应测试 |
|---:|---|---|---|---|
| U01 | `validateCreateProjectForm()` | `CreateProjectDialog.vue` | UI 即时校验，不代替后端校验 | required/max length |
| U02 | `handleCreateSubmit()` | 同上 | validated form→store.createNewProject | no double submit |
| U03 | `resetCreateForm()` | 同上 | Dialog 重置 | fields/defaults |
| U04 | `handleProjectCardClick()` | `ProjectHome.vue` | 调 openExistingProject 后导航 | open then route |
| U05 | `handleRetryLoad()` | `ProjectHome.vue` | 首页加载失败重试 | retry |
| U06 | `formatProjectLocale()` | `ProjectCard.vue` | code→UI 文案 | zh/en/region |
| U07 | `formatLastOpenedAt()` | `ProjectCard.vue` | 时间展示 | null/time |
| U08 | `bootstrapWorkspace()` | `ProjectWorkspace.vue` | route id→loadCurrentProject | reload recovery |
| U09 | `goBackToProjects()` | `ProjectWorkspace.vue` | 返回首页 | navigation |

UI 不处理文件系统，不直接拼 Workspace 最终路径。

---

# 21. Backend Schema / Model 文件

建议：

```text
engine/
├── requirements.txt
├── alembic.ini
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
│   ├── models/
│   │   └── project.py
│   ├── schemas/
│   │   └── project.py
│   ├── repositories/
│   │   └── projects.py
│   ├── services/
│   │   ├── project_validation.py
│   │   ├── project_paths.py
│   │   ├── project_manifest.py
│   │   ├── project_recovery.py
│   │   └── project_service.py
│   └── utils/
│       └── ids.py
├── migrations/
│   ├── env.py
│   └── versions/
│       └── 0001_create_projects.py
└── tests/
    ├── unit/
    └── integration/
```

只创建 F01 使用的模块，不建立空的 shots/characters/scenes/provider 目录。

---

# 22. Frontend 文件

```text
frontend/
├── package.json
├── package-lock.json
├── src/
│   ├── main.ts
│   ├── App.vue
│   ├── router/
│   │   └── index.ts
│   ├── api/
│   │   ├── http.ts
│   │   └── projects.ts
│   ├── types/
│   │   └── project.ts
│   ├── stores/
│   │   └── project.ts
│   ├── views/
│   │   ├── ProjectHome.vue
│   │   └── ProjectWorkspace.vue
│   └── components/projects/
│       ├── CreateProjectDialog.vue
│       └── ProjectCard.vue
└── tests/
```

F01 不建立 Timeline / Player / Inspector 组件。

---

# 23. Environment / Dependency

F01 只允许最小依赖。

Backend 预计：

```text
FastAPI
Uvicorn
SQLAlchemy
Alembic
Pydantic / pydantic-settings（若配置实现需要）
pytest
httpx（FastAPI TestClient/测试需要时）
```

Frontend 预计：

```text
Vue 3
TypeScript
Vite
Vue Router
Pinia
Vitest
Vue Test Utils
```

不在 F01 安装：

```text
PyTorch
CUDA Python packages
OpenCV
Whisper
DINO
TransNetV2
FFmpeg Python wrapper
任何视频 Provider SDK
```

注：项目总技术栈仍包含 PyTorch/CUDA/FFmpeg，但 F01 不需要它们，不提前增加安装与调试成本。

正式编码前必须把实际采用版本精确写入 lock / requirements，并更新 `docs/ENVIRONMENT_BASELINE.md`；禁止使用无约束 `latest`。

---

# 24. P0 Checklist — F01

## P0-01 Dependency / Revision / Invalidation

```text
适用：部分
```

F01 没有上游业务 Feature，没有 AI 派生数据。

但 `project_format_version`、Project ID、Workspace 路径是未来上游 Contract，用户验收后必须冻结。

F01 不实现 generic stale engine。

结果：开发完成时预期 `PASS`。

## P0-02 Media Timebase

```text
适用：N/A
```

F01 不读写任何媒体时间。

## P0-03 Environment Baseline

```text
适用：Yes
```

F01 创建项目运行骨架，必须首次锁定 Python/Node/FastAPI/Vue/SQLAlchemy/Alembic 等版本。

## P0-04 DB + File Recovery

```text
适用：Yes — 强适用
```

项目创建同时写 SQLite + Workspace + Manifest，必须实现 staging、atomic rename、同步 rollback、startup recovery。

## P0-05 Provider Job Safety

```text
适用：N/A
```

F01 不调用外部 Provider。

---

# 25. 测试计划 — 单函数 + 集成

## 25.1 Backend Unit

必须覆盖：

```text
Project ID 格式/唯一性
Project Name trim/边界
Language/Region normalization
默认 Workspace 解析
自定义 Workspace 解析
不可写路径
Final/Staging path 构造
Manifest build/serialize/read/validate
Manifest ID mismatch
Unsupported format version
Repository creating/ready transition
Repository ready list order
Creating row delete safety
Recovery final-valid
Recovery staging-valid
Recovery no-file
Recovery invalid staging
Service create happy path
Service write failure rollback
Service atomic rename failure rollback
Service open missing workspace
Service open missing manifest
Service open ID mismatch
Service open unsupported format
```

## 25.2 API Integration

```text
GET health 200
GET defaults 200
GET projects empty
POST project success
POST invalid name 422
POST invalid root
GET project success
GET project 404
POST open success
POST open missing workspace
Restart backend → GET projects still exists
```

## 25.3 Frontend

```text
首页 empty state
项目列表加载
Dialog required validation
创建中按钮 disabled
后端 error code 正确显示
创建成功自动进入 Workspace
点击历史项目先 open 再 navigate
直接刷新 /projects/:id 可恢复
Workspace 缺失时回退/提示
```

---

# 26. F01 真实验收场景

F01 不需要短剧素材，因为它还不接触媒体。

用户验收必须至少执行：

```text
1. 启动 FastAPI + Vue。
2. 首页显示“最近项目”空状态。
3. 创建项目 A：中文原片 → 英语 / 美国，使用默认路径。
4. 检查 app.db 有一条 ready project。
5. 检查 Workspace 只包含 project.json。
6. 检查 project.json 中 id / format / locale / app/schema 正确。
7. 返回首页，项目 A 在最近项目。
8. 关闭前端与后端。
9. 再次启动。
10. 项目 A 仍存在。
11. 点击项目 A，成功进入 Workspace。
12. 检查 last_opened_at 更新。
13. 创建项目 B，使用自定义路径。
14. 项目 B 创建到指定 root/project_id。
15. 创建同名项目 C，确认允许成功且 Project ID 不同。
16. 使用不可写/非法目录，确认没有残留 ready DB row 或半成品 final workspace。
17. 人工删除项目 A Workspace，再点击项目 A，必须提示 Workspace 缺失，不能 500/假装打开。
18. 恢复 Workspace 后再次打开成功。
```

### Interrupted Recovery 人工/集成测试

需要测试模拟：

```text
DB row = creating
+ valid staging
→ restart
→ 自动完成 final + ready

DB row = creating
+ valid final
→ restart
→ 自动 mark ready

DB row = creating
+ no staging/final
→ restart
→ creating row 被清理
```

---

# 27. Definition of Done

F01 只有满足以下条件才允许进入 `READY_FOR_REVIEW`：

```text
[ ] 所有 B/P/M/R/S/A/F/U 单函数按顺序完成
[ ] 每个核心函数有对应测试
[ ] projects migration 完成
[ ] Database Dictionary 与 Model/API 注释一致
[ ] app.db 首次创建正常
[ ] 默认/自定义 Workspace 正常
[ ] Manifest atomic write 正常
[ ] interrupted create recovery 正常
[ ] API error envelope 冻结
[ ] Project ID 冻结
[ ] project_format_version=1 冻结
[ ] Workspace path contract 冻结
[ ] ProjectDTO 冻结
[ ] 前端创建/列表/打开/刷新正常
[ ] 中文业务注释 review PASS
[ ] Current Feature Tests PASS
[ ] Regression: N/A — no Stable upstream feature
[ ] P0 review PASS/N/A
[ ] 用户验收步骤准备完成
[ ] Feature Doc / Session / PROJECT_STATE 同步
```

AI / Agent 完成以上内容后只能标记：

```text
READY_FOR_REVIEW
```

用户明确“验收通过”后，才允许：

```text
STABLE / FROZEN
```

---

# 28. F01 冻结项（用户验收后）

预计冻结：

```text
Project ID format
project_format_version = 1
projects table 字段语义
Workspace final path rule
project.json schema v1
CreateProjectCommand
ProjectDTO
API endpoints
API error envelope / F01 error codes
creating → ready lifecycle
startup recovery behavior
```

以后 F02 不允许为了上传视频方便直接改这些语义。

---

# 29. 当前不冻结/可后续扩展

```text
项目删除
项目重命名
项目归档
项目导入/导出
Workspace relink
Electron 原生 folder picker
Project thumbnail
Project tags
Project search/filter
```

这些未来必须以新增 Feature/显式 Contract 修改处理。

---

# 30. 推荐编码执行顺序

严格按以下顺序，不并行堆功能：

```text
Step 1  B01–B04 路径基础函数 + 测试
Step 2  B05–B09 SQLite/Alembic 基础 + 测试
Step 3  B10–B11 FastAPI 最小启动 + health test
Step 4  P01–P09 Project 校验/路径函数 + 测试
Step 5  M01–M06 Manifest 函数 + 测试
Step 6  Project Model + 0001 Migration + Database Dictionary 对照
Step 7  R01–R07 Repository 函数 + 测试
Step 8  S01–S04 Recovery 函数 + 故障测试
Step 9  S05 create_project + 集成测试
Step 10 S06–S09 list/get/open/defaults + 测试
Step 11 A01–A06 API + Contract tests
Step 12 Vue 最小骨架 + Router/Pinia
Step 13 F01–F06 Frontend API functions + 测试
Step 14 F07–F11 Store functions + 测试
Step 15 U01–U09 UI interactions + 测试
Step 16 前后端联调
Step 17 restart/recovery 测试
Step 18 用户验收包 + READY_FOR_REVIEW
```

任何 Step 失败，只修当前 Step；不得通过修改尚未开始的下游模块绕过问题。

---

# 31. 用户确认前仍属于 Draft 的关键决策

以下内容需要用户认可后才作为 F01 正式 Contract：

```text
1. app.db 采用应用级单 SQLite，而不是每项目独立 DB。
2. 默认 Workspace Root = %USERPROFILE%/AI Drama Studio Projects。
3. Project ID = PROJECT_<UUID4_HEX>。
4. Workspace Final = <root>/<project_id>/。
5. F01 只创建 project.json，不提前创建媒体目录。
6. 浏览器开发阶段存储位置使用文本路径，不做原生目录选择器。
7. F01 暂不做删除/重命名/归档/导入导出。
8. project_format_version 初始值 = 1。
9. 生命周期仅 `creating/ready`，中断通过 startup recovery 解决。
```

用户确认后：

```text
F01 Status: PLANNED → IN_PROGRESS
```

然后才开始第一行正式业务代码。

---

# 32. Next Action

> 用户审核本 F01 Contract，特别确认第 31 节九个核心决策。
>
> 未确认前不编码、不创建新分支、不实现 F02。