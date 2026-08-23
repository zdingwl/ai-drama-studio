# F01 — 核心函数职责说明（实现版）

> 目标：重要函数讲透，简单 helper 写清楚；不为了“单函数开发”制造几十层抽象。

## 1. 分层规则

### API / Controller

只负责：HTTP Request → 调用业务函数 → HTTP Response。

禁止：直接 SQL、mkdir、写 `project.json`、生成 Project ID、复制 Service 业务流程。

### Service / 核心业务函数

完成用户真正需要的一件事，例如创建项目、打开项目。涉及 DB/文件时必须写清安全边界。

### 小 helper

trim、JSON 读取、Path 拼接、日期显示等不单独做项目级 Contract，但代码命名和必要中文注释必须清楚。

---

# 2. 后端 9 个核心函数

## 2.1 `get_app_data_path()` — TESTED / PASS

文件：`engine/app/core/paths.py`

作用：确定 `app.db` 等应用级数据的根目录。测试/开发可用 `AI_DRAMA_APP_DATA_DIR` 覆盖，Windows 正式默认 `%LOCALAPPDATA%/AI Drama Studio`。

不做：不 mkdir、不建数据库、不创建项目。

测试：`4 passed`。

## 2.2 `init_database()` — TESTED / PASS

文件：`engine/app/core/database.py`

作用：创建应用数据目录和 `app.db`，统一通过 Alembic 升到当前 schema。

F01 只创建：`alembic_version + projects`。

不做：不创建 Workspace、不插入项目、不创建后续 Feature 表。

测试：原有数据库测试 `6 passed`；完整回归中继续 PASS。

## 2.3 `generate_project_id()` — TESTED / PASS

文件：`engine/app/core/ids.py`

规则：`PROJECT_<32位UUID4小写hex>`。

不访问 DB、不创建目录、不使用项目名/视频名/路径参与 ID 计算。

测试：`3 passed`，含连续 5000 次无重复。

## 2.4 `create_project_workspace()` — TESTED / PASS

文件：`engine/app/projects.py`

作用：创建 `<workspace_root>/<project_id>/project.json`。

关键实现：

```text
创建 Workspace Root
→ 创建唯一 project_id 目录（exist_ok=False）
→ 写 project.json.tmp
→ flush + fsync
→ os.replace() 发布为 project.json
→ 再读取校验 Project ID / format version
```

安全边界：

- 已有项目目录绝不覆盖；
- Root 本身是普通文件时返回 `PROJECT_WORKSPACE_INVALID`；
- 失败时只删除本函数明确创建的 `project.json(.tmp)` 并尝试删除空项目目录；
- 不递归删除 Workspace Root；
- 遇到未知用户文件时保留现场。

## 2.5 `create_project()` — TESTED / PASS

文件：`engine/app/projects.py`

作用：把“新建项目”完整变成一个可重新打开的 `ready` 项目。

流程：

```text
校验/规范输入
→ generate_project_id()
→ DB INSERT status=creating 并提交
→ create_project_workspace()
→ DB UPDATE status=ready + last_opened_at
→ 返回 ProjectRecord
```

失败规则：

- 输入错误发生在 DB 初始化前；
- Workspace 创建失败时删除本次 `creating` 行；
- Workspace 已完整写好但最终 DB 更新失败时保留 Workspace + `creating`，交给启动恢复，不删除用户项目文件。

支持：同名项目允许，ID 和 Workspace 不同。

## 2.6 `list_projects()` — TESTED / PASS

文件：`engine/app/projects.py`

作用：首页只读取 `ready` 项目，按 `last_opened_at DESC`、`created_at DESC` 排序。

这是只读函数，不打开项目、不修改 Workspace。

## 2.7 `open_project()` — TESTED / PASS

文件：`engine/app/projects.py`

作用：真正进入历史项目。

必须验证：

```text
DB 有项目
status = ready
Workspace 是目录
project.json 可读取
manifest.project_id == DB id
project_format_version == 1
```

成功后更新 `last_opened_at`。

损坏时只报错，不自动修复或删除用户 Workspace。

## 2.8 `recover_creating_projects()` — TESTED / PASS

