# AI Drama Studio — Project State

> 本文件是新对话恢复项目状态的第一入口。每次实际开发结束必须更新。

## 当前状态

- 项目：AI Drama Studio
- 形态：Windows 本地自用 AI 短剧重制工作台
- 当前分支：`docs/p0-hardening`
- 上游文档分支：`docs/project-skill`
- 当前主文档 PR：Draft PR #1 — 项目 Skill / 开发规则初始化
- 当前 Feature：`Feature 01 — 创建项目`
- 当前 Feature 状态：`PLANNED / NOT_STARTED`
- 已 Stable Feature：无
- 已 Frozen Feature：无

## 已经确定的核心技术方案

- Frontend：Vue 3 + TypeScript + Vite + Pinia
- AI Backend：Python 3.11 + FastAPI + PyTorch
- Video：FFmpeg / FFprobe / OpenCV
- Data：SQLite + SQLAlchemy + Alembic + 本地文件系统
- Desktop：Electron 后置，先浏览器 + localhost 开发
- GPU：RTX 4060 Ti 16GB，开发期不追求速度，GPU 任务默认串行
- 强 VLM / 视频生成 / Premium TTS / Premium Lip Sync：Provider Adapter 调用外部 API
- 核心原则：模型可替换、AI 原始结果与人工 Final 结果分离、Shot 独立、Generation/TTS/LipSync 版本化

## 固定业务开发顺序

Feature 01 → 30 的完整顺序见：

- `docs/FEATURE_SEQUENCE.md`

当前必须从 Feature 01 开始，不跳过前置功能。

## 完整 Skill 组成

项目 Skill 现在由两部分共同组成：

- `SKILL.md` — 主业务开发 Skill
- `SKILL_P0.md` — 5 个 P0 工程 Contract 补充

任何新 Agent 必须同时读取。

## P0 工程规则已建立

新增 5 个必须在 Feature Contract 阶段检查的 P0 规则：

1. `docs/DEPENDENCY_AND_INVALIDATION_RULES.md`
   - Revision / Dependency Snapshot / Stale / Invalidation
   - 防止上游 Final 修改后旧下游结果继续被误用

2. `docs/MEDIA_TIMEBASE_CONTRACT.md`
   - Source Timeline 为母时间轴
   - 业务权威时间使用 integer microseconds
   - 明确 CFR/VFR、PTS、Proxy/Audio offset

3. `docs/ENVIRONMENT_BASELINE.md`
   - Python/Node/lock/native tool/模型版本可复现
   - 禁止依赖未约束的 latest

4. `docs/DATA_RECOVERY_AND_MIGRATION_RULES.md`
   - SQLite + 本地媒体文件两阶段写入
   - staging/tmp、文件校验、崩溃恢复、migration 前备份

5. `docs/PROVIDER_JOB_RULES.md`
   - 本地 Job 先创建
   - idempotency/request fingerprint
   - provider_task_id 持久化
   - timeout 不等于 failed
   - restart resume，避免重复付费生成

索引：`docs/P0_RULES_INDEX.md`

每个 Feature 开发前必须填写：`templates/P0_FEATURE_CHECKLIST.md`。

## 当前仓库文档状态

关键规则文档包括：

- `SKILL.md`
- `SKILL_P0.md`
- `AGENTS.md`
- `docs/PROJECT_STATE.md`
- `docs/FEATURE_SEQUENCE.md`
- `docs/TECH_STACK.md`
- `docs/DATA_AND_FREEZE_RULES.md`
- `docs/CONTINUATION_PROTOCOL.md`
- `docs/CODE_AND_DATABASE_COMMENT_RULES.md`
- `docs/P0_RULES_INDEX.md`
- `docs/DEPENDENCY_AND_INVALIDATION_RULES.md`
- `docs/MEDIA_TIMEBASE_CONTRACT.md`
- `docs/ENVIRONMENT_BASELINE.md`
- `docs/DATA_RECOVERY_AND_MIGRATION_RULES.md`
- `docs/PROVIDER_JOB_RULES.md`
- `templates/FEATURE_SPEC_TEMPLATE.md`
- `templates/FEATURE_IMPLEMENTATION_LOG_TEMPLATE.md`
- `templates/SESSION_HANDOFF_TEMPLATE.md`
- `templates/P0_FEATURE_CHECKLIST.md`

## 跨对话续开发规则

- 每个 Feature 维护长期 Feature 文档。
- 每次实际开发会话创建独立 Session Handoff。
- 每次开发结束同步更新本文件。
- 代码与文档属于同一个交付物。
- Feature 缺少文档更新时不得标记 STABLE。

## 代码与数据库可理解性规则

- 业务代码必须包含足够的简体中文业务注释。
- 每张业务表和新增/修改的业务字段必须有明确中文说明。
- Feature 文档必须维护 Database Dictionary。
- Feature 标记 STABLE/FROZEN 前必须通过 Code Comment Review、Database Comment Review、Database Dictionary Review。

详细规则：`docs/CODE_AND_DATABASE_COMMENT_RULES.md`。

## P0 Stable Gate

任何 Feature Freeze 前必须记录：

```text
P0 DEPENDENCY REVIEW: PASS / N/A
P0 TIMEBASE REVIEW: PASS / N/A
P0 ENVIRONMENT REVIEW: PASS / N/A
P0 RECOVERY REVIEW: PASS / N/A
P0 PROVIDER JOB REVIEW: PASS / N/A
```

适用项未 PASS，不得进入 STABLE / FROZEN。

## 当前代码状态

- 尚未开始业务代码实现。
- 当前仍处于“正式开发前规则与 Contract 加固”阶段。
- 因此新增 P0 规则不会造成历史业务代码返工。

## 当前阻塞项

无技术阻塞。

## 已知 Bug

无业务代码，因此暂无运行 Bug。

## Feature 01 正式开发前需要确定

- 项目根目录默认位置
- Project ID 生成规则
- 项目 DB 是每项目独立 SQLite，还是应用级 SQLite + project workspace
- “创建项目”第一版表单最终字段
- Feature 01 的 P0 Checklist：环境基线与 DB/文件恢复规则明确适用；其它 P0 项需明确 PASS/N/A 和原因

这些应在 Feature 01 Contract 中冻结，不应只存在聊天里。

## 下一步唯一推荐动作

> 在 P0 规则合入上游文档分支后，创建 `docs/features/F01-create-project.md`；同时使用 `templates/FEATURE_SPEC_TEMPLATE.md`、`templates/FEATURE_IMPLEMENTATION_LOG_TEMPLATE.md` 和 `templates/P0_FEATURE_CHECKLIST.md` 定义 Feature 01 Contract。用户确认 Contract 后，才开始 Feature 01 编码。

## 新对话恢复顺序

1. `AGENTS.md`
2. `SKILL.md`
3. `SKILL_P0.md`
4. 本文件 `docs/PROJECT_STATE.md`
5. `docs/P0_RULES_INDEX.md`
6. `docs/CONTINUATION_PROTOCOL.md`
7. `docs/CODE_AND_DATABASE_COMMENT_RULES.md`
8. 当前 Feature 文档
9. 当前 Feature 标记为适用的 P0 详细规范
10. 最新相关 `docs/sessions/*.md`

## 最近一次状态更新

- 日期：2026-08-23 14:13 +08:00
- 内容：完成 Skill 审计后的 5 个 P0 工程 Contract 加固：依赖失效、媒体时间轴、环境复现、数据恢复/迁移、Provider 幂等与恢复。
- 下一步：完成本次 P0 规则 PR 后，正式建立 Feature 01 Contract。