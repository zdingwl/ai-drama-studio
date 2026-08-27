# AI Drama Studio — P1 匿名结构化拉片 Draft 数据 Contract

> **Status:** P1 CONTRACT DRAFT / READY FOR REVIEW / NOT IMPLEMENTED  
> **Date:** 2026-08-27  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Branch:** `main`  
> **Parent target plan:** `docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md`

## 0. 本文档的边界

本文档只冻结 **Phase P1 的数据语义、表关系、版本/失效规则、输入输出边界**。

```text
本文件 != 当前数据库已经有这些表
本文件 != 已经实现 ASR / OCR / VLM
本文件 != 已经修改 02 拉片页面
```

截至本文档创建时：

```text
业务代码：未修改
数据库：未修改
前端：未修改
Character V10.1：未修改
```

后续真正实现 P1 时，必须再次读取 CURRENT 文档和当前代码，不能只照抄本规划。

---

## 1. 先确认当前真实数据边界

当前 Reference Video V2 正式主链使用：

```text
engine/app/studio_v2.py
→ Base / Project / Episode / Shot
→ data_v2/studio_v2.sqlite3

engine/app/shot_revision_v2.py
→ ShotRevision / ShotRevisionItem

engine/app/shot_editor_v2.py
→ 当前正式 Shot 人工边界修正 / split / merge

engine/app/content_analysis_v2.py
→ 当前资产 AI Evidence

engine/app/asset_workspace_v3.py
→ Final Character / Scene / Prop + Shot Bindings + AssetRevision
```

仓库中历史 `core.database/app.db`、旧 `shot_workbench.py` 等代码仍存在，但 **P1 Breakdown Draft 不应新建到那条历史数据域**。

P1 推荐继续使用：

```text
engine.app.studio_v2.Base
+ 同一个 studio_v2.sqlite3
+ ADD-only 新表
```

原因：当前正式 `main.py` / Shot editing / Asset V2 数据都以这一套 Project / Episode / Shot ID 为主业务对象。

### 1.1 重要纠正：Shot ID 不是跨所有 Revision 永久不变

当前行为：

```text
人工移动 Shot 边界
→ 大部分已有 Shot ID 可继续保留

Split
→ 左 Shot 保留 ID，右 Shot 新建 ID

自动重新拉片 / Restore
→ Current v2_shots 会重建
→ 新 Current Shot 生成新的 Shot ID
```

而 `ShotRevisionItem` 会长期保存：

```text
revision_id
original_shot_id
ordinal
start_us / end_us
reference_clip_path
thumbnail_path
```

因此 P1 的历史 Draft **不能只用 `v2_shots.id` 作为永久外键**。

正式规划：

```text
BreakdownRun
→ 固定 source_shot_revision_id

ShotSemanticDraft
→ 固定 source_shot_revision_item_id
→ 同时保存 source_shot_id_snapshot
```

这样即使用户后来重新切 Shot，旧 Draft 仍然能打开对应历史 Reference Clip 和历史时间轴。

---

## 2. P1 核心不变量

### 2.1 第一版 Draft 是匿名语义，不是 Final Asset

```text
人物A / 人物B / LocalSubject
!= Character

location_hint / SceneSegmentDraft
!= Scene

DraftPropHint
!= Prop
```

Draft 只能提供“应该找什么”的软先验。

### 2.2 AI Draft 必须不可变

一次 READY 的 AI Draft Run 不允许被人工编辑覆盖。

未来 P3 的人工修改必须建立独立 Revision / Overlay，不 UPDATE 原始 AI Draft Evidence。

### 2.3 每次 Run 必须绑定一个明确 Shot Revision

```text
Episode Current Shot Revision R5
↓
BreakdownRun source_shot_revision_id = R5
↓
本 Run 所有 Shot Draft 都只解释 R5
```

Shot Revision 改成 R6 后：

```text
R5 BreakdownRun → STALE
R5 数据仍可读
R6 必须重新生成新的 BreakdownRun
```

禁止按 ordinal 或相似时间偷偷把旧 Draft 自动冒充成新 Shot 的结果。

### 2.4 正式时间统一 integer microseconds

所有正式字段统一：

```text
source_start_us
source_end_us
shot_relative_start_us
shot_relative_end_us
```

禁止把浮点秒或 `frame_index / fps` 作为正式时间事实。

### 2.5 不把完整 Draft 塞入一个 JSON / prose 字段

允许 JSON 保存：

