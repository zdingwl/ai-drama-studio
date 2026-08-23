# Feature 01 — 创建项目（Create Project）

> F01 已由用户确认，当前状态：`IN_PROGRESS / ALL_PLANNED_FUNCTIONS_IMPLEMENTED / VERIFICATION_PENDING`。
>
> Git：按用户要求直接维护 `main`，不得擅自新建/切换分支或 PR。

## 0. 一句话目标

用户填写项目基础信息后，系统把项目保存到 SQLite，并创建独立 Workspace 和 `project.json`；软件关闭重启后，项目仍能在首页看到并重新打开。

---

# 1. F01 范围

必须完成：

```text
Vue 3 最小前端
FastAPI 最小后端
应用级 app.db
projects 表
创建项目
项目列表
打开项目
Workspace/project.json
creating 简单恢复
中文业务注释
目标环境完整测试
用户验收
```

明确不做：视频上传、FFmpeg/FFprobe、Episode、Asset、Shot、人物、对白、Scene、演员库、AI/Provider、GPU、TTS、Lip Sync、项目删除/重命名/归档/导入导出、复杂 Repair UI、Electron。

F02 前不写任何上传原视频业务。

---

# 2. 数据与文件 Contract

应用数据库：

```text
%LOCALAPPDATA%/AI Drama Studio/app.db
```

测试可用 `AI_DRAMA_APP_DATA_DIR` 覆盖。

默认 Workspace Root：

```text
%USERPROFILE%/AI Drama Studio Projects/
```

Project ID：

```text
PROJECT_<32位UUID4小写hex>
```

Workspace：

```text
<workspace_root>/<project_id>/project.json
```

`project.json` V1：

```json
{
  "project_id": "PROJECT_86f767c94f2c4f96a1676ce36f615406",
  "project_format_version": 1,
  "name": "测试短剧",
  "source_language": "zh",
  "target_language": "en",
  "target_region": "US"
}
```

F01 不提前创建媒体目录。

---

# 3. Database Dictionary

F01 只有一张业务表：`projects`。

| Field | Type | Nullable | Default | 业务作用 |
|---|---|---:|---|---|
| `id` | TEXT PK | No | - | 稳定项目业务 ID |
| `name` | TEXT | No | - | 用户看到的项目名称，同名允许 |
| `source_language` | TEXT | Yes | NULL | 原片语言；空表示未确认 |
| `target_language` | TEXT | No | - | 目标语言 |
| `target_region` | TEXT | No | - | 本土化目标地区 |
| `workspace_path` | TEXT | No | - | 项目 Workspace 绝对路径 |
| `project_format_version` | INTEGER | No | 1 | Workspace/project.json 格式版本 |
| `status` | TEXT | No | creating | 只允许 creating / ready |
| `created_at` | DATETIME | No | - | 项目创建时间 |
| `last_opened_at` | DATETIME | Yes | NULL | 最近成功进入 Workspace 时间 |

约束：

```text
PRIMARY KEY(id)
UNIQUE(workspace_path)
CHECK(status IN ('creating', 'ready'))
```

Migration：`engine/migrations/versions/0001_create_projects.py`，表和字段均有简体中文业务说明。

---

# 4. API Contract

```text
GET  /api/health
GET  /api/projects
POST /api/projects                  # 201 Created
POST /api/projects/{project_id}/open
```

Controller 只负责 HTTP → Service → Response，不直接 SQL、mkdir、写 `project.json` 或生成 ID。

统一业务错误 envelope：

```json
{
  "error": {
    "code": "PROJECT_WORKSPACE_INVALID",
    "message": "项目保存位置不可创建或不可写"
  }
}
```

---

# 5. 创建与恢复

创建流程：

```text
校验输入
→ generate_project_id()
→ DB status=creating 并提交
→ create_project_workspace()
→ project.json 原子写入
→ DB status=ready + last_opened_at
```

失败安全边界：

