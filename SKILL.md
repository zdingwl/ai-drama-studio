---
name: ai-drama-studio-development
version: 2.1.0
description: AI Drama Studio 本地 AI 短剧重制工作台的项目级开发技能手册。定义 Source of Truth、35 Feature 生产流程、逐 Feature 验收冻结、P0 工程规则和跨对话续开发方式。
---

# AI Drama Studio Development Skill

> 本文件是项目最高层开发规则与规则索引。
>
> 详细实现规范放在 `docs/` 中；不要把所有详细规则重复写回本文件。

## 1. 项目定位

AI Drama Studio 是 **Windows 本地自用、单用户的 AI 短剧重制生产工作台**。

目标：

```text
原片分析
→ 人物 / 对白 / Scene 结构化
→ 本土选角
→ Character / Scene Bible
→ 目标语言翻译与本土化
→ Shot Specification
→ AI 视频重生成
→ 自动 QC / 人工失败镜头处理
→ TTS / Lip Sync
→ 最终音频 / 字幕
→ 合成 / QC / 导出
```

第一版优先级：

```text
真实生产流程完整可用
> 可测试、可人工修正、可恢复
> 自动化程度
> 性能
> 架构复杂度
```

第一版不做 SaaS、多租户、GPU 集群、Kubernetes、复杂微服务、在线计费等重架构。

---

## 2. main 是唯一正式 Source of Truth

正式确认的规则、Stable Feature、代码和文档最终必须进入 `main`。

```text
main = 最近一次用户已经确认的正式项目基线
branch / PR = 开发中或待审核状态
```

新对话默认从 `main` 恢复，除非用户明确指定继续某个未合并分支/PR。

`docs/PROJECT_STATE.md` 在 `main` 上必须代表最近一次真实状态。

---

## 3. 文档冲突优先级

```text
1. 用户最新明确确认并写入仓库的决策
2. 已 STABLE/FROZEN Feature Contract Snapshot
3. SKILL.md + 适用全局/P0 Contract
4. 当前 Feature Contract
5. docs/PROJECT_STATE.md
6. 最新 Session Handoff
7. 历史 Session / 旧讨论
```

发现冲突必须显式报告，禁止静默选择。

如需改变 Frozen Contract：

```text
Change Request
→ 影响分析
→ Migration / V2 方案
→ 用户确认
→ 实施
→ Regression
```

---

## 4. 只有用户能最终确认 STABLE/FROZEN

统一状态：

```text
PLANNED
IN_PROGRESS
TESTING
READY_FOR_REVIEW
STABLE
FROZEN
```

AI / Codex / Agent 最多自行推进到：

```text
READY_FOR_REVIEW
```

只有用户明确确认“验收通过”后才能：

```text
STABLE / FROZEN
```

未验收不得擅自开发下一依赖 Feature。

---

## 5. 必须逐 Feature 纵向开发

禁止按“大模块”一起开发后统一测试。

必须：

```text
当前 Feature Contract
→ 编码
→ 当前 Feature Test
→ Affected Stable Regression
→ 真实素材测试
→ 文档更新
→ READY_FOR_REVIEW
→ 用户人工验收
→ Freeze
→ 下一 Feature
```

一次只正式推进一个业务 Feature。

完整说明：`docs/FEATURE_SEQUENCE.md`。

---

## 6. Approved Production Flow — 35 Features

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

正式业务代码开始后，此顺序默认冻结；任何改序必须经过用户确认和影响分析。

---

## 7. 翻译 / 本土化是正式独立生产链

必须区分：

```text
Source Dialogue
├ asr_text
└ final_source_text

Target Dialogue
├ literal_translation（可选）
├ localized_draft
└ approved_target_text
```

规则：

1. ASR 只负责源语言；
2. 人工先确认 Final Source Dialogue；
3. AI 再翻译/本土化；
4. AI Draft 必须人工确认；
5. Shot Spec、TTS、字幕读取 Approved Target Dialogue；
6. 不允许等到 TTS 阶段才第一次翻译。

目标对白生成时必须保留剧情事实，并结合角色身份、关系、场景和目标市场自然表达。

---

## 8. 目标对白在 Shot Spec 前必须做时长约束

Feature 20 至少形成：

```text
available_duration_us
estimated_speech_duration_us
recommended_rate
status = pass / review
```

明显过长时优先回 Feature 19 改写，而不是视频生成后再强行高速 TTS。

正式 TTS 后仍由 Dialogue Fit 做真实时长适配。

---

## 9. AI 本土选角必须先形成 Casting Profile

Feature 14 不能只是视觉相似度排序。

Casting Profile 至少包含：

- 角色定位；
- 年龄表现；
- 外形/气质；
- 性格；
- 情绪范围；
- 动作/表演需求；
- 角色关系；
- 原角色视觉；
- 源对白/剧情上下文。

