# P9 Speaker / Character / Scene / Prop 最终归一：Professional Skill 与数据契约

> 状态：P9 工程设计基线。本文只定义 P9；P10 `SOURCE_VIDEO_SNAPSHOT` 仍禁止进入。
>
> 前置事实：P8 已完成真实人工验收并正式收口；`SHOT_BREAKDOWN = AVAILABLE`。P9 开发及自动化测试期间 `IDENTITY_RESOLUTION / SCENE_RESOLUTION / PROP_RESOLUTION` 继续保持 `PLANNED`，只有真实短剧 Provider、真实数据库和最终人工音画验收全部通过后才能另行评估 `AVAILABLE`。

当前 P9 Provider 输出契约：

```text
prompt_version = p9-source-resolution-v5
Ark Responses text.format = strict json_schema
Ark Responses max_output_tokens = 65536
```

v2 要求云 Provider 在请求层启用严格 JSON Schema 输出，不能只依赖提示词要求 JSON。`evidence_refs[].ref_id` 必须逐字引用输入中已经存在的 Episode、Shot Anchor、P6 Evidence 或 P7 candidate ID；全集级视觉连续性只能使用对应 `episode_id` 作为 `ref_id`，不得创造诸如“appearance_consistency”的语义标签 ID。v3 进一步从 Provider 专用 JSON Schema 的状态枚举中移除 `MANUAL_CONFIRMED`；该状态只能由显式人工 POST Command 产生，Provider 请求层和服务端校验层都必须拒绝模型伪造人工确认。v4 为完整 Character / Speaker / Scene / Prop 批次显式提供 32768 output token 预算。v5 根据真实 Prop 响应的未完成风险将该预算提高到 65536，并要求显式识别 Ark Responses `incomplete` 状态，不得把未完成输出混报为普通 JSON 校验失败；该预算属于 Provider profile 并进入 Task fingerprint。

## 1. P9 目标与边界

P9 把 P7/P8 的人物、说话人、场景、道具 candidate 收敛为稳定、版本化、可追溯的 Source identity。P9 不重新理解或改写原片，不修改 P5 Shot 时间，不重新听写 P6 canonical dialogue/OCR，不回写历史 P7 `SOURCE_BIBLE` 或 P8 `SOURCE_SHOT_FACTS` revision。

完整 Episode 永远是 Source Truth。P7 `SOURCE_BIBLE` 提供全集语义候选，P8 `SOURCE_SHOT_FACTS` 提供逐镜事实和 provisional binding，P5 `SHOT_ANCHORS` 提供唯一 Shot 时间边界；需要核对说话人、对白或画面文字时只读 CURRENT P6 canonical Source Evidence。

P9 必须按全集批次做跨 Shot 归一，并允许跨 Episode Evidence 参与同一项目的稳定 identity 判断。禁止“每个 Shot 独立判最终 identity，再按名称拼接”。

## 2. P9 Professional Skills

P9 新增四个独立 Professional Skill，均有正式 `manifest.json + SKILL.md`：

1. `character-resolution@1.0.0`
   - capability：`IDENTITY_RESOLUTION`
   - required：`SOURCE_VIDEO + SOURCE_BIBLE + SOURCE_SHOT_FACTS + SHOT_ANCHORS`
   - optional/readable：`SOURCE_DIALOGUE`
   - output：`SOURCE_CHARACTERS`
   - 以跨 Shot / 跨 Episode 的视觉连续性、人物关系、动作上下文、服装/发型/体态等多证据形成稳定 Character identity；同名和相似外观均不能单独触发 merge。

2. `speaker-attribution@1.0.0`
   - capability：`IDENTITY_RESOLUTION`
   - required：`SOURCE_VIDEO + SOURCE_BIBLE + SOURCE_SHOT_FACTS + SHOT_ANCHORS + SOURCE_DIALOGUE + SOURCE_CHARACTERS`
   - output：`SOURCE_SPEAKERS`
   - Speaker 与 Character 分层。Speaker 是 canonical utterance 上的稳定说话人 identity；每个 Speaker 可以有 `character_id = null`，每条 utterance 可以保持 unresolved。不得把 P8 `speaker candidate` 直接提升为最终 truth。

3. `scene-resolution@1.0.0`
   - capability：`SCENE_RESOLUTION`
   - required：`SOURCE_VIDEO + SOURCE_BIBLE + SOURCE_SHOT_FACTS + SHOT_ANCHORS`
   - optional/readable：`SOURCE_DIALOGUE`
   - output：`SOURCE_SCENES`
   - 支持同一真实地点跨多个 Shot / Episode merge；也支持同名但空间身份不同的地点 split。Shot 时间仍完全引用 P5。

4. `prop-resolution@1.0.0`
   - capability：`PROP_RESOLUTION`
   - required：`SOURCE_VIDEO + SOURCE_BIBLE + SOURCE_SHOT_FACTS + SHOT_ANCHORS`
   - optional/readable：`SOURCE_DIALOGUE`
   - output：`SOURCE_PROPS`
   - 只归一剧情相关道具。视觉相似不是实例相同；同一实例跨 Shot 才能 merge，不确定时保持 unresolved。

