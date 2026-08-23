# AI Drama Studio — Project State

> 本文件是新对话恢复项目状态的第一入口。每次实际开发结束必须更新。

## 当前状态

- 项目：AI Drama Studio
- 形态：Windows 本地自用 AI 短剧重制工作台
- 当前分支：`docs/project-skill`
- 当前 PR：Draft PR #1 — 项目 Skill / 开发规则初始化
- 当前 Feature：`Feature 01 — 创建项目`
- 当前 Feature 状态：`PLANNED / NOT_STARTED`
- 已 Stable Feature：无
- 已 Frozen Feature：无

## 已经确定的核心技术方案

- Frontend：Vue 3 + TypeScript + Vite + Pinia
- AI Backend：Python 3.11 + FastAPI + PyTorch
- Video：FFmpeg / FFprobe / OpenCV
- Data：SQLite + SQLAlchemy + Alembic + 本地文件系统
- Desktop：Electron 后置，先浏览器 + localhost 开发
- GPU：RTX 4060 Ti 16GB，开发期不追求速度，GPU 任务默认串行
- 强 VLM / 视频生成 / Premium TTS / Premium Lip Sync：Provider Adapter 调用外部 API
- 核心原则：模型可替换、AI 原始结果与人工 Final 结果分离、Shot 独立、Generation/TTS/LipSync 版本化

## 固定业务开发顺序

Feature 01 → 30 的完整顺序见：

- `docs/FEATURE_SEQUENCE.md`

当前必须从 Feature 01 开始，不跳过前置功能。

## 当前仓库文档状态

已建立：

- `SKILL.md`
- `AGENTS.md`
- `docs/FEATURE_SEQUENCE.md`
- `docs/TECH_STACK.md`
- `docs/DATA_AND_FREEZE_RULES.md`
- `docs/CONTINUATION_PROTOCOL.md`
- `docs/CODE_AND_DATABASE_COMMENT_RULES.md`
- `docs/PROJECT_STATE.md`
- `docs/features/README.md`
- `docs/sessions/README.md`
- `templates/FEATURE_SPEC_TEMPLATE.md`
- `templates/FEATURE_IMPLEMENTATION_LOG_TEMPLATE.md`
- `templates/SESSION_HANDOFF_TEMPLATE.md`

跨对话续开发规则已经启用：

- 每个 Feature 维护长期 Feature 文档。
- 每次实际开发会话创建独立 Session Handoff。
- 每次开发结束同步更新本文件。
- 代码与文档属于同一个交付物。
- Feature 缺少文档更新时不得标记 STABLE。

代码与数据库可理解性规则已经启用：

- 业务代码必须包含足够的简体中文业务注释。
- 注释重点解释业务作用、约束以及“为什么”，禁止机械翻译变量名。
- 核心文件、Service、公开方法、复杂算法、Provider Adapter、API Schema 必须有说明。
- 每张业务表必须有中文业务说明。
- 每个新增/修改的业务字段必须有字段级说明。
- SQLAlchemy Model、Alembic Migration 和 Pydantic/TypeScript Schema 需要同步表达字段语义。
- 每个涉及数据库变更的 Feature 文档必须维护 Database Dictionary。
- Feature 标记 STABLE/FROZEN 前必须通过 Code Comment Review、Database Comment Review 和 Database Dictionary 完整性检查。
- 详细规则见 `docs/CODE_AND_DATABASE_COMMENT_RULES.md`。

## 最新开发交接

- `docs/sessions/2026-08-23_1401_PROJECT_code-database-comment-rules.md`
- `docs/sessions/2026-08-23_1354_PROJECT_continuation-protocol.md`

最新交接记录本次“代码与数据库注释强制规范”的建立过程和后续执行要求。

## 当前代码状态

- 尚未开始业务代码实现。
- 当前主要成果是项目开发 Skill、技术规则、Feature 顺序、冻结规则、跨对话续开发规则和代码/数据库注释规范。

## 当前阻塞项

无技术阻塞。

## 已知 Bug

无业务代码，因此暂无运行 Bug。

## 未决策事项

Feature 01 正式开发前需要在 Feature Spec 中确定：

- 项目根目录默认位置
- Project ID 生成规则
- 项目 DB 是每项目独立 SQLite，还是应用级 SQLite + project workspace
- “创建项目”第一版表单最终字段

这些应在 Feature 01 Contract 中确定，不应在此全局文件中提前写死。

## 下一步唯一推荐动作

> 创建 `docs/features/F01-create-project.md`，使用 `templates/FEATURE_SPEC_TEMPLATE.md` 与 `templates/FEATURE_IMPLEMENTATION_LOG_TEMPLATE.md` 定义 Feature 01 Contract；其中数据库部分必须按 `docs/CODE_AND_DATABASE_COMMENT_RULES.md` 建立完整 Database Dictionary。用户确认 Contract 后，才开始 Feature 01 编码。

## 新对话恢复顺序

1. `AGENTS.md`
2. `SKILL.md`
3. 本文件 `docs/PROJECT_STATE.md`
4. `docs/CONTINUATION_PROTOCOL.md`
5. `docs/CODE_AND_DATABASE_COMMENT_RULES.md`
6. 当前 Feature 文档（目前应为 `docs/features/F01-create-project.md`，创建后生效）
7. 最新相关 `docs/sessions/*.md`

## 最近一次状态更新

- 日期：2026-08-23 14:01 +08:00
- 内容：新增强制代码与数据库注释规范；要求业务代码、表、字段、Migration、API Schema 均具备可理解的中文说明，并将注释完整性纳入 Feature Stable Gate。
- 下一步：建立 Feature 01 规格文档。