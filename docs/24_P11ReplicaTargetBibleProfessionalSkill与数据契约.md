# P11 Replica Target Bible Professional Skill 与数据契约

> 日期：2026-09-11  
> 状态：P11 当前最高优先级开发契约；工程实现与真实人工验收尚未完成。  
> 前置：`docs/23_P10最终验收与P11准入.md` 已确认 `SOURCE_SNAPSHOT = AVAILABLE`，P11 正式准入。  
> 范围：**仅 REPLICA Target Bible**。不得借本阶段提前实现 Target Script、Target Storyboard、TTS / Timing、Generation / QC / Selection / Post，也不得顺手铺开 REDRAW / TRANSLATION / 其他项目类型的 Target 链。

---

# 1. P11 的职责

P11 把已经通过 P10 冻结的完整 Source 世界，转换成一个**可版本化、可追溯、可供后续 Target Script / Storyboard / Production 消费的 Replica 目标世界**。

P11 不是：

- 再做一遍原片理解；
- 改写 Source Facts；
- 直接生成完整目标剧本；
- 直接翻译所有对白；
- 直接生成 Target Storyboard；
- 直接进入 TTS / Timing / 视频生成。

P11 正式业务关系：

```text
CURRENT SOURCE_VIDEO_SNAPSHOT
        ↓
Replica preservation locks
        +
Project target language / region / scene strategy / visual style
        ↓
Professional Skill: replica-target-bible
        ↓
ADAPTATION_PLAN
        +
TARGET_BIBLE
```

其中：

```text
SOURCE_VIDEO_SNAPSHOT
= 唯一当前 Source 世界版本锚点

ADAPTATION_PLAN
= 这次复刻哪些必须锁定、哪些需要本土化、如何本土化

TARGET_BIBLE
= 本次目标版本统一人物 / 场景 / 道具 / 世界 / 视觉 / 连续性设定
```

---

# 2. Professional Skill

新增：

```text
skills/professional/replica-target-bible/
  SKILL.md
  manifest.json
```

正式版本：

```text
replica-target-bible@1.0.0
```

运行契约：

```text
P11_SCHEMA_VERSION = 1.0
P11_PROMPT_VERSION = p11-replica-target-bible-v1
P11_TARGET_CONTRACT = replica-target-bible-v1
P11_PRESERVATION_CONTRACT = replica-story-rhythm-locks-v1
```

Skill 只依赖 capability：

```text
LOCALIZATION
TARGET_BIBLE
```

Skill 不绑定具体模型；具体模型属于 Provider Adapter。

---

# 3. 硬输入

P11 正式必需输入只有：

```text
CURRENT SOURCE_VIDEO_SNAPSHOT
```

并读取项目目标配置：

```text
target_language
target_region
scene_strategy
visual_style
```

需要 Source 细节时，必须从该 Snapshot 的 typed content 或 lineage 读取被冻结的内容：

```text
SOURCE_BIBLE
SOURCE_SHOT_FACTS
SOURCE_CHARACTERS
SOURCE_SPEAKERS
SOURCE_SCENES
SOURCE_PROPS
P5 Shot Anchors
P6 canonical dialogue / OCR
```

禁止 P11 自己重新从散落 P5~P9 CURRENT Artifact 拼装“当前 Source 世界”。

规则：

```text
Snapshot revision
= 当前 Source 世界版本
```

若 Snapshot `STALE` 或不是 CURRENT，P11 必须 fail closed。

---

# 4. Replica Preservation Locks

P11 必须确定性地从 Source Snapshot 构造 preservation locks；Provider 可以读取，但无权修改这些锁。

默认锁定：

```text
story mainline
Hook
冲突与冲突顺序
反转与反转顺序
信息揭示顺序
情绪峰值
Payoff
Cliffhanger
Story Beat timing
Shot rhythm baseline
Scene order baseline
Shot logic baseline
Action rhythm baseline
```

核心原则：

> 故事不乱改，节奏不重做，文化和表达才本土化。

Provider 不得通过“更合理”“更符合当地观众”等理由删除、合并、重排这些 Source Story / Rhythm 锁。

---

# 5. 允许本土化的内容

P11 允许在 Target namespace 设计：

- Target 世界背景与社会语境；
- 人物目标身份 / 姓名 / 外形定位；
- 场景的目标文化环境；
- 道具的目标文化替代；
- 货币、公司 / 学校 / 职业 / 居住 / 社交习惯等文化映射；
- 称谓、文化表达策略；
- visual style；
- continuity rules；
- 后续目标对白的**语言与文化策略**。

