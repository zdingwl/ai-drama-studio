# AI Drama Studio — 拉片先行 / Breakdown-first 资产识别改造地图

> **Status:** ACCEPTED TARGET PLAN / P1 IMPLEMENTED / P2 NEXT  
> **Created:** 2026-08-27 16:22 +08:00  
> **Last synchronized:** 2026-08-27 20:15 +09:00  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Branch:** `main`  
> **Current executable baseline:** Reference Video V2 / FastAPI 2.4.1 / Character V10.1 / Breakdown P1

## 0. 这份文档是什么

这份文档记录用户确认的**目标产品流程、保护规则和实施顺序**。

当前事实仍以：

```text
docs/PROJECT_STATE.md
+ docs/CURRENT_IMPLEMENTATION_MANIFEST.md
+ 当前代码 / 测试
= CURRENT
```

本文件同时记录目标与每个 Phase 的实施状态。

截至 P1.7：

```text
P0 = COMPLETE
P1 = COMPLETE
P2 = NEXT / NOT IMPLEMENTED
P3-P7 = PLANNED / NOT IMPLEMENTED
```

因此不能因为 `LocalSubject` / `TimelineEvent` 等表已经存在，就声称 ASR/OCR/VLM 内容拉片已经完成。

---

## 1. 用户确认的产品定义

### 1.1 “拉片”不等于“切镜头”

镜头切分只是拉片的技术准备。

目标完整拉片要输出类似人工拉片师整理的带时间轴视听脚本，例如：

```text
场景 1 · 内 · 住宅楼走廊 · 00:00-00:22
人物：人物A、人物B
关键道具：蓝玫瑰、花瓶、黑色塑料袋

[00:00] 蓝玫瑰插在玻璃花瓶中，镜头特写。
[00:01] 人物A拦住人物B。

人物A（质问）[00:01]：
“王阿姨，我刚到的花怎么又在你家花瓶里？”
```

第一遍 AI 拉片不能假装已经知道全剧真实人物身份，因此先使用 `人物A / 人物B / LocalSubject` 等匿名主体。

### 1.2 目标主线

```text
原视频
↓
视频预处理
↓
镜头切分
↓
Shot + Reference Clip + ShotRevision history
↓
ASR / OCR / VLM 看懂内容
↓
匿名结构化 Breakdown Draft
  Scene Segment / Shot / 人物A-B / 对白 / 动作 / 道具候选 / 镜头内容
↓
Draft 指导人物 / 场景 / 道具 Evidence 搜索
↓
专用模型验证
↓
跨 Shot / 全项目资产归并
↓
Character / Scene / Prop + Final Shot Bindings
↓
真实身份/资产回填 Draft
↓
Final Breakdown
↓
重制设计 / 视频生成
```

一句话原则：

> **先看懂，再识别，再回填。**

---

## 2. 不可破坏的架构原则

### 2.1 Reference Video V2 不推翻

继续保留：

```text
Project / Episode
FFmpeg / FFprobe
integer microseconds
TransNetV2 Shot boundaries
ShotRevision / ShotRevisionItem
Reference Clip / thumbnail / keyframes
```

注意：`Shot.id` **不是跨所有 Revision 永久稳定的历史锚点**。Auto rerun / restore 会重建 Current Shots。

因此匿名 Breakdown 的历史锚点已经按 P1 实现为：

```text
BreakdownRun → source_shot_revision_id
ShotSemanticDraft → source_shot_revision_item_id
+ source_shot_id_snapshot
```

### 2.2 第一遍 Draft 是语义 Evidence，不是身份真值

允许：

```text
人物A：年轻女性，黑色上衣，正在说话
人物B：中年女性，手提黑色塑料袋
```

禁止第一遍 VLM 直接宣布：

```text
人物A = Character_001 = 徐然
```

### 2.3 Semantic Prior 不能覆盖硬证据