然后再对 Actor Library 做候选 Ranking。

最终 Actor 必须人工选择。

---

## 10. Final Audio 与 Subtitle 是独立产物

### Final Audio Mix

V1 可组合：

- Final TTS Dialogue；
- 原片分离/导入环境音；
- SFX；
- BGM；
- 视频模型原生音频；
- 人工导入音频。

Feature 31 负责对齐、混合、基本音量/峰值处理，不要求 V1 自研 AI SFX/BGM 模型。

### Subtitle Track

Feature 32 读取 Approved Target Dialogue + Final Production Timeline。

最终字幕不能直接复制 Source ASR 时间。

---

## 11. 每个 Feature 开发前必须有 Contract

使用：

- `templates/FEATURE_SPEC_TEMPLATE.md`
- `templates/P0_FEATURE_CHECKLIST.md`

必须定义：

- Scope / Not In Scope；
- 前置 Stable Feature；
- User Flow；
- Input/Output；
- Reads/Writes/Must NOT Modify；
- Revision/Dependency/Stale；
- DB/Migration + Database Dictionary；
- File/Workspace；
- Project Format 影响；
- Media Timebase；
- API/Task；
- Model/Provider；
- Environment；
- Error/Recovery；
- Current Tests；
- Regression Scope；
- Real Sample Test；
- Comment Review；
- Freeze Snapshot。

没有 Contract，不编码。

---

## 12. P0 工程规则

5 个 P0 全部强制：

1. Dependency / Revision / Invalidation
2. Media Timebase
3. Environment Baseline
4. DB + File Recovery / Migration
5. Provider Job Safety

索引：`docs/P0_RULES_INDEX.md`。

详细：

- `docs/DEPENDENCY_AND_INVALIDATION_RULES.md`
- `docs/MEDIA_TIMEBASE_CONTRACT.md`
- `docs/ENVIRONMENT_BASELINE.md`
- `docs/DATA_RECOVERY_AND_MIGRATION_RULES.md`
- `docs/PROVIDER_JOB_RULES.md`

不再使用第二本 `SKILL_P0.md`。

---

## 13. 双时间域：Source / Production

不能把重制成片强行绑定到原片全局时间。

### Source Timeline

用于原片证据：

- Source / Proxy / Extracted Audio；
- Source Shot；
- Character Tracks；
- ASR Source Dialogue；
- Speaker；
- Source Scene Evidence。

### Production Timeline

用于最终重制：

- Approved Shot Spec duration；
- Generated/Selected Shot；
- Final Voice；
- Lip Sync；
- Final Audio；
- Subtitle；
- Render。

中间步骤优先使用 Shot-local time，再由 Timeline Builder 计算 Production 全局 offset。

统一权威单位：

```text
integer microseconds (µs)
```

详细：`docs/MEDIA_TIMEBASE_CONTRACT.md`。

---

## 14. Revision / Dependency / Stale

派生结果必须能回答：

> 我基于哪些上游版本产生？

例如 Generation 应可追溯：

```text
shot_revision
shot_spec_revision
character_bible_revision
scene_bible_revision
target_dialogue_revision
timing_constraint_revision
reference ids/hashes
provider/model/version
prompt compiler version
```

上游语义变化后：

```text
旧结果保留
→ stale
→ 显示原因
→ 不再静默作为正式输入
```

`stale` ≠ `failed` ≠ `invalid`。

---

## 15. AI Result 与 Human Final 分离

示例：

```text
Shot:
detected_start_us / detected_end_us
final_start_us / final_end_us

Dialogue:
asr_text
final_source_text
localized_draft
approved_target_text

QC:
ai_qc_status / ai_qc_scores
human_decision / human_reason
```

禁止人工修改覆盖原始 AI 证据。

---

## 16. Shot 是核心生产单元

一个 Shot 必须可独立：

- 修边界；
- 重跑分析；
- 改 Dialogue/Scene/Spec；
- 更换 Reference/Provider/Model；
- Generate / QC；
- TTS / Lip Sync；
- 手工替换；
- 选择 Final。

一个 Shot 出错不能要求整集重跑。

---

## 17. Version / Revision 必须保留历史

必须版本化：

- Video Generation；
- TTS；
- Lip Sync。

Character Bible、Scene Bible、Target Dialogue、Shot Spec 在对应 Feature 实现时也应保存可恢复 Revision Snapshot，而不是只保存一个会被覆盖的当前值。

---

## 18. Provider / Model 可替换

业务层使用统一能力 Contract，不直接绑定供应商。

```text
Business Service
→ Provider Adapter
→ Provider-specific API
```

Shot Spec 是模型无关数据；模型专属 Prompt/参数由 Prompt Compiler / Adapter 生成。

---

## 19. Project Format Version

