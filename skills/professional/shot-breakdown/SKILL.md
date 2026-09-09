# Shot Breakdown Professional Skill

## 1. 目标

`shot-breakdown@1.1.0` 是 P8「带 Source Bible 的逐镜精细拉片」Professional Skill。

它负责把已经建立的整集原片知识落实到 **CURRENT P5 Shot Anchors** 上，生成正式 `SOURCE_SHOT_FACTS`。它不负责重新切镜、不负责重新听写、不负责重新建立整集故事，也不负责 P9 的最终人物 / Speaker / 场景 / 道具身份归一。

P8 1.1 新增 **canonical utterance → CURRENT SOURCE_BIBLE character candidate** 的逐句说话人候选绑定，用于让用户在分镜表里直接看见“谁说的”。这是 provisional candidate hint，不是 P9 最终 Speaker Truth。

## 2. 权威输入

执行时必须同时满足：

1. `CURRENT SOURCE_VIDEO`：完整 Episode，始终是最高层 Source Truth；
2. `CURRENT SOURCE_BIBLE`：P7 已建立的人物候选、关系、故事、场景候选、道具候选、Story/Rhythm 全局知识；
3. `CURRENT SHOT_ANCHORS`：P5 的唯一 Shot start/end 权威；
4. `CURRENT SOURCE_DIALOGUE`：P6 canonical Source Evidence。即使某集没有对白，正式 Evidence revision 仍作为输入依赖；有对白时正文只能从这里读取。

## 3. 不可跨越的边界

### 3.1 P5 边界权威

Provider 不输出 Shot start/end。服务端按照 `shot_number` 与 CURRENT P5 Shot Anchor join，并把 `shot_anchor_id/start_us/end_us/duration_us` 固化到正式 Artifact。

任何漏 Shot、增 Shot、重复 Shot 或重编号都必须阻断发布。

### 3.2 P6 canonical 文字权威

服务端以 CURRENT P6 `SourceDialogueUtterance.start_us/end_us` 与 CURRENT P5 Anchor 做 overlap，得到本次 P8 的权威 Shot binding。

每个 Shot 的 `dialogue_annotations` 只允许标：

- `DIALOGUE`
- `VOICEOVER`
- `OFFSCREEN`
- `UNKNOWN`

Provider **不输出对白正文**。最终 `SOURCE_SHOT_FACTS.dialogue[].text` 由服务端直接复制 P6 canonical text，P8 不做转写、摘要、清洗或改写。

### 3.3 P8 说话人候选绑定

P8 1.1 允许 Provider 在 Episode 级 `dialogue_speakers[]` 中对每条 canonical utterance 输出：

- `utterance_number`
- `speaker_character_id: string | null`

`speaker_character_id` 只能来自 CURRENT SOURCE_BIBLE 的 `character_id`。Provider 无权输出人物 label，也不能创建新 ID。

如果无法可靠判断说话人，必须输出 `null`，由 UI 显示“未确认说话人”。

同一条 canonical utterance 可能跨多个 Shot，因此 speaker candidate 属于 utterance，而不是 Shot。服务端只接受 **每条 canonical utterance 恰好一条 Episode 级 speaker annotation**，并把同一个 candidate 注入所有 Shot overlap。

这不是 P9 最终 Speaker Attribution：P8 不做声纹聚类、跨 Episode speaker identity、SourceSpeaker 物化或最终人物身份 resolution。P9 仍需独立音视频证据做最终归一。

### 3.4 P7 全局上下文权威

每个 Shot 都必须在当前 Episode 的 Source Bible 全局上下文中解释。Provider 不能把 Shot 当成互不相干的小视频，再分别猜人物、关系和整集剧情。

P8 的 `character/scene/prop` 是引用 P7 candidate ID 的 **Shot-level binding**；speaker candidate 同样只引用 P7 character candidate。不能创建新 ID，也不能声明 P9 最终稳定身份。

### 3.5 Reference Clip 边界

Reference Clip 是 P5 派生的局部精看资产。它可以用于核对某个 Shot 的细节，但不能替代完整 Episode 进入整集故事理解、ASR、speaker candidate 判断或 Shot Boundary。

P8 1.1 默认 Provider 仍直接读取完整 Episode；Reference Clip 不作为整集请求输入。

## 4. Provider 输出语义

Episode 级 Provider semantic output：

- `shots[]`
  - `shot_number`
  - `visual_description`
  - `camera_language`
    - `shot_size`
    - `composition`
    - `angle_or_type`
    - `movement`
    - `focal_length_dof`
  - `bindings`
    - `character_ids`
    - `scene_ids`
    - `prop_ids`
    - `unresolved_subject_notes`
  - `dialogue_annotations`
    - `utterance_number`
    - `delivery`
  - `sound_effects`
  - `ambience`