```text
模型 provider metadata
可扩展 appearance attributes
soft screen-position hints
模型原始辅助 metadata
```

但下面这些必须是可查询实体：

```text
Scene Segment
Shot Draft
Local Subject
Subject Shot Presence
Timeline Event
Prop Hint
Resolution
```

---

## 3. 推荐实体关系

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
      │  │  └─ DraftPropOccurrence
      │  ├─ LocalSubject
      │  └─ DraftPropHint
      │
      └─ EvidenceLink

LocalSubject
└─ future SubjectResolution → Final Character

SceneSegmentDraft
└─ future SceneResolution → Final Scene

DraftPropHint
└─ future PropResolution → Final Prop
```

核心语义：

```text
BreakdownRun = 一次 AI 拉片证据快照
SceneSegmentDraft = 一段连续剧情场景
ShotSemanticDraft = 一个 Shot 的结构化理解
LocalSubject = 一个 Scene Segment 内的匿名人物
ShotLocalSubject = LocalSubject 在某个 Shot 中的具体出现
TimelineEvent = 某时间段发生了什么
DraftPropHint = 剧情上值得后续验证的道具候选
DraftResolution = 匿名 Draft → Final Asset 的回填关系
```

---

## 4. 表 1：`v2_breakdown_runs`

### 作用

保存一次 Episode 级匿名结构化拉片分析 Run，并冻结它解释的 Shot Revision。

推荐字段：

```text
id                         BREAKDOWNRUN_xxx PK
project_id                 FK → v2_projects.id
episode_id                 FK → v2_episodes.id
source_shot_revision_id    FK → v2_shot_revisions.id

status                     PROCESSING | READY | READY_WITH_WARNINGS | FAILED | STALE
is_current                 bool
schema_version             breakdown-draft-v1
pipeline_profile           provider/profile version

component_status_json      ASR/OCR/VLM/segmenter 各阶段状态
provider_metadata_json     模型/版本/设备/参数摘要
counts_json                segment/shot/subject/event/prop counts
warning_json               非致命警告
error_message              nullable

started_at
completed_at
```

约束：

```text
同一 episode 同时最多一个 is_current = true 的 READY/READY_WITH_WARNINGS Run
source_shot_revision_id 必须属于 episode_id
Run READY 前必须完整通过 validator
```

推荐 Run 粒度：**每 Episode 一个 Run**。

原因：ASR、Speaker、Scene Segment 和 Shot Revision 都天然是 Episode 时间轴；项目批量拉片只负责按照 `Episode.sort_order` 顺序调度多个 Episode Run，不需要把所有集硬塞进一个事务。

---

## 5. 表 2：`v2_scene_segment_drafts`

### 作用

表达剧情意义上的连续场景段，而不是项目级视觉 Scene Asset。

推荐字段：

```text
id                         SCENESEG_xxx PK
run_id                     FK → v2_breakdown_runs.id
episode_id                 FK → v2_episodes.id
ordinal                    1..N

source_start_us
source_end_us

location_hint              住宅楼走廊 / 病房 / 办公室 ...
interior_exterior           INTERIOR | EXTERIOR | MIXED | UNKNOWN
time_of_day                 DAY | NIGHT | DAWN | DUSK | UNKNOWN
scene_function_hint         confrontation / transition / setup ... nullable
summary                     该段剧情概要
environment_description     环境视觉描述
confidence

metadata_json               可扩展 soft semantic metadata
```

约束：

```text
同一个 Run 内 ordinal 唯一
source_start_us < source_end_us
Scene Segment 必须由连续 Shot Draft 组成
每个 ShotSemanticDraft 在一个 Run 内恰好属于一个 SceneSegmentDraft
```

注意：

```text
SceneSegmentDraft “走廊争执”
可以最终解析到 Final Scene “住宅楼走廊”

另一个 SceneSegmentDraft “走廊和解”
也可以解析到同一个 Final Scene
```

---

## 6. 表 3：`v2_shot_semantic_drafts`

### 作用

保存每个历史 Shot Revision Item 的第一遍结构化理解。

推荐字段：

```text
id                              SHOTDRAFT_xxx PK
run_id                          FK → v2_breakdown_runs.id
scene_segment_id                FK → v2_scene_segment_drafts.id
source_shot_revision_item_id    FK → v2_shot_revision_items.id

source_shot_id_snapshot         原 v2_shots.id，仅作为快照/追踪，不做永久 Current FK
shot_ordinal_snapshot
source_start_us
source_end_us

