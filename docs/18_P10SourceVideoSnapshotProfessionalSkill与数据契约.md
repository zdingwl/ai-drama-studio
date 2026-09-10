# P10 SourceVideoSnapshot / 原片分析定稿：Professional Skill 与数据契约

> 日期：2026-09-10  
> 状态：P10 工程设计基线；尚未完成真实人工验收。  
> 前置事实：P9 已最终 PASS；`IDENTITY_RESOLUTION / SCENE_RESOLUTION / PROP_RESOLUTION = AVAILABLE`。  
> 当前门禁：`SOURCE_SNAPSHOT = PLANNED`，不得进入 Target Localization / Target Bible 正式实现。

---

## 1. P10 目标与边界

P10 负责把已经通过 P5~P9 建立并验收的 CURRENT Source Facts **确定性冻结**为正式 `SOURCE_VIDEO_SNAPSHOT`，使后续 Target / Production 只消费一个版本明确、可追溯、可判 stale 的 Source 边界。

P10 不是新的理解阶段：

```text
P10 = freeze / validate / publish
P10 != model re-understanding
P10 != evidence rewrite
P10 != identity resolution
P10 != localization
```

完整 Episode 永远是最高层 Source Truth。P10 不允许重新调用 VLM / LLM / ASR / OCR / identity Provider，不产生新的剧情、人物、场景、道具或说话人判断。

必须保持：

- P5 Shot start/end/duration 只读；
- P6 canonical dialogue / OCR 只读；
- P7 SOURCE_BIBLE 历史 revision 不回写；
- P8 SOURCE_SHOT_FACTS 历史 revision 不回写；
- P9 SOURCE_CHARACTERS / SOURCE_SPEAKERS / SOURCE_SCENES / SOURCE_PROPS 历史 revision 不回写；
- Source namespace 不允许 Target / Production 反向写入。

---

## 2. Professional Skill

正式 Professional Skill：

```text
skills/professional/source-video-snapshot/SKILL.md
skills/professional/source-video-snapshot/manifest.json
source-video-snapshot@1.0.0
```

Capability：

```text
SOURCE_SNAPSHOT
```

在真实人工验收通过前，Capability 必须继续保持 `PLANNED`。

执行步骤：

```text
1. load_current_source_chain
   读取并校验 P5~P9 所有正式 CURRENT Source Artifact

2. validate_authoritative_facts
   重新做确定性 authority / provenance / revision 一致性校验
   不调用任何模型

3. freeze_source_facts
   把当前正式 Source Facts 原样物化到 typed SourceVideoSnapshotContent

4. publish_snapshot
   创建 SOURCE_VIDEO_SNAPSHOT revision / provenance / Artifact Graph
```

---

## 3. P10 硬输入

P10 第一版只对已经进入完整 Source Understanding + P9 resolution 链的视频项目执行，即当前 `REPLICA / REDRAW`。

必须同时存在以下 CURRENT Source Artifact：

```text
SOURCE_VIDEO
SHOT_ANCHORS
SOURCE_DIALOGUE
SOURCE_BIBLE
STORY_SKELETON
RHYTHM_SKELETON
SOURCE_SHOT_FACTS
SOURCE_CHARACTERS
SOURCE_SPEAKERS
SOURCE_SCENES
SOURCE_PROPS
```

其中 `SOURCE_SPEAKERS` 是独立正式输入，不能通过 Character 推导替代，也不能只冻结 Character / Scene / Prop。

虽然 Story / Rhythm typed 内容已存在于 SOURCE_BIBLE 中，`STORY_SKELETON` 与 `RHYTHM_SKELETON` 仍作为独立 CURRENT Artifact 纳入 fingerprint / provenance / graph，以冻结当前正式 Artifact 链并保证任何独立 revision 变化都能使旧 Snapshot STALE。

---

## 4. Source Truth 权威顺序

