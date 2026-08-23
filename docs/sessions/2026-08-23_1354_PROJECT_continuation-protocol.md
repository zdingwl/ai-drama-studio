# Session Handoff — 2026-08-23 13:54 — Project Rules — Continuation Protocol

## 1. 本次开发目标

用户明确要求：为了防止聊天上下文超限，每一次后续开发都必须有足够详细的仓库文档，使新的 ChatGPT/Codex 对话可以直接继续开发，而不是重新从头分析项目。

本次目标是把该要求变成仓库强制规则、固定文档结构和模板。

## 2. 开始前项目状态

- Repository：`zdingwl/ai-drama-studio`
- Branch：`docs/project-skill`
- PR：Draft PR #1
- 业务代码：尚未开始
- 当前业务 Feature：Feature 01 — 创建项目（PLANNED / NOT_STARTED）
- 已有主要规则：`SKILL.md`、Feature 01→30 固定顺序、技术栈、Data/Freeze Rule、Feature Spec 模板
- 问题：项目尚未定义“跨新对话持续开发”的强制文档交接机制

## 3. 本次实际完成

新增完整的跨对话开发恢复机制：

1. 新增根目录 `AGENTS.md` 作为 Agent 进入仓库的强制读取入口。
2. 新增 `docs/CONTINUATION_PROTOCOL.md`，定义跨对话恢复、Feature 长期文档、Session Handoff、Project State、Contract Snapshot 等规则。
3. 新增 `docs/PROJECT_STATE.md`，作为项目当前唯一状态入口。
4. 新增 `templates/FEATURE_IMPLEMENTATION_LOG_TEMPLATE.md`。
5. 新增 `templates/SESSION_HANDOFF_TEMPLATE.md`。
6. 新增 `docs/features/README.md`，定义 Feature 主文档目录和命名规则。
7. 新增 `docs/sessions/README.md`，定义每次开发 Session Handoff 目录和命名规则。
8. 更新 `docs/PROJECT_STATE.md`，同步模板和续开发规则已生效。
9. 创建本 Session Handoff，立即开始按新规则执行。

## 4. 修改文件清单

### 新增

- `AGENTS.md` — 新 Agent / 新对话强制读取入口
- `docs/CONTINUATION_PROTOCOL.md` — 跨对话持续开发完整协议
- `docs/PROJECT_STATE.md` — 当前项目状态唯一入口
- `templates/FEATURE_IMPLEMENTATION_LOG_TEMPLATE.md` — Feature 长期开发档案模板
- `templates/SESSION_HANDOFF_TEMPLATE.md` — 单次开发会话交接模板
- `docs/features/README.md` — Feature 文档目录规则
- `docs/sessions/README.md` — Session 文档目录规则
- `docs/sessions/2026-08-23_1354_PROJECT_continuation-protocol.md` — 本交接记录

### 修改

- `docs/PROJECT_STATE.md` — 在创建模板后同步实际状态

### 删除

- 无

## 5. 关键规则位置

| 文件 | 作用 | 后续注意事项 |
|---|---|---|
| `AGENTS.md` | 新 Agent 入口 | 新对话首先读取 |
| `docs/PROJECT_STATE.md` | 当前真实状态 | 每次开发结束必须更新 |
| `docs/CONTINUATION_PROTOCOL.md` | 持续开发制度 | 不得只依赖聊天历史 |
| `docs/features/FXX-*.md` | Feature 永久技术档案 | 开发过程中持续维护 |
| `docs/sessions/*.md` | 单次开发快照 | 每次实际开发结束创建新文件 |
| `templates/SESSION_HANDOFF_TEMPLATE.md` | 交接模板 | 必须包含具体 Next Action |

## 6. API 变化

无。当前尚未开始业务代码。

## 7. Database 变化

无。

## 8. 文件系统变化

仓库新增文档目录约定：

```text
docs/
├── PROJECT_STATE.md
├── CONTINUATION_PROTOCOL.md
├── features/
│   └── FXX-<feature>.md
└── sessions/
    └── YYYY-MM-DD_HHMM_FXX_<topic>.md
```

项目运行时 workspace 目录规则没有变化。

## 9. 依赖 / 环境变化

