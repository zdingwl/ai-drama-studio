# Session Handoff — Production Flow Review & Main Merge

## 1. 本次目标

重新审查 Skill/规则体系，修正业务生产流程缺口，并在文档一致后把所有正式文档合入 `main`。

## 2. 开始前状态

- 业务代码尚未开始。
- PR #1：`docs/project-skill` → `main`，包含初始 Skill/规则。
- PR #2：`docs/p0-hardening` → `docs/project-skill`，包含 5 个 P0 规则。
- 原业务流程为 30 Feature。
- 原流程缺少正式“目标语言翻译/本土化、目标对白确认/时长约束、最终音频、最终字幕”。
- 原 Timebase 将 Source Timeline 视为唯一母时间轴，无法完整覆盖生成 Shot 时长改变后的最终 Production Timeline。

## 3. 本次主要决策

### 3.1 生产流程调整为 35 Feature

新增独立 Feature：

- F18 AI 翻译与本土化对白
- F19 目标对白人工确认
- F20 目标对白时长约束
- F31 最终音频组装与混音
- F32 最终字幕组装

F14 AI Casting 不额外拆 Feature，但 Contract 必须产生 `Casting Profile + Casting Candidates`。

### 3.2 翻译链前置

正式链路：

```text
Final Source Dialogue
→ Localization Draft
→ Approved Target Dialogue
→ Target Dialogue Timing Constraint
→ Shot Spec / Video / TTS / Subtitle
```

不能等到 TTS 才第一次翻译。

### 3.3 双时间域

修正为：

```text
Source Timeline = 原片分析证据
Production Timeline = 最终重制成片
Shot-local Time = 单镜头内部时间
```

Source 与 Production 通过 Shot/版本/映射关联，不假设最终时长永远等于原片。

业务时间仍统一使用 integer microseconds。

### 3.4 Source of Truth

正式确认的文档和 Stable 代码最终进入 `main`。

```text
main = 最近一次用户确认的正式基线
branch/PR = 开发中/待审核
```

### 3.5 Agent 权限

Agent 只能推进到 `READY_FOR_REVIEW`。

只有用户明确验收通过，Feature 才能 `STABLE/FROZEN`。

### 3.6 文档权威顺序

```text
用户已确认决策
→ Stable/Frozen Contract
→ SKILL/全局规则
→ 当前 Feature Contract
→ PROJECT_STATE
→ Session
→ 历史讨论
```

### 3.7 Skill 减负

- 5 个 P0 总则合并到 `SKILL.md`。
- 删除第二本 `SKILL_P0.md`，避免双 Skill 冲突。
- 新对话只先读少量入口文档，再按当前 Feature 读取必要详细 P0。

### 3.8 Regression

新增 `docs/TESTING_AND_REGRESSION_RULES.md`。

后续 Feature 修改共享层时：

```text
Current Feature Tests
+ Affected Stable Feature Regression
```

必须通过。

### 3.9 Project Format

F01 必须从第一版保存 `project_format_version`，与 Alembic schema revision 分离。

## 4. 修改文件

主要修改：

- `SKILL.md`
- `AGENTS.md`
- `README.md`
- `docs/FEATURE_SEQUENCE.md`
- `docs/PROJECT_STATE.md`
- `docs/CONTINUATION_PROTOCOL.md`
- `docs/DATA_AND_FREEZE_RULES.md`
- `docs/DEPENDENCY_AND_INVALIDATION_RULES.md`
- `docs/MEDIA_TIMEBASE_CONTRACT.md`
- `docs/P0_RULES_INDEX.md`
- `templates/FEATURE_SPEC_TEMPLATE.md`
- `templates/FEATURE_IMPLEMENTATION_LOG_TEMPLATE.md`

新增：

- `docs/TESTING_AND_REGRESSION_RULES.md`
- 本 Session Handoff

删除：

- `SKILL_P0.md`（总则已经合并进 `SKILL.md`）

## 5. 未修改业务代码

本次只有文档/Contract 调整：

- 没有前端代码；
- 没有 Python 业务代码；
- 没有 SQLite；
- 没有 Migration；
- 没有模型依赖变化。

因此不会造成业务代码返工。

## 6. 当前 PR 关系

```text
main
↑ PR #1
 docs/project-skill
 ↑ PR #2
 docs/p0-hardening
```

正确合并顺序：

```text
1. Merge PR #2 into docs/project-skill
2. PR #1 自动包含全部最新文档
3. Merge PR #1 into main
```

## 7. 合并后正式状态

- `main` 成为唯一正式 Source of Truth。
- Approved Production Flow = 35 Feature。
- 当前 Feature = F01 创建项目。
- F01 状态 = PLANNED / NOT_STARTED。
- 下一步不是编码，而是建立 `docs/features/F01-create-project.md` Contract。

## 8. F01 Contract 必须确认

- Project ID；
- `project_format_version`；
- Workspace 默认位置/目录；
- SQLite 布局（每项目独立 DB vs 应用级 DB + workspace）；
- Project metadata；
- 创建项目表单；
- DB/File 创建事务与失败回滚；
- Database Dictionary；
- P0 Checklist；
- Current Tests / Regression；
- 用户人工验收步骤。

## 9. 新对话建议读取

合并完成后：

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/features/F01-create-project.md（创建后）
→ 最新 Session
```

再按 F01 Rule References 阅读必要详细规则。

## 10. 下一步

> 完成 PR #2 → PR #1 的顺序合并，然后在 `main` 上确认文档存在且 PROJECT_STATE 指向 F01；随后创建 F01 Feature 分支和 Contract。
