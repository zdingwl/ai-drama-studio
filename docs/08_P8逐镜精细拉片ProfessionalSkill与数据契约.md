# P8 逐镜精细拉片 Professional Skill 与数据契约

> 阶段：P8 implementation baseline  
> 日期：2026-09-09  
> 前置基线：P5 / P6 / P7 已通过真实人工验收  
> P7 冻结契约：`source-video-understanding@1.1.0` / `p7-source-bible-v2` / `SOURCE_BIBLE schema 1.1` / `grounded-source-truth-v2`

---

# 1. P8 解决什么问题

P8 负责：

> **在整集 Source Bible 已建立后，把完整 Episode 的视觉与声音事实，精确绑定回 P5 Shot Anchors，形成可追溯、可版本化的逐镜精细拉片。**

P8 不重新做整集剧情理解，也不进入人物 / 场景 / 道具最终身份归一。

正式 Professional Skill：

```text
skills/professional/shot-breakdown/SKILL.md
skills/professional/shot-breakdown/manifest.json
shot-breakdown@1.0.0
```

正式输出 Artifact：

```text
SOURCE_SHOT_FACTS
```

`SHOT_BREAKDOWN` 在真实短剧人工验收通过前继续保持 `PLANNED`。

---

# 2. 硬输入与权威顺序

P8 固定输入：

```text
完整 Episode / CURRENT SOURCE_VIDEO
+
CURRENT SOURCE_BIBLE
+
CURRENT SHOT_ANCHORS
+
CURRENT P6 canonical Source Evidence（对白 / OCR 绑定时读取）
```

权威边界：

```text
完整 Episode
= Source Truth
= 镜头视觉、表演、声音现场的最高层原片事实源

CURRENT SHOT_ANCHORS
= Shot start / end / duration 的权威时间边界

CURRENT P6 canonical Source Evidence
= 对白正文与 OCR 正文的权威文字事实源

CURRENT SOURCE_BIBLE
= 人物、关系、故事、场景、道具、Story / Rhythm 的全局语义知识

Reference Clip
= P5 派生局部精看资产
= 不能替代完整 Episode
```

严禁：

```text
Shot 1 独立猜整集故事
Shot 2 独立猜整集故事
...
→ 再把多个猜测拼成剧情
```

P8 Provider 必须按 **完整 Episode + 整集 Source Bible + 全部 Shot Anchors** 做一次 Episode 级逐镜分析，而不是把 Provider 调用粒度降成单 Shot 故事理解。

---

# 3. 与 P5 / P6 / P7 / P9 的职责分界

## 3.1 P5 → P8

P5 已确定：

- Shot 顺序；
- `start_us`；
- `end_us`；
- `duration_us`；
- thumbnail；
- Reference Clip。

P8 **不得让模型重新生成或微调 Shot Boundary**。Provider 只返回 `shot_number` 与逐镜语义，服务端再和 CURRENT P5 Anchor 做权威绑定。

## 3.2 P6 → P8

P6 已确定：

- canonical `SourceDialogueUtterance`；
- canonical OCR span；
- 原始时间戳与 provenance。

P8 的 dialogue Shot binding 规则：

```text
CURRENT P6 utterance time
∩
CURRENT P5 Shot Anchor time
↓
服务端计算 overlap
↓
P8 只允许补充 delivery 类型
↓
正文仍逐字复制 CURRENT P6 canonical text
```

因此 P8 Provider Schema **没有 dialogue text 输出字段**，从结构上阻断重新听写 / 润色 canonical 对白。

P6 历史 `ShotDialogueProjection` 只代表 P6 运行当时的可选 Shot hint。P8 必须以 **CURRENT** P5 Anchors 重新做纯时间 overlap，避免 P5 后续重建后消费旧 projection。

## 3.3 P7 → P8

P7 提供整集全局知识：

- 故事概述与背景；
- timed script；
- 人物候选与关系；
- 场景候选；
- 关键道具候选；
- Story Events；
- Story Skeleton；
- Rhythm Skeleton。

P8 可以把某 Shot 绑定到已有 P7 candidate ID，但不能创建新的“最终人物身份”。

## 3.4 P8 ≠ P9

P8 只做：

```text
Shot ↔ P7 Character candidate
Shot ↔ P7 Scene candidate
Shot ↔ P7 Prop candidate
```