```text
完整 Episode / SOURCE_VIDEO
= 永久 Source Truth

CURRENT SHOT_ANCHORS
= Shot 时间唯一权威

CURRENT SOURCE_DIALOGUE + CURRENT SourceEvidenceSet
= canonical dialogue / OCR 唯一文字事实

CURRENT SOURCE_BIBLE
= 已验收整集语义、Story / Rhythm

CURRENT SOURCE_SHOT_FACTS
= 已验收逐镜视觉 / 镜头语言 / 声音与 candidate binding

CURRENT SOURCE_CHARACTERS / SOURCE_SPEAKERS / SOURCE_SCENES / SOURCE_PROPS
= 已验收稳定 Source resolution
```

P10 遇到任何不一致必须 fail closed，不能通过“重新理解”或自动纠正来修复。

---

## 5. Typed Schema：SOURCE_VIDEO_SNAPSHOT schema 1.0

正式内容：

```text
SourceVideoSnapshotContent
├─ schema_version = "1.0"
├─ title = "原片分析定稿"
├─ source_truth_contract = "frozen-accepted-source-facts-v1"
├─ frozen_artifacts[]
├─ episodes[]
├─ source_bible
├─ source_shot_facts
├─ source_characters
├─ source_speakers
├─ source_scenes
└─ source_props
```

### 5.1 Frozen Artifact Ref

每个正式输入保存：

```text
artifact_type
artifact_id
revision
input_fingerprint
```

`frozen_artifacts` 必须恰好覆盖第 3 节的完整输入集合，不允许漏掉 `SOURCE_SPEAKERS`。

### 5.2 Episode Snapshot

每个 Episode 至少冻结：

```text
episode_id
source_asset_id
episode_order
source_filename
source_asset_sha256
media duration / width / height / codec / avg_frame_rate / has_audio

shot_boundary_set_id
shot_boundary_fingerprint
shot_anchors[]
  shot_anchor_id
  shot_number
  start_us
  end_us
  duration_us

source_evidence_set_id
source_evidence_fingerprint
canonical_dialogue[]
  utterance_id
  utterance_number
  start_us
  end_us
  text
  language

canonical_visual_text[]
  span_id
  span_number
  start_us
  end_us
  text
  confidence
```

P10 只复制 CURRENT P5/P6 的正式值，不重新生成任何时间或正文。

### 5.3 Higher-level frozen facts

以下内容直接使用当前 typed content 原样冻结：

```text
SOURCE_BIBLE        -> SourceBibleContent
SOURCE_SHOT_FACTS   -> SourceShotFactsContent
SOURCE_CHARACTERS   -> CharacterResolutionContent
SOURCE_SPEAKERS     -> SpeakerResolutionContent
SOURCE_SCENES       -> SceneResolutionContent
SOURCE_PROPS        -> PropResolutionContent
```

Snapshot 不把 P9 Speaker 合并进 Character；两者继续是独立 typed section。

---

## 6. Domain / Revision

新增正式 revision row：

```text
SourceVideoSnapshotRevision
├─ id
├─ project_id
├─ artifact_id
├─ source_video_artifact_id
├─ shot_anchors_artifact_id
├─ source_dialogue_artifact_id
├─ source_bible_artifact_id
├─ story_skeleton_artifact_id
├─ rhythm_skeleton_artifact_id
├─ source_shot_facts_artifact_id
├─ source_characters_artifact_id
├─ source_speakers_artifact_id
├─ source_scenes_artifact_id
├─ source_props_artifact_id
├─ generated_by_task_id = null（第一版同步确定性 Command，不创建 Provider Task）
├─ schema_version
├─ content_json
├─ provenance_json
└─ created_at
```

Artifact 通用字段继续由 `ArtifactNode` 管理：revision / input_fingerprint / skill_id / skill_version / validity / is_current。

P10 第一版是轻量确定性发布 Command，不创建 ProviderJob，也不需要外部 Provider Task。后续若冻结规模需要异步化，可以保持同一业务契约再迁移到 Task；GET 永远不能承担该动作。

---

## 7. Fingerprint

`SOURCE_VIDEO_SNAPSHOT.input_fingerprint` 必须为 64 位 SHA256，并至少包含：