四个 Skill 可以由一个 P9 Command 编排，但 Provider 输入、ProviderJob、输出契约和 provenance 必须能分别审计到具体 Professional Skill。

## 3. 正式 Artifact 与 typed schema

P9 正式 Source Artifact：

- `SOURCE_CHARACTERS`
- `SOURCE_SPEAKERS`（P9 新增，禁止把 Speaker 塞进 Character 并默认一一对应）
- `SOURCE_SCENES`
- `SOURCE_PROPS`

四类 Artifact 均使用独立 `ArtifactNode` revision，并由一组 P9 resolution revision rows 保存 typed content/provenance。P9 不创建 `SOURCE_VIDEO_SNAPSHOT`。

### 3.1 通用 resolution 状态

实体与绑定使用以下状态：

- `RESOLVED`：证据足够，已归入稳定 identity；
- `UNKNOWN`：当前没有可靠 identity 候选；
- `UNRESOLVED`：存在一个或多个候选，但证据不足以决定；
- `MANUAL_CONFIRMED`：人工裁决生成的新 revision 已确认。

`UNKNOWN / UNRESOLVED` 是一等正式结果，不是错误，也不能在 Provider 或服务端被自动填成最高相似候选。

### 3.2 Character

每个 stable Character 至少包含：

- `character_id`：P9 stable ID，不复用 P7 candidate ID 作为 identity 语义；
- `display_name`：用户可读名称，可来自 P7，但不能作为 merge key；
- `aliases`；
- `source_candidate_ids`；
- `episode_ids / shot_anchor_ids`；
- `evidence_refs`；
- `confidence` 与 `resolution_status`；
- `notes`。

另保存 unresolved character observations，使未归一的人物出现不会消失。

### 3.3 Speaker

每个 stable Speaker 至少包含：

- `speaker_id`；
- `display_label`；
- `character_id: str | null`；
- `utterance_ids`；
- `episode_ids`；
- `source_candidate_character_ids`（仅证据提示，不是 final identity）；
- `evidence_refs`；
- `confidence` 与 `resolution_status`。

每条 canonical utterance 保存 `speaker_id | null` 与独立 `attribution_status`。P9 永远引用 P6 `utterance_id + canonical text/time`；不得复制后修改文字。

### 3.4 Scene

每个 stable Scene 至少包含：

- `scene_id`；
- `display_name`；
- `aliases`；
- `source_candidate_ids`；
- `episode_ids / shot_anchor_ids`；
- `evidence_refs`；
- `confidence` 与 `resolution_status`；
- `disambiguation_notes`，用于记录同名场景 split 依据。

每个 Shot 只能绑定一个 P5 `shot_anchor_id` 的场景结果；服务端不得修改其 `start_us/end_us`。

### 3.5 Prop

每个 stable Prop 至少包含：

- `prop_id`；
- `display_name`；
- `aliases`；
- `source_candidate_ids`；
- `episode_ids / shot_anchor_ids`；
- `evidence_refs`；
- `confidence` 与 `resolution_status`；
- `instance_notes`，记录“同类物件”和“同一具体实例”的区分依据。

## 4. revision / fingerprint / provenance / CURRENT / STALE

每个 P9 Artifact revision 必须具有 64 位 SHA256 input fingerprint。自动 P9 运行的 fingerprint 至少包含：

- CURRENT `SOURCE_VIDEO` artifact id + fingerprint；
- CURRENT `SOURCE_BIBLE` artifact id + fingerprint；
- CURRENT `SOURCE_SHOT_FACTS` artifact id + fingerprint；
- CURRENT `SHOT_ANCHORS` artifact id + fingerprint；
- Speaker 归一还必须包含 CURRENT `SOURCE_DIALOGUE` artifact id + fingerprint 和每 Episode CURRENT SourceEvidenceSet fingerprint；
- 每 Episode source asset SHA256；
- P5 shot anchor id/number/start/end/duration；
- P6 utterance id/number/start/end/text（只读，用于检测 canonical 变化）；
- Professional Skill id/version；
- P9 schema/prompt/source-truth contract；
- Provider profile；
- 同类型前一 revision id（若存在）。

provenance 至少包含上述上游 Artifact、Episode Evidence、ProviderJob、Professional Skill、schema/prompt/source-truth contract、task id、`supersedes_artifact_id`。

上游产生新 CURRENT revision 后，依赖旧上游的 P9 Artifact 必须通过 Artifact Graph 自动变为 `STALE`。读取接口不得隐式重算或修复 stale。

## 5. Artifact Graph

每类 P9 Artifact 最少建立：

- `SOURCE_VIDEO --DERIVED_FROM--> P9 artifact`
- `SOURCE_BIBLE --USES--> P9 artifact`
- `SOURCE_SHOT_FACTS --DERIVED_FROM--> P9 artifact`
- `SHOT_ANCHORS --DERIVED_FROM--> P9 artifact`
- `SOURCE_DIALOGUE --DERIVED_FROM--> SOURCE_SPEAKERS`
- `SOURCE_CHARACTERS --USES--> SOURCE_SPEAKERS`
- `new P9 artifact --SUPERSEDES--> previous same-type artifact`

