# AI Drama Studio — P1 匿名结构化拉片 Draft 数据 Contract

> **Status:** P1 CONTRACT / IMPLEMENTED / CLOSED  
> **Contract date:** 2026-08-27  
> **P1 implementation closed:** 2026-08-27  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Branch:** `main`  
> **Schema version:** `breakdown-draft-v1`  
> **Parent target plan:** `docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md`

## 0. 本文档的边界与当前状态

本文档冻结 **Phase P1 的数据语义、表关系、历史锚点、Run 生命周期、Validator、只读 API、STALE 与兼容规则**。

创建本 Contract 时它是设计稿；截至 P1.7，P1.1–P1.7 已按当前仓库代码实现并完成 Windows 兼容验收。

当前真实边界：

```text
P1 数据模型 / Run lifecycle / validator / read API / history / STALE
= IMPLEMENTED

ASR / OCR / VLM 自动生成匿名 Draft
= P2 / NOT IMPLEMENTED

02 拉片 structured Draft UI
= P3 / NOT IMPLEMENTED

Draft → Final Asset identity fill-back
= P5/P6 / NOT IMPLEMENTED
```

P1 仍然**不运行 ASR/OCR/VLM**，不创建 Final Character/Scene/Prop，不写 Final Shot Bindings。

---

## 1. 正式数据域

Reference Video V2 正式主链：

```text
engine/app/studio_v2.py
→ Base / Project / Episode / Shot
→ data_v2/studio_v2.sqlite3

engine/app/shot_revision_v2.py
→ ShotRevision / ShotRevisionItem

engine/app/shot_editor_v2.py
→ boundary edit / split / merge
```

P1 正式实现继续使用：

```text
engine.app.studio_v2.Base
+ 同一个 data_v2/studio_v2.sqlite3
+ ADD-only tables
```

禁止把 P1 新数据接回历史：

```text
core.database/app.db
shot_workbench.py
```

---

## 2. P1 核心不变量

### 2.1 Draft 是匿名语义，不是 Final Asset

```text
LocalSubject / 人物A / 人物B
!= Character

SceneSegmentDraft
!= Scene

DraftPropHint
!= Prop
```

P1 Draft 只能作为后续“应该找什么”的语义 Evidence / soft prior。

### 2.2 READY AI Draft 是不可变历史证据

一次 READY / READY_WITH_WARNINGS 的 AI Draft Run 不允许被人工修改覆盖。

未来人工编辑必须建立独立 Overlay / Revision 层，不能 UPDATE 原始 AI Draft 来伪造模型历史。

### 2.3 每个 Run 固定一个 ShotRevision

```text
Episode Current ShotRevision R5
↓
BreakdownRun.source_shot_revision_id = R5
↓
本 Run 只解释 R5 的 ShotRevisionItems
```

如果产生 R6：

```text
R5 active BreakdownRun → STALE
R5 历史数据仍可读
R6 需要新的 BreakdownRun
```

禁止按 ordinal/相似时间把 R5 Draft 自动冒充 R6 结果。

### 2.4 Shot ID 不是永久历史锚点

当前行为：

```text
manual boundary edit
→ 多数现有 Shot ID 可保留

split
→ 左 Shot 可保留 ID，右 Shot 新 ID

auto rerun / restore
→ Current v2_shots 重建
→ 新 Shot IDs
```

因此正式历史锚点：

```text
BreakdownRun
→ source_shot_revision_id FK

ShotSemanticDraft
→ source_shot_revision_item_id FK
→ source_shot_id_snapshot plain string
```

`source_shot_id_snapshot` 故意不是 Current `v2_shots` FK。

### 2.5 正式时间统一 integer microseconds

```text
source_start_us
source_end_us
shot_relative_start_us
shot_relative_end_us
```

浮点秒、frame index、fps 推导值不能替代正式时间事实。

### 2.6 关键结构必须可查询

允许 JSON 保存可扩展 metadata，但以下是正式实体：

