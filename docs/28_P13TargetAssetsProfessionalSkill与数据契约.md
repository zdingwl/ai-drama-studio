# P13 Target Assets / 目标资产：Professional Skill 与数据契约

> 日期：2026-09-11  
> 状态：**P13 正式工程契约；工程实现与真实人工验收尚未完成。**  
> 前置：`docs/27_P12最终验收与后续阶段准入评估.md` 已确认 `P12 PASS`、`TARGET_SCRIPT = AVAILABLE`，并要求后续 `TARGET_ASSETS / TTS / TIMING / STORYBOARD / Generation / Post` 在各自正式契约与真实验收前继续保持 `PLANNED`。  
> 优先级：本文只新增 P13 合同；不改变 P10/P11/P12 已验收事实，不准入 P14 或任何后续阶段。

---

## 1. P13 正式名称与职责

正式名称：

```text
P13 Target Assets / 目标资产
```

P13 负责把 P11 `TARGET_BIBLE` 已确定的人物、场景、关键道具目标设定，物化为后续 Target Storyboard / Video Generation 可以通过稳定 ID 引用、版本化、追溯和复用的正式视觉资产包：

```text
CURRENT TARGET_BIBLE
        ↓
Professional Skill: replica-target-assets
        ↓
Provider visual realization semantics
        ↓
服务端 deterministic binding / validation / composition
        ↓
NEEDS_REVIEW candidate
        ↓ 用户显式确认
CURRENT TARGET_ASSETS
```

核心语义：

```text
Target Bible  = semantic truth
Target Assets = visual realization
```

P13 的重点不是生成一张“好看图片”，而是建立跨 Shot、跨 GenerationSegment 可重复引用的视觉身份约束。正式 Target Asset 是一个 **visual identity packet**：稳定绑定一个 P11 Target entity，包含可执行的视觉基线、连续性约束、生成指导、negative constraints，以及可选 reference media 槽位。

P13 不得：

- 修改或重新生成 `SOURCE_VIDEO_SNAPSHOT`；
- 修改或重新生成 `ADAPTATION_PLAN`；
- 修改或重新生成 `TARGET_BIBLE`；
- 修改或重新生成 `TARGET_SCRIPT`；
- 生成 Target Voice / TTS / Actual Speech Duration / Timing Plan；
- 生成正式 Target Storyboard / Generation Segment；
- 进入 Video Generation / QC / Selection / Lip Sync / Post / Final Output。

---

## 2. 硬输入与准入条件

### 2.1 唯一正式硬输入

P13 v1 正式硬输入保持 Root Replica Skill 当前定义：

```text
CURRENT TARGET_BIBLE
```

不得静默增加：

```text
SOURCE_VIDEO_SNAPSHOT
ADAPTATION_PLAN
TARGET_SCRIPT
```

为硬输入。

理由：

1. P11 `TARGET_BIBLE` 已是 Target 世界的人物 / 场景 / 道具 semantic truth；
2. P11 已为 Target Character / Scene / Prop 建立稳定独立 Target identity，并保留 Source lineage；
3. P13 的职责是把这些已确定 Target identity 做视觉实现，而不是重新打开 Source 世界或对白语义；
4. `TARGET_SCRIPT` 的对白内容不应导致人物脸型、场景布局、关键道具视觉身份因一句台词变化而全部 STALE；
5. 后续若真实生产证明某类资产必须直接读取额外 Artifact，必须通过新的 P13 contract/schema version 显式升级，不能在 v1 中以“可能有帮助”为由隐式读取。

### 2.2 准入

P13 v1 只允许：

```text
ProjectType.REPLICA
```

并要求：

```text
TARGET_BIBLE capability = AVAILABLE
CURRENT TARGET_BIBLE 存在且 typed revision 可解析
TARGET_BIBLE.target_language / target_region 与 Project 当前配置一致
Target Character / Scene / Prop id 集合唯一且结构合法
```

若 `TARGET_BIBLE` 缺失或 STALE，P13 command fail closed。

P13 工程可以实现、测试和进入真实验收，但在用户明确 `P13 PASS` 前：

```text
TARGET_ASSETS = PLANNED
```

---

## 3. Professional Skill

新增：

```text
skills/professional/replica-target-assets/
  SKILL.md
  manifest.json
```

