# AI Drama Studio — Project State

> 本文件是新对话恢复当前项目状态的第一入口。历史过程放 `docs/sessions/`。

## 当前状态

- 项目：AI Drama Studio
- 正式基线分支：`main`
- Source of Truth：`main`
- 当前业务 Feature：`Feature 01 — 创建项目`
- 当前 Feature 状态：`PLANNED / NOT_STARTED`
- 已 Stable Feature：无
- 已 Frozen Feature：无
- 正式业务代码：尚未开始
- 业务数据库 / Migration：尚未创建

## 文档合并状态

已完成：

```text
PR #2 → docs/project-skill
PR #1 → main
```

现在所有已经确认的项目 Skill、P0 工程规则、35 Feature 生产流程、模板和交接文档都已经进入 `main`。

新对话默认只需要从 `main` 恢复，不再依赖 `docs/project-skill` 或 `docs/p0-hardening`。

## 当前批准的生产流程

Approved Production Flow = **35 Features**。

完整顺序：`docs/FEATURE_SEQUENCE.md`。

关键新增/修正：

- F18 AI 翻译与本土化对白；
- F19 目标对白人工确认；
- F20 目标对白时长约束；
- F31 最终音频组装与混音；
- F32 最终字幕组装；
- F14 AI Casting 必须输出 Casting Profile + Candidates；
- F01 从第一版保存 `project_format_version`。

## 时间轴规则

采用三个明确概念：

```text
Source Timeline     = 原片分析证据时间
Shot-local Time     = 单 Shot 内部生产时间
Production Timeline = 最终重制成片时间
```

Source 与 Production 不假设时长恒等。

业务权威时间统一使用 integer microseconds。

详细：`docs/MEDIA_TIMEBASE_CONTRACT.md`。

## Feature 开发流程

```text
Contract
→ 开发
→ Current Feature Tests
→ Affected Stable Regression
→ 真实素材测试
→ READY_FOR_REVIEW
→ 用户人工验收
→ STABLE/FROZEN
→ 下一 Feature
```

AI / Codex / Agent 只能自行推进到 `READY_FOR_REVIEW`。

只有用户明确确认验收通过后，才能标记 `STABLE/FROZEN`。

## 文档权威顺序

```text
用户最新明确确认并写入仓库的决策
→ Stable/Frozen Feature Contract
→ SKILL.md + 适用全局/P0规则
→ 当前 Feature Contract
→ PROJECT_STATE
→ 最新 Session Handoff
→ 历史 Session / 旧讨论
```

## 当前核心工程规则

- Dependency / Revision / Invalidation / Stale；
- Source / Shot-local / Production Timebase；
- Environment Baseline / Dependency Lock；
- SQLite + File Recovery / Migration；
- Provider idempotency / resume / duplicate-charge protection；
- Simplified-Chinese code/database business comments；
- Database Dictionary；
- Stable Feature Regression；
- Cross-conversation documentation continuity。

入口：

- `SKILL.md`
- `docs/P0_RULES_INDEX.md`
- `docs/TESTING_AND_REGRESSION_RULES.md`
- `docs/CODE_AND_DATABASE_COMMENT_RULES.md`

## 当前技术方案

- Frontend：Vue 3 + TypeScript + Vite + Pinia
- Backend / AI Engine：Python 3.11 + FastAPI + PyTorch
- Media：FFmpeg / FFprobe + OpenCV
- Data：SQLite + SQLAlchemy + Alembic + Local Filesystem
- Desktop：Electron 后置
- GPU：RTX 4060 Ti 16GB，开发期默认 concurrency = 1
- Strong VLM / Video / Premium TTS / Premium Lip Sync：Provider Adapter API

## 当前代码状态

目前没有正式业务代码，因此：

- 没有历史代码需要兼容；
- 没有已有业务表需要迁移；
- 没有 Stable Feature 可被下游破坏；
- 可以从 F01 正确冻结第一份 Project Contract。

## 当前阻塞项

无。

## 已知 Bug

无业务代码，暂无运行 Bug。

## Feature 01 Contract 必须确定

- Project ID 规则；
- `project_format_version` 初始版本；
- 默认 Workspace 根目录；
- 项目目录结构；
- 项目 DB 采用每项目独立 SQLite，还是应用级 DB + Workspace；
- Project metadata；
- 创建项目表单字段；
- DB/File 创建事务、失败回滚与恢复；
- Database Dictionary；
- P0 Checklist；
- Current Tests；
- 用户人工验收步骤。

## 新对话最短恢复路径

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ 当前 docs/features/FXX-*.md（存在后）
→ 最新相关 docs/sessions/*.md
→ 按当前 Feature Rule References 读取必要详细规范
```

不要无差别读取整个 `docs/`，也不要要求用户重新解释已记录的项目规则。

## 下一步唯一动作

> 从 `main` 创建 `feature/F01-create-project`，先建立 `docs/features/F01-create-project.md` Contract；用户确认 F01 Contract 后，才开始写第一行业务代码。

## 最新交接

- `docs/sessions/2026-08-23_1440_PROJECT_production-flow-review-and-main-merge.md`
- 合并完成后的最终状态见随后新增的 main-baseline Session Handoff。

## 最近更新时间

- 日期：2026-08-23 14:40 +08:00
- 状态：项目规则与文档已经正式进入 `main`，准备开始 Feature 01 Contract。
