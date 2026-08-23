---
name: ai-drama-studio-development
version: 2.0.0
description: AI Drama Studio 本地自用 AI 短剧重制工作台的项目级开发技能手册。以真实生产流程、逐 Feature 开发、人工验收、Contract 冻结、跨对话续开发和工程安全为核心。
---

# AI Drama Studio Development Skill

> 本文件是项目最高层开发规则与执行索引。
>
> 详细 Feature 顺序、P0 工程规则、技术栈、数据库/注释规范等放在 `docs/` 中；本文件负责定义“必须遵守什么、文档冲突时听谁的、开发如何推进”。

---

# 1. 项目定位

AI Drama Studio 是一个：

> **Windows 本地自用、单用户的 AI 短剧重制生产工作台。**

目标：把一部已有短剧经过自动分析 + 人工校正，转换为可编辑、可追踪、可版本化的结构化生产工程，并完成：

```text
原片分析
→ 人物/对白/场景结构化
→ 本土选角
→ Character / Scene Bible
→ 目标语言翻译与本土化
→ Shot Specification
→ AI 视频重生成
→ 自动 QC + 人工失败镜头处理
→ TTS / Lip Sync
→ 最终音频 / 字幕
→ 整集合成 / QC / 导出
```

它不是：

- SaaS 多租户平台；
- 通用 AIGC 商城；
- Premiere / DaVinci 完整替代品；
- 视频基础模型训练平台；
- 高并发云服务。

第一版优先级：

> **完整跑通真实生产流程 > 自动化程度 > 性能 > 架构复杂度。**

---

# 2. main 是唯一正式 Source of Truth

正式确认的项目规则、Stable Feature、代码和文档最终必须进入 `main`。

分支 / PR 代表：

```text
正在开发 / 等待审核 / 尚未成为正式基线
```

因此：

- 新对话默认从 `main` 恢复项目；
- 不允许把长期真实状态只留在某个临时分支；
- Feature 完成并经用户验收后，应通过 PR 合并进入 `main`；
- `docs/PROJECT_STATE.md` 在 `main` 上必须始终代表最近一次已确认状态。

---

# 3. 文档权威优先级

如果仓库文档发生冲突，按以下顺序处理：

```text
1. 用户最新明确确认并已经写入仓库的决策
2. 已 STABLE / FROZEN Feature 的 Contract Snapshot
3. 本文件 SKILL.md + 适用的 P0 / 全局规则
4. 当前 Feature Contract
5. docs/PROJECT_STATE.md
6. 最新 Session Handoff
7. 历史 Session / 旧讨论
```

## 3.1 Stable Contract 不能被下游静默覆盖

如果当前 Feature 确实必须改变已 Frozen Contract：

```text
提出 Change Request
→ 说明原因
→ 影响分析
→ 数据/API/文件迁移方案
→ 用户明确确认
→ V2 Contract / Migration
→ 回归测试
```

禁止直接改同名字段语义、删除旧字段或让下游绕过旧 Contract。

---

# 4. 只有用户可以最终确认 STABLE / FROZEN

Feature 状态建议统一：

```text
PLANNED
IN_PROGRESS
TESTING
READY_FOR_REVIEW
STABLE
FROZEN
```

AI / Codex / 开发代理可以：

- 实现；
- 自动测试；
- 真实素材测试；
- 修复；
- 写文档；
- 把 Feature 标记为 `READY_FOR_REVIEW`。

但：

> **只有用户明确确认“验收通过”，才允许进入 `STABLE / FROZEN`。**

未得到用户验收：

- 不得自己宣布 Stable；
- 不得擅自开始依赖它的下一个 Feature；
- 不得把当前 Contract 当成最终冻结事实。

---

# 5. 最高优先级开发模式：逐 Feature 纵向开发

禁止：

```text
先一起开发
拉片 + 人物 + 对白 + Scene + Bible + Generation
→ 最后统一测试
→ 上游出问题
→ 全部返工
```

必须：

```text
当前 Feature Contract
→ 编码
→ 单功能测试
→ 回归测试
→ 真实素材测试
→ 文档更新
→ READY_FOR_REVIEW
→ 用户验收
→ Freeze
→ 下一 Feature
```

一次只正式推进一个业务 Feature。

完整顺序见：

- `docs/FEATURE_SEQUENCE.md`

当前批准版本共 **35 个 Feature**。

---

# 6. Approved Production Flow

业务流程固定为：

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

任何 Agent 不得为了保持旧“30 Feature”编号而把新增业务步骤偷偷塞进其它 Feature。

---

# 7. 翻译 / 本土化是正式生产步骤

源对白和目标对白必须是两个不同的业务对象/状态。

推荐概念：

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