P11 **不能**产出正式逐句目标对白或完整 `TARGET_SCRIPT`。

正式逐句目标对白 / Target Script 属于后续阶段，必须保持：

```text
Source Dialogue
→ Translation
→ Localization
→ Final Target Dialogue
→ Voice / TTS
→ Actual Duration
→ Timing
```

P11 只能为该后续流程提供 Target Bible 和 localization decision 约束。

---

# 6. Target Identity 规则

Target 人物 / 场景 / 道具必须是新的 Target identity，不能复用 Source identity 充当目标实体。

必须保持 lineage：

```text
Target Character → source_character_id
Target Scene     → source_scene_id
Target Prop      → source_prop_id
```

Target ID 由服务端确定性生成，Provider 不生成数据库 / Artifact ID。

第一版 Replica 采用一对一覆盖契约：

- 每个 CURRENT Source Character 必须有且只有一个 Target Character mapping；
- 每个 CURRENT Source Scene 必须有且只有一个 Target Scene mapping；
- 每个 CURRENT Source Prop 必须有且只有一个 Target Prop mapping；
- Provider 不得遗漏 Source identity；
- Provider 不得擅自创造没有 Source lineage 的主要人物 / 场景 / 道具。

未来确需一对多 / 多对一 Target adaptation 时，必须通过新 schema revision 显式升级，不在 P11 v1 静默放宽。

Source Speaker 不在 P11 转成 Target Voice；Target Voice / TTS 属于后续阶段。

---

# 7. `ADAPTATION_PLAN` typed schema

P11 正式产出一个 TARGET namespace 的 `ADAPTATION_PLAN` Artifact。

建议 typed content：

```text
ReplicaAdaptationPlanContent
- target_language
- target_region
- source_snapshot_artifact_id
- preservation_locks[]
- localization_decisions[]
- dialogue_localization_strategy
- scene_strategy
- visual_style
```

`preservation_locks[]` 至少包含：

```text
lock_id
category
source_summary
source_refs[]
constraint
```

`localization_decisions[]` 至少包含：

```text
decision_id
category
source_ref
source_value
target_value
reason
```

允许 category：

```text
CHARACTER
SCENE
PROP
CULTURE
ADDRESSING
WORLD
VISUAL_STYLE
```

`ADAPTATION_PLAN` 是正式 Target Artifact，不是 Prompt 文本缓存。

---

# 8. `TARGET_BIBLE` typed schema

P11 正式产出一个 TARGET namespace 的 `TARGET_BIBLE` Artifact。

第一版至少包含：

```text
ReplicaTargetBibleContent
- target_language
- target_region
- target_world
- characters[]
- scenes[]
- props[]
- visual_style
- continuity_rules[]
- dialogue_style_rules[]
- adaptation_summary
```

## 8.1 Target World

至少包含：

```text
setting_summary
cultural_context
social_context
localization_principles[]
```

不得把 Source FACT 改成新的“Target Source Truth”；这些字段是 Target 设计。

## 8.2 Target Character

至少包含：

```text
target_character_id
source_character_id
display_name
localized_identity
appearance_direction
personality_constraints[]
continuity_rules[]
```

其中 `personality_constraints` 必须保持 Source 主线人物功能，不得为了本土化改写人物在故事中的核心作用。

## 8.3 Target Scene

至少包含：

```text
target_scene_id
source_scene_id
display_name
localized_setting
visual_direction
continuity_rules[]
```

Scene 本土化不得重排 Source Scene order / Story Beat timing。

## 8.4 Target Prop

至少包含：

```text
target_prop_id
source_prop_id
display_name
localized_form
continuity_rules[]
```

不能把同一 Source Prop 的 continuity 静默拆成多个无 lineage Target Prop。

---

# 9. Provider Semantic Contract

Provider 只返回**Target 设计语义**，不返回正式 Artifact ID / revision / fingerprint。

Provider semantic 必须完整覆盖 Source Snapshot 中：

```text
SOURCE_CHARACTERS
SOURCE_SCENES
SOURCE_PROPS
```

服务端负责：

- 校验覆盖完整性；
- 校验所有 source_*_id 都来自当前 Snapshot；
- 确定性生成 Target identity；
- 构造 preservation locks；
- 合成 ADAPTATION_PLAN / TARGET_BIBLE typed content；
- 创建 Artifact / revision / provenance / Graph。

