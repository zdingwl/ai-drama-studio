# P12 Target Script / Localization Professional Skill 与数据契约

> 状态：**工程预实现合同已定义；P12 尚未正式准入，尚未真实人工验收，TARGET_SCRIPT capability 必须保持 PLANNED。**
>
> 前置事实：P10 已真实人工 PASS；P11 Replica Target Bible 工程实现已进入真实 Provider 验收，但截至本合同建立时 **P11 尚未由用户明确 PASS**。因此 P11 的 `LOCALIZATION / TARGET_BIBLE` 仍为 `PLANNED`，P12 普通产品流程不得真实执行。

## 1. P12 的唯一职责

P12 只负责 **Target Script / Localization**：

1. 读取未来已通过 P11 人工验收的目标世界与本土化策略；
2. 以 P10 Source Snapshot 中冻结的 P6 canonical Source Dialogue 为原始对白事实；
3. 对每条 canonical Source Dialogue 依次形成可审计的 Translation、Localization、Final Target Dialogue；
4. 发布 typed `TARGET_SCRIPT` revision、provenance 与 Artifact Graph；
5. 为后续 Target Speaker/Voice、TTS、Actual Speech Duration、Timing Plan 保留稳定 lineage。

P12 **不负责**：Target Storyboard、Target Assets、Target Voice、TTS、Actual Speech Duration、Timing Plan、Video Generation、QC、Selection、Lip Sync、Post Production。

必须保持以下单向链路：

`Source Dialogue → Translation → Localization → Final Target Dialogue → Target Speaker/Voice → TTS → Actual Speech Duration → Timing Plan`

其中 P12 的输出终点是 `Final Target Dialogue`。P12 可以把对白绑定到已有 `target_character_id` 以保留角色 lineage，但**不得创建 voice_id、speaker voice、TTS audio、speech duration 或 timing decision**。

## 2. P12 正式准入门禁

P12 当前允许完成合同、Professional Skill、typed schema、service/provider、API、测试和 UI 工程准备，但正式执行必须 fail closed。

### 2.1 必须同时满足

未来正式执行 P12 时，服务端必须同时验证：

1. 项目类型为 `REPLICA`；
2. P11 已真实人工验收通过，并已按仓库正式流程把 `LOCALIZATION` 与 `TARGET_BIBLE` capability 升级为 `AVAILABLE`；
3. `TARGET_SCRIPT` 的正式准入状态已经由 P11 PASS 后的开发阶段明确开启；
4. 存在且仅存在一个 CURRENT `SOURCE_VIDEO_SNAPSHOT`；
5. 存在且仅存在一个 CURRENT `ADAPTATION_PLAN`；
6. 存在且仅存在一个 CURRENT `TARGET_BIBLE`；
7. 三个 CURRENT 输入属于同一条 P11 lineage：`ADAPTATION_PLAN` 与 `TARGET_BIBLE` 必须都绑定当前 `SOURCE_VIDEO_SNAPSHOT`；
8. 项目的 `target_language / target_region` 与 P11 typed content 一致。

截至当前阶段，第 2/3 项尚未满足，因此：

- POST P12 command 必须在创建 Task/ProviderJob/Artifact 前拒绝；
- GET 可以只读返回 `NOT_BUILT / CURRENT / STALE`；
- 普通产品 UI 不得出现可点击的“生成目标剧本”动作；
- 不能因为 P11 Provider 技术任务成功、P11 Artifact 已写库或 P12 单测通过就绕过人工准入；
- 不得把 `LOCALIZATION / TARGET_BIBLE / TARGET_SCRIPT` 标记为 `AVAILABLE`；
- 不得记录或伪造 P11/P12 人工 PASS。

## 3. P12 硬输入

正式 P12 的硬输入固定为：

- `CURRENT TARGET_BIBLE`
- `CURRENT ADAPTATION_PLAN`
- `CURRENT SOURCE_VIDEO_SNAPSHOT`

Professional Skill 不允许退回散落的 P5~P9 Artifact 重新拼 Source 世界，也不允许只拿 Target Bible 丢掉 Adaptation Plan。

### 3.1 Source Dialogue 真相来源

P12 的原始对白正文只允许读取 `CURRENT SOURCE_VIDEO_SNAPSHOT.episodes[*].canonical_dialogue[*]`。该列表是 P10 对已验收 P6 canonical Source Dialogue 的冻结版本。

每条输入至少保留：

- `episode_id`
- `utterance_id`
- `utterance_number`
- `start_us`
- `end_us`
- `text`
- `language`

规则：

1. `text` 是 Source Dialogue canonical 正文，必须逐字复制到 P12 typed lineage；
2. Provider 不得重新 ASR、重新 OCR、重新听写、根据视频口型猜台词、根据剧情补台词，也不得“润色” Source 正文；
3. P12 不直接读取原视频来猜对白；
4. 如果 Source Dialogue 本身需要纠错，必须回到 P6 canonical adjudication / human edit 链路，形成新的 Source revision，并使 Snapshot 与下游 Target 递归 STALE；
5. P12 不允许通过 Target 结果反向修改 Source。