文件：`engine/app/projects.py`

作用：应用启动时处理异常退出遗留的 `creating` 项目。

V1 简单规则：

- valid Workspace + Manifest → `ready`；
- Workspace 不存在 → 删除无意义 creating 行；
- 只包含 F01 已知半成品文件且目录名等于 Project ID → 安全清理；
- 有未知用户文件、路径异常或无法确认归属 → 保留现场并计入 `preserved`。

不建立 Repair UI / orphan 管理 / 复杂 Recovery Framework。

## 2.9 `create_app()` — TESTED / PASS（后端）

文件：`engine/app/main.py`

作用：创建最小 FastAPI App，配置本地 Vue CORS、统一 ProjectError 响应、启动时 `init_database()` + `recover_creating_projects()`。

不在 `create_app()` 内实现项目 SQL/Workspace 业务。

---

# 3. Controller — 已实现 / TESTED

文件：`engine/app/main.py`

```text
health_api()          GET  /api/health
list_projects_api()   GET  /api/projects
create_project_api()  POST /api/projects      → 201 Created
open_project_api()    POST /api/projects/{id}/open
```

Controller 只做 HTTP → Service → Response。

FastAPI 集成测试已经覆盖健康检查、空列表、创建、列表、打开、业务错误映射。

---

# 4. 前端 4 个核心动作 — 已实现

## `apiRequest()`

文件：`frontend/src/api/http.ts`

统一调用 `http://127.0.0.1:8000`，统一 JSON 和 error envelope；不负责导航和业务状态。

## `loadProjects()`

文件：`frontend/src/stores/project.ts`

首页加载 ready 项目列表，维护 `loading/errorMessage`。

## `submitCreateProject()`

文件：`frontend/src/stores/project.ts`

防重复提交；调用创建 API；成功更新 `currentProject` 和首页列表；导航由页面负责。

## `openProject()`

文件：`frontend/src/stores/project.ts`

统一调用 `/open`，成功后写入 `currentProject`。

项目首页卡片只导航到 `/projects/:id`；真正 `openProject()` 由 Workspace 页面统一调用，因此：

```text
卡片点击
页面刷新
直接访问 URL
```

都只执行一次后端 `/open`，避免 `last_opened_at` 被重复更新。

---

# 5. F01 页面 — 已实现

```text
frontend/src/views/ProjectHome.vue
frontend/src/components/CreateProjectDialog.vue
frontend/src/components/ProjectCard.vue
frontend/src/views/ProjectWorkspace.vue
```

当前 UI 只覆盖 F01：项目列表、新建项目、空 Workspace。没有 F02 上传逻辑。

---

# 6. 测试结果

## Python / FastAPI

重建当前 `main` F01 代码后实际执行：

```text
29 passed
```

覆盖旧的路径/数据库/ID 测试，以及 Workspace、create/list/open、Recovery、Controller。

## 前端核心 API

`frontend/src/types/project.ts`、`api/http.ts`、`api/projects.ts` 已通过 TypeScript 严格类型检查。

所有 `.ts` 和 Vue `<script setup lang="ts">` 已做 TypeScript 语法解析，共 10 个脚本块无语法错误。

实际启动 FastAPI 后，用编译后的真实前端 API 函数完成：

```text
fetchProjects() → []
createProject() → HTTP 201 / ready
fetchProjects() → 1 project
openProjectRequest() → HTTP 200
```

## 尚未宣称通过

当前执行容器无法联网安装 npm 包，因此尚未执行真实：

```text
npm ci
npm run typecheck   # vue-tsc
npm run build       # Vite
npm run test        # Vitest
```

因此 F01 当前仍是 `IN_PROGRESS`，不能标 `READY_FOR_REVIEW`。

---

# 7. 当前开发纪律

所有计划中的 F01 函数已经实现。下一步不再新增业务函数，而是完成目标环境验证与依赖锁：

```text
生成 package-lock.json
→ npm ci
→ vue-tsc
→ Vite build
→ 前端真实浏览器联调
→ Python 3.11 全量 pytest
→ READY_FOR_REVIEW
→ 用户验收
```

未经用户明确要求不新建分支，不进入 F02。
