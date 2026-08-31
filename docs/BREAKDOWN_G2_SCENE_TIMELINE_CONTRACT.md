# Breakdown G2 — Scene Timeline Contract v1

> Status: **G2.1 Contract + G2.2 Deterministic Assembler FINAL PASS / FROZEN FOUNDATION**  
> Schema: `scene-timeline-v1`  
> Scope: G1 frozen facts → ordinary-user readable Scene Timeline  
> Downstream Narrative: `docs/BREAKDOWN_G2_SCENE_NARRATIVE_CONTRACT.md`

## 1. Why this layer exists

G1 负责“看懂视频并提取事实”。G2.1/G2.2 不再看视频，只把 G1 冻结事实整理成普通用户能直接理解的拉片结果：

```text
Scene
→ 场景信息
→ 出场人物
→ 镜头列表
→ 每镜画面描述
→ 人物动作 / 表演
→ 对白
→ 道具
→ 景别 / 构图
→ 画面文字
→ 确定性剧情摘要基线
```

主结果不展示 Evidence ID、cluster、confidence、subject_A/B、provider profile 等工程诊断信息。

## 2. Frozen source truth

G2.1/G2.2 只消费当前 G1 Serializer 已经组织好的只读结构：

```text
BreakdownRun
└─ SceneSegmentDraft
   ├─ LocalSubject
   ├─ DraftPropHint
   └─ ShotSemanticDraft
      ├─ ShotLocalSubject
      ├─ TimelineEvent
      │  ├─ DIALOGUE / origin=ASR
      │  ├─ OCR / origin=OCR
      │  └─ ACTION
      ├─ DraftPropOccurrence
      └─ ShotRevisionItem media links
```

事实优先级固定：

```text
Exact-Shot current-Shot visual fact > Window / Scene context
ASR DIALOGUE text = 对白文本真相
OCR event text = 画面文字真相
LocalSubject = Scene 内匿名人物，不是 Character
DraftPropHint / occurrence = Draft 道具事实，不是 Final Prop
SceneSegmentDraft = 连续剧情段，不是 Final Scene
```

G2 不读取 Final Character / Scene / Prop 绑定，也不会创建这些资产。

## 3. User-facing output contract

正式 Pydantic Contract：

```text
engine/app/breakdown_scene_timeline_contract_v1.py
```

顶层：

```text
SceneTimelinePayloadV1
├─ schema_version = scene-timeline-v1
├─ source_breakdown_run_id
├─ source_shot_revision_id
├─ episode_id
├─ status / is_current
├─ scene_count / shot_count
├─ warnings
└─ scenes[]
```

每个 Scene：

```text
ordinal / start_us / end_us / duration_us
title
scene_info
people[]       # P1/P2/... + 人物1/人物2/...
story_summary
shots[]
```

每个 Shot：

```text
ordinal / start_us / end_us / duration_us
thumbnail_url / reference_url
visual_description
people[]
performance[]
dialogue[]
props[]
cinematography
on_screen_text[]
```

## 4. Scene-local anonymous people

每个 Scene 独立建立匿名阅读引用：

```text
Scene 1 LocalSubject ordinal 1 → P1 → 人物1
Scene 1 LocalSubject ordinal 2 → P2 → 人物2
Scene 2 LocalSubject ordinal 1 → P1 → 人物1
```

因此 `Scene1.P1` 与 `Scene2.P1` **绝不表示同一个真实人物**。

已有 G1 描述中的唯一匿名标签可以做确定性展示替换，例如：

```text
人物A转头看向人物B
→ 人物1转头看向人物2
```

ASR 对白和 OCR 文字禁止做这种替换。

## 5. Dialogue / OCR truth guards

对白只接受：

```text
event_type = DIALOGUE
origin = ASR
```

`content_text` 原样进入 Timeline：不纠错、不重写、不总结、不因姓名做身份绑定。
只有已有 SPEAKER 关系能映射到当前 Scene LocalSubject 时才填写 `speakers=[P*]`；否则为空。

