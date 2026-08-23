# Session Handoff — F01 全部计划函数已实现

时间：2026-08-23 18:09 +08:00  
分支：`main`（用户明确要求不得擅自新建分支）  
Feature：F01 创建项目  
状态：`IN_PROGRESS / CODE FUNCTIONS COMPLETE / VERIFICATION PENDING`

## 本次用户要求

> 继续完成全部函数。

因此本次不再逐函数停顿，而是一次完成 F01 剩余全部计划函数，但严格不进入 F02。

---

# 已完成代码

## 后端核心函数

```text
get_app_data_path()
init_database()
generate_project_id()
create_project_workspace()
create_project()
list_projects()
open_project()
recover_creating_projects()
create_app()
```

其中本次新增：

```text
engine/app/projects.py
engine/app/main.py
```

### `create_project_workspace()`

- `<root>/<project_id>/project.json`；
- `project.json.tmp → fsync → os.replace`；
- 已有 Project 目录绝不覆盖；
- Root 是普通文件时返回 `PROJECT_WORKSPACE_INVALID`；
- 失败只清理已知文件并尝试 rmdir 空项目目录；
- 不递归删除 Workspace Root/未知文件。

### `create_project()`

```text
validate
→ generate_project_id
→ DB creating commit
→ create_project_workspace
→ DB ready + last_opened_at
```

Workspace 失败时删除 creating 行；Workspace 已完成但最终 DB 失败时保留 Workspace + creating，交给启动恢复。

### `list_projects()`

只查 `ready`，按最近打开时间排序。

### `open_project()`

验证 DB ready、Workspace、Manifest ID、format version；成功更新 `last_opened_at`；损坏时不自动删用户文件。

### `recover_creating_projects()`

完整项目转 ready；无 Workspace 删除 creating 行；仅含已知半成品且归属明确时安全清理；未知用户文件保留。

### `create_app()` / Controller

```text
GET  /api/health
GET  /api/projects
POST /api/projects
POST /api/projects/{id}/open
```

Controller 只做 HTTP → Service → Response；含 F01 ProjectError envelope 和 localhost:5173 CORS。

---

# 前端已完成

新增最小 Vue 3 + TypeScript + Vite + Pinia + Router 代码：

```text
frontend/package.json
frontend/.node-version
frontend/tsconfig.json
frontend/vite.config.ts
frontend/index.html
frontend/src/types/project.ts
frontend/src/api/http.ts
frontend/src/api/projects.ts
frontend/src/stores/project.ts
frontend/src/router/index.ts
frontend/src/main.ts
frontend/src/App.vue
frontend/src/components/ProjectCard.vue
frontend/src/components/CreateProjectDialog.vue
frontend/src/views/ProjectHome.vue
frontend/src/views/ProjectWorkspace.vue
frontend/src/styles.css
```

核心动作：

```text
apiRequest()
loadProjects()
submitCreateProject()
openProject()
```

重要 UI 修正：

旧设计会出现：

```text
首页卡片 openProject()
→ router.push
→ Workspace onMounted openProject()
```

导致 `/open` 和 `last_opened_at` 连续执行两次。

已修正为：

```text
首页卡片只 router.push
→ Workspace 统一 openProject()
```

所以卡片点击、刷新、直接 URL 都只有一个真正打开入口。

---

# 依赖

Backend 直接依赖已固定：

```text
fastapi==0.128.2
uvicorn==0.48.0
pydantic==2.13.4
SQLAlchemy==2.0.50
alembic==1.18.4
httpx==0.28.1
pytest==9.0.2
```

Frontend 精确版本：

```text
Node 22.16.0
Vue 3.5.41
Pinia 4.0.3
Vue Router 5.2.0
Vite 8.2.2
@vitejs/plugin-vue 6.0.8
TypeScript 7.0.2
Vitest 4.1.11
vue-tsc 3.3.11
```

当前容器无外网，不能 npm install，因此**没有手工伪造 package-lock.json**。

---

# 实际验证

## Backend

由于容器无法直接 git clone GitHub，本次从 `main` 逐文件重建 F01 工作副本后真实执行：

```text
python -m compileall -q engine
pytest -q
```

结果：

```text
29 passed
```

覆盖：

- 旧 `get_app_data_path()`；
- 旧 `init_database()` 6 tests；
- `generate_project_id()`；
- Workspace/Manifest；
- create/list/open；
- creating recovery；
- FastAPI Controller。

第一轮测试发现并修复：Workspace Root 本身是普通文件时被错误映射成 `PROJECT_CREATE_FAILED`，现已正确映射 `PROJECT_WORKSPACE_INVALID`。

## Frontend

实际做过：

1. `types/project.ts + api/http.ts + api/projects.ts` TypeScript strict 检查 PASS；
2. 所有 `.ts` 与 Vue `<script setup lang="ts">` 使用 TypeScript parser 检查，共 10 个脚本块无语法错误；
3. 启动真实 Uvicorn/FastAPI；
4. 把真实前端 API TS 编译为 JS；
5. Node 直接调用真实函数：

```text
fetchProjects()       → 0
createProject()       → HTTP 201 + ready
fetchProjects()       → 1
openProjectRequest()  → HTTP 200
```

---

# 未完成验证（不得冒充 PASS）

当前容器无法下载 npm 依赖，因此未执行：

```text
npm ci
npm run typecheck
npm run build
npm run test
真实浏览器 Vue 页面验收
```

也未生成真实 `package-lock.json`。

当前 Python 执行容器为 3.13.5；项目正式基线仍为 Python 3.11，因此还需目标环境完整 pytest。

---

# 当前状态结论

```text
F01 Planned Functions: COMPLETE
Backend tests: 29 PASS
Frontend API integration: PASS
Frontend package install/build: PENDING
Python 3.11 final verification: PENDING
Feature Status: IN_PROGRESS
READY_FOR_REVIEW: NO
STABLE/FROZEN: NO
```

只有用户最终人工验收后才能 STABLE/FROZEN。

---

# 下一步唯一动作

不要新增 F01 业务函数，不进入 F02。

下一步：

```text
在联网/目标开发机生成 package-lock.json
→ npm ci
→ npm run typecheck
→ npm run build
→ npm run test
→ 浏览器真实 F01 创建/重启/打开测试
→ Python 3.11 全量 pytest
→ 更新文档
→ READY_FOR_REVIEW
→ 用户验收
```