summary                          该 Shot 发生了什么
visual_description               纯画面事实描述
shot_language                    zh / en / ... nullable
shot_type_hint                   CLOSE_UP / MEDIUM / WIDE ... nullable
camera_motion_hint               STATIC / PAN / TILT / DOLLY ... nullable
narrative_function_hint          reaction / dialogue / insert ... nullable
confidence

model_metadata_json
```

唯一约束：

```text
(run_id, source_shot_revision_item_id) UNIQUE
```

为什么保存时间快照：

即使历史 `ShotRevisionItem` 可读，Draft 自身也应该能独立验证：模型实际分析时认为的 Shot 时间范围与 Revision Item 是否一致。

---

## 7. 表 4：`v2_local_subjects`

### 作用

保存一个 Scene Segment 内的匿名人物，不承担跨 Scene / 跨 Episode 身份真值。

推荐字段：

```text
id                         LOCALSUBJECT_xxx PK
run_id                     FK → v2_breakdown_runs.id
scene_segment_id           FK → v2_scene_segment_drafts.id
ordinal                    1..N within segment

display_label              人物A / 人物B / 人物C
role_hint                  女主? / 保安? / 医生? 等只能是 hint，nullable
appearance_summary         年轻女性、黑色上衣、长发...
appearance_json            clothing / hair / approximate age presentation / accessories 等 soft hints
first_seen_us
last_seen_us
speaking_state_summary     speaking / silent / mixed / unknown
confidence
```

约束：

```text
(scene_segment_id, ordinal) UNIQUE
LocalSubject 不允许写 character_id
LocalSubject 不允许直接生成 Final Character
```

为什么按 Scene Segment 局部化：

```text
Scene 1 的“人物A”
和 Scene 2 的“人物A”
默认不是同一个身份声明
```

未来 Character V10.1 / Final Binding 可以把多个 LocalSubject 分别解析到同一个 Character，这比让 VLM 第一遍就跨全剧认人更安全。

---

## 8. 表 5：`v2_shot_local_subjects`

### 作用

表达 LocalSubject 在具体 Shot 中的出现状态。

这是必须独立出来的 many-to-many 层，因为一个 LocalSubject 可以跨同一 Scene Segment 的多个 Shot，而其画面位置、可见度、说话状态每 Shot 都不同。

推荐字段：

```text
id                         SHOTSUBJECT_xxx PK
run_id
shot_draft_id              FK → v2_shot_semantic_drafts.id
local_subject_id           FK → v2_local_subjects.id

first_seen_us
last_seen_us
screen_position            LEFT | CENTER | RIGHT | MIXED | UNKNOWN
visibility                 FULL | PARTIAL | OCCLUDED | BACK_VIEW | UNKNOWN
speaking_state             SPEAKING | NOT_SPEAKING | POSSIBLE | UNKNOWN
activity_summary
confidence

search_hint_json           只作为后续 Person Evidence 定向搜索提示
```

唯一约束：

```text
(shot_draft_id, local_subject_id) UNIQUE
```

重要：`search_hint_json` 不是 bbox Evidence，更不是 Character Track。

---

## 9. 表 6：`v2_timeline_events`

### 作用

统一保存一个 Shot 内带时间的视听事件。

`event_type` 第一版固定：

```text
VISUAL
ACTION
DIALOGUE
OCR
AUDIO_EVENT
```

推荐字段：

```text
id                         TIMELINEEVENT_xxx PK
run_id
shot_draft_id              FK → v2_shot_semantic_drafts.id
ordinal                    1..N within shot

event_type
source_start_us
source_end_us
shot_relative_start_us
shot_relative_end_us