```text
BreakdownRun
SceneSegmentDraft
ShotSemanticDraft
LocalSubject
ShotLocalSubject
TimelineEvent
TimelineEventSubject
DraftPropHint
DraftPropOccurrence
EvidenceLink
```

---

## 3. 已实现实体关系

```text
Project
└─ Episode
   ├─ ShotRevision
   │  └─ ShotRevisionItem
   │
   └─ BreakdownRun
      ├─ SceneSegmentDraft
      │  ├─ ShotSemanticDraft
      │  │  ├─ ShotLocalSubject
      │  │  ├─ TimelineEvent
      │  │  │  └─ TimelineEventSubject
      │  │  └─ DraftPropOccurrence
      │  ├─ LocalSubject
      │  └─ DraftPropHint
      │
      └─ BreakdownEvidenceLink
```

未来逻辑关系：

```text
LocalSubject → SubjectResolution → Final Character
SceneSegmentDraft → SceneResolution → Final Scene
DraftPropHint → PropResolution → Final Prop
```

Resolution 物理表**没有在 P1 创建**；按原 Contract 允许延后到 P5/P6，避免 P1 过早引入 Final Asset FK。

---

## 4. 已实现表清单

P1.1 ADD-only 创建 10 张表：

```text
1. v2_breakdown_runs
2. v2_scene_segment_drafts
3. v2_shot_semantic_drafts
4. v2_local_subjects
5. v2_shot_local_subjects
6. v2_timeline_events
7. v2_timeline_event_subjects
8. v2_draft_prop_hints
9. v2_draft_prop_occurrences
10. v2_breakdown_evidence_links
```

`studio_v2.init_database()` 在 `Base.metadata.create_all()` 前注册 P1 models；升级行为是 ADD-only / idempotent。

---

## 5. `v2_breakdown_runs`

### 作用

一次 Episode 级匿名 Breakdown Evidence 快照，并冻结其 ShotRevision。

核心字段：

```text
id
project_id
 episode_id
source_shot_revision_id
status
is_current
schema_version
pipeline_profile
component_status_json
provider_metadata_json
counts_json
warning_json
error_message
started_at
completed_at
```

正式状态：

```text
PROCESSING
READY
READY_WITH_WARNINGS
FAILED
STALE
```

规则：

```text
source_shot_revision_id 必须属于同 Episode
READY 前必须通过真实 validator
FAILED 不替换旧 Current
同 Episode 只有一个可消费的 Current READY 类 Run
```

---

## 6. `v2_scene_segment_drafts`

### 作用

表达一段连续剧情场景，不是 Final Scene Asset。

核心字段：

```text
id
run_id
episode_id
ordinal
source_start_us
source_end_us
location_hint
interior_exterior
time_of_day
scene_function_hint
summary
environment_description
confidence
metadata_json
```

规则：

```text
(run_id, ordinal) unique
source_start_us < source_end_us
Segment 由连续且有序的 ShotSemanticDraft 组成
Segment 时间必须与首尾 Shot 覆盖一致
```

---

## 7. `v2_shot_semantic_drafts`

### 作用

对一个明确历史 `ShotRevisionItem` 的匿名结构化理解。

核心字段：

```text
id
run_id
scene_segment_id
source_shot_revision_item_id
source_shot_id_snapshot
shot_ordinal_snapshot
source_start_us
source_end_us
summary
visual_description
shot_language
shot_type_hint
camera_motion_hint
narrative_function_hint
confidence
model_metadata_json
```

唯一约束：

```text
(run_id, source_shot_revision_item_id) UNIQUE
```

READY Run 必须覆盖其 source ShotRevision 的全部 Revision Items，不能缺 Shot Draft。

---

## 8. `v2_local_subjects`

### 作用

Scene Segment 作用域内匿名人物。

核心字段：

```text
id
run_id
scene_segment_id
ordinal
display_label
role_hint
appearance_summary
appearance_json
first_seen_us
last_seen_us
speaking_state_summary
confidence
```

