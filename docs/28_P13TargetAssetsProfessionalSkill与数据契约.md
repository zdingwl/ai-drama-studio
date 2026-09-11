# P13 Target Assets Professional Skill 与数据契约

> 状态：P13 正式工程契约（实现前基线）  
> 日期：2026-09-11  
> 上游验收基线：`docs/27_P12最终验收与后续阶段准入评估.md`  
> 本文只覆盖 P13。P12 的既有 PASS 结论继续有效；本文不准入 P14 或任何后续阶段。

---

## 0. 本文优先级与阶段状态

对于 **P13 Target Assets / 目标资产**，本文是当前最高优先级契约；若 `docs/00 ~ docs/27` 中存在与 P13 冲突的旧口径，以本文为准。P10/P11/P12 已验收事实仍以各自最终验收文档为准。

当前阶段门禁：

```text
P12 PASS
TARGET_SCRIPT = AVAILABLE

P13 = FORMALLY_ADMITTED_FOR_IMPLEMENTATION_AND_REAL_VALIDATION
TARGET_ASSETS = PLANNED
```

`P13 = FORMALLY_ADMITTED...` 只表示在 P12 PASS 后允许实现和真实验证 P13，不等于 P13 PASS。只有用户明确回复：

```text
P13 PASS
```

后，才允许评估把 `TARGET_ASSETS` capability 从 `PLANNED` 升为 `AVAILABLE`。

---

## 1. 正式名称与职责

P13 正式名称：

```text
Replica Target Assets / 复刻目标资产
```

Professional Skill 建议固定为：

```text
replica-target-assets@1.0.0
```

P13 的职责是把 P11 `TARGET_BIBLE` 中已经确定的 Target Character / Scene / Prop **语义身份**，实现为后续 Target Storyboard / Video Generation 能稳定引用、版本化、追溯、复用的正式视觉资产。

核心关系：

```text
TARGET_BIBLE = semantic truth
TARGET_ASSETS = visual realization
```

P13 不重新决定人物故事功能、Scene 功能、Prop 功能、目标世界或对白内容；它只在 P11 语义真值范围内把视觉身份具体化。

P13 的成功标准不是“生成了几张好看的图”，而是：

1. 每个正式 Target entity 都有稳定可引用的 Target Asset identity；
2. 视觉规格和 reference media 能约束跨镜一致性；
3. 每次生成、替换、升级均可审计且不会静默覆盖历史；
4. Provider 结果必须先经过 strict validation 和用户显式确认，才能发布为 CURRENT `TARGET_ASSETS`；
5. 后续阶段只通过 `target_asset_id` / formal reference media 消费资产，不重新猜人物、场景、道具视觉身份。

---

## 2. P13 严格阶段边界

### 2.1 P13 可以做

```text
Target Character Assets
Target Scene Assets
Target Prop Assets
TARGET_ASSETS typed Artifact
Visual asset specification
Reference sheet image generation
Reference media immutable storage
Professional Skill
Provider adapter / ProviderJob
Candidate review + explicit approval
Artifact Graph / provenance / revision
CURRENT / STALE
API / UI / tests
P13 人工验收入口
```

### 2.2 P13 禁止做

```text
Target Voice
TTS
Actual Speech Duration
Timing Plan
Target Storyboard
Generation Segments
Video Generation
QC / Selection
Lip Sync
Post Production
Final Output
```

P13 也不得重新生成、修改或反向覆盖：

```text
SOURCE_VIDEO_SNAPSHOT
ADAPTATION_PLAN
TARGET_BIBLE
TARGET_SCRIPT
```

---

## 3. 正式硬输入与准入条件

### 3.1 唯一硬输入

P13 正式硬输入保持 Root Replica Skill 当前定义，不扩大：

```text
CURRENT TARGET_BIBLE
```

Root step 保持：

```text
requires: TARGET_BIBLE
produces: TARGET_ASSETS
capability: TARGET_ASSETS
```

### 3.2 为什么不把 SOURCE_VIDEO_SNAPSHOT 设为硬输入

P13 不直接读取 `SOURCE_VIDEO_SNAPSHOT`。

理由：

