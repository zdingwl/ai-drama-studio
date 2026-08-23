# AI Drama Studio

AI Drama Studio 是一个 **Windows 本地自用、单用户的 AI 短剧重制生产工作台**。

目标：把现有短剧转换为可编辑、可追踪、可逐镜头重制的结构化生产工程，并完成本土选角、翻译本土化、AI 视频重生成、QC、配音口型、最终音频/字幕和成片导出。

## Approved Production Flow

```text
01 创建项目
→ 02 上传原视频
→ 03 视频预处理
→ 04 自动拉片
→ 05 Shot 人工修正
→ 06 自动人物识别
→ 07 人物人工修正
→ 08 ASR 源对白识别
→ 09 Speaker / Character 匹配
→ 10 源对白人工修正
→ 11 Scene 自动识别
→ 12 Scene 人工修正
→ 13 本土演员库
→ 14 AI 本土选角
→ 15 人工选演员
→ 16 Character Bible
→ 17 Scene Bible
→ 18 AI 翻译与本土化对白
→ 19 目标对白人工确认
→ 20 目标对白时长约束
→ 21 Shot Specification
→ 22 Shot Spec 人工确认
→ 23 单 Shot 视频生成
→ 24 Generation 版本管理
→ 25 Auto QC
→ 26 失败 Shot 人工处理
→ 27 批量生成
→ 28 TTS
→ 29 Dialogue Fit
→ 30 Lip Sync
→ 31 最终音频组装与混音
→ 32 最终字幕组装
→ 33 最终合成
→ 34 整集 QC
→ 35 导出
```

详细：[`docs/FEATURE_SEQUENCE.md`](./docs/FEATURE_SEQUENCE.md)

## 开发方法

```text
Contract
→ 当前 Feature 开发
→ 单功能测试
→ Regression
→ 真实素材测试
→ READY_FOR_REVIEW
→ 用户人工验收
→ STABLE/FROZEN
→ 下一 Feature
```

AI / Codex 不能自行宣布 STABLE/FROZEN。

## Source of Truth

```text
main = 最近一次用户已经确认的正式基线
branch / PR = 开发中或待审核状态
```

新对话默认从 `main` 恢复项目。

## 核心规则

1. 一个 Feature 一个 Feature 开发，不做“大模块一起写完再测”。
2. Shot 是核心生产单元，单 Shot 可以独立重跑/生成/QC/TTS/LipSync/替换。
3. AI Result 与 Human Final 分离，不覆盖原始 AI 证据。
4. Revision / Dependency / Stale 可追溯，上游变化后旧结果不能静默继续用。
5. Video / TTS / Lip Sync 版本化；Bible/Target Dialogue/Shot Spec 逐步保存 Revision Snapshot。
6. Source Dialogue 与 Target Dialogue 分离；目标对白在 Shot Spec/TTS 前正式确认。
7. **Source Timeline 与 Production Timeline 分离**：原片分析属于 Source Domain，最终重制属于 Production Domain；统一使用 integer microseconds，并通过 Shot/映射关系连接。
8. Provider / Model 可替换，业务层不绑定具体供应商。
9. SQLite + 媒体文件写入必须可恢复。
10. 异步计费 Provider 必须防 timeout 导致重复提交/重复扣费。
11. 新增代码、数据库表/字段、Migration、API Schema 必须有简体中文业务注释。
12. Stable Feature 必须有 Regression 保护。
13. 第一版不做 SaaS、集群、微服务等过度设计。

## 技术方向

```text
Frontend: Vue 3 + TypeScript + Vite + Pinia
Backend: Python 3.11 + FastAPI + PyTorch + CUDA
Media: FFmpeg / FFprobe + OpenCV
Data: SQLite + SQLAlchemy + Alembic + Local Filesystem
Desktop: Electron（后置）
GPU: RTX 4060 Ti 16GB，开发期默认 GPU concurrency = 1
```

## 新对话最短恢复路径

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ 当前 docs/features/FXX-*.md
→ 最新相关 docs/sessions/*.md
→ 根据当前 Feature Rule References 读取必要详细规则
```

不要要求用户重新解释已经写进仓库的需求和技术决定。

## 主要文档

### 必读

- [`AGENTS.md`](./AGENTS.md)
- [`SKILL.md`](./SKILL.md)
- [`docs/PROJECT_STATE.md`](./docs/PROJECT_STATE.md)
- [`docs/FEATURE_SEQUENCE.md`](./docs/FEATURE_SEQUENCE.md)

### 工程规则

- [`docs/P0_RULES_INDEX.md`](./docs/P0_RULES_INDEX.md)
- [`docs/DEPENDENCY_AND_INVALIDATION_RULES.md`](./docs/DEPENDENCY_AND_INVALIDATION_RULES.md)
- [`docs/MEDIA_TIMEBASE_CONTRACT.md`](./docs/MEDIA_TIMEBASE_CONTRACT.md)
- [`docs/ENVIRONMENT_BASELINE.md`](./docs/ENVIRONMENT_BASELINE.md)
- [`docs/DATA_RECOVERY_AND_MIGRATION_RULES.md`](./docs/DATA_RECOVERY_AND_MIGRATION_RULES.md)
- [`docs/PROVIDER_JOB_RULES.md`](./docs/PROVIDER_JOB_RULES.md)
- [`docs/CODE_AND_DATABASE_COMMENT_RULES.md`](./docs/CODE_AND_DATABASE_COMMENT_RULES.md)
- [`docs/TESTING_AND_REGRESSION_RULES.md`](./docs/TESTING_AND_REGRESSION_RULES.md)
- [`docs/DATA_AND_FREEZE_RULES.md`](./docs/DATA_AND_FREEZE_RULES.md)
- [`docs/CONTINUATION_PROTOCOL.md`](./docs/CONTINUATION_PROTOCOL.md)
- [`docs/TECH_STACK.md`](./docs/TECH_STACK.md)

### 模板

- [`templates/FEATURE_SPEC_TEMPLATE.md`](./templates/FEATURE_SPEC_TEMPLATE.md)
- [`templates/P0_FEATURE_CHECKLIST.md`](./templates/P0_FEATURE_CHECKLIST.md)
- [`templates/FEATURE_IMPLEMENTATION_LOG_TEMPLATE.md`](./templates/FEATURE_IMPLEMENTATION_LOG_TEMPLATE.md)
- [`templates/SESSION_HANDOFF_TEMPLATE.md`](./templates/SESSION_HANDOFF_TEMPLATE.md)

## 当前开发入口

业务代码尚未正式开始。

下一步：**Feature 01 — 创建项目 Contract**。