人工裁决生成的新 revision 同样必须建立 `SUPERSEDES`。不得建立 Target/Production -> Source 的反向依赖。

## 6. merge / split / manual adjudication

人工裁决必须使用显式 POST Command，禁止 GET 写入。第一版支持：

- `CONFIRM`：确认实体字段或绑定；
- `MERGE`：把多个 stable identity 合并为一个新 identity；
- `SPLIT`：把一个 stable identity 按指定 observation/shot/utterance 拆成多个；
- `MARK_UNKNOWN`：撤销强归一并保留证据；
- `REASSIGN`：对 Speaker↔Character、Shot↔Scene、Shot↔Prop、observation↔Character 做明确重绑。

Command 必须携带 `expected_revision` 做乐观并发控制，携带人工理由 `reason`，并生成新的正式 Artifact revision。历史 revision 不更新、不删除。

人工 revision fingerprint 额外包含前一 artifact id/fingerprint、裁决 payload、裁决 contract version。provenance 标记 `adjudication.mode = MANUAL`、operation、reason 与 supersedes。

如果 Character 人工 revision 改变，当前 `SOURCE_SPEAKERS` 因 `SOURCE_CHARACTERS --USES--> SOURCE_SPEAKERS` 自动 STALE，必须重新归因或人工重绑；不能静默继续使用旧 Speaker↔Character 关系。

## 7. P9 Service / Provider 执行规则

- 重任务入口：`POST /projects/{project_id}/commands/source-resolution`。
- GET 只读：读取 current/stale P9 aggregate、各类 revision history，不创建 Task、不调用 Provider、不发布 Artifact。
- 自动执行顺序：Character -> Speaker -> Scene -> Prop。四个 Provider call 均在远程调用前先持久化 `ProviderJob`。
- Provider 必须读取完整 Episode；允许把所有 Episode 的候选与跨 Episode summary 一并放入 prompt/context，禁止按 Shot 单独请求后简单拼接。
- 云 Provider 必须使用 Responses API 的 strict JSON Schema structured output；解析与服务端 publication validation 继续双重 fail-closed。
- 服务端验证所有返回的 `shot_anchor_id / utterance_id / P7 candidate id / P8 binding ref` 都来自当前硬输入；Provider 不能创造不存在的 Source evidence id。
- 对置信不足的结果要求 Provider 返回 UNKNOWN/UNRESOLVED；服务端不得做“最高分兜底”。
- 发布前重新核验 Task input artifact ids、fingerprint 与 Provider profile；变化则 fail closed。
- 任一正式 artifact/revision/graph 持久化失败必须使本次 P9 结果不可被误认为完整可用。

## 8. P9 人工验收规范

真实短剧最终验收至少覆盖：

1. Character：同一人物跨 Shot 正确 merge；相似外观不同人物不误合并；同名不作为唯一依据；证据不足可 UNKNOWN/UNRESOLVED。
2. Speaker：逐条对 CURRENT P6 canonical utterance 做音画核对；P8 provisional speaker candidate 不能直接冒充 final；Speaker↔Character 可为空且不是默认一一对应。
3. Scene：P8 最终 Scene 基线（Shot #001 王桂香家客厅、#002–#009 居民楼公共楼道、#010–#028 徐然家客厅）必须能在 P9 中稳定合并；另验证同名不同地点可 split。
4. Prop：同一关键道具跨 Shot 能 merge；相似但不同实例不误合并。
5. P5：所有 Shot 时间 100% 与 CURRENT P5 一致，P9 无修改路径。
6. P6：P9 引用的 utterance text/time 与 CURRENT canonical P6 逐字逐时一致，差异必须为 0。
7. Artifact：四类 P9 Artifact revision、fingerprint、provenance、CURRENT/STALE、SUPERSEDES、Artifact Graph 全部正确。
8. Runtime：GET 无副作用；真实重任务是 POST；每个外部 ProviderJob 在远程调用前已持久化；失败/重试/idempotency 不产生假成功。
9. Manual：至少真实执行一次 merge 或 split、一次 Speaker↔Character 重新裁决，确认旧 revision 保留、新 revision CURRENT、受影响下游 STALE。
10. Source/Target：P9 全部结果属于 Source namespace，未创建 P10 `SOURCE_VIDEO_SNAPSHOT`，未进入 Target。

只有上述真实 Provider、真实数据库、最终人工音画验收全部 PASS，才允许另起收口变更评估 P9 capabilities 是否从 `PLANNED` 升为 `AVAILABLE`。本开发阶段不得提前修改 capability availability。

## 9. P10 禁入条件

在 P9 完成真实人工验收之前：

- 不创建 `SOURCE_VIDEO_SNAPSHOT` revision；
- 不实现或调用 P10 snapshot service/provider；
- 不把 P9 输出视为已经冻结的下游唯一 Source Snapshot；
- 不进入 Target localization / storyboard / generation。
