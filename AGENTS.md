# AI Drama Studio — Agent Entry Rules

任何开发人员、ChatGPT、Codex 或其他 AI Coding Agent 在修改本仓库前，必须按以下顺序读取项目上下文：

1. `SKILL.md` — 项目长期开发规则、技术边界与 30 个 Feature 顺序。
2. `docs/PROJECT_STATE.md` — 当前项目真实状态、当前 Feature、已冻结 Feature、阻塞项与下一步。
3. `docs/CONTINUATION_PROTOCOL.md` — 跨对话/跨会话续开发规则。
4. 当前 Feature 文档：`docs/features/FXX-*.md`。
5. 最新相关开发会话记录：`docs/sessions/*.md`。
6. 仅在需要时读取当前 Feature 所依赖的上游 Stable Feature 文档。

## 强制规则

- 不允许仅依赖聊天历史作为项目上下文。
- 每一次实际开发都必须同步更新仓库内文档。
- 代码变更与对应文档变更属于同一个交付物。
- 没有完成开发记录和交接文档，本次开发不得视为完成。
- 新对话必须优先从仓库恢复上下文，不得要求用户重新从头解释已记录的项目规则。
- 已 Stable / Frozen 的 Feature，不得因下游开发方便而随意修改。
- 若确需修改 Stable Contract，必须在文档中说明原因、影响范围、迁移方案和版本变化。

## 新对话恢复上下文的最短路径

```text
SKILL.md
  ↓
docs/PROJECT_STATE.md
  ↓
当前 docs/features/FXX-*.md
  ↓
最新 docs/sessions/*.md
  ↓
直接继续当前 Next Action
```

目标：即使原聊天记录不可用，也应仅依赖仓库文档和代码恢复到可继续开发状态。