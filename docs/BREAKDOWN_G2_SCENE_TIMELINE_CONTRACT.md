# Breakdown G2 — Scene Timeline Contract v1

> Status: **G2.1 Contract + G2.2 Deterministic Assembler IMPLEMENTED / USER-LOCAL ACCEPTANCE PENDING**  
> Schema: `scene-timeline-v1`  
> Scope: G1 frozen facts → ordinary-user readable Scene Timeline  
> Does not include: Scene-level LLM, persistence, API route, final result UI

## 1. Why G2 exists

G1 已经负责“看懂视频并提取事实”。G2 不再看视频，也不重新识别任何视觉内容。

G2 的第一目标是把机器内部的 Draft / Evidence 表达整理成普通用户一眼能看懂的拉片结果：

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
→ 这一段剧情发生了什么
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

## 3. G2.1 user-facing output contract

正式 Pydantic Contract：

```text
engine/app/breakdown_scene_timeline_contract_v1.py
```

顶层：

```text
SceneTimelinePayloadV1
├─ schema_version = scene-timeline-v1
├─ source_breakdown_run_id        # 追溯字段，普通主 UI 不展示
├─ source_shot_revision_id        # 历史媒体锚点，普通主 UI 不展示
├─ episode_id
├─ status / is_current
├─ scene_count / shot_count
├─ warnings                       # 只允许用户可理解的降级提示
└─ scenes[]
```

每个 Scene：

```text
SceneTimelineSceneV1
├─ ordinal / start_us / end_us / duration_us
├─ title
├─ scene_info
│  ├─ location
│  ├─ interior_exterior
│  ├─ time_of_day
│  └─ environment
├─ people[]
│  ├─ ref = P1/P2/...
│  ├─ display_name = 人物1/人物2/...
│  └─ appearance
├─ story_summary
└─ shots[]
```

每个 Shot：

```text
SceneTimelineShotV1
├─ ordinal / start_us / end_us / duration_us
├─ thumbnail_url / reference_url
├─ visual_description
├─ people[]
├─ performance[]
├─ dialogue[]
├─ props[]
├─ cinematography
│  ├─ shot_type
│  ├─ composition
│  └─ camera_motion
└─ on_screen_text[]
```

## 4. Scene-local anonymous people

G2 不允许把 LocalSubject 变成 Character。

每个 Scene 独立建立匿名阅读引用：

```text
Scene 1 LocalSubject ordinal 1 → P1 → 人物1
Scene 1 LocalSubject ordinal 2 → P2 → 人物2

Scene 2 LocalSubject ordinal 1 → P1 → 人物1
```

因此：

```text
Scene1.P1 == Scene2.P1
```

**绝不表示同一个真实人物。** P* 只是当前 Scene 内用于让结果文字容易阅读的临时引用。

已有 G1 描述中的唯一匿名标签可以做确定性展示替换，例如：

```text
人物A转头看向人物B
→
人物1转头看向人物2
```

但是 ASR 对白和 OCR 文字禁止做这种替换。

## 5. Dialogue truth guard

最终对白只接受：

```text
event_type = DIALOGUE
origin = ASR
```

`content_text` 原样进入 Scene Timeline：

- 不 trim；
- 不纠错；
- 不重写；
- 不总结；
- 不因为里面出现姓名/“人物A”等文字而做身份绑定。

只有 G1 已经存在 `TimelineEventSubject.role=SPEAKER` 且该 LocalSubject 属于当前 Scene 时，才填写 `speakers=[P*]`。

没有可靠 SPEAKER 关系时：

```text
speakers = []
```

G2 不猜谁在说话。

任何非 ASR 来源的 DIALOGUE event 都不会进入用户对白，并产生汇总 warning。

## 6. OCR truth guard

最终画面文字只接受：

```text
event_type = OCR
origin = OCR
```

OCR `content_text` 原样保留，并与 dialogue 分开输出。没有 OCR 时 `on_screen_text=[]`，前端后续直接隐藏该区域即可。

## 7. Exact-Shot visual / props / cinematography

### Visual description

优先读取：

```text
ShotSemanticDraft.visual_description
```