无 Python / Node / CUDA / FFmpeg 依赖变化。

## 10. 技术决策与原因

### Decision 001 — 仓库是长期上下文的唯一可靠来源

- 决策：聊天历史不作为唯一项目状态来源。
- 原因：聊天可能超长、丢失、切换会话、换 Agent。
- 结果：每次开发必须把关键信息落到仓库。

### Decision 002 — 三层文档结构

采用：

```text
PROJECT_STATE（当前全局状态）
+
Feature Document（某功能长期状态）
+
Session Handoff（一次开发快照）
```

原因：单独一种文档无法同时兼顾“当前状态”“长期技术档案”和“最近一次工作细节”。

### Decision 003 — 代码和文档是同一个交付物

如果代码完成但 Feature 文档、Session Handoff、PROJECT_STATE 没有更新，该开发不得视为完成，也不得标记 Feature STABLE。

### Decision 004 — Next Action 必须具体

Session Handoff 禁止只写“继续开发 Feature 01”。

必须写成下一位 Agent 能立即执行的文件/接口/测试级动作。

## 11. 本次没有做的内容

- 没有开始 Feature 01 业务代码。
- 没有创建 `docs/features/F01-create-project.md`。
- 没有定义 Feature 01 的 Project ID、数据库组织和创建项目表单 Contract。
- 没有修改任何运行时代码。

## 12. 测试执行情况

### 文档一致性检查

已确认：

- 新文档全部写入 `docs/project-skill` 分支。
- `PROJECT_STATE.md` 已同步模板从“待创建”改为“已创建”。
- 新对话读取路径在 `AGENTS.md` 和 `CONTINUATION_PROTOCOL.md` 中已定义。

### 运行测试

无业务代码，因此无需运行测试。

## 13. 当前 Bug / 风险

### Bug

无。

### 风险

- 根 `SKILL.md` 当前主体规则已经存在，但本次新增的持续开发细则主要通过 `AGENTS.md` + `docs/CONTINUATION_PROTOCOL.md` 进行增强；未来如果更新 `SKILL.md`，应考虑在主 Skill 中加入对该协议的显式引用。

## 14. Contract 变化检查

- 业务 Input Contract：未变
- 业务 Output Contract：未变
- API Contract：未变
- DB Contract：未变
- File Runtime Contract：未变
- 开发流程 Contract：**已增强**

新增强制 Gate：

```text
编码完成
→ 测试
→ 真实素材验证
→ 人工验收
→ Feature 文档更新
→ Session Handoff 创建
→ PROJECT_STATE 更新
→ Freeze
→ 下一 Feature
```

## 15. 当前 Feature 状态

- Feature 01：PLANNED / NOT_STARTED
- 是否可开始 Feature 01 Contract：Yes
- 是否可直接开始 Feature 01 编码：No
- 缺少：`docs/features/F01-create-project.md` Contract + 用户确认

## 16. Git 状态

- Repository：`zdingwl/ai-drama-studio`
- Branch：`docs/project-skill`
- PR：Draft PR #1
- 本次修改已逐文件提交到该分支
- 无已知未提交的本地业务代码

## 17. 下一步唯一推荐动作

> 创建 `docs/features/F01-create-project.md`，基于 Feature Spec / Implementation Log 模板完整定义 Feature 01「创建项目」的用户流程、Input/Output、SQLite 策略、Project ID、workspace 目录、API、UI、异常与验收标准；用户确认后再写第一行业务代码。

## 18. 新对话读取清单

1. `AGENTS.md`
2. `SKILL.md`
3. `docs/PROJECT_STATE.md`
4. `docs/CONTINUATION_PROTOCOL.md`
5. 本文件
6. 开始 Feature 01 时读取：`templates/FEATURE_SPEC_TEMPLATE.md`
7. 开始 Feature 01 时读取：`templates/FEATURE_IMPLEMENTATION_LOG_TEMPLATE.md`

## 19. 给下一位 Agent 的一句话

> 项目尚未开始业务编码；跨对话持续开发机制已经建立，下一步只需定义并确认 Feature 01「创建项目」Contract，然后开始实现，不要重新规划整个 AI Drama Studio。