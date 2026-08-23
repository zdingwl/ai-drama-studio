# AI Drama Studio — Project State

> 新对话恢复当前项目状态的第一入口。历史过程放 `docs/sessions/`。

## 当前状态

```text
Project: AI Drama Studio
Official Baseline: main
Current Working Branch: main（用户未要求切换/新建其它分支）
Current Feature: F01 — 创建项目
Feature Status: PLANNED
F01 Contract: AUDITED V2 / WAITING_USER_CONFIRMATION
F01 Function Contracts: AUDITED V2 / WAITING_USER_CONFIRMATION
Stable Features: none
Frozen Features: none
Business Code: not started
Business DB/Migration: not started
```

`main` 是唯一正式 Source of Truth。

## Git 操作权限

未经用户明确要求，AI / Codex / Agent 不得新建、切换、删除、重命名分支，也不得擅自创建/关闭/合并/重定向 PR。

当前继续维护 `main` 文档，不创建新分支。

---

# F01 当前权威文档

主 Contract：

```text
docs/features/F01-create-project.md
```

单函数职责：

```text
docs/features/F01-function-contracts.md
```

通用模板：

```text
templates/FUNCTION_CONTRACT_TEMPLATE.md
```

新对话恢复 F01 时必须同时读取主 Contract + Function Contracts。

---

# F01 第二轮函数审核结果

本轮不再把“所有小 helper”都升级成正式单函数 Contract。

函数分三级：

```text
A级：核心业务 / Controller / DB-File状态变化 / Recovery
→ 完整 Function Contract

B级：Repository / Manifest / Frontend API / Store / 业务语义 helper
→ 简化 Contract

C级：日期格式、JSON小helper、表单reset、简单导航等
→ 代码中文注释 + 必要测试，不单独写大段规格
```

主要调整：

```text
1. 删除 build_database_url() 正式 Contract。
2. 删除 serialize_project_manifest() 正式函数。
3. final/staging 两个路径函数合并为 build_project_paths()。
4. validate_workspace_root() 改为 prepare_workspace_root()，明确它会创建目录/做写权限探针。
5. ensure_database_schema() 改为 run_database_migrations()，明确会修改 Schema。
6. create_app() 与 application_lifespan() 拆开。
7. health_endpoint() 归 API 层。
8. Repository 不再 commit/rollback，事务边界由 Service/Recovery 控制。
9. 删除 F01 GET /projects/{id} 详情链路。
10. 卡片点击、刷新、直接 URL 全部统一 POST /projects/{id}/open。
11. openExistingProject + loadCurrentProject 合并为 openProjectById。
12. loadRecentProjects 不再顺带请求 Project Defaults。
13. Defaults 只在新建 Dialog 打开时懒加载。
14. final Workspace 发布后，后续失败禁止自动删除 final。
15. 新增 PROJECT_CREATE_FINALIZATION_PENDING 错误语义。
```

## 重要事务边界

```text
DB creating + COMMIT #1
→ staging / manifest
→ staging rename final          # FILE PUBLISH POINT
→ DB ready + COMMIT #2
```

发布前失败可以安全回滚 staging + creating row。

发布后失败：

```text
保留 final
保留 creating row
返回 FINALIZATION_PENDING
交给 startup recovery
```

禁止为了“回滚干净”删除已经发布的 final Project Workspace。

---

# F01 仍待用户确认的 12 项

```text
1. 应用级单 SQLite app.db。
2. 默认 Workspace Root = %USERPROFILE%/AI Drama Studio Projects。
3. Project ID = PROJECT_<UUID4_HEX>。
4. Final Workspace = <root>/<project_id>/。
5. F01 只创建 project.json，不提前创建媒体目录。
6. 浏览器开发期自定义路径使用文本输入。
7. F01 暂不做删除/重命名/归档/导入导出。
8. project_format_version = 1。
9. lifecycle 仍为 creating/ready；invalid-final 自动恢复不了时保留 creating + 日志，F01 不做 repair UI。
10. 所有进入 Workspace 的动作统一走 POST /open，并允许更新 last_opened_at。
11. Create Project 成功 HTTP Status = 201 Created。
12. final Workspace 一旦发布，后续失败不得自动删除，由 startup recovery 完成 DB finalization。
```

用户确认前：

```text
不得把 F01 改为 IN_PROGRESS
不得开始业务代码
不得实现 F02
```

---

# 当前技术方案

```text
Frontend: Vue 3 + TypeScript + Vite + Pinia
Backend: Python 3.11 + FastAPI
Data: SQLite + SQLAlchemy + Alembic + Local Filesystem
Desktop: Electron 后置
```

F01 只安装本 Feature 真正需要的依赖，不提前安装 PyTorch/CUDA/OpenCV/AI 模型。

---

# 新对话最短恢复路径

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/features/F01-create-project.md
→ docs/features/F01-function-contracts.md
→ 最新 F01 Session Handoff
```

---

# 下一步唯一动作

> 用户继续审核并确认 F01 V2 Contract 的 12 项关键决策。确认后将 F01 改为 `IN_PROGRESS`，再从 `INF-01 resolve_app_data_dir()` 开始正式编码和对应测试。

## 最近更新时间

- 日期：2026-08-23 15:48 +08:00
- 状态：完成 F01 第二轮函数职责审核与精简，仍未开始业务代码。
