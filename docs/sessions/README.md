# Development Session Handoffs

本目录保存每一次实际开发会话的独立交接文档，用于跨 ChatGPT/Codex 对话继续开发。

命名格式：

```text
YYYY-MM-DD_HHMM_FXX_<topic>.md
```

示例：

```text
2026-08-23_1420_F01_project-create-api.md
2026-08-24_1035_F01_project-create-ui.md
```

每次实际修改代码后，结束会话前必须创建一份新的 handoff 文档。

必须使用：

- `templates/SESSION_HANDOFF_TEMPLATE.md`

Session Handoff 是时间点快照，不替代 Feature 主文档：

- `docs/features/FXX-*.md` 记录 Feature 的长期真实状态。
- `docs/sessions/*.md` 记录一次具体开发会话做了什么，以及下一次从哪里继续。
- `docs/PROJECT_STATE.md` 记录整个项目当前唯一状态入口。

新的对话优先阅读最新、与当前 Feature 相关的 Session Handoff，不需要遍历所有历史 session 文档。