OCR 只接受：

```text
event_type = OCR
origin = OCR
```

OCR 原文同样逐字保留，与 dialogue 分开输出。

## 6. Exact-Shot visual / props / cinematography

### Visual

```text
ShotSemanticDraft.visual_description
```

优先作为当前镜头可见事实。为空时只允许使用同一 Shot 的 `summary` 做保守后备。
禁止用 Scene summary 或邻镜内容补当前 Shot。

### Props

Shot 只读取已经落到当前 Shot 的 `DraftPropOccurrence`，不会因为某个 PropHint 属于 Scene 就猜它出现在所有 Shot。

### Composition

读取冻结 G1 已落在：

```text
ShotSemanticDraft.model_metadata["composition_hint"]
```

### Camera motion

`UNKNOWN` 转为空值，不由 G2 猜测。

## 7. Deterministic assembler

正式实现：

```text
engine/app/breakdown_scene_timeline_assembler_v1.py
```

处理顺序：

```text
Serializer Draft payload
→ 校验 Run historical anchor
→ Scene 按 ordinal 排序
→ 每 Scene 建立独立 P1/P2 命名空间
→ Shot 按 ordinal 排序
→ Exact-Shot visual
→ ShotLocalSubject / ACTION performance
→ ASR-only dialogue
→ current-Shot prop occurrences
→ shot type / composition / reliable camera motion
→ OCR-only on-screen text
→ strict Pydantic validation
→ scene-timeline-v1
```

整个过程没有模型调用，没有数据库写操作。

## 8. Fail-closed protections

结构性问题直接抛出 `SceneTimelineAssemblyError`：

```text
Scene ordinal 重复/非法
Episode 内 Shot ordinal 重复/非法
Shot scene ownership 不一致
Scene / Shot / event 时间范围非法
Shot 越过所属 Scene
同一 Scene LocalSubject id/ordinal 重复
缺少 Run / ShotRevision historical anchor
```

可降级缺失不创造事实：

```text
无 visual → null + warning
无 ASR → dialogue=[]
无 OCR → on_screen_text=[]
无人物 → people=[]
无 props → props=[]
UNKNOWN camera motion → null
```

## 9. Technical data deliberately excluded

`scene-timeline-v1` 禁止以下工程内部字段进入用户主结果：

```text
EvidenceLink / evidence id
cluster / cluster_key
confidence
subject_A / subject_B observation identity
LocalSubject database id
ShotSemanticDraft database id
provider metadata
VLM/ASR/OCR model profile
search_hint_json
normalized_hint
Final Character / Scene / Prop id
```

Pydantic 使用 `extra="forbid"`。

## 10. Final acceptance

Tests：

```text
engine/tests/v2/test_breakdown_scene_timeline_v1.py
```

User-local regression acceptance on 2026-08-31:

```text
python -m pytest engine/tests/v2/test_breakdown_scene_timeline_v1.py -q
4 passed
```

Final accepted real Run smoke:

```text
Run = BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
scenes = 2
shots = 30
people = [2, 2]
shot1_people = []
shot1_props = ['遥控器', '蓝色玫瑰花束', '玻璃花瓶', '书本']
warnings = []
```

Therefore:

```text
G2.1 Scene Timeline Contract = FINAL PASS / FROZEN FOUNDATION
G2.2 Deterministic Assembler = FINAL PASS / FROZEN FOUNDATION
```

Do not modify this foundation to accommodate Narrative output unless a concrete deterministic regression is proven.

## 11. Downstream G2.3 / G2.4

G2.3/G2.4 are now implemented on top of this frozen contract. See:

```text
docs/BREAKDOWN_G2_SCENE_NARRATIVE_CONTRACT.md
```

The downstream LLM is allowed to produce only:

```text
readable_title
story_summary
```

It cannot own or rewrite any Shot fact. Narrative acceptance remains pending until user-local tests and real local-Qwen validation pass.
