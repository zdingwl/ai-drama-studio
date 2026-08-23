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
F01 Function Contracts: DRAFTED / WAITING_USER_CONFIRMATION
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

主 Contract：

```text
docs/features/F01-create-project.md
```

单函数详细职责字典：

```text
docs/features/F01-function-contracts.md
```

通用单函数模板：

```text
templates/FUNCTION_CONTRACT_TEMPLATE.md
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

原函数顺序见：

```text
docs/features/F01-create-project.md
```

每个函数的详细业务作用、调用关系、输入输出、副作用、禁止行为、异常和测试见：

```text
docs/features/F01-function-contracts.md
```

以后仅列函数名和一句“单一职责”不视为完成规划。

每个函数正式开发前必须能够回答：

```text
1. 解决什么真实业务问题？
2. 为什么需要独立成函数？
3. 谁调用它？
4. 它调用哪些下层函数？
5. 输入是什么、谁保证输入合法？
6. 输出是什么？
7. 会修改 DB / 文件 / 前端状态吗？
8. 明确禁止修改什么？
9. 会抛哪些业务异常？
10. 对应哪些测试？
```

执行原则：

```text
函数 Contract 明确
→ 函数实现
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
→ API Controller
→ Frontend API / Store
→ Frontend UI
→ 前后端联调
→ Restart / Recovery
→ READY_FOR_REVIEW
→ 用户验收
```

禁止一次把整个 F01 堆完后再统一测试。

## Controller 层特别规则

Controller / Endpoint 是 HTTP 边界层，只允许：

```text
读取 HTTP 输入
→ Schema 校验
→ 调用 Service
→ 返回 DTO
→ 映射 Domain Error
```

Controller 禁止：

- 直接 SQL；
- mkdir；
- 读写 project.json；
- 生成 Project ID；
- 拼 Workspace 路径；
- 编写创建事务和 Recovery；
- 把 Service 业务逻辑复制进路由函数。

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
- Cross-conversation documentation continuity；
- 单函数 Function Contract：业务意义/调用关系/副作用/异常/测试必须明确。

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

- F01 主 Contract 文档已创建；
- F01 单函数详细职责字典已创建；
- 通用 Function Contract 模板已创建；
- 无正式业务代码；
- 无业务数据库；
- 无 Migration；
- 无 Stable/Frozen Feature。

## 当前阻塞项

唯一阻塞：

> 等待用户审核 F01 主 Contract + Function Contracts，并确认关键设计后再进入编码。

## 已知 Bug

无业务代码，暂无运行 Bug。

## 新对话最短恢复路径

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/features/F01-create-project.md
→ docs/features/F01-function-contracts.md
→ 最新相关 Session Handoff
→ 按 F01 Rule References 读取必要详细规范
```

不要无差别读取整个 `docs/`，也不要要求用户重新解释已记录的需求和技术决定。

## 下一步唯一动作

> 用户审核 F01 主 Contract 与详细单函数职责。确认后把 F01 状态从 `PLANNED` 改为 `IN_PROGRESS`，然后从 B01 开始，每次严格按 Function Contract → 实现 → 测试 → PASS 的顺序开发；不擅自新建分支，不实现 F02。

## 最近更新时间

- 日期：2026-08-23 15:43 +08:00
- 状态：补充 F01 单函数详细职责、Controller 边界和通用 Function Contract 模板，仍未开始业务编码。
