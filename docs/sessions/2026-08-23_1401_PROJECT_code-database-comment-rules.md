# Session Handoff — Code & Database Comment Rules

## Session

- Date：2026-08-23 14:01 +08:00
- Scope：PROJECT RULES
- Branch：`docs/project-skill`
- PR：Draft PR #1
- Related Feature：全局规则，适用于 Feature 01–30

## 本次目标

用户提出：代码和数据库都必须增加足够的注释，方便直接理解代码、数据库表和字段的真正业务作用。

本次将该要求从对话约定升级为仓库级强制开发规范。

## 本次完成

1. 新增 `docs/CODE_AND_DATABASE_COMMENT_RULES.md`。
2. 更新 `AGENTS.md`，要求任何开发者/AI Agent 开发前读取注释规范。
3. 更新 `docs/PROJECT_STATE.md`，把注释完整性纳入当前项目强制规则和 Stable Gate。
4. 明确 SQLite 场景下不能只依赖数据库原生 COMMENT，而是使用：
   - SQLAlchemy Model 注释/metadata；
   - Alembic Migration 说明；
   - Feature 文档 Database Dictionary；
   三层共同保证字段语义可追溯。

## 新增核心规则

### 代码

所有新增/修改的核心业务代码都必须说明真实业务作用，而不是机械翻译变量名。

重点覆盖：

- 核心业务文件职责；
- Service / Repository 边界；
- 公开方法和复杂函数 docstring；
- AI/视频算法关键流程与阈值原因；
- Provider Adapter 字段映射；
- Vue/TypeScript Store、DTO、Timeline 复杂状态；
- Pydantic Schema 字段 description。

### 数据库

每张业务表必须说明：

- 为什么存在；
- 对应哪个业务对象；
- 哪个 Feature 创建；
- 哪些 Feature 可以写；
- 哪些下游只读；
- 生命周期与冻结状态。

每个业务字段必须说明：

- 类型；
- 是否可空；
- 默认值；
- 真正业务含义；
- 数据来源；
- 谁可以修改；
- 是否属于 Frozen Contract；
- 示例值。

禁止使用“`final_start` = 最终开始时间”这类没有说明与 `detected_start` 关系的低价值描述。

## Stable Gate 新增条件

Feature 进入 `STABLE / FROZEN` 前必须：

```text
CODE COMMENT REVIEW: PASS
DATABASE COMMENT REVIEW: PASS
DATABASE DICTIONARY: COMPLETE
```

代码实现完成但注释/字段字典缺失，不能视为 Feature 完成。

## 重要设计决策

### SQLite 注释策略

由于第一版数据库为 SQLite，不依赖数据库引擎原生列 COMMENT。

采用：

```text
SQLAlchemy Model
+ Alembic Migration
+ docs/features/FXX-*.md Database Dictionary
```

共同作为数据库字段说明的权威来源。

### 注释语言

- 业务解释：简体中文优先；
- 代码变量、类名、表名、字段名：规范英文；
- Shot / Scene / Character Bible / Provider 等成熟术语可保留英文；
- 注释重点解释业务含义、约束和设计原因。

## 修改文件

- `docs/CODE_AND_DATABASE_COMMENT_RULES.md` — 新增
- `AGENTS.md` — 更新
- `docs/PROJECT_STATE.md` — 更新
- `docs/sessions/2026-08-23_1401_PROJECT_code-database-comment-rules.md` — 本文件

## 当前代码状态

尚未开始 Feature 01 业务代码实现，因此没有需要补注释的历史业务代码。

从 Feature 01 第一行正式业务代码开始，必须执行本规范。

## 当前未完成

- Feature 01 Contract 尚未创建。
- Feature 01 数据库表和字段尚未确定。

## 下一步唯一动作

创建：

`docs/features/F01-create-project.md`

在 Feature 01 Contract 中明确：

1. 创建项目的业务字段；
2. 每个表/字段的 Database Dictionary；
3. 哪些字段可修改、哪些字段 Frozen；
4. 后续代码实现时对应的中文业务注释要求。

用户确认 Feature 01 Contract 后，才开始编码。