正式版本：

```text
replica-target-assets@1.0.0
```

运行契约：

```text
P13_SCHEMA_VERSION            = 1.0
P13_PROMPT_VERSION            = p13-replica-target-assets-v1
P13_TARGET_ASSET_CONTRACT     = replica-target-visual-identity-v1
P13_ENTITY_BINDING_CONTRACT   = target-bible-entity-binding-v1
P13_REVIEW_CONTRACT           = human-target-asset-approval-v1
```

Skill 依赖：

```text
required_inputs       = [TARGET_BIBLE]
required_capabilities = [TARGET_ASSETS]
output_contracts      = [TARGET_ASSETS]
```

执行步骤：

```text
1. load_target_bible
   读取 CURRENT TARGET_BIBLE，建立权威 entity manifest

2. design_visual_identity_packets
   Provider 只生成 Character / Scene / Prop 的视觉实现语义

3. deterministic_compose_candidate
   服务端绑定稳定 Target Asset ID、注入 Target Bible identity、严格覆盖校验

4. stage_for_human_review
   持久化 NEEDS_REVIEW candidate；不创建 CURRENT TARGET_ASSETS Artifact

5. publish_accepted_assets
   用户显式确认后，重新校验 Target Bible 仍 CURRENT，原子发布 TARGET_ASSETS
```

---

## 4. `TARGET_ASSETS` typed schema

正式 Artifact：

```text
ArtifactType.TARGET_ASSETS
namespace = TARGET
```

正式内容：

```text
ReplicaTargetAssetsContent
├─ schema_version = "1.0"
├─ title = "目标资产"
├─ target_bible_artifact_id
├─ target_language
├─ target_region
├─ visual_style
├─ characters[]
├─ scenes[]
└─ props[]
```

三类资产必须完整一对一覆盖 CURRENT `TARGET_BIBLE` 中同类 entity。P13 v1 不允许 Provider 新增、删除、合并或拆分 Target entity。

### 4.1 通用 Target Asset 字段

每个正式资产至少具有：

```text
target_asset_id
target_asset_revision
asset_type               # CHARACTER | SCENE | PROP
target_entity_id
display_name
asset_fingerprint
continuity_constraints[]
generation_guidance[]
negative_constraints[]
reference_media[]
```

`reference_media[]` 预留：

```text
reference_id
role                      # FACE / FULL_BODY / WARDROBE / LAYOUT / LANDMARK / DETAIL / OTHER
uri
mime_type
sha256
width
height
provider_job_id
```

v1 当前仓库没有已接入、已验收的生成式图片 Provider，因此 **P13 v1 Provider 不得伪造 `uri/sha256/width/height`**。当前正式资产首先以 typed visual identity packet 成立；未来真实图片 Provider 接入时，在不改变 `target_asset_id` 的前提下通过新的 contract/schema version 增加真实 reference media。

### 4.2 Character Asset

```text
TargetCharacterAsset
├─ target_asset_id
├─ target_asset_revision
├─ target_character_id
├─ display_name
├─ identity_direction
├─ demographic_direction
├─ face_direction
├─ hair_direction
├─ body_direction
├─ wardrobe_baseline
├─ signature_visual_features[]
├─ continuity_constraints[]
├─ generation_guidance[]
├─ negative_constraints[]
└─ reference_media[]
```

规则：

- `target_character_id` 必须逐字等于 CURRENT Target Bible 中已有 ID；
- identity / demographic / face / hair / body / wardrobe 只能具体化 `localized_identity + appearance_direction + visual_style`，不能改变人物剧情身份或故事功能；
- 服装允许给出明确 baseline，但不得在 P13 擅自设计逐 Scene/逐 Shot wardrobe change；
- signature features 必须服务跨镜 ReID，而不是堆审美形容词。

### 4.3 Scene Asset

```text
TargetSceneAsset
├─ target_asset_id
├─ target_asset_revision
├─ target_scene_id
├─ display_name
├─ spatial_identity
├─ layout
├─ architecture_style
├─ interior_exterior_style
├─ materials_palette[]
├─ fixed_landmarks[]
├─ lighting_baseline
├─ time_of_day_baseline
├─ continuity_constraints[]
├─ generation_guidance[]
├─ negative_constraints[]
└─ reference_media[]
```

