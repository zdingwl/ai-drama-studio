# AI Drama Studio — Project State

> 新对话恢复当前项目状态的第一入口。历史过程放 `docs/sessions/`。

## 当前状态

```text
Project: AI Drama Studio
Official Baseline: main
Current Feature: F01 — 创建项目
Feature Status: PLANNED / NOT_STARTED
Stable Features: none
Frozen Features: none
Business Code: not started
Business DB/Migration: not started
```

`main` 已经是唯一正式 Source of Truth。PR #2 和 PR #1 均已完成合并，不再依赖旧文档分支恢复上下文。

## Approved Production Flow

当前正式流程 = **35 Features**。

完整说明：`docs/FEATURE_SEQUENCE.md`。

关键新增/修正：

- F18 AI 翻译与本土化对白；
- F19 目标对白人工确认；
- F20 目标对白时长约束；
- F31 最终音频组装与混音；
- F32 最终字幕组装；
- F14 AI Casting 必须输出 Casting Profile + Candidates；
- F01 从第一版保存 `project_format_version`。

## 时间域

```text
Source Timeline     = 原片分析证据时间
Shot-local Time     = 单 Shot 内部生产时间
Production Timeline = 最终重制成片时间
```

Source 与 Production 不假设时长恒等。

业务权威时间使用 integer microseconds。

详细：`docs/MEDIA_TIMEBASE_CONTRACT.md`。

## Feature 开发流程

```text
Contract
→ Current Feature Tests
→ Affected Stable Regression
→ 真实素材测试
→ READY_FOR_REVIEW
→ 用户人工验收
→ STABLE/FROZEN
→ 下一 Feature
```

AI / Codex / Agent 只能自行推进到 `READY_FOR_REVIEW`。

只有用户明确确认验收通过后才能 `STABLE/FROZEN`。

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

## 当前技术方案

```text
Frontend: Vue 3 + TypeScript + Vite + Pinia
Backend: Python 3.11 + FastAPI + PyTorch
Media: FFmpeg / FFprobe + OpenCV
Data: SQLite + SQLAlchemy + Alembic + Local Filesystem
Desktop: Electron（后置）
GPU: RTX 4060 Ti 16GB，开发期 concurrency = 1
Strong VLM / Video / Premium TTS / Premium LipSync: Provider Adapter API
```

## 当前代码/数据状态

- 无正式业务代码；
- 无业务数据库；
- 无 Migration；
- 无 Stable/Frozen Feature；
- 无历史业务 Contract 需要兼容。

因此下一步可以从 F01 正确冻结第一份 Project Contract。

## 当前阻塞项

无。

## 已知 Bug

无业务代码，暂无运行 Bug。

## F01 Contract 必须确定

- Project ID；
- `project_format_version`；
- 默认 Workspace 根目录；
- Project 目录结构；
- 每项目独立 SQLite vs 应用级 DB + Workspace；
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
→ 当前 docs/features/FXX-*.md（创建后）
→ 最新相关 Session Handoff
→ 按当前 Feature Rule References 读取必要详细规范
```

不要无差别读取整个 `docs/`，也不要要求用户重新解释已记录的需求和技术决定。

## 最新交接

`docs/sessions/2026-08-23_1440_PROJECT_main-baseline-established.md`

该文档记录了 PR #2 / PR #1 合并、35 Feature、双时间域和下一步 F01 Contract 状态。

## 下一步唯一动作

> 从 `main` 创建 `feature/F01-create-project`，先创建并完善 `docs/features/F01-create-project.md` Contract；用户确认 Contract 后，才开始写第一行业务代码。

## 最近更新时间

- 日期：2026-08-23 14:40 +08:00
- 状态：项目规则与文档已正式进入 `main`，准备开始 Feature 01 Contract。