- P11 已经把 Source Character / Scene / Prop lineage 冻结到 Target Bible；
- P13 的真值边界是 Target Bible，而不是重新观察 Source 世界；
- 直接读 Snapshot 会让 P13 有机会绕过 P11 Target identity 或重新解释 Source 视觉事实；
- `SOURCE_VIDEO_SNAPSHOT -> TARGET_BIBLE -> TARGET_ASSETS` Graph lineage 已能提供完整上游追溯与 stale propagation。

如未来确实需要“保持原演员脸”“保留原场景建筑”等 Source visual lock，必须先升级正式契约，由上游显式提供可消费的 visual reference contract；不能在 P13 v1 静默读取 Snapshot。

### 3.3 为什么不把 TARGET_SCRIPT 设为硬输入

P13 不直接读取 `TARGET_SCRIPT`。

Target Script 的正式职责是目标对白；人物、场景、道具视觉 identity 已在 Target Bible 确定。让 P13 依赖 Target Script 会把视觉资产与对白 revision 不必要耦合，使普通对白重生成把视觉资产标成 STALE。

P12 PASS / `TARGET_SCRIPT = AVAILABLE` 是 **阶段准入事实**，不是 P13 的 runtime Artifact hard input。

### 3.4 执行准入

P13 command 执行前必须满足：

```text
project_type == REPLICA
P13_FORMALLY_ADMITTED == true
TARGET_BIBLE capability == AVAILABLE
TARGET_SCRIPT capability == AVAILABLE   # 证明 P12 已 PASS；不是 Artifact input
存在且只有一个 CURRENT TARGET_BIBLE
TARGET_BIBLE typed revision 可解析
```

`TARGET_ASSETS` capability 在 P13 验收期间仍然 `PLANNED`，不能把它自身的 availability 当作执行开关；执行开关使用独立 P13 formal-admission gate，沿用 P12 的阶段准入模式。

---

## 4. Target Asset Identity 与绑定规则

### 4.1 已有 Target entity identity 是权威身份

P13 必须直接消费 P11 已发布：

```text
target_character_id
target_scene_id
target_prop_id
```

Provider 不得生成、修改或替换这些 ID。

### 4.2 稳定 target_asset_id

服务端确定性生成：

```text
target_asset_id = stable_id(
  asset_kind,
  target_entity_id
)
```

v1 不把 Provider、模型、prompt、图片内容、Artifact revision 放入 `target_asset_id`。

因此只要 Target entity identity 没变，同一人物 / 场景 / 道具在 P13 多次重新生成、替换、升级中始终使用相同 `target_asset_id`。

推荐前缀：

```text
Target Character Asset -> tasset_chr_...
Target Scene Asset     -> tasset_scn_...
Target Prop Asset      -> tasset_prop_...
```

### 4.3 绑定必须一一覆盖

首次生成正式候选时：

```text
Target Bible characters <-> Character Assets 1:1 exact coverage
Target Bible scenes     <-> Scene Assets     1:1 exact coverage
Target Bible props      <-> Prop Assets      1:1 exact coverage
```

禁止：

- Provider 漏实体；
- Provider 增实体；
- 重复 target entity id；
- 一个 asset 绑定多个 Target entity；
- 用 Source ID 代替 Target ID。

---

## 5. TARGET_ASSETS typed schema

正式 Artifact 内容：

```text
ReplicaTargetAssetsContent
├── schema_version
├── title
├── target_bible_artifact_id
├── target_bible_revision
├── target_language
├── target_region
├── visual_style
├── global_continuity_constraints[]
├── character_assets[]
├── scene_assets[]
└── prop_assets[]
```

所有数组都必须 strict typed，不允许把未校验 Provider JSON 原样塞进 Artifact。

### 5.1 共用 Asset fields

每个正式 Asset 至少包含：

```text
target_asset_id          # stable business identity
asset_kind               # CHARACTER | SCENE | PROP
asset_revision           # entity-level revision，>= 1
target_entity_id         # P11 Target entity id
display_name             # 服务端从 Target Bible 复制
semantic_anchor          # 服务端从 Target Bible 复制的只读语义锚点
continuity_constraints[] # P11 rules + P13 visual-specific constraints
generation_guidance[]    # 后续 Storyboard / Generation 可消费的视觉指导
negative_constraints[]   # 明确禁止漂移项
reference_assets[]       # immutable formal reference media
```