1. ASR 只负责源语言内容；
2. 人工先确认 Final Source Dialogue；
3. AI 再进行目标语言翻译/本土化；
4. AI Draft 必须人工确认；
5. Shot Spec、TTS、字幕正式读取 `Approved Target Dialogue`；
6. 不能等到 TTS 阶段才第一次处理翻译。

本土化目标：

- 保留剧情事实；
- 符合角色身份/关系；
- 目标语言自然；
- 避免机械逐字翻译；
- 可根据目标市场调整表达，但不得未经确认改写核心剧情。

---

# 8. 目标对白必须在 Shot Spec 前做时长约束

不同语言长度不同。

因此视频生成前必须知道：

```text
available_duration_us
estimated_speech_duration_us
recommended_rate
pass / review
```

如果目标对白明显过长：

> 优先回 Feature 19 缩短/改写，而不是先生成视频，再在 TTS 阶段强行加速。

最终正式 TTS 后仍由 Dialogue Fit 做真实时长适配。

---

# 9. AI 本土选角必须有 Casting Profile

AI Casting 不能直接做“图片相似度排行榜”。

Feature 14 必须先形成结构化/可解释的 `Casting Profile`，至少考虑：

- 角色定位；
- 年龄表现；
- 外形；
- 气质；
- 性格；
- 情绪范围；
- 动作/表演需求；
- 人物关系；
- 原角色视觉；
- 源对白与剧情上下文。

再基于 Actor Library 产生候选与理由。

最终 Actor 仍由用户人工选择。

---

# 10. 最终音频与字幕必须有独立产物

## 10.1 Final Audio Mix

最终视频不能只有 TTS 人声。

V1 可以组合：

- TTS Dialogue；
- 原片分离/导入的环境音；
- SFX；
- BGM；
- 视频模型原生音频；
- 人工导入素材。

Feature 31 负责对齐、选择、混合和基本音量/峰值处理。

V1 不要求自研 AI SFX/BGM 模型。

## 10.2 Subtitle Track

目标语言字幕必须根据最终生产时间轴重新组装。

不能简单把源 ASR 时间直接当最终字幕时间。

正式输出至少支持：

```text
SRT
VTT
```

---

# 11. 每个 Feature 开发前必须建立 Contract

使用：

- `templates/FEATURE_SPEC_TEMPLATE.md`
- `templates/P0_FEATURE_CHECKLIST.md`

至少定义：

1. Feature 目标；
2. 明确不做什么；
3. 前置 Stable Feature；
4. 用户操作流程；
5. Input Contract；
6. Output Contract；
7. 读取的数据；
8. 允许修改的数据；
9. 禁止修改的数据；
10. DB / Migration；
11. 文件输入输出；
12. API；
13. 模型 / Provider；
14. P0 适用性；
15. 异常和恢复；
16. 当前 Feature 测试；
17. 受影响 Stable Feature 回归测试；
18. 真实素材验收；
19. 中文代码/数据库注释；
20. Definition of Done；
21. Freeze Snapshot。

没有 Contract，不开始编码。

---

# 12. P0 工程规则

5 个 P0 规则全部仍然强制，但不再要求单独读取第二本 Skill。

索引：

- `docs/P0_RULES_INDEX.md`

详细规则：

1. `docs/DEPENDENCY_AND_INVALIDATION_RULES.md`
2. `docs/MEDIA_TIMEBASE_CONTRACT.md`
3. `docs/ENVIRONMENT_BASELINE.md`
4. `docs/DATA_RECOVERY_AND_MIGRATION_RULES.md`
5. `docs/PROVIDER_JOB_RULES.md`

每个 Feature 必须填写：

- `templates/P0_FEATURE_CHECKLIST.md`

适用项未 PASS，不得进入 Stable。

---

# 13. Revision / Dependency / Stale

重要 Final/Locked/Approved 对象发生语义变化时，需要 revision。

派生结果必须能回答：

> 我基于哪个上游版本产生？

例如 Generation 应保存：

```text
shot_revision
shot_spec_revision
character_bible_revision
scene_bible_revision
target_dialogue_revision
reference asset ids/hashes
provider/model/version
prompt compiler version
```

上游语义变化后：

```text
旧结果保留
→ 标记 stale
→ 显示 stale_reason
→ 不再静默作为正式 Final 输入
```

`stale` ≠ `failed` ≠ `invalid`。

详细规则见 Dependency/Invalidation 文档。

---

# 14. AI Result 与人工 Final 必须分离

只要 AI 结果可以被人工修正，就不能直接被人工覆盖。

例如：

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

目的：

- 可追溯；
- 可回退；
- 可比较 AI 与人工；
- 可重新计算；
- 可积累优化数据。

---

# 15. Shot 是核心生产单元

单 Shot 必须能够独立：