```text
Breakdown Draft / context
= soft prior / search hint

Detection / Track / Face / Person-ReID / Audio / OCR
= measurable evidence
```

冲突时必须保持冲突/重新验证/unresolved，不能为了文案完整强制绑定。

### 2.4 Character V10.1 Contract 保护

P1 已证明匿名 Draft 可以独立落地而无需修改 Character V10.1。

后续阶段仍禁止：

- 放宽新 Character `>=3 Shot / >=3 model-usable images` 等硬 Gate；
- 绕过 same-sample cannot-link；
- 覆盖高质量 Face hard conflict；
- 让 VLM 文本直接创建 Character；
- 让 VLM 文本直接写 `ShotCharacterBinding`；
- 回到 `candidate.tracks` 推导新 Run Final Shot Binding。

### 2.5 Scene Segment 与 Final Scene 分离

```text
SceneSegmentDraft
= 一段连续剧情戏，例如“走廊争执”

Final Scene Asset
= 项目级可复用视觉环境，例如“住宅楼走廊”
```

多个 SceneSegmentDraft 可以最终解析到同一个 Final Scene。

### 2.6 Draft 必须结构化

底层不能只保存一篇 prose。

核心事实需要保持可查询：

```text
ShotRevision / ShotRevisionItem
SceneSegmentDraft
ShotSemanticDraft
LocalSubject
ShotLocalSubject
TimelineEvent / participants
DraftPropHint / occurrence
EvidenceLink
confidence / provenance
```

### 2.7 Migration 先 ADD，不先 DROP

P1 已按此原则完成。

后续继续：

```text
新增表/sidecar/API
→ 与旧项目并存
→ focused tests + Windows acceptance
→ 再考虑废弃旧路径
```

禁止为了新流程删除旧 Run、历史 Revision、Reference Clip 或兼容读取能力。

---

## 3. 当前 → 目标改造地图

| 阶段 | CURRENT | TARGET / 下一步 |
|---|---|---|
| 项目/剧集 | `studio_v2` Project/Episode、多集排序 | 保留 |
| 预处理 | FFprobe/FFmpeg Proxy/Audio/完整解码 | 保留，P2 ASR 消费现有媒体事实 |
| Shot | TransNetV2 + integer-us boundaries | 保留 |
| Shot history | ShotRevision/ShotRevisionItem + manual/split/merge/restore | 保留，Breakdown 绑定 Revision history |
| Reference Clip | 每 Shot 独立 Clip + thumbnail/keyframes | 保留，P2 VLM/OCR 输入 |
| Anonymous Draft storage | **P1 IMPLEMENTED** | P2 自动填充 |
| SceneSegmentDraft | **P1 entity IMPLEMENTED** | P2 生成剧情段；P3 UI 展示 |
| LocalSubject | **P1 entity IMPLEMENTED** | P2 匿名主体；P5 才做安全 Character mapping |
| TimelineEvent | **P1 entity IMPLEMENTED** | P2 用 ASR/OCR/VLM/FUSION 填充 |
| DraftPropHint | **P1 entity IMPLEMENTED** | P4 定向视觉验证 |
| Run lifecycle/validator | **P1 IMPLEMENTED** | P2 必须复用，不能绕过 |
| ShotRevision→STALE | **P1.6 IMPLEMENTED** | 所有后续 Breakdown producer 自动继承 |
| read-only history API | **P1.4 IMPLEMENTED** | P3 消费 |
| ASR/OCR/VLM semantic producer | NOT IMPLEMENTED | **P2 NEXT** |
| 02 拉片 structured UI | NOT IMPLEMENTED | P3 |
| Character | V10.1 implemented | P5 才允许解释性 Draft mapping；硬 Gate 不动 |
| Scene asset | 当前轻量候选 | P4/P6 增强 resolver/fill-back |
| Prop asset | data boundary + fail-closed | P4 定向 detector/tracker/OCR 验证 |
| Final DraftResolution | NOT IMPLEMENTED | P5/P6 |
| Final renderer | NOT IMPLEMENTED | P6 |
| downstream remake | partial/planned | P7 |

