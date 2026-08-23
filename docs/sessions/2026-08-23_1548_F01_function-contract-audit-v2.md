# Session Handoff — F01 Function Contract Audit V2

## Session Goal

继续审核 F01 单函数职责，删除不必要抽象、修正误导命名、减少重复调用链，并确保 Controller / Service / Repository / Recovery 的职责真正可理解。

## What Changed

- `templates/FUNCTION_CONTRACT_TEMPLATE.md`
  - 引入 A/B/C 三级函数规则；
  - 明确“单函数开发 ≠ 每个 helper 都写完整 Contract”；
  - 有副作用但名字看起来像 `validate/get` 时必须重命名；
  - Repository 不应隐藏业务事务 commit。

- `docs/features/F01-function-contracts.md`
  - 完整重写为审核后的 V2；
  - 删除 `build_database_url()` 正式 Contract；
  - 删除 `serialize_project_manifest()`；
  - final/staging path 合并成 `build_project_paths()`；
  - `validate_workspace_root()` → `prepare_workspace_root()`；
  - `ensure_database_schema()` → `run_database_migrations()`；
  - `create_app()` 与 `application_lifespan()` 分离；
  - health endpoint 移到 API 层；
  - Repository 不 commit，Service/Recovery 控制 transaction；
  - 删除 F01 `GET /projects/{id}` 详情链路；
  - 卡片、刷新、直接 URL 统一使用 POST `/open`；
  - `openExistingProject()` + `loadCurrentProject()` 合并成 `openProjectById()`；
  - recent projects 与 defaults 分离，defaults 在 Create Dialog 懒加载；
  - 发布 final 后禁止自动删除 final；
  - 增加 `PROJECT_CREATE_FINALIZATION_PENDING`。

- `docs/features/F01-create-project.md`
  - 重写并与 Function Contracts V2 对齐；
  - Create API 成功状态建议并写入 201 Created；
  - 删除 GET Project Detail API；
  - 重写 Recovery、测试、DoD、函数清单和编码顺序。

- `docs/PROJECT_STATE.md`
  - 状态改为 `F01 Contract: AUDITED V2 / WAITING_USER_CONFIRMATION`；
  - 等待确认项从旧版 9 项更新为 12 项。

## Key Architecture Decisions Introduced by Audit

### 1. DB Transaction ownership

Repository 只做 SQLAlchemy 数据操作/flush，不自行 commit/rollback。

Service / Recovery 明确控制：

```text
creating + COMMIT #1
→ file staging
→ publish final
→ ready + COMMIT #2
```

### 2. File Publish Point

```text
staging rename → final
```

是不可逆安全边界。

发布前可以清理 staging + creating row；发布后不得自动删除 final。

### 3. Unified Open Flow

F01 不再维护 `GET project detail` 与 `POST open` 两套项目进入逻辑。

```text
card click / route refresh / direct URL
→ POST /projects/{id}/open
```

### 4. Function Levels

- A: core business/state/file/DB/controller/recovery → full contract
- B: repository/manifest/frontend API/store/business helper → simplified contract
- C: presentational/private helper → comments/tests only

## No Business Code Was Written

Current status remains:

```text
F01 = PLANNED
Business Code = NOT_STARTED
DB/Migration = NOT_STARTED
```

## Git

- Working branch: `main`
- No branch created
- No PR created
- Do not create/switch branch unless user explicitly requests

## User Confirmation Still Needed

1. App-level single SQLite `app.db`.
2. Default Workspace Root `%USERPROFILE%/AI Drama Studio Projects`.
3. Project ID `PROJECT_<UUID4_HEX>`.
4. Final Workspace `<root>/<project_id>/`.
5. F01 creates only `project.json`.
6. Browser dev uses text path input.
7. No delete/rename/archive/import/export in F01.
8. `project_format_version = 1`.
9. lifecycle remains `creating/ready`; unrecoverable invalid-final stays `creating` + logs, no repair UI in F01.
10. All Workspace entry uses POST `/open` and updates `last_opened_at`.
11. Create Project returns `201 Created`.
12. After final publish, automatic rollback may not delete final; startup recovery finalizes DB.

## Next Action

User reviews the V2 function design and 12 decisions. If accepted, update F01 status to `IN_PROGRESS`, then begin with:

```text
INF-01 resolve_app_data_dir()
```

For each function:

```text
Function Contract
→ implementation
→ corresponding test
→ PASS
→ next function
```