父 `TARGET_ASSETS` Artifact 的 `CURRENT / STALE` 是正式有效性真值。单个 asset 的 `asset_revision` 表示该稳定 `target_asset_id` 的视觉版本，不另造独立 CURRENT ArtifactNode。

### 5.2 Character Asset

```text
ReplicaTargetCharacterAsset
├── target_asset_id
├── asset_revision
├── target_character_id
├── display_name
├── localized_identity       # server copy from Target Bible
├── appearance_direction     # server copy from Target Bible
├── face_identity
├── hair_identity
├── body_silhouette
├── wardrobe_baseline
├── signature_features[]
├── palette_materials[]
├── continuity_constraints[]
├── generation_guidance[]
├── negative_constraints[]
└── reference_assets[]
```

目标是形成后续生成真正能稳定引用的“视觉身份”，而不是只写审美形容词。

### 5.3 Scene Asset

```text
ReplicaTargetSceneAsset
├── target_asset_id
├── asset_revision
├── target_scene_id
├── display_name
├── localized_setting       # server copy
├── visual_direction       # server copy
├── spatial_identity
├── layout
├── architecture_style
├── materials_palette[]
├── fixed_landmarks[]
├── lighting_baseline
├── time_of_day_baseline
├── continuity_constraints[]
├── generation_guidance[]
├── negative_constraints[]
└── reference_assets[]
```

### 5.4 Prop Asset

```text
ReplicaTargetPropAsset
├── target_asset_id
├── asset_revision
├── target_prop_id
├── display_name
├── localized_form          # server copy
├── visual_form
├── materials[]
├── color_palette[]
├── scale
├── functional_identity
├── signature_details[]
├── continuity_constraints[]
├── generation_guidance[]
├── negative_constraints[]
└── reference_assets[]
```

---

## 6. Reference media contract

### 6.1 P13 正式资产不能只有文本说明

正式 `TARGET_ASSETS` v1 每个 Target Asset 至少必须有一份可解码、已持久化、带 hash 的 `REFERENCE_SHEET` image。

不允许：

- 用空文件占位；
- 用固定 placeholder 冒充 Provider 成果；
- 只保存 Provider URL 而不持久化；
- 图片生成失败后仍发布 CURRENT；
- 把未经过媒体校验的 base64 / bytes 直接写成正式 reference。

### 6.2 ReferenceAsset typed fields

```text
reference_asset_id
role = REFERENCE_SHEET
media_type
relative_path
sha256
size_bytes
width
height
provider_job_id
provider
model
```

`relative_path` 必须位于 server artifact root 下的 P13 target namespace 目录，并通过 path traversal 防护解析。

### 6.3 Reference sheet 内容方向

一个 reference sheet 可以在单张图里表达多个视角，降低 Provider 调用数量同时提高一致性：

- Character：脸部、3/4、全身、核心服装和标志特征；
- Scene：空间 wide、主要布局、固定 landmark、材质/光线基线；
- Prop：主视图、多角度、尺度与材质特征。

这是 **asset reference sheet**，不是 Target Storyboard，也不是剧情镜头，不得加入 Shot timing、镜头号或生成片段信息。

---

## 7. Provider 与 deterministic 层责任边界

P13 v1 分为两个 Provider 边界。

### 7.1 Visual Spec Provider

可复用项目当前 reasoning Provider，但输入只允许 CURRENT Target Bible 的 typed content 和服务端 scope manifest。

Provider 可以输出：

- Character face / hair / body / wardrobe 等视觉具体化；
- Scene layout / architecture / materials / landmark / lighting baseline；
- Prop visual form / material / color / scale / detail；
- visual generation guidance；
- visual negative constraints。

Provider 必须逐字返回被要求覆盖的 `target_*_id`，不得输出数据库 ID、Artifact ID、revision 或修改 Target Bible 字段。

### 7.2 Image Provider

Image Provider 输入是服务端已组合并锁定语义的 reference-sheet prompt。它只负责返回 image bytes + provider remote metadata。

P13 首个工程实现允许通过独立的、server-side 配置的 image generation adapter 接入真实 Provider；不得把 Source Understanding Provider 的“文本能力”假装成图片生成能力。

若 image Provider 未配置：

```text
P13_IMAGE_PROVIDER_NOT_CONFIGURED
```

command 必须 fail closed；不得生成 placeholder，不得发布候选或 CURRENT Artifact。