---

## 4. P1 已落地的数据层

P1 正式使用：

```text
engine.app.studio_v2.Base
+ data_v2/studio_v2.sqlite3
```

ADD-only tables：

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

Resolution 表根据 frozen Contract 延后到 P5/P6；P1 不向 Draft 表加入 Final Character/Scene/Prop FK。

正式 P1 模块：

```text
breakdown_models_v1.py
breakdown_service_v1.py
breakdown_validator_v1.py
breakdown_serializer_v1.py
breakdown_routes_v1.py
shot_revision_v2.py          # automatic STALE integration
```

详细字段/约束以 `docs/BREAKDOWN_DRAFT_DATA_CONTRACT.md` 为准。

---

## 5. P1 已落地的历史与 STALE 语义

```text
Episode Current ShotRevision R5
↓
BreakdownRun(source_shot_revision_id=R5)
↓
READY / READY_WITH_WARNINGS
```

如果任何操作产生 R6：

```text
boundary edit / split / merge / record_manual_revision / auto rerun / restore
↓
R6 becomes Current ShotRevision
+
R5 active Breakdown → STALE
```

两者在同一个 DB transaction 中完成。

历史数据继续可读：

```text
R5 BreakdownRun
R5 Draft rows
R5 ShotRevisionItems
R5 Reference Clips
```

禁止把 R5 Draft 按 ordinal/time 猜测迁移为 R6 Draft。

---

## 6. 推荐技术方向（P2+ 候选，不代表已安装/已实现）

| 目标能力 | 候选方向 | 规则 |
|---|---|---|
| 媒体 | 当前 FFmpeg / FFprobe | 保留 |
| Shot boundary | 当前 TransNetV2 | 保留 |
| ASR | 评估 Qwen3-ASR / WhisperX 等 | 用真实短剧 benchmark 后选 Provider |
| Speaker | diarization + active speaker | 先匿名 Speaker，再映射主体 |
| OCR | PaddleOCR 类 | 保存原始 OCR Evidence，不只写 Timeline prose |
| 视频理解 | 独立 VLM Provider，评估 Qwen3-VL 等 | 当前 TransVLM route 不等于 P2 |
| Character | 当前 V10.1 | 硬身份验证核心不变 |
| Scene | visual embedding + VLM + OCR + object + temporal context | 不把轻量 HSV candidate 当 Final Scene |
| Prop | Draft hints + open-vocabulary detector + mask/track/OCR | 只物化剧情关键 Prop |
| Final 文案 | deterministic structured renderer + optional language polish | ID/时间/绑定不让语言模型重猜 |

任何 Provider 正式落地前都必须检查：

```text
效果
Windows兼容
本地部署/显存/速度
模型/权重来源
商业许可
可替换 Provider Contract
```

---

## 7. 正式 Phase 顺序

### P0 — Planning / Contract

**COMPLETE**。

### P1 — Draft data/runtime contract

**COMPLETE**。

包含：

```text
P1.1 ADD-only models/tables
P1.2 Run lifecycle
P1.3 validator
P1.4 read-only serializer/API
P1.5 focused compatibility tests
P1.6 ShotRevision → automatic STALE
P1.7 docs sync + Windows empty/historical project acceptance
```

P1 未接 ASR/OCR/VLM inference，未写 Final Asset/Binding。

### P2 — ASR / OCR / VLM anonymous Draft sidecar

**NEXT / NOT IMPLEMENTED**。

目标：

```text
Current ShotRevision
+ ShotRevisionItems / Reference Clips / keyframes
+ Episode audio
↓
ASR Evidence
OCR Evidence
VLM semantic output
↓
P1 validator-compatible anonymous Draft rows
↓
publish BreakdownRun
```

P2 只能写 P1 anonymous Draft/Evidence layer。

明确禁止写：

