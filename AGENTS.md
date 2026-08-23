# AI Drama Studio — Agent Entry Rules

任何开发人员、ChatGPT、Codex 或其他 AI Coding Agent 在修改本仓库前，必须按以下顺序读取项目上下文：

1. `SKILL.md` — 项目长期开发规则、技术边界与 30 个 Feature 顺序。
2. `docs/PROJECT_STATE.md` — 当前项目真实状态、当前 Feature、已冻结 Feature、阻塞项与下一步。
3. `docs/CONTINUATION_PROTOCOL.md` — 跨对话/跨会话续开发规则。
4. `docs/CODE_AND_DATABASE_COMMENT_RULES.md` — 代码、数据库表、字段、Migration 和 API Schema 的强制中文说明规范。
5. 当前 Feature 文档：`docs/features/FXX-*.md`。
6. 最新相关开发会话记录：`docs/sessions/*.md`。
7. 仅在需要时读取当前 Feature 所依赖的上游 Stable Feature 文档。

## 强制规则

- 不允许仅依赖聊天历史作为项目上下文。
- 每一次实际开发都必须同步更新仓库内文档。
- 代码变更与对应文档变更属于同一个交付物。
- 没有完成开发记录和交接文档，本次开发不得视为完成。
- 新对话必须优先从仓库恢复上下文，不得要求用户重新从头解释已记录的项目规则。
- 已 Stable / Frozen 的 Feature，不得因下游开发方便而随意修改。
- 若确需修改 Stable Contract，必须在文档中说明原因、影响范围、迁移方案和版本变化。
- **所有新增/修改的业务代码必须按 `docs/CODE_AND_DATABASE_COMMENT_RULES.md` 添加足够的简体中文业务注释。**
- **所有新增/修改的数据库表和业务字段必须有明确的中文业务说明，Feature 文档必须维护 Database Dictionary。**
- 代码注释必须解释业务作用、约束和“为什么”，禁止只机械翻译变量名。
- SQLAlchemy Model、Pydantic Schema、Alembic Migration、复杂算法和 Provider Adapter 必须留下可供后续开发者理解的说明。
- Feature 标记 STABLE/FROZEN 前，必须通过 Code Comment Review、Database Comment Review，并确认 Database Dictionary 完整。

## 新对话恢复上下文的最短路径

```text
SKILL.md
  ↓
docs/PROJECT_STATE.md
  ↓
docs/CODE_AND_DATABASE_COMMENT_RULES.md
  ↓
当前 docs/features/FXX-*.md
  ↓
最新 docs/sessions/*.md
  ↓
直接继续当前 Next Action
```

目标：即使原聊天记录不可用，也应仅依赖仓库文档和代码恢复到可继续开发状态；同时仅阅读代码和数据库字典，就能理解主要表、字段、接口和业务逻辑的真实作用。