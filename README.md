# AI Drama Studio

AI Drama Studio 是一个 **Windows 本地自用、单用户的 AI 短剧重制生产工作台**。

目标：将已有短剧转换为可编辑、可追踪、可逐镜头重制的结构化生产工程，并完成本土选角、翻译本土化、AI 视频重生成、QC、配音口型、音频字幕和最终导出。

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

完整说明见：[`docs/FEATURE_SEQUENCE.md`](./docs/FEATURE_SEQUENCE.md)。

## 最重要的开发方式

不要按“大模块”一起开发。

必须：

```text
当前 Feature Contract
→ 开发
→ 单功能测试
→ 回归测试
→ 真实素材测试
→ READY_FOR_REVIEW
→ 用户人工验收
→ 文档更新
→ STABLE/FROZEN
→ 下一 Feature
```

AI / Codex 只能把 Feature 推进到 `READY_FOR_REVIEW`；只有用户明确确认验收通过后，才能标记 `STABLE/FROZEN`。

## Source of Truth

正式确认的项目事实最终必须进入 `main`。

- `main`：最近一次已确认稳定基线；
- feature/docs 分支：正在开发或审核中的变更；
- 新对话默认从 `main` 恢复项目，除非用户明确指定继续某个未合并分支。

## 当前技术方向

- Frontend：Vue 3 + TypeScript + Vite + Pinia
- Backend / AI Engine：Python 3.11 + FastAPI + PyTorch + CUDA
- Media：FFmpeg / FFprobe + OpenCV
- Data：SQLite + SQLAlchemy + Alembic + Local Workspace
- Desktop：Electron 后置
- GPU：RTX 4060 Ti 16GB，开发期默认 GPU 单任务串行
- 强 VLM / Video Generation / Premium TTS / Premium Lip Sync：Provider Adapter 调用 API

## 核心规则

1. **一个 Feature 一个 Feature 开发。**
2. **Shot 是核心生产单元。** 单 Shot 可独立重跑、生成、QC、TTS、Lip Sync、替换。
3. **AI Result 与 Human Final 分离。** 人工修正不能覆盖 AI 原始结果。
4. **Revision / Dependency / Stale 可追溯。** 上游语义变化后，旧下游结果不能静默继续使用。
5. **Video / TTS / Lip Sync 版本化。** 历史结果不覆盖。
6. **源对白与目标对白分离。** 翻译/本土化必须在 Shot Spec 和 TTS 之前正式确认。
7. **Source Timeline 是母时间轴。** 业务权威时间使用 integer microseconds。
8. **模型/Provider 可替换。** 业务层不绑定具体供应商。
9. **SQLite 与媒体文件写入必须可恢复。**
10. **计费异步 Provider 必须防重复提交/重复扣费。**
11. **代码和数据库必须有简体中文业务注释。**
12. **Stable Feature 必须有回归测试保护。**
13. **第一版不做 SaaS/集群/微服务重架构。**

## 新对话最短恢复路径

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ 当前 docs/features/FXX-*.md
→ 最新相关 docs/sessions/*.md
→ 再按当前 Feature 的 Rule References 阅读必要详细规则
```

不要要求用户重新从头解释已经写进仓库的项目背景。

## 文档入口

### 必读入口

- [`AGENTS.md`](./AGENTS.md) — Agent 进入项目的最短规则
- [`SKILL.md`](./SKILL.md) — 项目级开发技能手册 / 最高层规则
- [`docs/PROJECT_STATE.md`](./docs/PROJECT_STATE.md) — 当前真实开发状态
- [`docs/FEATURE_SEQUENCE.md`](./docs/FEATURE_SEQUENCE.md) — 35 个 Approved Production Features

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

### Feature 开发模板

- [`templates/FEATURE_SPEC_TEMPLATE.md`](./templates/FEATURE_SPEC_TEMPLATE.md)
- [`templates/P0_FEATURE_CHECKLIST.md`](./templates/P0_FEATURE_CHECKLIST.md)
- [`templates/FEATURE_IMPLEMENTATION_LOG_TEMPLATE.md`](./templates/FEATURE_IMPLEMENTATION_LOG_TEMPLATE.md)
- [`templates/SESSION_HANDOFF_TEMPLATE.md`](./templates/SESSION_HANDOFF_TEMPLATE.md)

## 当前开发入口

业务代码尚未正式开始。

下一步：

> **Feature 01 — 创建项目 Contract**
