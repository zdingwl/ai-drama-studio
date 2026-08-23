# Session Handoff — Git Branch / PR Permission Rule

## 1. 本次目标

根据用户最新明确要求，补充项目级 Git 操作权限规则：

> **不要擅自新建分支。**

该要求不仅适用于新建分支，也用于约束 Agent 对分支、PR、branch ref 的其它结构性操作。

## 2. 开始前状态

- Official Baseline：`main`
- Current Feature：F01 — 创建项目
- Feature Status：PLANNED / NOT_STARTED
- Business Code：尚未开始
- 原 Skill 中存在“正式业务开发建议使用 `feature/F01-create-project`”的建议；
- 原 PROJECT_STATE 的 Next Action 也写着“从 main 创建 feature/F01-create-project”。

这两处会诱导新 Agent 未经用户授权自动建立分支，因此与用户最新要求冲突。

## 3. 本次实际修改

### AGENTS.md

新增 `Git 操作权限边界`：

未经用户明确要求，AI / Codex / Agent 禁止：

- 新建分支；
- 自动创建 `feature/*` / `fix/*` / `docs/*`；
- 切换分支后擅自开发；
- 删除/重命名分支；
- force update / 移动 branch ref；
- 擅自创建、关闭、合并、重新打开 PR；
- 擅自修改 PR base/head；
- 用“最佳实践”作为理由改变用户 Git 工作流。

### SKILL.md

版本从 `2.1.0` 更新为 `2.1.1`。

原第 28 节“Git / PR”中建议按 Feature 建分支的内容已删除，改为：

> Git / Branch / PR 操作必须由用户授权。

同时在 Source of Truth 章节补充：

> `main` 是正式读取基线，并不意味着 Agent 有权自动创建 feature 分支。

### docs/PROJECT_STATE.md

- 记录当前 Working Branch：`main`；
- 新增 Git 操作权限章节；
- 删除“下一步创建 feature/F01-create-project”的要求；
- Next Action 改为：在用户当前指定的 Git 工作方式下继续 F01 Contract，未经用户明确要求不得创建新分支。

## 4. 没有做的事情

本次没有：

- 新建任何分支；
- 切换任何分支；
- 创建 PR；
- 修改业务代码；
- 创建数据库或 Migration；
- 修改 35 Feature 顺序；
- 开始 F01 Contract 实现。

所有修改直接写入用户已经确认的正式基线 `main`。

## 5. 新的正式 Git 权限 Contract

以后 Agent 应遵守：

```text
用户明确要求 Git 结构操作
→ 执行明确要求的动作

用户没有明确要求创建/切换/删除/合并
→ 不执行对应 Git 结构操作
```

特别强调：

```text
一个 Feature 一个 Feature 开发
≠
一个 Feature 必须一个新分支
```

Feature 顺序和 Git 分支策略是两个独立概念。

## 6. Contract 是否变化

项目治理 Contract：**是**。

新增：

- Git Branch / PR Operations Require Explicit User Authorization。

业务 Feature Contract：无变化。

35 Feature Production Flow：无变化。

## 7. 当前状态

```text
Official Baseline: main
Current Working Branch: main
Current Feature: F01 — 创建项目
Feature Status: PLANNED / NOT_STARTED
Stable Features: none
Frozen Features: none
```

## 8. 下一步

继续 F01 时：

1. 读取 `AGENTS.md`；
2. 读取 `SKILL.md`；
3. 读取 `docs/PROJECT_STATE.md`；
4. 不自动创建 `feature/F01-create-project`；
5. 在用户当前明确指定的 Git 工作方式下建立 `docs/features/F01-create-project.md` Contract；
6. Contract 经用户确认后再编码。

如果用户后续明确说“创建一个 F01 分支”或指定其它分支策略，才执行对应 Git 操作。