规则：

- P13 固化场景空间身份、布局和可连续识别 landmark；
- 不得改变 Target Bible `localized_setting / visual_direction` 的场景功能；
- `time_of_day_baseline` 是视觉基线，不得据此重排剧情时间或 Scene order。

### 4.4 Prop Asset

```text
TargetPropAsset
├─ target_asset_id
├─ target_asset_revision
├─ target_prop_id
├─ display_name
├─ visual_form
├─ materials[]
├─ color_palette[]
├─ scale_reference
├─ functional_identity
├─ signature_visual_features[]
├─ continuity_constraints[]
├─ generation_guidance[]
├─ negative_constraints[]
└─ reference_media[]
```

规则：

- `functional_identity` 只能实现 Target Bible 已确定的 `localized_form` 与剧情功能，不得把关键道具换成改变剧情功能的新物件；
- scale / material / color 是后续跨镜一致性约束；
- 不得用 P13 视觉资产反向覆盖 P11 Target Prop semantic truth。

---

## 5. Target Bible entity → Target Asset 稳定绑定

P13 v1：

```text
每个 Target Character → exactly one Target Character Asset
每个 Target Scene     → exactly one Target Scene Asset
每个 Target Prop      → exactly one Target Prop Asset
```

Provider 返回语义时只允许引用当前 entity ID；正式 `target_asset_id` 由服务端生成。

稳定 ID：

```text
target_asset_id = stable_hash(
  project_id,
  asset_type,
  target_entity_id,
  P13_ENTITY_BINDING_CONTRACT
)
```

因此同一个 P11 Target entity 在重新生成 / 替换视觉实现时：

```text
target_asset_id 不变
visual packet / asset_fingerprint 可变
target_asset_revision 递增
```

若上游 P11 产生新的 Target entity ID，则它是新的 Target identity，必须得到新的 `target_asset_id`；不得把旧资产静默移植给新 identity。

---

## 6. Revision / CURRENT / STALE

正式 `TARGET_ASSETS` 使用通用 `ArtifactNode`：

```text
revision
input_fingerprint
skill_id / skill_version
validity = CURRENT | STALE
is_current
```

同时每个 packet 有：

```text
target_asset_revision
asset_fingerprint
```

新 publication set 与上一个 CURRENT bundle 比较：

- 相同 `target_asset_id` 且 `asset_fingerprint` 未变化：保留原 `target_asset_revision`；
- 相同 `target_asset_id` 但视觉实现变化：`target_asset_revision + 1`；
- 新 `target_asset_id`：revision 从 1 开始；
- 旧 Target entity 不再存在时，不把旧 packet 带入新 bundle；旧历史仍在 STALE `TARGET_ASSETS` revision 中可追溯。

正式下游必须至少引用：

```text
target_assets_artifact_id
target_asset_id
target_asset_revision
```

---

## 7. Provider 与 deterministic 层责任边界

当前仓库已验收的 Target Provider Adapter 是：

```text
Volcengine Ark text-only reasoning
Local vLLM text-only reasoning
```

P13 v1 复用同一项目 reasoning-runtime 选择，但 Professional Skill 仍只依赖 capability，不绑定具体模型。

Provider 负责严格 typed **视觉实现语义**，不负责：

- 创建正式 Target Asset ID；
- 创建 Artifact / revision；
- 改 Target Bible；
- 生成 Source / Target identity；
- 伪造图片 URI / sha256；
- 发布 CURRENT；
- 进入 Storyboard / Video Generation。

服务端确定性完成：

```text
Target Bible exact entity manifest
Target Asset stable ID
target_entity_id binding
Target Bible identity/display_name 注入
exact coverage validation
single-asset fingerprint
per-asset revision calculation
bundle fingerprint
candidate persistence
human-review gate
Artifact / typed revision / provenance / graph publication
stale propagation
```

---

## 8. Candidate / 人工确认边界

**Provider 生成结果不得未经确认直接标记 CURRENT。**

P13 引入 staging row：