## 4. Professional Skill

新增 Professional Skill：

- id: `target-script-localization`
- version: `1.0.0`
- category: `target-script`
- required capabilities: `TARGET_SCRIPT`
- required inputs: `SOURCE_VIDEO_SNAPSHOT`, `ADAPTATION_PLAN`, `TARGET_BIBLE`
- readable artifacts: 仅上述三个正式 Artifact
- output contract: `TARGET_SCRIPT`

建议执行步骤：

1. `load_current_target_inputs`
2. `freeze_canonical_dialogue_manifest`
3. `translate_dialogue`
4. `localize_dialogue`
5. `validate_dialogue_lineage`
6. `publish_target_script`

Provider 只承担目标语言语义转换，不承担 Artifact/revision/fingerprint/ID/Graph 生成。

## 5. P12 typed schema

### 5.1 Provider semantic

Provider 对每条 canonical utterance 只能返回目标侧语义字段：

```text
ProviderLocalizedDialogue
- utterance_id
- translation_text
- localization_text
- final_target_dialogue
- localization_notes[]
```

`utterance_id` 只能逐字引用服务端提供的 canonical dialogue manifest。Provider 不得返回/修改 source text、source timing、Artifact id、revision、fingerprint、target_character_id 或 voice id。

Provider 返回集合必须与 canonical Source Dialogue **一一完整覆盖**：

- 不得缺失；
- 不得重复；
- 不得创造新的 utterance；
- 不得改变顺序；
- 不得把多条 Source Dialogue 静默合并成一条；
- 不得把一条 Source Dialogue 静默拆成多条。

第一版采用严格 1:1 lineage，未来若需要字幕/配音层面的 split/merge，只能由后续独立合同显式升级，不得在 P12 v1 偷做。

### 5.2 Published Target Script

建议 `TARGET_SCRIPT` schema `1.0`：

```text
ReplicaTargetScriptContent
- schema_version = "1.0"
- title
- target_language
- target_region
- source_snapshot_artifact_id
- adaptation_plan_artifact_id
- target_bible_artifact_id
- episodes[]
  - episode_id
  - episode_order
  - dialogue[]
    - utterance_id
    - utterance_number
    - source_start_us
    - source_end_us
    - source_text
    - source_language
    - target_character_id?      # 仅从服务端可证明 lineage 时绑定
    - translation_text
    - localization_text
    - final_target_dialogue
    - localization_notes[]
```

三个文本字段必须同时存在并保持语义分层：

- `translation_text`：尽量忠实保留 Source Dialogue 的直接语义；
- `localization_text`：结合 P11 Target Bible / Adaptation Plan 完成本土文化、称谓、语气、习惯表达适配；
- `final_target_dialogue`：P12 最终批准给下游 Speaker/Voice/TTS 使用的对白正文。

不得为了预计时长在 P12 静默压缩到“看起来能塞进原镜头”。真实时长只能由后续 TTS 得到；必要的 timing adjustment 属于后续 Timing Plan。

## 6. Target Character 绑定

若 Source Snapshot 可以通过已冻结的 Source Speaker / Character lineage 唯一确定该 utterance 对应的 `source_character_id`，且 P11 Target Bible 对该 Source Character 存在唯一一对一 Target Character 映射，则服务端可确定性写入 `target_character_id`。

否则 `target_character_id = null`，不得让 P12 Provider 猜人。

`target_character_id` 只表示剧本角色 lineage，不等同于 Target Speaker/Voice。真正的 voice/speaker casting 属于后续阶段。

## 7. Provider 合同

Provider prompt 必须显式包含：

1. CURRENT `TARGET_BIBLE` typed content；
2. CURRENT `ADAPTATION_PLAN` typed content；
3. 从 CURRENT `SOURCE_VIDEO_SNAPSHOT` 确定性提取的 canonical dialogue manifest；
4. P11 preservation locks 与 dialogue localization strategy；
5. 严格 JSON Schema；
6. 禁止重新猜 Source Dialogue；
7. 禁止 Story/Beat/Scene/Shot 重排；
8. 禁止生成 Target Storyboard/TTS/Timing/Generation 内容。

Provider 响应必须经过 Pydantic strict schema + 服务端 exact utterance coverage 校验。无效响应 fail closed，不发布部分 TARGET_SCRIPT。

## 8. Task / ProviderJob / publication

任务类型：`P12_TARGET_SCRIPT_LOCALIZATION`。

正式可执行后：

