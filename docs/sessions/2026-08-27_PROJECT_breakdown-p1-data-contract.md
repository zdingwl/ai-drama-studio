# Session Handoff — P1 匿名结构化拉片 Draft 数据 Contract

> Date: 2026-08-27  
> Repository: `zdingwl/ai-drama-studio`  
> Branch: `main`  
> Status: P1 CONTRACT DOCUMENTED / READY FOR REVIEW / NO BUSINESS CODE CHANGED

## 1. 本次工作

用户确认继续 Breakdown-first 的下一步，但要求仍然先规划，不写业务代码。

本次已经完成：

```text
读取当前正式 Shot / Revision / Asset / Dialogue 数据结构
→ 确认正式存储链
→ 发现 Shot ID 的真实 Revision 行为
→ 设计 P1 匿名结构化拉片 Draft 数据 Contract
→ 新增正式规划文档
```

新增：

```text
docs/BREAKDOWN_DRAFT_DATA_CONTRACT.md
```

没有修改：

```text
Python 业务代码
Vue 前端
数据库 schema
Character V10.1
Shot Character Assignment
Final Asset / Binding
```

## 2. 关键工程发现

### 2.1 当前正式 V2 Shot 主链

当前正式 `main.py` 的 Shot 编辑路由使用：

```text
shot_edit_routes_v2.py
→ shot_editor_v2.py
→ shot_revision_v2.py
→ studio_v2.Base / studio_v2.sqlite3
```

不是旧：

```text
shot_workbench.py
→ core.database/app.db
```

旧链代码仍存在，但 P1 不应把新 Breakdown 表写到历史数据域。

### 2.2 Shot ID 不能当跨 Revision 永久主锚点

当前：

```text
manual boundary edit
→ Shot ID 通常保留

split
→ left 保留 ID / right 新 ID

auto rerun / restore
→ Current v2_shots 重建
→ 生成新的 Shot IDs
```

但是 `ShotRevisionItem` 会保留历史：

```text
revision_id
original_shot_id
ordinal
start_us/end_us
reference_clip_path
thumbnail_path
```

因此 P1 已冻结：

```text
BreakdownRun.source_shot_revision_id
ShotSemanticDraft.source_shot_revision_item_id
ShotSemanticDraft.source_shot_id_snapshot
```

历史 Draft 不直接依赖 Current `v2_shots.id` 的永久存在。

## 3. P1 核心语义

```text
ShotRevision / Reference Clip
= 媒体事实

BreakdownRun / anonymous Draft
= Semantic Evidence / soft prior

Character / Scene / Prop analysis
= 专用验证 Evidence

Final Asset / Shot Binding
= 产品真值

DraftResolution
= 可追踪回填关系
```

第一遍 Draft：

```text
人物A / 人物B
location_hint
prop_hint
Timeline Events
```

不得直接写：

```text
Character ID
Scene ID
Prop ID
ShotCharacterBinding
ShotSceneBinding
ShotPropBinding
```

## 4. P1 推荐实体

核心运行与 Draft：

```text
v2_breakdown_runs
v2_scene_segment_drafts
v2_shot_semantic_drafts
v2_local_subjects
v2_shot_local_subjects
v2_timeline_events
v2_timeline_event_subjects
v2_draft_prop_hints
v2_draft_prop_occurrences
v2_breakdown_evidence_links
```

未来回填 Contract：

```text
v2_draft_subject_resolutions
v2_draft_scene_resolutions
v2_draft_prop_resolutions
```

具体字段、约束、关系和 validator 见：

```text
docs/BREAKDOWN_DRAFT_DATA_CONTRACT.md
```

## 5. LocalSubject 的重要设计

LocalSubject 不做 Episode/Project 全局身份。

推荐按 Scene Segment 局部化：

```text
SceneSegment 1 的 人物A
!=
SceneSegment 2 的 人物A
```

后续多个 LocalSubject 可以分别被 Character V10.1 / Final Evidence 回填为同一个 Character。

这避免第一遍 VLM 在没有硬 Evidence 时跨场景偷偷“认人”。

## 6. Scene Segment 与 Scene Asset 继续分离

```text
SceneSegmentDraft
= 一段连续剧情，例如“走廊争执”

Final Scene
= 项目级可复用视觉环境，例如“住宅楼走廊”
```

多个 Segment 可以 Resolution 到同一个 Scene。

## 7. TimelineEvent

第一版固定：

```text
VISUAL
ACTION
DIALOGUE
OCR
AUDIO_EVENT
```

每条 Event：

```text
absolute source microseconds
+ shot-relative microseconds
+ participants
+ optional emotion/language
+ provenance/evidence link
```

`DIALOGUE/OCR` TimelineEvent 是拉片语义层，未来不能取代原始 ASR/OCR Evidence。

## 8. Run / Current / STALE

每个 Episode 一个 BreakdownRun：

```text
Current ShotRevision
→ PROCESSING BreakdownRun
→ 全量生成 + validator
→ READY + Current
```

任何新 ShotRevision：

```text
boundary edit
split
merge
restore
auto rerun
```

必须让旧 BreakdownRun：

```text
STALE
但仍可读
```

禁止把旧 Draft 按 ordinal/time 自动迁移冒充新结果。

## 9. P1 后续真正开发建议

用户确认 Contract 后再写代码，顺序：

```text
P1.1 models + ADD-only tables
P1.2 Run lifecycle / Current / STALE
P1.3 validator
P1.4 read-only serializer/API
P1.5 focused tests
P1.6 Shot Revision change → Breakdown stale
P1.7 docs + Windows compatibility acceptance
```

P1 不接 ASR/OCR/VLM；先用 fixture 测试数据模型和生命周期。

## 10. 下一步

下一次继续时先读取：

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
docs/BREAKDOWN_DRAFT_DATA_CONTRACT.md
当前 Shot / Revision / storage code
本 handoff
```

然后先由用户确认 P1 Contract 是否需要调整。

未确认前不要开始 P1 schema/code implementation。
