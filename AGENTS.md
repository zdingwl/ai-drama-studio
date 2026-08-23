# AI Drama Studio — Agent Entry Rules

本文件是 ChatGPT、Codex、人工开发者进入项目时的最短入口。

## 1. 新对话强制读取顺序

不要一开始无差别读取整个仓库文档。按以下顺序恢复：

```text
1. AGENTS.md
2. SKILL.md
3. docs/PROJECT_STATE.md
4. 当前 Feature 文档 docs/features/FXX-*.md
5. 最新与当前 Feature 相关的 docs/sessions/*.md
6. 根据当前 Feature 标记的 Rule References / P0 Checklist，再读取必要的详细规则
```

目标：在聊天上下文有限的情况下，快速恢复当前真实状态，而不是重新分析整个项目。

---

## 2. Source of Truth

`main` 是最近一次已经正式确认的项目基线。

分支/PR 中的内容属于：开发中、审核中或待合并状态。

如果当前任务明确要求继续某个尚未合并的分支，则读取该分支；否则默认以 `main` 为正式基线。

---

## 3. 文档冲突时的优先级

```text
1. 用户最新明确确认并写入仓库的决策
2. 已 STABLE/FROZEN Feature Contract
3. SKILL.md + 适用的全局/P0 Contract
4. 当前 Feature Contract
5. docs/PROJECT_STATE.md
6. 最新 Session Handoff
7. 历史 Session / 旧讨论
```

发现冲突：必须指出冲突并按优先级处理，禁止静默选一个版本。

---

## 4. Feature 开发强制规则

- 一次只正式开发一个业务 Feature。
- 未定义 Contract，不开始编码。
- 不允许为了下游方便修改 Stable/Frozen 上游 Contract。
- 如必须改变 Frozen Contract，先做影响分析、迁移/V2 方案并取得用户确认。
- 每个 Feature 编码前填写 `templates/P0_FEATURE_CHECKLIST.md`。
- AI 原始结果与人工 Final 结果分离。
- 上游语义变化后按 Revision / Stale 规则处理下游。
- 涉及媒体时间时遵守 Source Timeline + integer microseconds。
- 调用计费异步 Provider 时必须防重复提交/重复扣费。
- SQLite + 媒体文件写入必须考虑 staging、校验、事务和恢复。
- 新增/升级依赖必须锁定版本，不依赖 `latest`。
- 新增/修改的业务代码、数据库表、字段、Migration、API Schema 必须有足够的简体中文业务注释。
- 涉及数据库的 Feature 文档必须维护 Database Dictionary。
- 修改共享代码后必须运行受影响 Stable Feature 的回归测试。

---

## 5. Agent 权限边界

AI / Codex / 自动化 Agent 可以将 Feature 推进到：

```text
READY_FOR_REVIEW
```

但不能自行宣布：

```text
STABLE
FROZEN
```

只有用户明确确认“验收通过”后才能进入 STABLE/FROZEN，并继续下一个依赖 Feature。

---

## 6. 每次实际开发结束必须更新

至少：

1. 当前 `docs/features/FXX-*.md`；
2. `docs/PROJECT_STATE.md`；
3. 新建 `docs/sessions/YYYY-MM-DD_HHMM_FXX_topic.md`。

代码改了但文档未更新：视为开发未完成。

---

## 7. 详细规则索引

按需读取：

- `docs/FEATURE_SEQUENCE.md`
- `docs/P0_RULES_INDEX.md`
- `docs/DEPENDENCY_AND_INVALIDATION_RULES.md`
- `docs/MEDIA_TIMEBASE_CONTRACT.md`
- `docs/ENVIRONMENT_BASELINE.md`
- `docs/DATA_RECOVERY_AND_MIGRATION_RULES.md`
- `docs/PROVIDER_JOB_RULES.md`
- `docs/CODE_AND_DATABASE_COMMENT_RULES.md`
- `docs/TESTING_AND_REGRESSION_RULES.md`
- `docs/CONTINUATION_PROTOCOL.md`
- `docs/DATA_AND_FREEZE_RULES.md`
- `docs/TECH_STACK.md`

当前项目正式生产流程为 **35 个 Feature**，以 `docs/FEATURE_SEQUENCE.md` 为准。