### 7.3 服务端 deterministic 层负责

服务端必须独占：

```text
target_asset_id
asset_revision
Target entity exact coverage validation
Target Bible locked fields copy
final prompt composition
reference_asset_id
media hash / dimensions / path
candidate fingerprint
Artifact revision / fingerprint
CURRENT / STALE
Graph edges
provenance
approval publication
```

Provider 永远无权修改这些正式身份或版本控制字段。

---

## 8. Candidate -> Approval -> CURRENT publication

### 8.1 为什么需要 Candidate

“Provider 返回成功”不能等同于“正式资产可用”。尤其图像质量和身份一致性必须有人确认。

P13 采用两阶段：

```text
Generate Task
  -> strict schema validation
  -> exact entity coverage validation
  -> image decode/hash/dimension/storage validation
  -> READY_FOR_REVIEW candidate
  -> user explicit APPROVE command
  -> atomic CURRENT TARGET_ASSETS publication
```

因此模型生成结果不会未经确认直接成为 CURRENT Artifact。

### 8.2 Candidate status

```text
READY_FOR_REVIEW
PUBLISHED
REJECTED   # 可保留，若实现显式拒绝命令
STALE      # 上游 Target Bible 在批准前变化
```

Candidate 不是 `ArtifactNode`，不能被下游当正式输入。

### 8.3 Approval publication

批准时服务器必须再次验证：

1. candidate 仍绑定当前 CURRENT Target Bible；
2. target entity exact coverage 仍成立；
3. 所有 reference file 仍存在；
4. sha256 / size / image dimensions 与 candidate metadata 一致；
5. typed content 仍可解析；
6. candidate 尚未被其他版本取代。

全部通过后才在单一 DB transaction 内：

- 把旧 CURRENT `TARGET_ASSETS` 及 downstream 标记 STALE；
- 创建新 `TARGET_ASSETS` ArtifactNode；
- 创建 typed `ReplicaTargetAssetsRevision`；
- 创建 Graph edge；
- 创建 SUPERSEDES edge（若存在旧版本）；
- 将 candidate 标记 PUBLISHED 并绑定 published artifact；
- invalidate current execution plan；
- commit。

任何一步失败必须 rollback，不允许半发布。

---

## 9. Asset revision / CURRENT / STALE

### 9.1 Artifact revision

每次用户批准一套新的正式资产：

```text
TARGET_ASSETS Artifact revision += 1
```

旧 Artifact：

```text
validity = STALE
is_current = false
```

### 9.2 Entity-level asset_revision

同一稳定 `target_asset_id`：

- 首次正式资产：`asset_revision = 1`；
- 该 asset 被重新生成 / 替换后批准：`+1`；
- 未被修改、从上一 CURRENT set 直接 carry forward：revision 不变。

### 9.3 Target Bible 变化

新的 `TARGET_BIBLE` 发布时，已有 Graph：

```text
TARGET_BIBLE -> TARGET_ASSETS
```

必须让旧 `TARGET_ASSETS` 及未来所有 downstream 递归 STALE。

若 P13 candidate 尚未批准而 Target Bible 改变，candidate 在 read/approve 时必须被视为 STALE / 拒绝批准，不能把旧语义资产发布到新 Target 世界。

---

## 10. 全量生成与定向重新生成

### 10.1 首次生成

没有同一 Target Bible 的 CURRENT `TARGET_ASSETS` 时，必须全量覆盖 Character / Scene / Prop。

### 10.2 定向重新生成

当存在与当前 Target Bible 完全同 lineage 的 CURRENT `TARGET_ASSETS` 时，command 可以显式传：

```text
target_asset_ids[]
```

只重新生成被选 asset；其他 asset 从当前正式 set 原样 carry forward。

若：

- 传入未知 asset id；
- asset id 重复；
- 当前正式 set 不属于当前 Target Bible；
- 当前正式 set 已 STALE；

则 fail closed。

定向重新生成产生完整候选 set，批准后替换整个 `TARGET_ASSETS` Artifact revision，但只提升被重新生成的 entity-level `asset_revision`。

---

## 11. Artifact Graph relation

P13 v1 正式 Graph：

```text
CURRENT TARGET_BIBLE
    --DERIVED_FROM/USES--> TARGET_ASSETS
```

为避免语义含糊，正式关系固定：