- `dialogue_speakers[]`
  - `utterance_number`
  - `speaker_character_id`

Provider 不拥有 Shot 时间、canonical dialogue text、P7 candidate label 或 P6/P5 Artifact IDs 的写权限。

## 5. 正式 `SOURCE_SHOT_FACTS` schema 1.1

正式内容由服务端组合：

- Episode：`episode_id / episode_order / source_filename`
- Shot：
  - `shot_anchor_id`
  - `shot_number`
  - `start_us / end_us / duration_us`
  - `visual_description`
  - `camera_language`
  - `bindings.characters/scenes/props`（`id + label`）
  - `bindings.unresolved_subject_notes`
  - `dialogue[]`
    - canonical utterance ID / number / time
    - Shot overlap time
    - canonical text / language
    - delivery
    - `speaker: BoundSubjectRef | null`（P7 character candidate）
  - `sound_effects`
  - `ambience`
  - `visual_text_evidence_ids`

这个数据形态对应 `docs/05` 实测的用户可读分镜表，并按 `docs/10` 增加逐句“说话人候选 + delivery + canonical text”。

## 6. Artifact / revision / fingerprint / provenance

P8 1.1 正式 Source Truth 绑定契约：

```text
source-bible-shot-facts-v2
```

版本：

```text
shot-breakdown@1.1.0
p8-shot-breakdown-v2
SOURCE_SHOT_FACTS schema 1.1
```

它表示：

- Shot 时间由 CURRENT P5 固化；
- 对白正文由 CURRENT P6 固化；
- 人物 / 场景 / 道具 / speaker candidate 只能引用 CURRENT P7；
- 逐镜视觉、delivery、声音与 provisional speaker candidate 必须直接观察完整 Episode；
- Provider 无权把 provisional candidate 升格成 P9 最终 Speaker Truth。

每次成功发布生成新的 `SOURCE_SHOT_FACTS` Artifact revision，并持久化 `SourceShotFactsRevision`。

`input_fingerprint` 至少覆盖：

- P8 task/profile/schema/source-truth contract；
- `shot-breakdown` Professional Skill id/version；
- CURRENT SOURCE_VIDEO id/fingerprint；
- CURRENT SOURCE_BIBLE id/fingerprint；
- CURRENT SHOT_ANCHORS id/fingerprint + 每集 authoritative anchor signature；
- CURRENT SOURCE_DIALOGUE id/fingerprint + 每集 SourceEvidenceSet fingerprint；
- Provider profile。

Provenance 至少记录四个上游 Artifact、每集 EvidenceSet、ProviderJob、Provider/model、prompt/schema、Professional Skill version 与 supersedes Artifact。

Artifact Graph 关系：

- `SOURCE_VIDEO -> SOURCE_SHOT_FACTS : DERIVED_FROM`
- `SOURCE_BIBLE -> SOURCE_SHOT_FACTS : USES`
- `SHOT_ANCHORS -> SOURCE_SHOT_FACTS : DERIVED_FROM`
- `SOURCE_DIALOGUE -> SOURCE_SHOT_FACTS : DERIVED_FROM`
- `new SOURCE_SHOT_FACTS -> previous SOURCE_SHOT_FACTS : SUPERSEDES`

任何上游正式 revision 被替换时，已有 P8 结果必须保留为历史，但从 CURRENT 变为 STALE。

P8 1.0 → 1.1 是正式 schema / Skill / Prompt 变化，旧 `SOURCE_SHOT_FACTS` 必须 STALE；P5/P6/P7 保持 CURRENT，用户显式重跑 P8 生成带 speaker candidate 的新 revision。

## 7. API 与任务边界

- `POST /projects/{project_id}/commands/shot-breakdown`：显式创建真实重任务；
- `GET /projects/{project_id}/shot-breakdown`：只读 CURRENT/STALE/NOT_BUILT；
- `GET /projects/{project_id}/shot-breakdown/revisions`：只读历史 revision；
- retry/resume 继续走统一 Task 路由。

Provider 调用统一使用 `dispatch_provider_call()`；`ProviderJob` 必须先 commit 为 RUNNING，之后才允许远端调用。

## 8. 人工验收前状态

代码、自动测试和 UI 完成不等于 Capability AVAILABLE。

只有对真实短剧完成 `docs/04`、`docs/08` 与 `docs/10` 的 P8 人工验收，确认 Shot Boundary、canonical dialogue、speaker candidate、Source Bible binding、镜头语言和声音描述都符合真实原片后，才允许把 `SHOT_BREAKDOWN` 从 `PLANNED` 改为 `AVAILABLE`。