- P10 schema / source truth contract / Professional Skill id + version；
- 第 3 节每个 CURRENT Artifact 的 id / revision / input_fingerprint；
- 每个 Episode 的 immutable source asset SHA256；
- CURRENT ShotBoundarySet id / fingerprint；
- CURRENT P5 `shot_anchor_id / number / start / end / duration`；
- CURRENT SourceEvidenceSet id / fingerprint；
- CURRENT P6 canonical dialogue `id / number / start / end / text / language`；
- CURRENT P6 visual text `id / number / start / end / text / confidence`；
- P7/P8/P9 typed content 的确定性 hash；
- 前一 SOURCE_VIDEO_SNAPSHOT artifact id / fingerprint（若存在）。

动态时间戳不得进入业务 fingerprint。

---

## 8. Provenance

正式契约：

```text
snapshot_contract = p10-source-video-snapshot-v1
schema_version = 1.0
source_truth_contract = frozen-accepted-source-facts-v1
professional_skill_id = source-video-snapshot
professional_skill_version = 1.0.0
```

provenance 至少记录：

- 全部 frozen artifact refs；
- 每个 Episode source asset / ShotBoundarySet / SourceEvidenceSet 指纹；
- `provider_jobs = []`，明确 P10 没有重新调用模型；
- `supersedes_artifact_id`；
- publication mode = `DETERMINISTIC_FREEZE`。

不得保存 API Key / Authorization / secret。

---

## 9. Artifact Graph / STALE

所有箭头仍表示 `source_node -> target_node`。

P10 至少建立：

```text
SOURCE_VIDEO        --DERIVED_FROM--> SOURCE_VIDEO_SNAPSHOT
SHOT_ANCHORS        --DERIVED_FROM--> SOURCE_VIDEO_SNAPSHOT
SOURCE_DIALOGUE     --DERIVED_FROM--> SOURCE_VIDEO_SNAPSHOT
SOURCE_BIBLE        --USES---------> SOURCE_VIDEO_SNAPSHOT
STORY_SKELETON      --USES---------> SOURCE_VIDEO_SNAPSHOT
RHYTHM_SKELETON     --USES---------> SOURCE_VIDEO_SNAPSHOT
SOURCE_SHOT_FACTS   --DERIVED_FROM--> SOURCE_VIDEO_SNAPSHOT
SOURCE_CHARACTERS   --CONTAINS-----> SOURCE_VIDEO_SNAPSHOT
SOURCE_SPEAKERS     --CONTAINS-----> SOURCE_VIDEO_SNAPSHOT
SOURCE_SCENES       --CONTAINS-----> SOURCE_VIDEO_SNAPSHOT
SOURCE_PROPS        --CONTAINS-----> SOURCE_VIDEO_SNAPSHOT

SOURCE_VIDEO_SNAPSHOT revN --SUPERSEDES--> revN-1
```

这里 `CONTAINS` 采用现有 Artifact Graph 的统一 `source_node -> target_node` 方向，以便任何被 Snapshot 冻结的 Source entity Artifact 变化时，通用 downstream STALE 传播能直接命中 Snapshot。

因此上游任一冻结 CURRENT Artifact 被新 revision 替代后：

```text
旧 SOURCE_VIDEO_SNAPSHOT.validity = STALE
旧 SOURCE_VIDEO_SNAPSHOT.is_current = false
历史 snapshot / content / provenance 保留
GET 不自动重建
```

---

## 10. Publication fail-closed

以下任一情况不得发布 Snapshot：

- 缺任一硬输入 CURRENT Artifact；
- 同类型出现多个 CURRENT；
- P7 provenance 与 CURRENT P5/P6/SOURCE_VIDEO 不一致；
- P8 provenance 与 CURRENT P5/P6/P7/SOURCE_VIDEO 不一致；
- P9 任一 artifact provenance 与 CURRENT P5/P7/P8/SOURCE_VIDEO 不一致；
- SOURCE_SPEAKERS 未引用当前 SOURCE_DIALOGUE / SOURCE_CHARACTERS；
- P8 Shot 时间与 CURRENT P5 有任何差异；
- P8 / P9 dialogue text/time 与 CURRENT P6 canonical 有任何差异；
- Episode / Shot / utterance / visual-text 集合不一致；
- typed content parse 失败；
- 冻结过程中任一输入失去 CURRENT；
- Source namespace / graph relation 校验失败。

