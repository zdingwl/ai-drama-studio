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
StudioShell.vue
ProjectHome.vue
CreateProjectDialog.vue
ProjectCard.vue
ProjectWorkspace.vue
```

F01 前端已经重新对齐正式深色工作台设计体系；没有任何 F02 上传视频代码。

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

# 创建项目固定选项规则

用户确认：固定格式数据不得继续自由输入，避免写入不规范值。

当前创建项目表单：

```text
source_language  下拉选择，可选“自动识别”
target_language  下拉选择，必选
target_region    下拉选择，必选
```

前端选项集中在：

```text
frontend/src/constants/project-options.ts
```

当前语言代码：

```text
zh en ja ko es pt fr de id th vi
```

当前地区代码：

```text
US GB JP KR ES BR FR DE ID TH VN TW SG
```

前端不再允许用户手写固定代码；后端 `CreateProjectRequest` 同时使用 Literal 白名单进行 API Schema 校验。

绕过前端直接提交 `English / english / USA / 中文` 等非标准值时，API 必须返回 422，并保持统一 error envelope：

```text
PROJECT_SOURCE_LANGUAGE_UNSUPPORTED
PROJECT_TARGET_LANGUAGE_UNSUPPORTED
PROJECT_TARGET_REGION_UNSUPPORTED
```

新增测试：

```text
engine/tests/unit/test_project_option_validation.py
```

规则：以后增加语言/地区时，必须同时更新前端选项、后端白名单和测试，禁止只改一侧。

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

此前重建 F01 工作副本并执行：

```text
python -m compileall engine
pytest -q
```

此前完整结果：

```text
29 passed
```

覆盖旧的路径/DB/ID 测试，以及 Workspace、create/list/open、Recovery、Controller。

本轮新增固定语言/地区 API 测试文件；由于当前工具环境无法直接拉取完整 Git 仓库进行最新完整 pytest，本轮新增测试仍需在用户 Windows / Python 3.11 环境与完整测试一起重跑，不把此前 29 PASS 冒充为本轮新增代码后的完整结果。

## 前端核心 API

- TypeScript strict 基础检查此前通过；
- 前端 API 与 FastAPI 实际联调此前完成：空列表 → 201 创建 → 列表出现 → `/open` 200；
- 本轮把语言/地区自由输入改成固定 select，等待用户本机 `npm run typecheck` / `npm run build` 再做最终确认。

---

# 2026-08-23 本机运行问题：CORS 预检 400

用户将 FastAPI 改为：

```text
127.0.0.1:8080
```

健康检查已经返回 `200 OK`，说明 8080 后端本身正常。

浏览器创建项目时曾出现：

```text
OPTIONS /api/projects 400 Bad Request
```

根因：原 CORS 只允许固定 5173；已修正为本机 localhost / 127.0.0.1 任意开发端口，并增加 5174 OPTIONS 回归测试。

前端当前 API 地址：

```text
http://127.0.0.1:8080
```

---

# 当前尚未完成的验证 Gate

目标环境仍需执行：

```text
package-lock.json / npm ci
npm run typecheck
npm run build
npm run test
真实浏览器 UI 验收
Python 3.11 全量 pytest
```

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
engine/tests/unit/test_project_option_validation.py
frontend/package.json
frontend/.node-version
frontend/src/constants/project-options.ts
frontend/src/api/http.ts
frontend/src/api/projects.ts
frontend/src/stores/project.ts
frontend/src/components/StudioShell.vue
frontend/src/components/CreateProjectDialog.vue
frontend/src/views/ProjectHome.vue
frontend/src/views/ProjectWorkspace.vue
```

---

# 下一步唯一动作

不进入 F02。

当前优先：用户本机同步最新 `main`，检查新建项目弹窗中的原片语言 / 目标语言 / 目标地区已经全部变成下拉框，然后执行：

```text
npm run typecheck
npm run build
pytest -q
```

之后继续创建项目、重启、重新打开的 F01 最终验收。

## 最近更新时间

- 日期：2026-08-23 20:54 +08:00
- 状态：F01 固定格式字段已改为下拉选择 + 后端枚举白名单；等待用户本机同步后完成目标环境验证。