Provider 必须禁止：

- 修改 Source Facts；
- 输出新的 Shot 边界；
- 改写 P6 canonical dialogue；
- 改写 Source identity；
- 删除 / 重排 preservation locks；
- 生成完整 Target Script；
- 生成 Target Storyboard；
- 生成 TTS / Timing / Generation 参数。

---

# 10. Task / ProviderJob

重任务必须显式启动：

```text
POST /api/v3/projects/{project_id}/commands/target-bible
```

GET 只读：

```text
GET /api/v3/projects/{project_id}/target-bible
GET /api/v3/projects/{project_id}/target-bible/revisions
```

P11 Task 必须绑定：

```text
input_artifact_ids = [CURRENT SOURCE_VIDEO_SNAPSHOT artifact_id]
```

input fingerprint 至少覆盖：

```text
source_snapshot artifact id / fingerprint / revision
project target_language
target_region
scene_strategy
visual_style
Professional Skill id/version
Provider profile
P11 prompt/schema/preservation contract version
```

任何外部 Provider 请求前：

```text
先持久化 ProviderJob
再发远端请求
```

ProviderJob 的 `artifact_id` 必须绑定 CURRENT `SOURCE_VIDEO_SNAPSHOT`。

有限 retry / cancel / resume 继续使用 P4 Task Runtime。

---

# 11. Artifact / Revision / Provenance

新增 P11 revision storage，至少记录：

```text
project_id
artifact_id
artifact_kind = ADAPTATION_PLAN | TARGET_BIBLE
source_snapshot_artifact_id
generated_by_task_id
schema_version
content_json
provenance_json
created_at
```

正式 provenance 至少包含：

```text
source_snapshot_artifact_id
source_snapshot_revision
source_snapshot_fingerprint
target_language
target_region
scene_strategy
visual_style
professional_skill_id / version
provider / model
provider_job_id
payload_fingerprint
prompt_version
schema_version
target_contract
preservation_contract
generated_by_task_id
supersedes_artifact_id
```

API Key / Authorization 永远不得进入 revision、Artifact、ProviderJob、日志或 provenance。

---

# 12. Artifact Graph

P11 正式关系：

```text
SOURCE_VIDEO_SNAPSHOT
  ├─ DERIVED_FROM → ADAPTATION_PLAN
  └─ DERIVED_FROM → TARGET_BIBLE

ADAPTATION_PLAN
  └─ USES → TARGET_BIBLE

new ADAPTATION_PLAN
  └─ SUPERSEDES → old ADAPTATION_PLAN

new TARGET_BIBLE
  └─ SUPERSEDES → old TARGET_BIBLE
```

实际方向仍按 Artifact Graph 的 `source_node_id → target_node_id` 语义创建。

因此：

```text
SOURCE_VIDEO_SNAPSHOT STALE
→ ADAPTATION_PLAN STALE
→ TARGET_BIBLE STALE
```

Target 不得反向写 Source。

---

# 13. 原子发布

P11 一次运行必须把以下视作一个 publication set：

```text
ADAPTATION_PLAN
TARGET_BIBLE
对应 typed revision rows
Artifact Graph edges
```

不能出现：

```text
ADAPTATION_PLAN 已 CURRENT
但 TARGET_BIBLE 发布失败
```

因此 P11 不能简单依次调用当前每个 Artifact 都自动 commit 的通用 helper。

必须在同一数据库事务中：

1. 再次验证 Snapshot 仍 CURRENT；
2. 创建两个新 Artifact；
3. 创建两个 typed revision；
4. 建立 Source→Target / Target→Target / SUPERSEDES edges；
5. 将旧 P11 CURRENT set 及其 downstream 标 STALE；
6. invalidate current ProjectExecutionPlan；
7. 一次 commit。

任一步失败整体 rollback，旧 CURRENT Target set 保持可用。

---

# 14. 幂等与 STALE

同一个：

```text
CURRENT Snapshot
+ 相同 target config
+ 相同 Professional Skill / Provider / contract
```

不应因为用户重复点击而制造重复 Task / ProviderJob / Target revision。

新的 Snapshot revision 或 Target config 改变必须形成新的 P11 input fingerprint。

Snapshot 更新后：

- 旧 `ADAPTATION_PLAN` STALE；
- 旧 `TARGET_BIBLE` STALE；
- GET 可以读取最新历史，但不能把旧 Target Bible 冒充 CURRENT；
- 用户必须显式重新生成 Target Bible。

---