```text
TargetAssetsCandidate
├─ id
├─ project_id
├─ target_bible_artifact_id
├─ generated_by_task_id
├─ generation_sequence
├─ input_fingerprint
├─ schema_version
├─ content_json
├─ provenance_json
├─ review_status = NEEDS_REVIEW | ACCEPTED | REJECTED | SUPERSEDED
├─ review_reason
├─ reviewed_at
└─ created_at
```

行为：

```text
Provider Task SUCCEEDED
→ strict schema / exact coverage / Target Bible consistency PASS
→ candidate = NEEDS_REVIEW
→ 不创建 CURRENT TARGET_ASSETS
```

只有显式人工确认：

```text
POST .../target-assets/candidates/{candidate_id}/commands/accept
```

才发布正式 `TARGET_ASSETS`。

人工拒绝：

```text
POST .../target-assets/candidates/{candidate_id}/commands/reject
```

只把 candidate 标记为 REJECTED；不覆盖旧 CURRENT `TARGET_ASSETS`。

如果已有旧 CURRENT 资产，新 candidate 生成失败或被拒绝，旧 CURRENT 继续保持可用；如果上游 Target Bible 已变化导致旧正式资产 STALE，拒绝新 candidate 不会让旧 STALE 资产重新 CURRENT。

---

## 9. Artifact Graph

P13 正式 publication 最少建立：

```text
TARGET_BIBLE --DERIVED_FROM--> TARGET_ASSETS
new TARGET_ASSETS --SUPERSEDES--> old TARGET_ASSETS
```

P13 v1 **不增加** `TARGET_SCRIPT → TARGET_ASSETS`，因为 Target Script 不是硬输入。

`TARGET_ASSETS` 与其内部 Target Character / Scene / Prop packet 的绑定记录在 typed content；当前 Artifact Graph 没有为每个 Target Bible 内嵌 entity 单独建立 ArtifactNode，因此不伪造 entity-level graph node。

后续 Target Storyboard publication 必须建立：

```text
TARGET_ASSETS --USES--> TARGET_STORYBOARD
```

并在 `TargetStoryboardShot` 内使用 `target_asset_id + target_asset_revision` 引用具体 Character / Scene / Prop asset。这里只定义消费合同，不在 P13 实现 Storyboard。

---

## 10. Provenance

P13 candidate 与正式 revision 至少记录：

```text
target_bible_artifact_id
target_bible_revision
target_bible_fingerprint
target_language
target_region
professional_skill_id / version
provider / model
provider_job_id
payload_fingerprint
prompt_version
schema_version
target_asset_contract
entity_binding_contract
review_contract
generated_by_task_id
candidate_id
supersedes_artifact_id
```

正式 publication 额外记录：

```text
reviewed_by = USER_EXPLICIT_ACTION
reviewed_at
review_reason
```

不得保存 API Key / Authorization / secret / 原始敏感 Provider payload。

---

## 11. STALE propagation

因为正式 graph 为 `TARGET_BIBLE → TARGET_ASSETS`，任何上游 `TARGET_BIBLE` 新 revision 替代旧 CURRENT 后：

```text
旧 TARGET_ASSETS → STALE
旧 TARGET_ASSETS 下游 → 递归 STALE
绑定旧 Target Bible 的未审核 candidate → 不可 accept，并在下一次写操作时标 SUPERSEDED
```

GET 不自动重建或修改 candidate 状态。

新 candidate 通过人工确认后：

```text
old TARGET_ASSETS → STALE
new TARGET_ASSETS → CURRENT
new --SUPERSEDES--> old
```

依赖旧 `TARGET_ASSETS` 的正式下游 Artifact 必须递归 STALE。

因为 P13 v1 不读取 `TARGET_SCRIPT`：

```text
TARGET_SCRIPT 新 revision
!=
TARGET_ASSETS 自动 STALE
```

这避免对白局部修改无意义地使视觉资产全部失效。

---

## 12. API command / read 行为

生成候选：

```text
POST /api/v3/projects/{project_id}/commands/target-assets
Idempotency-Key: ...
```

显式重新生成候选：

```text
POST /api/v3/projects/{project_id}/commands/target-assets/regenerate
Idempotency-Key: ...
```

人工确认：

```text
POST /api/v3/projects/{project_id}/target-assets/candidates/{candidate_id}/commands/accept
```

人工拒绝：

```text
POST /api/v3/projects/{project_id}/target-assets/candidates/{candidate_id}/commands/reject
```

