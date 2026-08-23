# AI Drama Studio — Project State

> 新对话恢复当前项目状态的第一入口。历史过程放 `docs/sessions/`。

## 当前状态

```text
Project: AI Drama Studio
Official Baseline: main
Current Working Branch: main（用户未要求切换/新建其它分支）
Current Feature: F01 — 创建项目
Feature Status: PLANNED
F01 Contract: DRAFTED / WAITING_USER_CONFIRMATION
Stable Features: none
Frozen Features: none
Business Code: not started
Business DB/Migration: not started
```

`main` 是唯一正式 Source of Truth。

## Git 操作权限

Git 分支和 PR 结构由用户控制。

未经用户明确要求，AI / Codex / Agent 不得：

- 新建分支；
- 自动创建 `feature/*` / `fix/*` / `docs/*` 等分支；
- 切换、删除或重命名分支；
- force update / 移动 branch ref；
- 擅自创建、关闭、合并或重定向 PR。

当前用户已经明确要求：**不要擅自新建分支。**

因此 F01 当前直接在用户指定的 `main` 维护文档；只有用户后续明确要求其它 Git 结构动作时才执行。

详细规则：`AGENTS.md` 与 `SKILL.md` 第 28 节。

## F01 Contract 已建立

当前正式草案：

```text
docs/features/F01-create-project.md
```

F01 被定义为：

> 建立 Project 容器、应用级项目注册、Workspace、`project.json`、重启恢复；不涉及任何视频或 AI。

当前建议的关键设计（等待用户确认）：

```text
1. 应用级单 SQLite：app.db
2. 默认 Workspace Root：%USERPROFILE%/AI Drama Studio Projects
3. Project ID：PROJECT_<UUID4_HEX>
4. Project Workspace：<root>/<project_id>/
5. F01 只创建 project.json，不提前创建媒体目录
6. 浏览器开发期自定义存储位置使用文本路径；Electron 后续再接原生目录选择器
7. F01 不做删除/重命名/归档/导入导出
8. project_format_version = 1
9. Project lifecycle = creating → ready；创建中断通过 startup recovery 恢复
```

用户确认前不得把 F01 标记 `IN_PROGRESS`，不得开始业务代码。

## F01 单函数开发方式

F01 已拆成单函数执行顺序，详细见 `docs/features/F01-create-project.md`。

执行原则：

```text
函数实现
→ 对应测试
→ PASS
→ 下一个函数
```

分组：

```text
Backend Foundation
→ Project Validation / ID / Paths
→ Manifest
→ Repository
→ Recovery / Service
→ API
→ Frontend API / Store
→ Frontend UI
→ 前后端联调
→ Restart / Recovery
→ READY_FOR_REVIEW
→ 用户验收
```

禁止一次把整个 F01 堆完后再统一测试。

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

F01 实现时只安装 F01 实际需要的最小依赖；PyTorch/CUDA/OpenCV/AI 模型不在 F01 提前安装。

## 当前代码/数据状态

- F01 Contract 文档已创建；
- 无正式业务代码；
- 无业务数据库；
- 无 Migration；
- 无 Stable/Frozen Feature。

## 当前阻塞项

唯一阻塞：

> 等待用户确认 `docs/features/F01-create-project.md` 第 31 节的 9 个关键决策。

## 已知 Bug

无业务代码，暂无运行 Bug。

## 新对话最短恢复路径

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/features/F01-create-project.md
→ 最新相关 Session Handoff
→ 按 F01 Rule References 读取必要详细规范
```

不要无差别读取整个 `docs/`，也不要要求用户重新解释已记录的需求和技术决定。

## 下一步唯一动作

> 用户审核并确认 F01 Contract 的 9 个关键决策。确认后把 F01 状态从 `PLANNED` 改为 `IN_PROGRESS`，然后严格从单函数 B01 开始编码；不擅自新建分支，不实现 F02。

## 最近更新时间

- 日期：2026-08-23 15:18 +08:00
- 状态：F01 单函数级开发 Contract 已建立，等待用户确认后开始编码。
