# Session Handoff — Canonical Main Baseline Established

## 1. 本次结果

AI Drama Studio 的项目 Skill、P0 工程规则、35 Feature Approved Production Flow、测试/回归规则、代码/数据库注释规则、跨对话续开发协议和模板已经正式进入 `main`。

合并顺序已经完成：

```text
PR #2: docs/p0-hardening → docs/project-skill
PR #1: docs/project-skill → main
```

PR #2 merge commit：`ceea005b973c97e4b3f6ad389c07560a41075d05`

PR #1 merge commit：`91e3b190dcf55c27a1d1c812d2215e3b127ab7ed`

随后在 `main` 更新 PROJECT_STATE，使其不再保留“待合并”的旧状态。

## 2. 当前正式 Source of Truth

```text
main
```

新对话默认不再读取旧的文档分支。

## 3. 当前业务状态

```text
Current Feature: F01 — 创建项目
Status: PLANNED / NOT_STARTED
Stable Features: none
Frozen Features: none
Business Code: none
Business DB/Migration: none
```

## 4. Approved Production Flow

当前正式顺序为 35 Feature。

关键新增步骤：

- F18 AI 翻译与本土化对白
- F19 目标对白人工确认
- F20 目标对白时长约束
- F31 最终音频组装与混音
- F32 最终字幕组装

AI Casting 的 F14 内部必须显式产出 `Casting Profile + Casting Candidates`。

## 5. 关键项目治理规则

### Feature 生命周期

```text
PLANNED
→ IN_PROGRESS
→ TESTING
→ READY_FOR_REVIEW
→ 用户验收
→ STABLE/FROZEN
```

Agent 不得自行宣布 STABLE/FROZEN。

### Source of Truth

```text
main = 用户已经确认的正式基线
branch/PR = 开发中或待审核状态
```

### 文档优先级

```text
用户已确认决策
→ Stable/Frozen Contract
→ SKILL/全局/P0
→ 当前 Feature Contract
→ PROJECT_STATE
→ 最新 Session
→ 历史记录
```

## 6. 时间轴正式规则

当前使用：

```text
Source Timeline
Shot-local Time
Production Timeline
```

不再使用“Source Timeline 是整个项目唯一母时间轴”的旧假设。

业务权威时间使用 integer microseconds。

## 7. 当前文档入口

新对话依次读取：

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/features/F01-create-project.md（创建后）
→ 最新 Session Handoff
```

然后按当前 Feature 的 Rule References / P0 Checklist 读取必要详细规则。

## 8. Feature 01 尚未开始

不要直接写代码。

F01 Contract 必须先确认：

- Project ID；
- project_format_version；
- Workspace；
- Project metadata；
- SQLite 布局；
- DB/File transaction/recovery；
- API；
- Database Dictionary；
- P0 Checklist；
- Tests；
- 用户验收步骤。

## 9. 下一步唯一动作

> 从 `main` 创建 `feature/F01-create-project`，创建 `docs/features/F01-create-project.md`，先完成并让用户确认 Contract，再开始 F01 编码。