强规则：

```text
(scene_segment_id, ordinal) UNIQUE
不允许 character_id
不允许直接创建 Final Character
```

```text
Scene 1 的 人物A
!= 默认声明 Scene 2 的 人物A 是同一身份
```

---

## 9. `v2_shot_local_subjects`

### 作用

LocalSubject 在一个 Shot Draft 中的具体出现状态。

核心字段：

```text
id
run_id
shot_draft_id
local_subject_id
first_seen_us
last_seen_us
screen_position
visibility
speaking_state
activity_summary
confidence
search_hint_json
```

唯一约束：

```text
(shot_draft_id, local_subject_id) UNIQUE
```

`search_hint_json` 是 soft search hint，不是 bbox/Track Evidence。

---

## 10. `v2_timeline_events`

第一版 event type：

```text
VISUAL
ACTION
DIALOGUE
OCR
AUDIO_EVENT
```

核心字段：

```text
id
run_id
shot_draft_id
ordinal
event_type
source_start_us
source_end_us
shot_relative_start_us
shot_relative_end_us
content_text
language
emotion_hint
speaking_style_hint
confidence
origin
metadata_json
```

`origin` 可表达：

```text
VLM | ASR | OCR | FUSION | RULE
```

规则：

```text
事件时间必须完全落入所属 Shot
relative/source 时间必须一致
(shot_draft_id, ordinal) UNIQUE
```

P2 即使把 ASR/OCR 融合成 TimelineEvent，也必须另外保留原始 ASR/OCR Evidence；TimelineEvent 不替代原始 Evidence。

---

## 11. `v2_timeline_event_subjects`

允许一条事件有多个匿名主体及角色：

```text
ACTOR
TARGET
SPEAKER
LISTENER
WITNESS
OTHER
```

规则：

```text
(event_id, local_subject_id, role) UNIQUE
participant 必须属于同 Run / 合法 Segment context
```

---

## 12. `v2_draft_prop_hints`

### 作用

保存剧情相关、值得 P4 后续验证的 Prop 候选，不是所有画面 Object。

核心字段：

```text
id
run_id
scene_segment_id
ordinal
label_hint
normalized_hint
importance
narrative_reason
first_seen_us
last_seen_us
confidence
metadata_json
```

强规则：

```text
DraftPropHint 不允许 prop_id
DraftPropHint 不直接创建 Final Prop
```

---

## 13. `v2_draft_prop_occurrences`

告诉后续阶段去哪些 Shot/时间范围定向寻找 Prop。

核心字段：

```text
id
prop_hint_id
shot_draft_id
source_start_us
source_end_us
screen_position_hint
interaction_summary
confidence
search_region_hint_json
```

规则：

```text
Occurrence 必须与 PropHint/ShotDraft 属于一致 Run/Segment context
时间必须落入所属 Shot
search_region_hint_json 不是正式 bbox/mask Evidence
```

---

## 14. `v2_breakdown_evidence_links`

### 作用

建立匿名语义 Draft 与 P2+ 原始 Evidence/artifact 的 provenance link。

核心字段：

```text
id
run_id
owner_type
owner_id
source_type
source_id
source_uri
role
confidence
metadata_json
```

`owner_type`：

```text
SCENE_SEGMENT
SHOT_DRAFT
LOCAL_SUBJECT
TIMELINE_EVENT
PROP_HINT
```

`source_type` 可扩展：

```text
ASR_SEGMENT
ASR_WORD
OCR_OBSERVATION
VLM_OUTPUT
FRAME
AUDIO_RANGE
RULE
```

`role`：

```text
SUPPORT
PRIMARY
CONFLICT
CONTEXT
```

注意：早期设计文档示例中的 `aowner_id` 拼写没有进入正式实现；正式字段是 `owner_id`。

---

## 15. Resolution 逻辑 Contract

未来目标：

```text
LocalSubject → Character
SceneSegmentDraft → Scene
DraftPropHint → Prop
```

推荐后续分表：