P8 不做：

- Speaker → Character 最终归一；
- 跨 Shot 人脸 / 角色身份 resolution；
- 场景最终归一；
- 道具最终归一；
- `SOURCE_CHARACTERS` / `SOURCE_SCENES` / `SOURCE_PROPS`；
- SourceVideoSnapshot。

以上属于后续阶段，P8 实现不得提前进入。

---

# 4. Professional Skill 执行形态

P8 Professional Skill 分三步：

```text
1. establish_shot_context
   校验 CURRENT SOURCE_VIDEO / SOURCE_BIBLE / SHOT_ANCHORS / P6 Evidence

2. full_episode_shot_analysis
   Provider 读取完整 Episode，一次返回该 Episode 全部 Shot 的精细语义

3. canonical_bind_and_publish
   服务端注入 P5 时间、P6 canonical 正文、P7 candidate label，严格校验后发布 SOURCE_SHOT_FACTS
```

Provider 的职责：

- visual description；
- 景别；
- 构图；
- 镜头类型 / 角度；
- 运镜；
- 焦距 / 景深描述；
- P7 candidate ID 绑定；
- 对已由服务端确定 overlap 的 canonical utterance 标记 delivery；
- 音效；
- 环境声。

Provider 无权：

- 改 Shot 时间；
- 改 canonical dialogue / OCR；
- 重新解释整集故事替代 SOURCE_BIBLE；
- 返回不存在于 CURRENT SOURCE_BIBLE 的 candidate ID；
- 创建 P9 最终身份。

---

# 5. Typed Schema：SOURCE_SHOT_FACTS schema 1.0

项目级内容：

```text
SourceShotFactsContent
├─ schema_version = "1.0"
├─ title = "逐镜精细拉片"
└─ episodes[]
```

Episode：

```text
SourceShotFactsEpisode
├─ episode_id
├─ episode_order
├─ source_filename
└─ shots[]
```

每个 Shot：

```text
SourceShotFact
├─ shot_anchor_id
├─ shot_number
├─ start_us                  ← P5 authoritative
├─ end_us                    ← P5 authoritative
├─ duration_us               ← P5 authoritative
├─ visual_description        ← P8
├─ camera_language
│  ├─ shot_size
│  ├─ composition
│  ├─ angle_or_type
│  ├─ movement
│  └─ focal_length_dof
├─ bindings
│  ├─ characters[]           ← P7 candidate id + label
│  ├─ scenes[]               ← P7 candidate id + label
│  ├─ props[]                ← P7 candidate id + label
│  └─ unresolved_subject_notes[]
├─ dialogue[]
│  ├─ utterance_id           ← P6 canonical
│  ├─ utterance_number       ← P6 canonical
│  ├─ utterance_start_us     ← P6 canonical
│  ├─ utterance_end_us       ← P6 canonical
│  ├─ overlap_start_us       ← P5 × P6 server-side join
│  ├─ overlap_end_us         ← P5 × P6 server-side join
│  ├─ text                   ← P6 canonical，Provider 无 text 字段
│  ├─ language               ← P6 canonical
│  └─ delivery               ← DIALOGUE / VOICEOVER / OFFSCREEN / UNKNOWN
├─ sound_effects[]
├─ ambience[]
└─ visual_text_evidence_ids[] ← CURRENT P6 OCR spans overlapping this Shot
```

`delivery=UNKNOWN` 表示当前 P8 无法可靠判断声音在画面内 / 画外，不允许据此创建 Speaker 身份。

---

# 6. 分镜表用户可读形态

参考 `docs/05_Seko源作概览画布节点实测.md`，P8 UI 至少展示：

| 列 | 来源 |
|---|---|
| 镜头编号 | P5 |
| 源片段 | P5 Reference Clip，仅局部播放 |
| 时长 | P5 |
| 画面描述 | P8 |
| 镜头语言 | P8：景别 / 构图 / 角度或类型 / 运镜 / 焦距景深 |
| 绑定主体 | P7 candidate binding |
| 对白 / 旁白 | P6 canonical text + P8 delivery |
| 音效 | P8 sound effects / ambience |

Reference Clip 是查看入口，不是 P8 Source Truth 替代物。

---