F01 从第一版保存：

```text
project_format_version
```

用于识别 Workspace、项目 metadata、持久化 JSON/Bible/Asset 格式版本。

它不同于 Alembic `schema_revision`。

项目元数据至少应可追溯：

```text
project_format_version
app_version
schema_revision
created_at
```

---

## 20. DB + 文件必须可恢复

SQLite 与媒体文件不是同一个事务。

重要文件默认：

```text
DB pending/writing
→ staging/tmp
→ close/validate
→ atomic rename
→ DB completed
```

Migration 前必须有安全备份。

Source Video 默认只读。

详细：`docs/DATA_RECOVERY_AND_MIGRATION_RULES.md`。

---

## 21. Provider Job 必须防重复付费

计费异步 Provider：

```text
先创建 local job
→ request_id/fingerprint
→ submit
→ provider_task_id 立即持久化
→ poll/resume
```

HTTP timeout 只能表示 `UNKNOWN`，不能直接自动重新提交付费任务。

详细：`docs/PROVIDER_JOB_RULES.md`。

---

## 22. 环境必须可复现

禁止依赖未约束 `latest`。

逐步锁定：

- Python / Node / package manager；
- Python/frontend lock；
- PyTorch/CUDA；
- FFmpeg；
- 本地模型 source/version/hash；
- Provider model/API version。

开发硬件基线：RTX 4060 Ti 16GB，GPU 默认 concurrency = 1。

详细：`docs/ENVIRONMENT_BASELINE.md`。

---

## 23. 代码与数据库必须有中文业务注释

新增/修改的：

- 核心业务代码；
- 表/字段；
- Migration；
- API Schema；
- Provider Adapter；
- 复杂算法；

必须有足够简体中文说明，重点解释业务意义、边界和“为什么”。

数据库 Feature 文档必须维护 Database Dictionary。

详细：`docs/CODE_AND_DATABASE_COMMENT_RULES.md`。

---

## 24. Stable Feature 必须有 Regression 保护

推荐：

```text
tests/
├ unit/
├ integration/
├ regression/
└ fixtures/
```

后续修改共享代码时必须运行：

```text
Current Feature Tests
+ Affected Stable Feature Regression
```

详细：`docs/TESTING_AND_REGRESSION_RULES.md`。

---

## 25. 文档是代码交付的一部分

每次实际开发结束至少更新：

1. 当前 `docs/features/FXX-*.md`；
2. `docs/PROJECT_STATE.md`；
3. 新建 `docs/sessions/YYYY-MM-DD_HHMM_FXX_topic.md`。

代码完成但文档没更新 = 开发未完成。

---

## 26. 新对话最短恢复路径

为了防止上下文超限：

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ 当前 Feature 文档
→ 最新相关 Session
→ 再按 Rule References / P0 Checklist 读取必要详细规范
```

不要一开始无差别读取整个 `docs/`。

---

## 27. 技术栈

```text
Frontend: Vue 3 + TypeScript + Vite + Pinia
Backend: Python 3.11 + FastAPI + PyTorch + CUDA
Media: FFmpeg / FFprobe + OpenCV
Data: SQLite + SQLAlchemy + Alembic + Local Filesystem
Desktop: Electron（核心流程稳定后）
```

本地优先：媒体处理、Shot/Scene/Face/ASR/Speaker、基础 QC、Render。

API 优先：强 VLM、Localization 辅助、Video Generation、Premium TTS/LipSync、Semantic QC。

---

## 28. Git / PR

正式业务开发建议：

```text
main = 用户已确认稳定基线
feature/F01-create-project
feature/F02-upload-source
...
```

一个 Feature 尽量对应：

```text
Contract + Code + Tests + Feature Doc + Session Handoff + PR
```

用户验收后再合入 `main`。

---

## 29. Stable Gate

```text
[ ] Scope / Contract 完成
[ ] P0 Checklist 完成
[ ] 实现与错误恢复完成
[ ] 中文代码/数据库注释完成
[ ] Current Feature Tests 通过
[ ] Affected Stable Regression 通过/N/A
[ ] 真实素材测试完成
[ ] Feature Doc 更新
[ ] Session Handoff 创建
[ ] PROJECT_STATE 更新
[ ] Agent 状态 READY_FOR_REVIEW
[ ] 用户明确验收通过
[ ] Freeze Snapshot 完成
```

缺任何适用项，不进入 STABLE/FROZEN。

---

## 30. 当前唯一开发入口

业务代码尚未正式开始。

下一步：

> **Feature 01 — 创建项目 Contract**

必须先建立：

```text
docs/features/F01-create-project.md
```

并在 Contract 中确定：Project ID、`project_format_version`、Workspace、SQLite 布局、表/字段字典、API、P0、测试、Regression 和用户验收步骤，然后才能编码。