# 15. Project Type Guard

P11 v1 只允许：

```text
ProjectType.REPLICA
```

必须 service-level fail closed。

以下项目类型均拒绝当前 P11 command / Target Bible 工作区：

```text
REDRAW
TRANSLATION
NOVEL_TO_DRAMA
SCRIPT_TO_DRAMA
SCRIPT_LOCALIZATION
```

后续项目类型必须通过各自 Root Skill 正式接入，不得因为 ArtifactType 相同就复用 Replica P11。

---

# 16. Root Replica Skill 修正

当前旧 `target_localize` 一步同时声明：

```text
LOCALIZATION + TARGET_BIBLE + TARGET_SCRIPT
→ ADAPTATION_PLAN + TARGET_BIBLE + TARGET_SCRIPT
```

这会跨越 P11 / P12 边界。

P11 必须修正为：

```text
step: target_bible
requires: SOURCE_VIDEO_SNAPSHOT
capabilities:
  LOCALIZATION
  TARGET_BIBLE
produces:
  ADAPTATION_PLAN
  TARGET_BIBLE
```

`TARGET_SCRIPT` 留给后续正式阶段。

---

# 17. Capability 状态

P10 PASS 后必须修正运行时 Registry：

```text
SOURCE_SNAPSHOT = AVAILABLE
```

P11 工程实现期间继续保持：

```text
LOCALIZATION = PLANNED
TARGET_BIBLE = PLANNED
```

即使代码、自动测试、Provider 真实运行成功，也不能仅凭工程成功把 P11 Capability 标记 AVAILABLE。

必须等 P11 真实人工验收 PASS 后再升级状态。

---

# 18. 普通产品 UI

普通 REPLICA 项目在“原片解析结果”之后增加一个业务区：

```text
目标设定
```

用户不应看到：

```text
P11
Artifact id
fingerprint
provenance
ProviderJob
schema version
```

普通模式应看到：

- 当前目标语言 / 地区；
- “生成目标设定 / 重新生成目标设定”显式按钮；
- 生成进度 / 失败恢复；
- 本土化策略摘要；
- 保留项；
- Target 人物；
- Target 场景；
- Target 道具；
- visual style；
- continuity rules。

工程信息可以继续留在 debug / API / tests。

页面加载与刷新只能 GET，不自动创建 P11 Task。

---

# 19. 自动测试最低要求

后端至少覆盖：

- Professional Skill manifest 可加载；
- `SOURCE_SNAPSHOT` runtime availability 已与 docs23 一致；
- Root Replica P11 step 不再产出 TARGET_SCRIPT；
- 非 REPLICA fail closed；
- 无 CURRENT Snapshot fail closed；
- Task 只绑定 Snapshot；
- GET 无写副作用；
- ProviderJob-before-remote；
- Provider semantic exact coverage；
- Source ID 不得伪造；
- Target ID 与 Source ID 分离；
- preservation locks 不由 Provider 控制；
- 两个 Target Artifact 原子发布；
- Graph Source→Target 合法，Target→Source fail closed；
- Snapshot STALE 递归使 P11 Target STALE；
- 同输入业务幂等；
- 新 revision 保留旧历史；
- Provider / publication failure 不覆盖旧 CURRENT。

前端至少覆盖：

- 仅 REPLICA 显示目标设定区；
- 页面 GET 不自动 POST；
- 显式按钮才启动；
- NOT_BUILT / RUNNING / CURRENT / STALE / FAILED 可读；
- 不显示工程术语；
- Target Characters / Scenes / Props / locks 可读；
- 不出现 Target Script / Storyboard / TTS / Generation 操作。

---

# 20. 真实人工验收

P11 工程完成后必须使用已通过 P10 的真实短剧项目做真实 Provider + 页面验收。

至少确认：

1. 输入确实绑定 CURRENT Source Snapshot；
2. Replica Story / Rhythm locks 没被改变；
3. Target 人物与 Source 人物 lineage 清晰，但 Target identity 独立；
4. Target Scene / Prop 本土化合理，不改变 Story order；
5. 目标语言 / 地区策略合理；
6. 没有提前生成正式 Target Script；
7. Source 页面 / Source Artifact 没有被 Target 操作改写；
8. Source Snapshot 更新后旧 Target Bible 正确 STALE；
9. 用户明确给出 P11 PASS。

在此之前：

```text
LOCALIZATION = PLANNED
TARGET_BIBLE = PLANNED
P12+ = 不准入
```
