# AI Drama Studio — Project State

> 新对话恢复当前项目状态的第一入口。历史过程放 `docs/sessions/`。

## 当前状态

```text
Project: AI Drama Studio
Official Baseline: main
Current Working Branch: main（用户未要求切换/新建其它分支）
Current Feature: F01 — 创建项目
Feature Status: IN_PROGRESS
F01 Contract: CONFIRMED
F01 Planned Functions: ALL IMPLEMENTED
Verification Gate: PENDING
READY_FOR_REVIEW: NO
Stable Features: none
Frozen Features: none
```

`main` 是唯一正式 Source of Truth。

## Git 操作权限

未经用户明确要求，AI / Codex / Agent 不得新建、切换、删除、重命名分支，也不得擅自创建/关闭/合并/重定向 PR。

当前继续直接维护 `main`，不创建新分支。

---

# F01 权威文档

```text
docs/features/F01-create-project.md
docs/features/F01-function-contracts.md
```

---

# F01 当前完成度

第一阶段仍只解决：

```text
创建项目
→ 保存项目
→ 首页能看到
→ 重启后还在
→ 能重新打开
```

所有计划中的函数已经实现。

## 后端核心函数

```text
get_app_data_path()             [PASS]
init_database()                 [PASS]
generate_project_id()           [PASS]
create_project_workspace()      [PASS]
create_project()                [PASS]
list_projects()                 [PASS]
open_project()                  [PASS]
recover_creating_projects()     [PASS]
create_app()                    [PASS - backend tests]
```

## Controller

```text
health_api()
list_projects_api()
create_project_api()
open_project_api()
```

## 前端核心动作

```text
apiRequest()
loadProjects()
submitCreateProject()
openProject()
```

## 页面

```text
ProjectHome.vue
CreateProjectDialog.vue
ProjectCard.vue
ProjectWorkspace.vue
```

没有任何 F02 上传视频代码。

---

# 当前数据设计

应用级 SQLite：

```text
%LOCALAPPDATA%/AI Drama Studio/app.db
```

唯一业务表：`projects`。

Workspace：

```text
<workspace_root>/<project_id>/project.json
```

Project ID：

```text
PROJECT_<32位UUID4小写hex>
```

状态：

```text
creating
ready
```

---

# API

```text
GET  /api/health
GET  /api/projects
POST /api/projects
POST /api/projects/{project_id}/open
```

Controller 只负责 HTTP → Service → Response，不直接 SQL、不 mkdir、不写 `project.json`。

---

# 已验证结果

## Python / FastAPI

重建当前 F01 工作副本并执行：

```text
python -m compileall engine
pytest -q
```

结果：

```text
29 passed
```

覆盖旧的路径/DB/ID 测试，以及 Workspace、create/list/open、Recovery、Controller。

## 前端核心 API

- TypeScript strict 检查通过：`types/project.ts`、`api/http.ts`、`api/projects.ts`；
- 所有 `.ts` 与 Vue `<script setup lang="ts">` 做过 TypeScript 语法解析，共 10 个脚本块无语法错误；
- 真实启动 FastAPI 后，编译后的前端 API 函数完成：空列表 → 201 创建 → 列表出现 → `/open` 200。

---

# 当前尚未完成的验证 Gate

当前容器无法联网安装 npm 包，因此没有伪造：

```text
package-lock.json
npm ci
npm run typecheck
npm run build
npm run test
真实浏览器 UI 验收
```

前端依赖已使用精确版本写入 `frontend/package.json`，Node 固定为 `22.16.0`，但必须由联网/目标开发机生成真实 `package-lock.json`。

当前 Python 测试容器为 3.13.5；正式项目基线仍为 Python 3.11，F01 进入 READY_FOR_REVIEW 前必须在目标 Python 3.11 环境重跑完整 pytest。

因此当前：

```text
Code Functions = COMPLETE
Feature = IN_PROGRESS
READY_FOR_REVIEW = NO
STABLE/FROZEN = NO
```

---

# 当前主要代码

```text
engine/app/core/paths.py
engine/app/core/database.py
engine/app/core/ids.py
engine/app/projects.py
engine/app/main.py
engine/migrations/versions/0001_create_projects.py
engine/tests/unit/test_remaining_f01.py
frontend/package.json
frontend/.node-version
frontend/src/api/http.ts
frontend/src/api/projects.ts
frontend/src/stores/project.ts
frontend/src/views/ProjectHome.vue
frontend/src/views/ProjectWorkspace.vue
```

---

# 下一步唯一动作

不再新增 F01 业务函数，也不进入 F02。

下一步是目标环境验证：

```text
生成真实 package-lock.json
→ npm ci
→ npm run typecheck
→ npm run build
→ npm run test
→ 浏览器真实创建/重启/打开流程
→ Python 3.11 全量 pytest
→ READY_FOR_REVIEW
→ 用户人工验收
```

## 最近更新时间

- 日期：2026-08-23 18:09 +08:00
- 状态：F01 所有计划函数已实现；后端 29 tests PASS；前端 API 实际联调通过；等待联网/目标环境完成 npm build/typecheck/test 与 Python 3.11 验证。