accept / reject 必须携带 `expected_target_bible_artifact_id` 与 `expected_candidate_revision` 或等价乐观并发字段；Target Bible 或 candidate 状态已变化时返回 409 fail closed。

只读：

```text
GET /api/v3/projects/{project_id}/target-assets
GET /api/v3/projects/{project_id}/target-assets/revisions
GET /api/v3/projects/{project_id}/target-assets/candidates
```

GET 禁止创建 Task / ProviderJob、调 Provider、生成 candidate、自动 accept、创建 Artifact、自动修复 STALE 或重编 Plan。

---

## 13. Provider failure / partial failure / retry / idempotency

所有外部 Provider 调用必须：

```text
Task RUNNING
↓
ProviderJob RUNNING 持久化 + commit
↓
remote call
```

ProviderJob `artifact_id` 绑定 CURRENT `TARGET_BIBLE`。

以下任一情况不产生 `NEEDS_REVIEW` candidate：

- Target Bible 缺失 / STALE / 多 CURRENT；
- typed Target Bible parse 失败；
- Provider 输出未知 Target entity id；
- Character / Scene / Prop 任一集合漏项、重复、增项；
- Provider 输出正式 asset id / Artifact id 等不属于其权限的字段；
- 字段越界或 strict schema 非法；
- Provider incomplete / transport failure；
- Task 执行期间 Target Bible / Provider profile / Skill contract 改变。

P13 v1 publication unit 是完整资产包；任一实体失败都使整个候选失败，不得发布半套 CURRENT。

沿用 P4 finite retry / cancel / resume，默认最多 3 次。失败重试不覆盖旧 CURRENT 正式资产。

同一 CURRENT TARGET_BIBLE + Skill / Provider / contract 的普通重复提交通过 Task business key 幂等复用。显式 `regenerate` 由服务端确定性递增 `generation_sequence`，将其纳入 input fingerprint / business key，从而创建新的 Task / ProviderJob / candidate；不能把换 Idempotency-Key 当作隐式重生成。

---

## 14. 后续 Storyboard / Generation 消费合同（只定义，不实现）

后续正式消费者必须通过 typed ref 使用 P13 资产：

```text
TargetAssetRef
├─ target_assets_artifact_id
├─ target_asset_id
├─ target_asset_revision
├─ asset_type
└─ target_entity_id
```

Target Storyboard：

- 每个目标镜头按 Target Bible entity 绑定相应 Character / Scene / Prop `TargetAssetRef`；
- 同一人物跨镜默认引用同一 `target_asset_id + target_asset_revision`；
- wardrobe / lighting variation 必须是明确 variation overlay，不得悄悄替换 base identity。

Video Generation：

- GenerationSegment 读取正式 CURRENT `TARGET_ASSETS` / Target Storyboard；
- Provider prompt/reference-media 由正式 asset packet 确定性展开；
- Generation Attempt 不能反向更新 Target Asset；
- 需要改变人物脸、场景布局、道具形态时，应回到 Target Asset 新 revision，而不是在某个 Generation prompt 里偷偷漂移。

P13 不实现上述后续 Artifact。

---

## 15. UI / 用户人工确认边界

P13 产品工作区名称：

```text
目标资产
```

普通用户至少能看到：

- Character / Scene / Prop 分组；
- 每项绑定的 Target Bible 名称；
- 视觉身份摘要与关键连续性约束；
- generation guidance / negative constraints；
- candidate 状态：待确认 / 已确认 / 已拒绝；
- 正式资产状态：未生成 / CURRENT / STALE；
- “生成目标资产 / 重新生成候选”；
- “确认并作为正式资产”与“拒绝候选”。

页面加载只 GET。只有显式生成按钮才 POST Provider Task；只有显式确认按钮才发布 CURRENT `TARGET_ASSETS`。

若未来接入图片 Provider，UI 必须展示真实 reference media 供人工视觉核对后再 accept，不能仅因 ProviderJob SUCCEEDED 自动确认。

---

## 16. 自动验收最低覆盖

P13 工程测试至少证明：

