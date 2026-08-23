# AI Drama Studio — Agent Entry Rules

任何开发人员、ChatGPT、Codex 或其他 AI Coding Agent 在修改本仓库前，必须按以下顺序读取项目上下文：

1. `SKILL.md` — 项目长期开发规则、技术边界与 30 个 Feature 顺序。
2. `SKILL_P0.md` — 与主 Skill 同等强制的 5 个 P0 工程 Contract。
3. `docs/PROJECT_STATE.md` — 当前项目真实状态、当前 Feature、已冻结 Feature、阻塞项与下一步。
4. `docs/CONTINUATION_PROTOCOL.md` — 跨对话/跨会话续开发规则。
5. `docs/CODE_AND_DATABASE_COMMENT_RULES.md` — 代码、数据库表、字段、Migration 和 API Schema 的强制中文说明规范。
6. `docs/P0_RULES_INDEX.md` — 判断当前 Feature 需要读取哪些 P0 详细规则。
7. 当前 Feature 文档：`docs/features/FXX-*.md`。
8. 最新相关开发会话记录：`docs/sessions/*.md`。
9. 仅在需要时读取当前 Feature 所依赖的上游 Stable Feature 文档与适用的 P0 详细规范。

## 强制规则

- 不允许仅依赖聊天历史作为项目上下文。
- `SKILL.md + SKILL_P0.md` 共同构成完整项目 Skill，任何 Agent 不得只读其中一个。
- 每一次实际开发都必须同步更新仓库内文档。
- 代码变更与对应文档变更属于同一个交付物。
- 没有完成开发记录和交接文档，本次开发不得视为完成。
- 新对话必须优先从仓库恢复上下文，不得要求用户重新从头解释已记录的项目规则。
- 已 Stable / Frozen 的 Feature，不得因下游开发方便而随意修改。
- 若确需修改 Stable Contract，必须在文档中说明原因、影响范围、迁移方案和版本变化。
- 每个 Feature 编码前必须复制/填写 `templates/P0_FEATURE_CHECKLIST.md`；所有 P0 项必须明确 `PASS / N/A`，N/A 必须说明原因。
- 上游语义变化后，任何依赖旧 revision 的下游结果不得继续静默作为 Final 输入；必须按 `docs/DEPENDENCY_AND_INVALIDATION_RULES.md` 处理 stale。
- 涉及媒体时间的业务数据必须按 `docs/MEDIA_TIMEBASE_CONTRACT.md` 处理，禁止把 float 秒作为唯一权威时间值。
- 新增/升级环境、依赖、本地模型必须按 `docs/ENVIRONMENT_BASELINE.md` 锁定和记录，禁止依赖未约束的 `latest`。
- 同时写 SQLite 与媒体文件的 Feature 必须按 `docs/DATA_RECOVERY_AND_MIGRATION_RULES.md` 定义 staging、校验、事务和恢复流程。
- 调用外部计费/异步 Provider 的 Feature 必须按 `docs/PROVIDER_JOB_RULES.md` 处理 idempotency、provider_task_id、timeout、resume 和 retry，禁止网络超时后无脑重复生成。
- **所有新增/修改的业务代码必须按 `docs/CODE_AND_DATABASE_COMMENT_RULES.md` 添加足够的简体中文业务注释。**
- **所有新增/修改的数据库表和业务字段必须有明确的中文业务说明，Feature 文档必须维护 Database Dictionary。**
- 代码注释必须解释业务作用、约束和“为什么”，禁止只机械翻译变量名。
- SQLAlchemy Model、Pydantic Schema、Alembic Migration、复杂算法和 Provider Adapter 必须留下可供后续开发者理解的说明。
- Feature 标记 STABLE/FROZEN 前，必须通过 Code Comment Review、Database Comment Review、Database Dictionary Review 和所有适用 P0 Review。

## 新对话恢复上下文的最短路径

```text
SKILL.md
  ↓
SKILL_P0.md
  ↓
docs/PROJECT_STATE.md
  ↓
docs/P0_RULES_INDEX.md
  ↓
docs/CODE_AND_DATABASE_COMMENT_RULES.md
  ↓
当前 docs/features/FXX-*.md
  ↓
当前 Feature 适用的 P0 详细规范
  ↓
最新 docs/sessions/*.md
  ↓
直接继续当前 Next Action
```

目标：即使原聊天记录不可用，也应仅依赖仓库文档和代码恢复到可继续开发状态；同时仅阅读代码、数据库字典和 P0 Contract，就能理解主要表、字段、接口、数据有效性和恢复逻辑的真实作用。