```text
v2_draft_subject_resolutions
v2_draft_scene_resolutions
v2_draft_prop_resolutions
```

P1 没有创建这些表。

真值规则不变：

```text
SubjectResolution 只能消费已确认 Character / Shot Binding Evidence
VLM 说“像某人”不能直接 RESOLVED

Scene/Prop Resolution 也必须记录 Final Asset Evidence 来源
```

---

## 16. P1 不修改的系统

P1 明确没有修改：

```text
Character identity score
Character V10.1 thresholds
same-sample cannot-link
Face hard conflict
explicit Shot Character Assignment
Final Character Gate
Scene Final resolver
Prop Final resolver
Dialogue localization
Voice
Generation
```

P1 不把完整 Draft 塞入：

```text
Shot.short_description
Shot.shot_type
Shot.camera_motion
```

这些旧字段继续兼容，但不是新 Breakdown 主存储。

---

## 17. BreakdownRun 与 ContentAnalysisRun 分层

```text
BreakdownRun
= AI 先看懂视频，匿名结构化语义 Draft

ContentAnalysisRun
= 专用 Character/Scene/Prop Evidence / identity / candidates
```

目标依赖顺序：

```text
BreakdownRun READY
↓
ContentAnalysisRun 可读取 Draft hints
↓
Final Asset / Binding
↓
DraftResolution
```

BreakdownRun 本身不能直接修改 Final Asset。

---

## 18. Run lifecycle — 已实现

### 创建

```text
1. 找 Episode Current ShotRevision
2. 冻结 source_shot_revision_id
3. 创建 PROCESSING Run
4. 后续 producer 写完整 Draft rows
5. validator
6. publish READY / READY_WITH_WARNINGS
```

P1.2 为 legacy Episode 保留 `ensure_current_revision()` 兼容，但 P1.4 read-only API 不会因为读取历史项目偷偷创建 BASELINE。

### 失败

```text
validator hard error
→ Run FAILED
→ is_current false
→ old Current Breakdown 不变
```

### 成功

```text
validator passed
→ old Current non-current
→ new Run READY/READY_WITH_WARNINGS + is_current
```

如果 Run source ShotRevision 在 publish 前已失去 Current，Run 不能发布为新 Current。

---

## 19. ShotRevision → STALE — 已实现

任何创建新 Current ShotRevision 的操作：

```text
manual boundary edit
split
merge
record_manual_revision
auto rerun
restore
```

都会自动：

```text
old-revision PROCESSING/READY/READY_WITH_WARNINGS BreakdownRun
→ STALE + is_current=false
```

实现要求已经满足：

```text
ShotRevision Current switch
+
Breakdown STALE mutation
= same DB transaction
```

事务失败时二者一起 rollback。

不会删除：

```text
old BreakdownRun
old Draft rows
old ShotRevision
old ShotRevisionItem
old Reference Clip
```

---

## 20. Validator — 已实现

P1 validator 至少锁住：

```text
1. Run/Project/Episode/ShotRevision ownership
2. source ShotRevisionItem 完整覆盖
3. 每个 RevisionItem 恰好一个 ShotSemanticDraft / Run
4. 每个 ShotDraft 恰好属于一个 SceneSegmentDraft
5. SceneSegment Shot 连续、有序、时间覆盖一致
6. LocalSubject 只能出现在自己 Segment 的 Shot
7. ShotLocalSubject ownership/time consistency
8. TimelineEvent 时间必须在 Shot 内
9. TimelineEvent relative/source 时间一致
10. participant 必须同 Run/context
11. PropOccurrence 必须同 Run/context 且时间在 Shot 内
12. EvidenceLink owner 必须存在且属于同 Run
13. confidence 只能 0..1 或 NULL
14. Draft 不能泄漏 Final character_id / scene_id / prop_id
15. Current READY Run 的 source revision 必须与 Episode Current 一致
```

历史 STALE Run 仍然允许做结构完整性验证；它只是不能作为 Current 结果消费。