1. Professional Skill 可机器加载，required input **只有 TARGET_BIBLE**；
2. `TARGET_ASSETS` capability 仍为 `PLANNED`；
3. P13 只允许 REPLICA；
4. GET 全部只读；
5. command 缺 / STALE Target Bible fail closed；
6. ProviderJob 在 remote call 前已持久化；
7. Provider exact coverage Character / Scene / Prop，未知 / 漏 / 重复 id 全拒绝；
8. Provider 无权生成正式 asset id / Artifact id；
9. Target Asset ID 对同一 Target entity 稳定；
10. Character / Scene / Prop schema 能表达跨镜 continuity，而不是单图 aesthetic prompt；
11. candidate 生成后没有 CURRENT TARGET_ASSETS；
12. accept 前重新校验 Target Bible / candidate；
13. reject 不覆盖旧 CURRENT；
14. accept 原子发布 typed revision / provenance / graph；
15. `TARGET_BIBLE --DERIVED_FROM--> TARGET_ASSETS` 完整；
16. 重生成后 stable asset id 保持、变更 asset revision 递增；
17. 新 CURRENT Target Bible 使旧正式 assets STALE，并使旧 candidate 不可 accept；
18. 新 TARGET_SCRIPT revision 不会无依据地使 TARGET_ASSETS STALE；
19. 新 TARGET_ASSETS publication 会递归 stale 已存在的依赖旧资产下游；
20. 相同普通 command 幂等，显式 regeneration 才产生新 candidate；
21. Provider / publication failure 不制造假成功或半套 CURRENT；
22. backend compile / FastAPI import / alembic upgrade head / pytest 全绿；
23. frontend typecheck / unit / build 全绿。

---

## 17. P13 真实人工验收标准

工程实现与自动测试通过后，仍必须基于已经 P11/P12 PASS 的真实 REPLICA 项目完成真实 Provider / UI / 内容质量验收。

至少确认：

```text
[ ] 页面 GET / 刷新无副作用
[ ] 一次显式“生成目标资产”产生真实 ProviderJob 与 NEEDS_REVIEW candidate
[ ] Provider 输出完整覆盖真实 Target Character / Scene / Prop
[ ] Character 身份方向、脸/发型/体态/服装基线足以保持跨镜一致
[ ] Scene 空间身份、layout、landmark、材质与 lighting baseline 足以保持跨镜一致
[ ] Prop form/material/color/scale/function 足以保持跨镜一致
[ ] 所有 packet 没有改变 Target Bible 人物/场景/道具语义身份
[ ] 未经确认时没有 CURRENT TARGET_ASSETS
[ ] 用户显式确认后才发布 CURRENT TARGET_ASSETS
[ ] provenance / ProviderJob / revision / fingerprint / Artifact Graph 可审计
[ ] 显式重新生成产生新 candidate，不覆盖已确认正式资产
[ ] 拒绝 candidate 后旧 CURRENT 继续可用
[ ] 接受新版后 asset stable id 保持，变化项 revision 正确升级
[ ] 安全地产生新 Target Bible revision 后旧 TARGET_ASSETS 正确 STALE
[ ] GET 不自动重建 STALE
[ ] 未创建 TTS / Timing / Target Storyboard / Generation / QC / Post Artifact
[ ] 用户最终明确回复 `P13 PASS`
```

若当前 v1 没有真实 reference-media Provider，则验收只能确认 **typed visual identity packet 的专业质量与工程合同**；不得把不存在的图片宣称为已生成。以后接入图片 Provider 时必须独立做 Provider qualification 和视觉 reference-media 人工验收。

在以上真实人工验收完成、且用户明确给出：

```text
P13 PASS
```

之前，正式状态必须保持：

```text
TARGET_ASSETS = PLANNED
```

P13 工程测试成功、ProviderJob SUCCEEDED、candidate NEEDS_REVIEW 或用户在页面预览候选，都不等于 P13 PASS。

---

## 18. P13 完成后的阶段边界

即使 P13 最终 PASS，本文件也**不自动准入** P14。

届时最多允许另起状态收口提交评估：

```text
TARGET_ASSETS = AVAILABLE
```

而以下仍保持独立阶段：

```text
TTS
TIMING
STORYBOARD
VIDEO_GENERATION
QC_SELECTION
LIP_SYNC
POST_PRODUCTION
```

下一阶段必须重新读取最新 main，并再次先立正式合同。