```text
TARGET_BIBLE --DERIVED_FROM--> TARGET_ASSETS
```

含义：Target Assets 是 Target Bible 视觉实现。

重新批准时：

```text
new TARGET_ASSETS --SUPERSEDES--> old TARGET_ASSETS
```

P13 不直接建立：

```text
SOURCE_VIDEO_SNAPSHOT -> TARGET_ASSETS
TARGET_SCRIPT -> TARGET_ASSETS
```

因为它们不是 P13 硬输入。

---

## 12. Provenance

正式 provenance 至少包含：

```text
target_bible_artifact_id
target_bible_revision
target_bible_fingerprint
professional_skill_id
professional_skill_version
schema_version
prompt_version
asset_contract
candidate_id
generated_by_task_id
approved_at
approval_method = EXPLICIT_USER_COMMAND
supersedes_artifact_id
visual_spec_provider_profile
visual_spec_provider_job_id
image_provider_profile
per_asset_image_provider_job_id
reference_media_sha256
```

不得记录 API key / Authorization / secret。

---

## 13. Provider failure / partial failure / retry / idempotency

### 13.1 ProviderJob-before-remote

每一次付费 / 外部调用必须先持久化 `ProviderJob`，再 remote call。

### 13.2 Partial failure

任何一个必须生成的 asset：

- spec 缺失；
- 图片 Provider failure；
- response 无 bytes；
- image decode 失败；
- media size/dimension 不满足；
- 存储失败；

整次 Generate Task 必须失败，且：

```text
不创建 READY_FOR_REVIEW candidate
不覆盖旧 CURRENT TARGET_ASSETS
不伪造 reference media
```

已经成功的 ProviderJob 继续保留用于审计。

### 13.3 Retry

沿用 Task 有限重试语义，默认最多 3 次。用户重新发起时使用新的 `Idempotency-Key`；同一个 command idempotency key 不得产生第二个独立 Task。

### 13.4 Approval idempotency

Approve command 也必须带 `Idempotency-Key`。

同一个 candidate + 同一个 key 重复请求必须返回同一 published artifact；candidate 已由其他 key 发布时不得再产生新 revision。

---

## 14. API command / read contract

建议正式 API：

```text
POST /api/v3/projects/{project_id}/commands/target-assets
GET  /api/v3/projects/{project_id}/target-assets
GET  /api/v3/projects/{project_id}/target-assets/revisions
POST /api/v3/projects/{project_id}/commands/target-assets/{candidate_id}/approve
```

Generate command body：

```json
{
  "target_asset_ids": []
}
```

空数组代表全量；非空代表定向重新生成。

### 14.1 GET 必须严格只读

普通页面加载调用 GET 时禁止：

- 隐式创建 Task；
- 隐式调用 Provider；
- 隐式生成图片；
- 隐式写 Artifact；
- 隐式批准 candidate；
- 为了“补齐缺失资产”自动重试。

GET 可返回：

- 正式 artifact `NOT_BUILT | CURRENT | STALE`；
- latest review candidate；
- asset typed content / provenance；
- review / stale reason。

但只允许读。

---

## 15. 后续 Storyboard / Generation 消费合同（只定义，不实现）

P13 不实现 P14，但为后续固定消费边界：

### 15.1 Storyboard

后续 Target Storyboard 若需要人物 / 场景 / 道具，必须引用：

```text
target_asset_id
asset_revision
reference_asset_id
```

而不是在每个 Shot 里重新写自由文本身份描述。

### 15.2 Generation

未来 Generation Segment 必须能够追溯到其消费的正式 `TARGET_ASSETS Artifact id + revision` 和具体 `target_asset_id`。

生成阶段可以把 generation guidance 转译为 Provider prompt，但不得静默改写正式 asset identity。

### 15.3 stale propagation

未来链路应形成：

```text
TARGET_BIBLE
  -> TARGET_ASSETS
    -> TARGET_STORYBOARD
      -> GENERATION_SEGMENTS
        -> GENERATED_VIDEO / GENERATION_SELECTION
```

因此资产更新会自然使旧 Storyboard / Generation downstream STALE。

本文只定义这项消费合同，不创建 P14 Artifact 或代码。

---

## 16. UI 与人工确认边界

P13 工作区至少需要显示：