失败不能产生半成品 CURRENT Snapshot。

---

## 11. API

显式定稿：

```text
POST /api/v3/projects/{project_id}/commands/source-video-snapshot
```

只读：

```text
GET /api/v3/projects/{project_id}/source-video-snapshot
GET /api/v3/projects/{project_id}/source-video-snapshot/revisions
```

POST 返回已发布 Snapshot read model；若当前输入与当前 Snapshot fingerprint 完全一致，应幂等返回现有 CURRENT revision，避免重复点击制造无意义 revision。

GET 不创建 Artifact、不调用模型、不修改 CURRENT / STALE、不重编 Plan。

---

## 12. Root Skill 修正

P10 接入时必须修正视频 Root Skill 的 Source finalize 输入：

- `REPLICA source_finalize` 必须显式 requires `SOURCE_SPEAKERS`；
- `REDRAW` 的 Source finalize 必须与当前 P9 正式链一致，不能只冻结 P7/P8 而遗漏 P9 resolution；
- 本阶段只调整 Source finalize 前置契约，不实现任何 Target Localization / Target Bible 服务。

---

## 13. UI

P10 验收 UI 至少显示：

- 当前状态：NOT_BUILT / CURRENT / STALE；
- Snapshot revision / fingerprint；
- “原片分析定稿”显式按钮；
- 冻结输入清单及各自 revision；
- Episode / Shot / canonical dialogue / OCR 数量；
- Character / Speaker / Scene / Prop 数量，Speaker 独立显示；
- provenance / source truth contract；
- 历史 revision；
- STALE 后明确提示重新显式定稿，不自动执行。

UI 不提供修改 P5/P6/P7/P8/P9 历史事实的入口。

---

## 14. 自动验收最低覆盖

至少证明：

1. Professional Skill 可机器加载，required inputs 含独立 SOURCE_SPEAKERS；
2. 没有 Provider 调用 / ProviderJob；
3. 缺任一 P5~P9 CURRENT artifact fail closed；
4. Snapshot P5 时间逐值等于 CURRENT SHOT_ANCHORS；
5. Snapshot P6 canonical dialogue / OCR 逐值等于 CURRENT Source Evidence；
6. Snapshot P7/P8/P9 typed content 与上游一致；
7. Speaker 与 Character 是独立 section；
8. fingerprint / provenance 覆盖全部上游；
9. Artifact Graph 必需关系完整；
10. 任一冻结上游产生新 revision 后旧 Snapshot 递归 STALE；
11. 第二次相同输入 POST 幂等，不产生额外 Snapshot revision；
12. GET 前后 Artifact / Task / ProviderJob 数量不变；
13. Source / Target namespace backflow 继续 fail closed；
14. backend compile / FastAPI import / alembic upgrade head / pytest 全绿；
15. frontend typecheck / unit / build 全绿。

---

## 15. 人工验收门禁

工程实现和自动测试通过后，仍必须使用当前真实短剧项目检查：

```text
P5 SHOT_ANCHORS rev1 CURRENT
P6 SOURCE_DIALOGUE rev9 CURRENT
P7 SOURCE_BIBLE rev8 CURRENT
P8 SOURCE_SHOT_FACTS rev6 CURRENT
P9 SOURCE_CHARACTERS / SOURCE_SPEAKERS / SOURCE_SCENES / SOURCE_PROPS CURRENT
```

人工至少确认：

- Snapshot 冻结的 Episode / 28 Shot / P6 canonical / P7/P8/P9 内容与验收链一致；
- Speaker 作为独立正式输入和结果存在；
- 点击定稿不会触发模型；
- GET / 刷新无副作用；
- provenance 能反查全部 Source revision；
- 人工制造一个安全的上游新 revision 后旧 Snapshot 正确 STALE，并通过再次显式定稿形成新 Snapshot revision；
- Source 与 Target 仍隔离。

只有真实人工验收最终 PASS 后，才允许另行把：

```text
SOURCE_SNAPSHOT = AVAILABLE
```

在此之前保持 `PLANNED`，并且不得进入 Target Localization / Target Bible 正式实现。