content_text               统一可读文本
language                   nullable
emotion_hint               nullable
speaking_style_hint        nullable
confidence
origin                     VLM | ASR | OCR | FUSION | RULE
metadata_json
```

约束：

```text
shot 的 source_start_us <= event.source_start_us < event.source_end_us <= shot.source_end_us
shot_relative_* 必须与 source_* 和 Shot start snapshot 一致
(shot_draft_id, ordinal) UNIQUE
```

注意：

- `DIALOGUE` Event 可以展示 ASR 文本，但底层 P2 仍应保留独立 ASR Speech Evidence；TimelineEvent 是拉片语义层，不取代原始 ASR Evidence。
- `OCR` Event 同理，不能取代 OCR Observation。

---

## 10. 表 7：`v2_timeline_event_subjects`

### 作用

允许一条事件包含多个匿名人物，并明确每个人在事件里的角色。

推荐字段：

```text
id
event_id                    FK → v2_timeline_events.id
local_subject_id            FK → v2_local_subjects.id
role                         ACTOR | TARGET | SPEAKER | LISTENER | WITNESS | OTHER
confidence
```

唯一约束：

```text
(event_id, local_subject_id, role) UNIQUE
```

为什么不只在 TimelineEvent 放一个 `subject_id`：

短剧常见：

```text
人物A 拦住人物B
人物A 对人物B说话
人物A、人物B同时转头看人物C
```

一个单值 subject 字段无法稳定表达。

---

## 11. 表 8：`v2_draft_prop_hints`

### 作用

保存“剧情上值得后续验证”的道具候选，而不是所有画面 Object。

推荐字段：

```text
id                         PROPHINT_xxx PK
run_id
scene_segment_id           FK → v2_scene_segment_drafts.id
ordinal
label_hint                 蓝玫瑰 / 合同 / 手机
normalized_hint            optional canonical text
importance                 KEY | SUPPORTING | AMBIENT | UNKNOWN
narrative_reason            为什么认为它是剧情相关物
first_seen_us
last_seen_us
confidence
metadata_json
```

约束：

DraftPropHint 不允许直接写 `prop_id`。

---

## 12. 表 9：`v2_draft_prop_occurrences`

### 作用

告诉 P4：应该去哪些 Shot / 时间段定向寻找这个 Prop。

推荐字段：

```text
id
prop_hint_id                FK → v2_draft_prop_hints.id
shot_draft_id               FK → v2_shot_semantic_drafts.id

source_start_us
source_end_us
screen_position_hint        nullable
interaction_summary         谁拿着 / 谁看向 / 放在哪里
confidence
search_region_hint_json     soft hint only
```

唯一约束可采用：

```text
(prop_hint_id, shot_draft_id, source_start_us, source_end_us)
```

`search_region_hint_json` 不是 Object Detector 的正式 bbox/mask Evidence。

---

## 13. 表 10：`v2_breakdown_evidence_links`

### 作用

建立 Semantic Draft 与未来 P2 原始 Evidence 的可追溯关系。

因为 P1 时 ASR/OCR/VLM Evidence 表尚未最终选型，这里不应该强行 FK 到不存在的表，而是先冻结一个通用 provenance contract。

推荐字段：

```text
id
run_id
owner_type                  SCENE_SEGMENT | SHOT_DRAFT | LOCAL_SUBJECT | TIMELINE_EVENT | PROP_HINT
aowner_id                   对应 owner id
source_type                 ASR_SEGMENT | ASR_WORD | OCR_OBSERVATION | VLM_OUTPUT | FRAME | AUDIO_RANGE | RULE
source_id                   nullable；正式 Evidence 实体存在后填写
source_uri                  可追踪 artifact/ref，nullable
role                         SUPPORT | PRIMARY | CONFLICT | CONTEXT
confidence
metadata_json
```

> 实现时字段名应为 `owner_id`，上面的 `aowner_id` 只说明逻辑位置；正式 schema 不应保留拼写错误。

P1 实现前最终 DDL 必须锁为：

```text
owner_id
```

原则：

```text
Draft confidence 不能只有一个数字而完全不知道来自什么。
```

---

## 14. `DraftResolution` 逻辑 Contract

目标概念仍然是：

```text
LocalSubject → Character
SceneSegmentDraft → Scene
DraftPropHint → Prop
```

但物理数据库 **不推荐做一个无外键的 polymorphic source_id/target_id 大表**。

为了 referential integrity，P1 推荐冻结成三个独立 Resolution 表：

### 14.1 `v2_draft_subject_resolutions`

```text
id
local_subject_id            FK → v2_local_subjects.id
character_id                FK → v2_characters.id
resolution_source           AUTO_EVIDENCE | MANUAL | RESTORE
source_asset_run_id         nullable
confidence
status                      RESOLVED | CONFLICT | REJECTED | NEEDS_REVIEW
provenance_json
created_at
```

### 14.2 `v2_draft_scene_resolutions`

```text
id
scene_segment_id            FK → v2_scene_segment_drafts.id
scene_id                    FK → v2_scenes.id
resolution_source
source_asset_run_id
confidence
status
provenance_json
created_at
```

### 14.3 `v2_draft_prop_resolutions`

```text
id
prop_hint_id                FK → v2_draft_prop_hints.id
prop_id                     FK → v2_props.id
resolution_source
source_asset_run_id
confidence
status
provenance_json
created_at
```

这些 Resolution 表可以在 P1 migration 先创建但不写入，也可以在 P5/P6 再 ADD；**Contract 现在先冻结，业务使用后置。**

### Resolution 真值规则

```text
SubjectResolution 只能消费已确认 Character / Shot Binding Evidence
不能因为 VLM 说“像徐然”就直接 RESOLVED

