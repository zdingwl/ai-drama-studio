# AI Drama Studio — Project State

> 本文件是新对话恢复当前项目状态的第一入口。历史细节放 `docs/sessions/`，不要把本文件写成流水账。

## 当前状态

- 项目：AI Drama Studio
- 形态：Windows 本地自用、单用户 AI 短剧重制工作台
- 当前工作分支：`docs/p0-hardening`
- 当前文档 PR：PR #2（基于 `docs/project-skill`）
- 上游主文档 PR：PR #1（`docs/project-skill` → `main`）
- 当前业务 Feature：`Feature 01 — 创建项目`
- 当前 Feature 状态：`PLANNED / NOT_STARTED`
- 已 Stable Feature：无
- 已 Frozen Feature：无
- 业务代码：尚未开始

## Source of Truth 状态

本轮文档修订完成后必须：

```text
先合并 PR #2 → docs/project-skill
再合并 PR #1 → main
```

目标：让 `main` 成为唯一正式项目基线。

在合并完成前，新对话如果要读取最新规则，必须明确使用 `docs/p0-hardening`；合并完成后默认只读 `main`。

## 当前批准的业务流程

正式流程已经从旧的 30 Feature 修正为 **35 Feature**。

新增的独立生产步骤：

- F18 AI 翻译与本土化对白
- F19 目标对白人工确认
- F20 目标对白时长约束
- F31 最终音频组装与混音
- F32 最终字幕组装

因此后续编号整体顺延。

完整顺序：`docs/FEATURE_SEQUENCE.md`。

关键修正原则：

1. 源对白与目标对白分离；
2. 目标对白必须在 Shot Spec / 视频生成之前人工确认；
3. 视频生成前先做目标对白时长约束；
4. AI Casting 必须产出 Casting Profile + Candidates；
5. 最终音频与最终字幕有独立可测试产物；
6. Feature 01 从第一版保存 `project_format_version`。

## 项目级规则已确认

### Feature 开发

```text
Contract
→ 开发
→ 当前 Feature 测试
→ 受影响 Stable Feature 回归测试
→ 真实素材测试
→ READY_FOR_REVIEW
→ 用户人工验收
→ 文档更新
→ STABLE/FROZEN
```

### 用户验收权限

AI / Codex / Agent 不能自行宣布 `STABLE/FROZEN`。

只有用户明确确认验收通过后，才允许冻结并进入下一依赖 Feature。

### 文档权威顺序

```text
用户最新确认并写入仓库的决策
→ Stable/Frozen Feature Contract
→ SKILL + 全局/P0规则
→ 当前 Feature Contract
→ PROJECT_STATE
→ 最新 Session
→ 历史讨论
```

### P0 工程规则

5 个 P0 继续强制，但总原则已经合并进 `SKILL.md`，不再使用第二本 `SKILL_P0.md`。

详细索引：`docs/P0_RULES_INDEX.md`。

### 回归测试

新增：`docs/TESTING_AND_REGRESSION_RULES.md`。

后续修改共享层时，必须运行受影响 Stable Feature regression，不能只测当前 Feature。

### 代码/数据库可理解性

- 业务代码必须有简体中文业务注释；
- 表/字段必须有中文业务说明；
- Feature 文档维护 Database Dictionary；
- Migration / API Schema / Provider Adapter / 复杂算法必须有说明。

详细：`docs/CODE_AND_DATABASE_COMMENT_RULES.md`。

## 当前技术方案

- Frontend：Vue 3 + TypeScript + Vite + Pinia
- Backend / AI Engine：Python 3.11 + FastAPI + PyTorch
- Media：FFmpeg / FFprobe + OpenCV
- Data：SQLite + SQLAlchemy + Alembic + 本地文件系统
- Desktop：Electron 后置
- GPU：RTX 4060 Ti 16GB，开发阶段默认 GPU concurrency = 1
- 强 VLM / Video / Premium TTS / Premium Lip Sync：Provider Adapter 调用 API

## 当前代码状态

- 没有正式业务代码；
- 没有业务数据库；
- 没有 Migration；
- 没有 Stable Feature；
- 当前仍是“正式 Feature 01 开发前的项目规则冻结阶段”。

因此现在修正规则不会造成业务代码返工。

## 当前阻塞项

唯一阻塞：

> 最新文档尚未正式进入 `main`。

本轮完成文档一致性检查后应直接合并 PR #2、PR #1。

## Feature 01 开始前需要在 Contract 确定

- 默认 Workspace 根目录；
- Project ID 规则；
- `project_format_version` 初始版本；
- 项目 DB：每项目独立 SQLite，还是应用级 DB + Workspace；
- 项目元数据字段；
- 创建项目表单字段；
- DB/文件创建事务和失败回滚；
- P0 Checklist；
- Database Dictionary；
- F01 测试与用户验收步骤。

## 新对话最短恢复路径

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ 当前 docs/features/FXX-*.md
→ 最新相关 docs/sessions/*.md
→ 按 Feature Rule References 读取必要详细规范
```

不要一开始无差别读取整个 `docs/`。

## 下一步唯一动作

> 完成本轮文档一致性检查并将 PR #2、PR #1 依次合并到 `main`；随后从 `main` 创建 `feature/F01-create-project`，建立 F01 Contract，不直接开始编码。

## 最近一次状态更新

- 日期：2026-08-23 14:40 +08:00
- 内容：重新审查 Skill 后，修正为 35 Feature 完整生产流程；加入翻译/本土化、目标对白时长、最终音频、字幕；合并 P0 总则到主 Skill；明确 main Source of Truth、文档优先级、用户唯一 Stable 权限和回归测试规则。