```text
Character
Scene
Prop
ShotCharacterBinding
ShotSceneBinding
ShotPropBinding
AssetRevision
```

### P3 — 02 拉片 structured Draft UI

**PLANNED**。

显示 Scene Segment、人物A/B、时间轴事件、对白、动作、场景/道具 hints；点击时间回到对应历史/Current Reference Clip。

### P4 — Draft-guided Scene / Prop evidence

**PLANNED**。

先增强当前较弱的 Scene/Prop，不碰 Character V10.1 硬身份门槛。

### P5 — Draft ↔ Character safe integration

**PLANNED**。

前置条件包括当前 Character V10.1 real-video baseline 验收。第一步只做可解释 mapping，不让 Draft 创建身份。

### P6 — Final fill-back + renderer

**PLANNED**。

```text
LocalSubject → Character
SceneSegmentDraft → Final Scene
DraftPropHint → Final Prop
```

从结构化数据渲染标准/国际格式。

### P7 — downstream remake integration

**PLANNED**。

Final Breakdown contract 稳定后再让内容剧本/重制/生成消费。

---

## 8. 每个 Phase 的发布规则

```text
1. 先读取 CURRENT docs + 当前代码 + 本 Plan
2. 一次只进入一个明确 Phase
3. 旧项目兼容优先
4. 数据变化 ADD-only 优先
5. 新 Run 完整成功后才切 Current
6. focused tests + 原有回归
7. Windows acceptance
8. 再同步 CURRENT docs / 本 Plan
9. 新建 session handoff
10. 通过 PR 合入 main
```

P1.7 已把 Windows P1 focused suite 固化为 CI job，后续 P2+ 不能移除该兼容门槛。

---

## 9. 明确禁止的捷径

```text
禁止：把 Shot Detection 完成当成完整拉片完成
禁止：把 P1 表存在当成 P2 模型推理已实现
禁止：VLM 直接创建 Character / Scene / Prop Final Asset
禁止：VLM prose 直接写 ShotCharacterBinding
禁止：从 candidate.tracks 恢复新 Run Final人物绑定
禁止：SceneSegmentDraft 与 Final Scene 共用身份概念
禁止：完整 Draft 只存一段 prose
禁止：剧情上下文覆盖可靠 Face/cannot-link 冲突
禁止：没有可靠 Prop Evidence 时伪造 Prop
禁止：删除旧 Breakdown/ShotRevision/Reference Clip 来“清理历史”
禁止：ShotRevision 变化后让旧 Breakdown 继续冒充 Current
禁止：P2 自己发明一套与 P1 平行的数据 schema
```

---

## 10. 用户最终感知的简单流程

```text
① 视频处理
② 镜头切分
③ AI 内容拉片
④ 人物 / 场景 / 道具识别
⑤ 资产确认与回填
⑥ 最终拉片
⑦ 重制
```

后台保持证据分层，但前端最终应该能渲染成人类易读的带时间轴剧本。

---

## 11. P1.7 验收记录

P1 closure acceptance：

```text
Windows focused P1 suite: 32/32 PASS
Ubuntu backend compile: PASS
FastAPI import/version: PASS
Ubuntu full pytest: 28 failed, 219 passed, 1 skipped
Frontend build: existing vue-tsc / TypeScript failure
```

新增兼容门槛覆盖：

```text
fresh empty DB
idempotent ADD-only init
pre-P1 historical V2 DB
Windows space/Unicode paths
legacy Project/Episode/Shot/reference clip readability
read-only Breakdown no hidden baseline writes
```

因此 **P1 已完成并可作为 P2 的稳定输入 Contract**。

---

## 12. 当前唯一下一阶段

```text
P2 — ASR/OCR/VLM anonymous Draft sidecar
```

开始 P2 前仍需重新读取 `main` 当前 SHA、CURRENT docs、P1 Contract 和最新 handoff。未经明确进入 P2，不提前修改 Provider/runtime。