SceneResolution / PropResolution 同样必须记录 Final Asset Evidence 来源
```

---

## 15. P1 不新增什么

P1 **不应该**新增或修改：

```text
Character identity score
Character V10.1 thresholds
ShotCharacterBinding rule
Scene Final resolver
Prop Final resolver
Dialogue final localization
Voice
Generation
```

P1 也不应该往现有 `Shot.short_description` 写一整篇 Draft。

现有字段：

```text
Shot.short_description
Shot.shot_type
Shot.camera_motion
```

继续保留兼容，但不是新结构化拉片的主存储。

---

## 16. P1 与当前现有表的关系

### 可以直接读取

```text
v2_projects
v2_episodes
v2_preprocess
v2_shots                 # 只用于启动当前分析
v2_shot_revisions
v2_shot_revision_items   # Breakdown 历史锚点
```

### P1 不能覆盖

```text
v2_content_analysis_runs
v2_character_candidates
v2_character_tracks
v2_scene_candidates
v2_prop_candidates
v2_shot_*_bindings
v2_asset_revisions
v2_dialogues
```

BreakdownRun 和 ContentAnalysisRun 是两个不同层：

```text
BreakdownRun
= AI 先看懂视频，产生匿名语义 Draft

ContentAnalysisRun
= 专用资产 Evidence / identity / Scene / Prop candidate
```

未来正确依赖顺序：

```text
BreakdownRun READY
↓
ContentAnalysisRun 可以读取 Draft hints
↓
Final Asset / Binding
↓
DraftResolution 回填
```

而不是反过来让 BreakdownRun 直接改 Final Asset。

---

## 17. Run 发布与 STALE 规则

### 创建

启动新的 Breakdown Run 前：

```text
1. 找 Episode 当前 ShotRevision
2. 快照 source_shot_revision_id
3. 读取该 Revision 的 ShotRevisionItems
4. 创建 PROCESSING Run
5. 生成全部 Scene/Shot/Subject/Event/Prop Draft
6. validator 全部通过
7. 一次事务切成 READY + is_current
```

### 失败

任一硬校验失败：

```text
Run = FAILED
旧 Current BreakdownRun 不变
```

### Shot 修改

任何产生新 Current `ShotRevision` 的动作：

```text
manual boundary edit
split
merge
restore
auto rerun
```

都必须：

```text
把该 Episode 当前 BreakdownRun 标记 STALE
不删除旧 Run
不删除历史 Draft
```

### 为什么不能“自动迁移旧 Draft”

因为 Shot split/merge/重切会改变：

```text
时间边界
Reference Clip
事件归属
LocalSubject 出现范围
Scene Segment 边界
ASR/OCR/VLM 上下文
```

简单按时间重映射会制造看似正常但语义错误的数据。

---

## 18. Validator 必须检查

P1 后续代码实现必须至少验证：

```text
1. Run 的 ShotRevision 属于同一 Episode
2. 每个 Revision Item 恰好一个 ShotSemanticDraft
3. 每个 Shot Draft 恰好属于一个 SceneSegmentDraft
4. Scene Segment 的 Shot 必须连续、顺序一致
5. Scene Segment 时间覆盖由其首尾 Shot 决定
6. LocalSubject 只能出现在自己所属 Scene Segment 的 Shot 中
7. TimelineEvent 时间必须落在所属 Shot 范围内
8. TimelineEvent relative/source 时间必须一致
9. PropOccurrence 时间必须落在所属 Shot 范围内
10. Draft 不能包含 Final character_id / scene_id / prop_id
11. READY Run 不允许缺 Shot Draft
12. READY Run 不允许引用另一个 Run 的 LocalSubject / Event / PropHint
13. confidence 必须在 0..1 或 NULL
14. 当前 ShotRevision 变化后旧 Run 不得继续 is_current
```

---

## 19. P2 的标准输入 / 输出接口

P1 Contract 冻结后，P2 不应该自己重新发明数据结构。

### P2 输入

```text
Episode
Current ShotRevision
ShotRevisionItems
Reference Clips / Keyframes
Episode Audio
ASR Evidence
OCR Evidence
邻接 Shot Context
```

### P2 输出

只允许写：

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

P2 明确禁止写：

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

## 20. 一个 Shot 的目标结构化示例

```json
{
  "shot": {
    "source_shot_revision_item_id": "SHOTREVITEM_xxx",
    "source_shot_id_snapshot": "SHOT_xxx",
    "ordinal": 2,
    "source_start_us": 1000000,
    "source_end_us": 4600000,
    "summary": "人物A拦住人物B并质问花的归属",
    "visual_description": "住宅楼走廊，两名女性面对面站立，人物B手提黑色塑料袋"
  },
  "local_subjects": [
    {
      "id": "LOCALSUBJECT_A",
      "display_label": "人物A",
      "appearance_summary": "年轻女性，黑色上衣"
    },
    {
      "id": "LOCALSUBJECT_B",
      "display_label": "人物B",
      "appearance_summary": "中年女性，手提黑色塑料袋"
    }
  ],
  "events": [
    {
      "type": "ACTION",
      "start_us": 1100000,
      "end_us": 1800000,
      "text": "人物A拦住人物B",
      "participants": [
        ["人物A", "ACTOR"],
        ["人物B", "TARGET"]
      ]
    },
    {
      "type": "DIALOGUE",
      "start_us": 1900000,
      "end_us": 4300000,
      "text": "王阿姨，我刚到的花怎么又在你家花瓶里？",
      "participants": [
        ["人物A", "SPEAKER"]
      ],
      "emotion_hint": "质问"
    }
  ]
}
```

注意：这里即使 Dialogue 文本里出现“王阿姨”，也不能因此把 `人物B` 直接绑定为某个 Character。

---

## 21. P1 后续实现建议顺序

真正开始写 P1 代码时，建议拆成：

```text
P1.1 新增 breakdown model module + ADD-only tables
P1.2 Run lifecycle / Current / STALE
P1.3 validator
P1.4 read-only serializer/API
P1.5 focused tests
P1.6 Shot edit / auto rerun → mark BreakdownRun STALE
P1.7 文档同步 + Windows 空数据/历史项目兼容验收
```

此阶段依然不接 ASR/OCR/VLM 推理，测试可以用固定 fixture 构造匿名 Draft。

这样先验证数据 Contract 本身，再进入 P2 模型层。

---

## 22. P1 focused tests 最低清单

```text
1. current ShotRevision 可创建 PROCESSING BreakdownRun
2. Run 必须固定 source_shot_revision_id
3. 每个 ShotRevisionItem 只能有一个 ShotSemanticDraft / Run
4. 多 Shot SceneSegment 顺序和时间连续
5. 同一 LocalSubject 可绑定同 Segment 多个 Shots
6. 不同 SceneSegment 可以分别出现“人物A”而不代表同一身份
7. Event participant 支持 ACTOR/TARGET/SPEAKER 多角色
8. PropHint 只做 hint，不产生 Final Prop
9. Draft rows 不含 Final Asset FK
10. READY 前 validator 阻断缺失 Shot Draft
11. 新 Shot Revision 产生后旧 BreakdownRun → STALE
12. 新 Shot Revision 不删除旧 BreakdownRun
13. 自动重拉产生新 Shot IDs 后旧 Draft 仍能通过 ShotRevisionItem 打开历史 Reference Clip
14. Failed Run 不替换旧 Current Run
15. P1 操作不改 Character/Scene/Prop/Shot Binding/AssetRevision
```

---

## 23. 结论

P1 最关键的不是“多建几张表”，而是先建立正确的语义隔离：

```text
Shot Revision / Reference Clip
= 媒体事实

BreakdownRun / Draft
= 匿名语义 Evidence

Character / Scene / Prop Evidence
= 专用验证 Evidence

Final Asset / Binding
= 产品真值

DraftResolution
= 两层之间可追踪回填
```

正式数据流因此固定为：

```text
ShotRevision
→ anonymous BreakdownRun
→ Draft-guided Evidence extraction
→ Final Asset / Binding
→ DraftResolution
→ Final Breakdown Renderer
```

这套 Contract 的目标就是保证：未来即使 ASR、OCR、VLM、人物、场景、道具模型替换，底层数据语义仍然不会重新混乱。
