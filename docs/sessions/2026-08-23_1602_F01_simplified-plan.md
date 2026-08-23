# Session Handoff — F01 Simplified Plan

## 1. Session Goal

把 F01「创建项目」从过度拆分的几十函数/复杂 Recovery 方案，瘦身为第一阶段真正需要的最小可验收方案。

## 2. Starting State

- main 为正式基线；
- F01 = PLANNED；
- 无业务代码；
- 无业务数据库；
- 上一版 F01 函数规划过细，包含大量 Helper/Repository/Recovery Function Contract。

## 3. 本次完成

更新：

```text
docs/features/F01-create-project.md
docs/features/F01-function-contracts.md
templates/FUNCTION_CONTRACT_TEMPLATE.md
docs/PROJECT_STATE.md
```

新建本 Handoff。

## 4. 核心决策

F01 只解决：

```text
创建项目
→ 保存
→ 项目列表
→ 重启后仍存在
→ 重新打开
```

## 5. 数据库

只使用一个应用级 SQLite：

```text
app.db
```

只建一张业务表：

```text
projects
```

字段：

```text
id
name
source_language
target_language
target_region
workspace_path
project_format_version
status
created_at
last_opened_at
```

删除上一规划中的非必要字段：

```text
created_with_app_version
created_with_schema_revision
updated_at
```

## 6. Workspace

```text
<workspace_root>/<project_id>/project.json
```

F01 不提前创建 source/proxy/shots/characters 等未来目录。

## 7. API

项目业务只保留：

```text
GET  /api/projects
POST /api/projects
POST /api/projects/{project_id}/open
```

基础：

```text
GET /api/health
```

## 8. 后端核心函数

控制在约 9 个：

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

Controller：

```text
list_projects_api()
create_project_api()
open_project_api()
health_api()
```

## 9. 前端核心动作

```text
apiRequest()
loadProjects()
submitCreateProject()
openProject()
```

简单 helper 不再建立项目级 Function Contract。

## 10. Recovery

仅保留：

```text
creating / ready
```

启动时：

```text
creating + 完整 Workspace/Manifest → ready
creating + 不完整 → 安全清理
```

不做复杂 Recovery Framework、Repair UI、orphan 管理后台。

## 11. 注释规则没有降低

虽然架构瘦身，但以下仍为强制：

- 核心业务函数中文 docstring；
- 解释业务作用、为什么、安全边界、主要异常；
- 数据库表和字段中文说明；
- Migration 中文说明；
- Database Dictionary 与代码一致。

## 12. 测试

F01 只围绕真实用户场景：

```text
创建成功
重启后仍存在
重新打开
同名项目
非法路径
creating 异常恢复
```

## 13. 明确未做

- 没有业务代码；
- 没有创建 app.db；
- 没有 Migration；
- 没有新建/切换分支；
- 没有 F02 代码。

## 14. 当前状态

```text
F01: PLANNED
Contract: SIMPLIFIED / WAITING_USER_CONFIRMATION
Business Code: NOT_STARTED
```

## 15. 下一步唯一动作

用户确认以下 8 项后才进入编码：

```text
1. 应用级单 SQLite app.db
2. 默认 Workspace Root
3. PROJECT_<UUID4_HEX>
4. F01 只创建 project.json
5. projects 只保留 10 个必要字段
6. 只保留 list/create/open 三个项目 API
7. creating/ready 简单恢复
8. project_format_version = 1
```

确认后：

```text
F01 PLANNED → IN_PROGRESS
```

先建立最小前后端运行骨架，再开发 `get_app_data_path()` / `init_database()`。

## 16. 新对话阅读顺序

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
docs/features/F01-create-project.md
docs/features/F01-function-contracts.md
本 Session Handoff
```

## 17. 一句话交接

F01 已从过度设计方案瘦身成“1 张表 + 1 个 project.json + 3 个项目 API + 少量核心函数”的最小完整功能，仍未开始业务编码。