它是当前生产链 Exact-Shot 的当前镜头视觉事实。只有该字段为空时，才使用同一个 ShotSemanticDraft 的 `summary` 做保守后备。

禁止：

- 用 Scene summary 补当前 Shot；
- 用邻镜人物/动作/道具补当前 Shot；
- 在 G2 重新调用 VLM。

### Props

Shot 只读取已经落到当前 Shot 的 `DraftPropOccurrence`。

不会因为某个 `DraftPropHint` 属于 Scene 就猜它出现在所有 Shot。

### Composition

当前 G1 Fusion 已把 Exact-Shot `composition_hint` 保存在：

```text
ShotSemanticDraft.model_metadata["composition_hint"]
```

G2 只读该值。

### Camera motion

Exact-Shot Compact v3 对静态采样不能可靠判断运镜，因此生产值通常为 `UNKNOWN`。G2 将 `UNKNOWN` 转为空值，不额外猜测。

## 8. Deterministic assembler

正式实现：

```text
engine/app/breakdown_scene_timeline_assembler_v1.py
```

处理顺序：

```text
Serializer Draft payload
→ 校验 Run historical anchor
→ Scene 按 ordinal 排序
→ 每 Scene 建立独立 P1/P2 匿名命名空间
→ Shot 按 ordinal 排序
→ Exact-Shot visual
→ ShotLocalSubject / ACTION performance
→ ASR-only dialogue
→ Shot prop occurrences
→ composition / shot type / reliable camera motion
→ OCR-only on-screen text
→ Pydantic Contract 严格校验
→ scene-timeline-v1
```

整个过程没有模型调用，没有数据库写操作。

## 9. Fail-closed protections

以下结构性问题直接抛出 `SceneTimelineAssemblyError`，不让 G2 猜修：

- Scene ordinal 重复/非法；
- Episode 内 Shot ordinal 重复/非法；
- Shot `scene_segment_id` 与所在 Scene 不一致；
- Scene / Shot / event 时间范围非法；
- Shot 时间跑出所属 Scene；
- 同一 Scene LocalSubject id/ordinal 重复；
- 缺少 Run / ShotRevision historical anchor。

以下属于可降级缺失，不创造事实：

- Shot 无可靠 visual → `visual_description=null` + 汇总 warning；
- 无 ASR dialogue → `dialogue=[]`；
- 无 OCR → `on_screen_text=[]`；
- 无人物 → `people=[]`；
- 无 props → `props=[]`；
- `camera_motion=UNKNOWN` → `null`；
- G1 有 unassigned Draft → 主结果不擅自归属，并给汇总 warning。

## 10. Technical data deliberately excluded

`scene-timeline-v1` 不允许以下工程内部字段进入用户主结果：

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

Pydantic Contract 使用 `extra="forbid"`，防止后续代码无意把调试字段塞进主结果。

## 11. G2.1/G2.2 acceptance tests

新增：

```text
engine/tests/v2/test_breakdown_scene_timeline_v1.py
```

覆盖：

- 2 Scene / Scene-local P* 重置；
- Shot0001 类“无人 + 蓝色玫瑰花束 + 玻璃花瓶”结构；
- Exact-Shot visual / composition；
- 人物动作的匿名展示替换；
- ASR 对白逐字保留，包括双空格和原文中的“人物A”；
- 非 ASR dialogue 不进入最终对白；
- OCR 原文保留；
- Evidence / confidence / LocalSubject ID 等不泄漏；
- STALE 历史 Run 保留历史状态，不发布新真相；
- 重复 Shot ordinal / Shot 越过 Scene 时间边界 fail closed。

按照项目测试纪律，本次通过 GitHub 连接器提交代码，不运行 Hosted GitHub Actions，也不声明 assistant-local pytest PASS。用户本机验收后再更新为 PASS。

## 12. Explicitly not implemented yet

本阶段故意没有实现：

```text
G2.3 Scene-level pure-text LLM
G2.4 LLM source/support validator
G2.5 Scene Timeline API
G2.6 ordinary-user Scene Timeline UI
G2 persistence tables
Final Character / Final Scene / Final Prop creation
```

下一步只有在 G2.1/G2.2 用户本机测试通过后，再进入 G2.3/G2.4。