# 7. Artifact / Revision / Fingerprint

正式 Artifact：

```text
ArtifactType.SOURCE_SHOT_FACTS
namespace = SOURCE
```

正式 revision 行：

```text
SourceShotFactsRevision
├─ artifact_id
├─ project_id
├─ source_video_artifact_id
├─ source_bible_artifact_id
├─ shot_anchors_artifact_id
├─ source_dialogue_artifact_id
├─ generated_by_task_id
├─ schema_version
├─ content_json
├─ provenance_json
└─ created_at
```

Artifact 通用字段继续使用：

```text
revision
input_fingerprint
skill_id / skill_version
validity
is_current
created_at
```

P8 `input_fingerprint` 必须至少包含：

- CURRENT SOURCE_VIDEO id + fingerprint；
- CURRENT SOURCE_BIBLE id + fingerprint；
- CURRENT SHOT_ANCHORS id + fingerprint；
- CURRENT SOURCE_DIALOGUE id + fingerprint；
- 每个 Episode 的 CURRENT P5 boundary set / P6 evidence set；
- `shot-breakdown` Professional Skill id + version；
- Provider profile（不含 secret）。

同一输入 + Provider profile 通过 Task business key / Idempotency 继续防重复。

---

# 8. Provenance

每个 P8 revision 必须记录：

```text
source_video_artifact_id / fingerprint
source_bible_artifact_id / fingerprint
shot_anchors_artifact_id / fingerprint
source_dialogue_artifact_id / fingerprint

episode_inputs[]
  episode_id
  shot_boundary_set_id
  shot_boundary_fingerprint
  source_evidence_set_id
  source_evidence_fingerprint

provider_jobs[]
  provider_job_id
  episode_id
  provider
  model
  payload_fingerprint
  remote_job_id

provider / model
prompt_version = p8-shot-breakdown-v1
schema_version = 1.0
professional_skill_id = shot-breakdown
professional_skill_version = 1.0.0
source_truth_contract = source-bible-shot-facts-v1
generated_by_task_id
supersedes_artifact_id
```

API Key / Authorization / secret 永远不得进入以上 provenance。

---

# 9. Artifact Graph 与 CURRENT / STALE

P8 发布关系：

```text
SOURCE_VIDEO     ─DERIVED_FROM→ SOURCE_SHOT_FACTS
SOURCE_BIBLE     ─USES────────→ SOURCE_SHOT_FACTS
SHOT_ANCHORS     ─DERIVED_FROM→ SOURCE_SHOT_FACTS
SOURCE_DIALOGUE  ─DERIVED_FROM→ SOURCE_SHOT_FACTS

SOURCE_SHOT_FACTS revN ─SUPERSEDES→ SOURCE_SHOT_FACTS revN-1
```

其中箭头表示 `source_node → target_node`。

任一上游 CURRENT revision 被替换 / 失效时：

```text
旧 SOURCE_SHOT_FACTS 保留
+
validity = STALE
+
is_current = false
```

不得删除旧结果，也不得让 GET 静默重算。

P8 发布前必须再次校验四个输入仍是 CURRENT，且 fingerprint 与 Task 创建时一致；否则 fail closed。

---

# 10. Task / API / ProviderJob

正式重任务只能显式启动：

```text
POST /api/v3/projects/{project_id}/commands/shot-breakdown
Idempotency-Key: ...
```

只读：

```text
GET /api/v3/projects/{project_id}/shot-breakdown
GET /api/v3/projects/{project_id}/shot-breakdown/revisions
```

GET 不得创建 Task，不得调用 Provider，不得改 Artifact。

真实 Provider 调用前继续统一走：

```text
dispatch_provider_call(...)
↓
ProviderJob RUNNING 先 commit
↓
remote call
```

P8 每个 Episode 建立一个 ProviderJob；默认 Provider 调用粒度仍是完整 Episode，而不是单 Shot。

---

# 11. Provider 策略

P8 第一版复用项目已有 `source_understanding_provider` 选择和服务端运行时连接：

- Doubao Seed 2.1 Pro / Ark；
- Qwen3.8-27B / local vLLM；
- Qwen3-VL-8B-Thinking / local vLLM。

复用“Provider 选择”不等于 P7 与 P8 是同一个 Skill：