1. POST command 首先重验 admission gate 与三个 CURRENT 硬输入；
2. Task 的 `input_artifact_ids` 必须固定为当前 `SOURCE_VIDEO_SNAPSHOT + ADAPTATION_PLAN + TARGET_BIBLE`；
3. `input_fingerprint` 必须包含三个 Artifact id/revision/fingerprint、target config、Professional Skill version、Provider profile、prompt/schema/contract version；
4. 外部 Provider 请求前必须先持久化 `ProviderJob`；
5. Worker 完成 Provider 调用后再次验证三硬输入仍 CURRENT 且 fingerprint 未变化；
6. publication 在单一事务中完成：旧 CURRENT TARGET_SCRIPT 递归 STALE、新 ArtifactNode、新 typed revision、provenance、Artifact Graph、SUPERSEDES、execution plan invalidation；
7. 任一步失败必须整体 rollback，旧 CURRENT TARGET_SCRIPT 保持不被半发布覆盖。

## 9. Artifact Graph

新 TARGET_SCRIPT 至少建立：

- `SOURCE_VIDEO_SNAPSHOT -> TARGET_SCRIPT : DERIVED_FROM`
- `ADAPTATION_PLAN -> TARGET_SCRIPT : USES`
- `TARGET_BIBLE -> TARGET_SCRIPT : USES`
- `new TARGET_SCRIPT -> previous TARGET_SCRIPT : SUPERSEDES`（存在旧 revision 时）

因此任意硬输入 STALE 都必须通过现有 graph invalidation 递归使 TARGET_SCRIPT STALE。

## 10. API

工程预实现允许建立：

- `POST /api/v3/projects/{project_id}/commands/target-script`
- `GET /api/v3/projects/{project_id}/target-script`
- `GET /api/v3/projects/{project_id}/target-script/revisions`

当前阶段行为：

- 两个 GET 必须只读，无 Task/ProviderJob/Artifact 写副作用；
- POST 必须 fail closed，返回稳定的 admission error（例如 `P12_NOT_ADMITTED`），且 Task/ProviderJob/Artifact 计数不变；
- P11 PASS 后只能通过正式 capability/admission 变更解除门禁，不允许 UI 或请求参数提供隐藏 bypass。

## 11. Root Replica Skill

`project.replica` 的 `target_script` step 必须收紧为：

- capabilities: `TARGET_SCRIPT`
- requires: `SOURCE_VIDEO_SNAPSHOT`, `ADAPTATION_PLAN`, `TARGET_BIBLE`
- produces: `TARGET_SCRIPT`

其 description 必须明确：只在已验收 Target Bible / Adaptation Plan 下，以冻结 canonical Source Dialogue 生成 Translation → Localization → Final Target Dialogue。

在 `TARGET_SCRIPT` capability 仍为 `PLANNED` 时，Execution Plan 必须继续显示 WAITING_CAPABILITY/阻断，不得变成可执行。

## 12. UI 工程准备

可以预先实现 Target Script 数据读取、展示组件与 API client，但普通产品流程在 P11 未 PASS 时：

- 不显示可执行“生成目标剧本”按钮；
- 不自动 POST；
- 不因页面挂载产生 Task/ProviderJob；
- 可在工程/测试层验证未来 CURRENT Target Script 的只读展示；
- UI 文案使用业务词“目标剧本 / 原对白 / 直译 / 本土化 / 最终对白”，不暴露 Artifact/fingerprint/provenance/ProviderJob 等工程词。

## 13. 自动化测试最低覆盖

P12 工程预实现至少覆盖：

1. Professional Skill contract 与 Root Replica 三硬输入；
2. `TARGET_SCRIPT` capability 仍为 `PLANNED`；
3. P11 未 PASS 时 POST `target-script` fail closed 且零写副作用；
4. GET read-only；
5. 非 REPLICA fail closed；
6. 三硬输入缺失/STALE/lineage 不一致 fail closed（在未来 admission 打开后的服务层测试中可注入准入状态）；
7. canonical dialogue exact coverage；
8. Source `text/start_us/end_us/utterance_id` 原样复制，Provider 无权覆盖；
9. Translation / Localization / Final Target Dialogue 三层都存在；
10. Target Character 只能确定性 lineage 绑定，不能 Provider 猜；
11. ProviderJob before remote call；
12. publication revision/fingerprint/provenance/三输入 Graph/SUPERSEDES 完整；
13. 任一硬输入新 revision 递归 STALE TARGET_SCRIPT；
14. UI 当前普通流程没有 P12 执行动作；
15. P12 不产生 TARGET_STORYBOARD / TARGET_AUDIO / TIMING_PLAN / generation Artifact。

## 14. 当前阶段完成定义

本轮“P12 预实现完成”只表示：

- 合同已冻结；
- Professional Skill / schema / service-provider / API / migration / tests / UI preparation 已有工程实现并通过 CI；
- execution gate 正确阻断真实 P12；
- capability 仍为 PLANNED。

它**不表示**：

- P11 已 PASS；
- P12 已正式准入；
- P12 已跑过真实 Provider；
- P12 已真实人工验收；
- `LOCALIZATION / TARGET_BIBLE / TARGET_SCRIPT` 已 AVAILABLE。

只有用户明确完成 P11 真实人工验收并给出 P11 PASS 后，才能进入下一次“解除 P12 admission gate + 真实 Provider + P12 人工验收”的工作；在那之前不得伪造或提前宣布 PASS。