- 播放；
- 修边界；
- 重跑人物分析；
- 修改 Dialogue；
- 修改 Scene；
- 修改 Shot Spec；
- 更换 Reference；
- 更换 Provider / Model；
- 重新生成；
- QC；
- TTS；
- Lip Sync；
- 上传人工替换；
- 选择最终版本。

一个 Shot 出错，不能要求整集重跑。

---

# 16. Generation / TTS / Lip Sync 必须版本化

禁止覆盖历史结果。

Generation 例如：

```text
SHOT_023
├ V001
├ V002
├ V003
└ V004
```

保存 `selected_generation_id`。

每个版本至少可追溯：

- provider/model；
- provider task id；
- prompt；
- references；
- upstream revisions；
- output path；
- cost；
- QC；
- created_at。

Character Bible、Scene Bible、Shot Spec 在对应 Feature 实现时也应设计可恢复的 Revision Snapshot，而不只是一个会被覆盖的 `revision` 数字。

---

# 17. 模型与供应商必须可替换

业务层禁止写：

```python
generate_with_xxx()
```

应通过统一能力接口：

```python
video_generation.generate(request)
```

Provider Adapter 负责映射供应商字段、状态和错误。

业务层认识：

- Bible；
- Shot Spec；
- Generation Request/Result；
- QC Result；
- TTS Request/Result；
- LipSync Request/Result。

不认识供应商私有状态。

---

# 18. Prompt Compiler 与 Shot Specification 分离

Shot Spec 是模型无关的镜头需求。

```text
Shot Specification
       ↓
Prompt Compiler
       ├ Provider/Model A
       ├ Provider/Model B
       └ Provider/Model C
```

模型 A 的特殊 Prompt/参数不得污染 Shot Spec Schema。

---

# 19. Media Timebase

唯一业务母时间轴：

```text
Source Timeline
```

业务权威时间默认：

```text
integer microseconds (µs)
```

如：

```text
start_us
end_us
duration_us
```

不得把 float 秒作为唯一权威持久化值。

必须考虑：

- rational FPS；
- VFR；
- PTS/time_base；
- Proxy offset；
- Audio offset；
- Source↔Proxy 映射。

详细规则见 `docs/MEDIA_TIMEBASE_CONTRACT.md`。

---

# 20. Project Format Version

Feature 01 从第一版必须保存：

```text
project_format_version
```

它与 Alembic schema revision 不同。

用于表示：

- Workspace 目录格式；
- Project metadata 格式；
- JSON/Bible/Asset 等项目级持久化格式。

建议项目元信息最终至少包含：

```text
project_format_version
app_version
schema_revision
created_at
```

未来应用打开旧项目时，可根据 Project Format 执行兼容/迁移判断。

---

# 21. DB + 文件写入必须可恢复

SQLite 与文件系统不能共享 ACID transaction。

重要媒体默认：

```text
DB pending/writing
→ 写 staging/tmp
→ close/flush
→ 文件/FFprobe 校验
→ atomic rename
→ DB completed
```

禁止 DB 先标记完成、再慢慢写文件。

Migration 前必须有安全备份。

Source Video 原则上只读。

详细规则见 `docs/DATA_RECOVERY_AND_MIGRATION_RULES.md`。

---

# 22. Provider Job 必须防重复付费

对计费/异步 Provider：

调用前先创建本地 Job，并记录：

```text
local_job_id
request_id
request_fingerprint
attempt
```

一旦拿到 `provider_task_id`，立即持久化。

HTTP timeout 只能表示：

```text
UNKNOWN
```

不能直接视为远端没收到请求。

应用重启后应 resume poll/query，而不是重新提交付费任务。

详细规则见 `docs/PROVIDER_JOB_RULES.md`。

---

# 23. 环境必须可复现

禁止依赖模糊的 `latest`。

必须逐步锁定/记录：

- Python exact version；
- Node / package manager；
- Python lock；
- frontend lock；
- PyTorch/CUDA；
- FFmpeg build；
- 本地模型来源/version/hash；
- Provider model id/API version。

开发硬件基线：

```text
NVIDIA RTX 4060 Ti 16GB
GPU concurrency = 1
```

模型按需 load/run/unload。

详细规则见 `docs/ENVIRONMENT_BASELINE.md`。

---

# 24. 代码和数据库必须可理解

所有新增/修改的业务代码、表、字段、Migration、API Schema、复杂算法、Provider Adapter 都必须有足够的**简体中文业务说明**。

注释要解释：

- 这个东西做什么；
- 为什么存在；
- 谁写；
- 谁读；
- 哪些字段不能随意改；
- 失败/为空会影响什么。

禁止机械注释：

```python
# 项目ID
project_id
```

数据库 Feature 文档必须维护 `Database Dictionary`。

详细规则：

- `docs/CODE_AND_DATABASE_COMMENT_RULES.md`