- Workspace 创建失败：删除本次 creating 行；
- 已完整写好 Workspace、但最终 DB 更新失败：保留 Workspace + creating，交给启动恢复；
- 不递归删除 Workspace Root；
- 不覆盖已存在 Project 目录；
- 未知用户文件永远不自动删除。

`recover_creating_projects()`：完整 Workspace 转 ready；明确缺失/可安全清理的半成品删除；未知文件保留现场。

---

# 6. 当前代码完成度

后端 9 个计划核心函数全部已实现：

```text
get_app_data_path()             PASS
generate_project_id()           PASS
init_database()                 PASS
create_project_workspace()      PASS
create_project()                PASS
list_projects()                 PASS
open_project()                  PASS
recover_creating_projects()     PASS
create_app()                    PASS（后端测试）
```

Controller 全部已实现：

```text
health_api()
list_projects_api()
create_project_api()
open_project_api()
```

前端 4 个核心动作全部已实现：

```text
apiRequest()
loadProjects()
submitCreateProject()
openProject()
```

页面已实现：

```text
ProjectHome.vue
CreateProjectDialog.vue
ProjectCard.vue
ProjectWorkspace.vue
```

卡片点击只导航；Workspace 页面统一调用 `openProject()`，所以卡片点击、刷新、直接 URL 都只调用一次后端 `/open`。

---

# 7. 实际测试记录

## Python / FastAPI

在重建当前 F01 工作副本后实际运行完整 pytest：

```text
29 passed
```

包含：已有路径/数据库/ID 测试 + Workspace + create/list/open + Recovery + Controller。

`python -m compileall engine` 通过。

FastAPI 路由确认：

```text
/api/health
/api/projects
/api/projects/{project_id}/open
```

## 前端 API

核心 API TypeScript 文件已通过 strict 类型检查。

所有 `.ts` 和 Vue `<script setup lang="ts">` 已完成 TypeScript 语法解析，无语法错误。

真实启动 FastAPI 后，用编译后的前端 API 函数完成联调：

```text
fetchProjects()       → []
createProject()       → 201 / ready
fetchProjects()       → 1 project
openProjectRequest()  → 200
```

---

# 8. 当前尚未通过的 Gate

当前执行容器不能联网安装 npm 包，所以没有伪造以下结果：

```text
package-lock.json              未生成
npm ci                         未执行
npm run typecheck (vue-tsc)    未执行
npm run build (Vite)           未执行
npm run test (Vitest)          未执行
真实浏览器 UI 验收             未执行
```

当前 Python 测试环境是 3.13.5；正式项目基线仍要求 Python 3.11，因此还需在目标 Python 3.11 环境重跑全部 F01 pytest。

所以目前：

```text
Feature Status = IN_PROGRESS
Code Functions = COMPLETE
READY_FOR_REVIEW = NO
STABLE/FROZEN = NO
```

---

# 9. 依赖

Backend：见 `engine/requirements.txt`，当前固定 FastAPI/Uvicorn/Pydantic/SQLAlchemy/Alembic/httpx/pytest 精确版本。

Frontend：见 `frontend/package.json`，固定：

```text
Vue 3.5.41
Pinia 4.0.3
Vue Router 5.2.0
Vite 8.2.2
@vitejs/plugin-vue 6.0.8
TypeScript 7.0.2
Vitest 4.1.11
vue-tsc 3.3.11
Node 22.16.0
```

完整 npm 传递依赖必须由联网环境生成真实 `package-lock.json`，禁止手工伪造 lock。

---

# 10. 下一步

不再新增 F01 业务函数。

下一步只做验证与验收准备：

```text
联网/目标开发机生成 package-lock.json
→ npm ci
→ npm run typecheck
→ npm run build
→ npm run test
→ 浏览器真实创建/重启/打开流程
→ Python 3.11 全量 pytest
→ READY_FOR_REVIEW
→ 用户人工验收
```

未经用户明确要求不新建分支，不进入 F02。