---

## 21. Read-only serializer/API — 已实现

P1.4 提供只读：

```text
Episode Breakdown Run history
Episode Current Breakdown
Breakdown by Run ID
Scene/Shot/Subject/Event/Prop structured serialization
ShotRevision/ShotRevisionItem provenance
historical Reference Clip URL
```

历史 Reference Clip 通过 `ShotRevisionItem` 读取，不依赖旧 Shot 仍存在于 Current `v2_shots`。

---

## 22. P2 标准输入 / 输出边界

P2 必须复用本 P1 Contract。

### P2 输入

```text
Episode
Current ShotRevision
ShotRevisionItems
Reference Clips
Keyframes
Episode Audio
ASR Evidence
OCR Evidence
neighbor Shot context
```

### P2 只允许写

```text
BreakdownRun
SceneSegmentDraft
ShotSemanticDraft
LocalSubject
ShotLocalSubject
TimelineEvent
TimelineEventSubject
DraftPropHint
DraftPropOccurrence
BreakdownEvidenceLink
```

### P2 明确禁止写

```text
Character
Scene
Prop
ShotCharacterBinding
ShotSceneBinding
ShotPropBinding
AssetRevision
```

---

## 23. P1 实现阶段 — 全部完成

```text
P1.1 breakdown models + ADD-only tables                         ✅
P1.2 Run lifecycle / Current / FAILED / STALE primitive        ✅
P1.3 fail-closed validator                                     ✅
P1.4 read-only serializer/API                                  ✅
P1.5 focused + compatibility tests                             ✅
P1.6 ShotRevision mutation → automatic STALE                   ✅
P1.7 docs sync + Windows empty/historical project acceptance   ✅
```

P1 未接 ASR/OCR/VLM inference，这不是缺口，而是明确 Phase 边界。

---

## 24. P1 focused/compatibility acceptance

核心覆盖：

```text
Current ShotRevision → PROCESSING Run
Run source revision frozen
one ShotDraft per RevisionItem
SceneSegment order/time
LocalSubject cross-Shot presence in same Segment
same label in different Segments does not imply identity
multi-participant events
PropHint remains hint
no Final Asset FK/leakage
validator blocks incomplete READY
Failed Run does not replace old Current
new ShotRevision automatically STALE old Breakdown
old Breakdown remains readable
old RevisionItem remains readable
auto rerun new Shot IDs do not break old Reference Clip
boundary/split/merge/manual/restore all trigger STALE
PROCESSING race becomes STALE
ShotRevision + STALE transaction rollback atomically
P1 operations do not modify Final Asset/Binding
fresh empty DB ADD-only init
pre-P1 historical DB ADD-only upgrade
Windows Unicode/space path compatibility
read-only historical access has no hidden writes
```

P1.7 verified：

```text
Windows focused P1 suite: 32/32 PASS
Ubuntu backend compile: PASS
FastAPI import/version: PASS
Ubuntu full pytest: 28 failed, 219 passed, 1 skipped
```

The 28 full-suite failures are pre-existing repository legacy/runtime/environment categories; no new P1 failure category was introduced.

---

## 25. 结论

P1 已把底层语义层级固定为：

```text
ShotRevision / ShotRevisionItem / Reference Clip
= media fact/history

BreakdownRun / anonymous Draft
= semantic Evidence

Character / Scene / Prop Evidence
= specialized validation Evidence

Final Asset / Binding
= product truth

DraftResolution
= future traceable fill-back
```

P1 closure 后正式数据流继续按：

```text
ShotRevision
→ anonymous BreakdownRun
→ P2 semantic evidence generation
→ P4/P5 specialized evidence/resolution
→ Final Asset / Binding
→ P6 DraftResolution / Final Breakdown Renderer
```

**下一阶段只能是 P2：ASR/OCR/VLM anonymous Draft sidecar。** P2 必须消费本 Contract，不能重新发明平行 schema，也不能越级写 Final Asset/Binding。