- 当前 Target Bible revision；
- 正式 `TARGET_ASSETS` 状态 / revision；
- Character / Scene / Prop 分类；
- 每个 `target_asset_id`、entity binding、asset revision；
- reference sheet；
- semantic anchor；
- continuity / negative constraints；
- generation guidance；
- latest candidate 是否待审核；
- “生成目标资产 / 重新生成所选资产”；
- “批准并设为正式资产”；
- stale / provider failure 的可读安全错误。

用户批准的是“该候选是否成为本项目正式视觉资产”，不是在 UI 中修改 P11 Target Bible。

若视觉方向有问题，应重新生成/替换 asset；不能借 P13 approval 反向修改 Target Bible。

---

## 17. P13 人工验收标准

P13 最终 PASS 前必须同时完成工程验收、真实 Provider 验收、真实项目人工质量验收。

### 17.1 工程验收

至少验证：

1. Root `target_assets` 仍只 require `TARGET_BIBLE`；
2. Professional Skill required input 只含 `TARGET_BIBLE`；
3. `TARGET_ASSETS` capability 仍 `PLANNED`；
4. GET read-only；
5. command 缺 CURRENT Target Bible 时 fail closed；
6. Provider exact target entity coverage；
7. Provider 不能改变 P11 entity identity；
8. stable `target_asset_id`；
9. entity-level asset revision；
10. immutable media hash/path/dimension validation；
11. ProviderJob-before-remote；
12. partial failure 不产生 candidate/current；
13. candidate 不能被下游当 Artifact；
14. approval 前不会出现 CURRENT Target Assets；
15. approval atomic publication；
16. old CURRENT + downstream stale；
17. Target Bible revision change 使 Target Assets/candidate stale；
18. SUPERSEDES lineage；
19. approval idempotency；
20. no credential in provenance/provider payload；
21. 非 REPLICA fail closed；
22. P14+ 禁止项没有被实现。

### 17.2 真实 Provider 验收

必须使用真实 image Provider，至少验证：

- Character reference sheet 真正可解码且身份明确；
- Scene reference sheet 能固定空间布局 / landmark / 材质；
- Prop reference sheet 能固定形态 / 材质 / 尺度；
- 失败不会被伪造成成功；
- ProviderJob 能追到具体 asset；
- 重新生成指定 asset 不会无故改动其他 asset identity。

### 17.3 真实项目人工质量验收

人工必须确认：

- 资产没有改变 Target Bible 的人物 / 场景 / 道具叙事身份；
- Character 视觉身份足以跨镜稳定复现；
- Scene 固定 landmark / layout 能支持连续镜头；
- Prop 的视觉与功能身份稳定；
- 同一资产的 reference sheet 内部一致；
- 资产之间属于同一 Target 世界 / visual style；
- 人工点击批准后才成为正式 CURRENT；
- 重生成和替换历史可追溯。

---

## 18. P13 PASS 前能力状态

在真实 Provider、真实项目、strict contract、人工质量验收全部完成，且用户明确回复 `P13 PASS` 之前：

```text
LOCALIZATION = AVAILABLE
TARGET_BIBLE = AVAILABLE
TARGET_SCRIPT = AVAILABLE

TARGET_ASSETS = PLANNED
TTS = PLANNED
TIMING = PLANNED
STORYBOARD = PLANNED
VIDEO_GENERATION = PLANNED
QC_SELECTION = PLANNED
LIP_SYNC = PLANNED
POST_PRODUCTION = PLANNED
```

工程代码、测试通过、候选图片生成成功、单项目 approval 成功，都不能单独等同于 P13 PASS。

---

## 19. 实现顺序

本文确认后，P13 实现顺序固定：

```text
1. Professional Skill manifest + SKILL.md
2. strict P13 schemas
3. DB candidate / typed revision models + migration
4. target media immutable storage + validation
5. visual spec Provider interface + concrete reasoning adapters
6. image Provider interface + concrete configured adapter
7. deterministic service compose / IDs / revisions / candidate
8. explicit approval atomic publication
9. API read / command
10. Artifact Graph / stale / provenance
11. frontend P13 review workspace
12. backend/frontend contract tests
13. CI
14. real Provider + real project manual acceptance
```

不得把第 14 步的结果预先写成 PASS；不得在 P13 实现中顺手开始 P14。
