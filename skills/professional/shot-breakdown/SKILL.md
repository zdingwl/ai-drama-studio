# Shot Breakdown Professional Skill

## 1. 目标

`shot-breakdown@1.0.0` 是 P8「带 Source Bible 的逐镜精细拉片」的 Professional Skill。

它只负责把已经建立的整集原片知识落实到 **CURRENT P5 Shot Anchors** 上，生成正式 `SOURCE_SHOT_FACTS`。它不负责重新切镜、不负责重新听写、不负责重新建立整集故事，也不负责 P9 的最终人物/场景/道具身份归一。

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

Provider 只允许对服务端给出的 `overlapping_utterance_numbers` 标注：

- `DIALOGUE`
- `VOICEOVER`
- `OFFSCREEN`
- `UNKNOWN`

Provider **不输出对白正文**。最终 `SOURCE_SHOT_FACTS.dialogue[].text` 由服务端直接复制 P6 canonical text，P8 不做转写、摘要、清洗或改写。

### 3.3 P7 全局上下文权威

每个 Shot 都必须在当前 Episode 的 Source Bible 全局上下文中解释。Provider 不能把 Shot 当成互不相干的小视频，再分别猜人物、关系和整集剧情。

P8 的 `character/scene/prop` 只是引用 P7 candidate ID 的 **Shot-level binding**。不能创建新 ID，也不能声明稳定身份；最终 `IDENTITY_RESOLUTION / SCENE_RESOLUTION / PROP_RESOLUTION` 属于 P9。

### 3.4 Reference Clip 边界

Reference Clip 是 P5 派生的局部精看资产。它可以在后续 Provider 优化中用于核对某个 Shot 的细节，但不能替代完整 Episode 进入整集故事理解、ASR 或 Shot Boundary。

P8 1.0 的默认 Provider 调用直接读取完整 Episode；Reference Clip 不作为整集请求输入。

## 4. Provider 输出语义

每个 Shot 的 Provider semantic output 只包含：

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

Provider 不拥有 Shot 时间、canonical dialogue text、P7 candidate label 或 P6/P5 Artifact IDs 的写权限。

## 5. 正式 `SOURCE_SHOT_FACTS` schema

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
  - `sound_effects`
  - `ambience`
  - `visual_text_evidence_ids`

这个数据形态对应 `docs/05` 实测的用户可读分镜表：镜头编号、源片段、时长、画面描述、镜头语言、绑定主体、对白/旁白、音效。

## 6. Artifact / revision / fingerprint / provenance

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

## 7. API 与任务边界

- `POST /projects/{project_id}/commands/shot-breakdown`：显式创建真实重任务；
- `GET /projects/{project_id}/shot-breakdown`：只读 CURRENT/STALE/NOT_BUILT；
- `GET /projects/{project_id}/shot-breakdown/revisions`：只读历史 revision；
- retry/resume 继续走统一 Task 路由。

Provider 调用统一使用 `dispatch_provider_call()`；`ProviderJob` 必须先 commit 为 RUNNING，之后才允许远端调用。

## 8. 人工验收前状态

代码、自动测试和 UI 完成不等于 Capability AVAILABLE。

只有对真实短剧完成 `docs/04` 与 `docs/08` 中 P8 人工验收，确认 Shot Boundary、canonical dialogue、Source Bible binding、镜头语言和声音描述都符合真实原片后，才允许把 `SHOT_BREAKDOWN` 从 `PLANNED` 改为 `AVAILABLE`。