---

# 25. 回归测试是 Stable Contract 的保护层

每个 Stable Feature 必须逐步形成可重复的回归测试。

测试结构推荐：

```text
tests/
├ unit/
├ integration/
├ regression/
└ fixtures/
```

固定 Fixture 应优先使用短小、可复现素材，例如：

```text
hardcut_10s.mp4
short_dialogue.mp4
vfr_sample.mp4
no_audio.mp4
ntsc_30000_1001.mp4
```

后续 Feature 如果修改共享层：

```text
Current Feature Tests
+
Affected Stable Feature Regression Tests
```

必须全部通过后才能 `READY_FOR_REVIEW`。

详细规则见：

- `docs/TESTING_AND_REGRESSION_RULES.md`

---

# 26. 文档是代码交付的一部分

每次实际开发结束至少更新：

1. 当前 `docs/features/FXX-*.md`；
2. `docs/PROJECT_STATE.md`；
3. 新建一份 `docs/sessions/YYYY-MM-DD_HHMM_FXX_topic.md`。

代码已提交但文档没更新：

> 视为开发未完成。

目的：新的聊天窗口不依赖旧对话，也能恢复项目。

---

# 27. 新对话恢复路径

为了控制上下文长度，新 Agent 不需要一开始读取所有规则全文。

最短强制路径：

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ 当前 Feature 文档
→ 最新相关 Session Handoff
```

然后根据当前 Feature 文档中的 P0 / Rule References，再读取需要的详细规范。

不要一开始无差别读取整个 `docs/`。

---

# 28. 技术栈

## Frontend

```text
Vue 3
TypeScript
Vite
Pinia
```

## Backend / AI Engine

```text
Python 3.11
FastAPI
PyTorch
CUDA
OpenCV
FFmpeg / FFprobe
```

## Data

```text
SQLite
SQLAlchemy
Alembic
Local Filesystem
```

## Desktop

```text
Electron（后置）
```

开发阶段先：

```text
Vue localhost
+
FastAPI localhost
```

核心流程稳定以后才封装 Electron。

---

# 29. 本地模型 / API 分工

本地优先：

- FFmpeg / FFprobe；
- OpenCV；
- Shot Detection；
- Scene Embedding；
- Face Detection / Tracking / Embedding；
- Whisper / WhisperX；
- Speaker Diarization；
- Technical QC；
- Basic consistency QC；
- Final Render。

API 优先：

- 强 VLM；
- Bible 语义分析；
- Translation/Localization 辅助；
- Shot Understanding；
- Video Generation；
- Premium TTS；
- Premium Lip Sync；
- Semantic QC。

第一版不投入时间训练基础 Video/VLM/ASR/TTS 模型。

---

# 30. 第一版禁止过度设计

没有真实需求前，不引入：

- Kubernetes；
- Redis Cluster；
- PostgreSQL Cluster；
- GPU Cluster；
- 多租户；
- 在线 Billing；
- 复杂 RBAC；
- 微服务拆分；
- 大型分布式消息队列。

本地单用户先把完整闭环做正确。

---

# 31. Git / PR 规则

正式业务开发建议：

```text
main = 最近一次用户确认的稳定基线

feature/F01-create-project
feature/F02-upload-source
...
```

一个 Feature 尽量对应：

```text
一份 Contract
+ 一批代码
+ 一批测试
+ Feature 文档
+ Session Handoff
+ 一个 PR
```

用户验收通过后再合入 `main`。

---

# 32. Feature Stable Gate

Feature 进入 Stable 前必须全部满足：

```text
[ ] Scope 明确
[ ] Input / Output / API / DB Contract 完成
[ ] P0 Checklist 完成
[ ] 功能实现完成
[ ] 错误/恢复完成
[ ] 中文代码注释完成
[ ] Database Dictionary 完成
[ ] 当前 Feature 自动测试通过
[ ] 受影响 Stable Feature 回归测试通过
[ ] 真实素材测试完成
[ ] Feature 文档更新
[ ] Session Handoff 创建
[ ] PROJECT_STATE 更新
[ ] AI/Agent 状态为 READY_FOR_REVIEW
[ ] 用户明确验收通过
[ ] Freeze Snapshot 完成
```

缺任何一项：

> 不进入 STABLE/FROZEN，不开始下一依赖 Feature。

---

# 33. 当前开发入口

当前业务代码尚未正式开始。

正式下一步：

> **Feature 01 — 创建项目**

开发前必须先建立：

```text
docs/features/F01-create-project.md
```

并冻结：

- Project ID；
- `project_format_version`；
- Workspace 规则；
- SQLite 布局；
- Project DB/应用级 DB 决策；
- 表与字段字典；
- API；
- P0 Checklist；
- 测试与回归规则；
- Freeze 项。