```text
P7 = source-video-understanding@1.1.0
P8 = shot-breakdown@1.0.0
```

两者有独立 Prompt version、Schema、Artifact 和 validation。

为了逐镜视觉精看，Doubao P8 使用至少 4 FPS 的完整 Episode 视频采样（仍受 10 FPS 上限约束），而不是切成 Reference Clip 后逐镜上传。

Reference Clip 的自动二次精看接口可以后续在 **P8 范围内**按低置信度局部补充，但第一版不依赖它才能成立，也不得让 Clip 替代完整 Episode。

---

# 12. Fail-closed 校验

以下任一情况 P8 不得发布 CURRENT Artifact：

- 缺 CURRENT SOURCE_VIDEO / SOURCE_BIBLE / SHOT_ANCHORS / P6 Source Evidence；
- P5 Anchors 未覆盖当前 Episode 集合；
- P6 Evidence 未覆盖当前 Episode 集合；
- SOURCE_BIBLE provenance 不指向当前 Source / Evidence；
- Provider 增删 Shot、重复 Shot 或改变 shot_number 集合；
- Provider 返回不存在于 CURRENT SOURCE_BIBLE 的 Character / Scene / Prop ID；
- Provider dialogue annotation 与服务端算出的 canonical utterance overlap 集合不一致；
- Provider 输出结构不合法；
- Task 执行期间任一输入 / Provider profile 改变；
- ProviderJob 未能先持久化；
- 发布阶段 Artifact Graph / revision 持久化失败。

失败不得覆盖旧 CURRENT 结果。

---

# 13. 自动测试最低覆盖

P8 自动测试至少证明：

- GET 是 read-only；
- 缺硬输入时 POST fail closed；
- ProviderJob 在 Provider call 前已经是 RUNNING；
- Provider 读取完整 Episode，不读取 P5 Reference Clip 作为唯一输入；
- 输出 Shot 集合与 P5 CURRENT Anchors 完全一致；
- `start_us/end_us/duration_us` 逐 Shot 精确来自 P5；
- canonical dialogue 正文逐字来自 P6，跨 Shot overlap 可绑定到多个 Shot；
- Provider 无 dialogue text 输出字段；
- P7 candidate ID 越界拒绝发布；
- provenance 含四个上游 Artifact 与 ProviderJob；
- 上游 SOURCE_BIBLE / SHOT_ANCHORS / SOURCE_DIALOGUE 失效会把 P8 递归标 STALE；
- revision / supersedes 可追溯；
- `SHOT_BREAKDOWN` 在人工验收前仍为 `PLANNED`。

---

# 14. 真实短剧人工验收门槛

只有真实短剧人工验收全部通过，才能把：

```text
SHOT_BREAKDOWN = AVAILABLE
```

人工逐 Shot 对照必须至少覆盖：

1. Shot Boundary：与 P5 CURRENT Anchor 一致；
2. 源片段：Reference Clip 能定位同一 Shot；
3. 画面描述：主要动作 / 表演 / 视觉主体无明显误读；
4. 镜头语言：景别、构图、角度 / 类型、运镜、焦距景深可用；
5. 人物 / 场景 / 道具：只绑定 CURRENT SOURCE_BIBLE 候选，不越权创建最终身份；
6. 对白：正文与 P6 canonical Evidence 一致；
7. 跨 Shot 对白：同一 canonical utterance 可投影到多个 Shot，不被强行拆写；
8. voiceover / offscreen：只标 delivery，不提前做 Speaker identity resolution；
9. 音效 / 环境声：与原片对应，不把音乐 / 环境声伪造成剧情事实；
10. 全局故事一致性：没有每 Shot 各猜一套剧情；
11. provenance / revision / fingerprint / CURRENT / STALE 正确；
12. GET 刷新不会产生新 Task 或费用。

如果真实验收未完成：

```text
P8 implementation 可以完成
但 SHOT_BREAKDOWN 必须继续 PLANNED
```

---

# 15. P8 完成后的边界

P8 完成并验收后，正式得到：

```text
CURRENT SOURCE_SHOT_FACTS
```

下一阶段才允许进入：

```text
人物 / Speaker identity resolution
场景归一
道具归一
SOURCE_VIDEO_SNAPSHOT
```

本阶段不得提前实现以上能力。
