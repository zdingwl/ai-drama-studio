# AI Drama Studio — 拉片先行 / Breakdown-first 资产识别改造地图

> **Status:** ACCEPTED TARGET PLAN / P1 COMPLETE / P2 IN PROGRESS / P2.1 + P2.2 + P2.3 + P2.4 COMPLETE / P2.5 NEXT  
> **Created:** 2026-08-27 16:22 +08:00  
> **Last synchronized:** 2026-08-28 09:21 +08:00  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Branch:** `main`  
> **Current executable baseline:** Reference Video V2 / FastAPI 2.4.1 / Character V10.1 / Breakdown P1 + P2.1 + P2.2 + P2.3 + P2.4

## 0. 这份文档是什么

这份文档记录用户确认的**目标产品流程、保护规则和实施顺序**。

当前事实仍以：

```text
docs/PROJECT_STATE.md
+ docs/CURRENT_IMPLEMENTATION_MANIFEST.md
+ 当前代码 / 测试
= CURRENT
```

截至 P2.4：

```text
P0 = COMPLETE
P1 = COMPLETE
P2 = IN PROGRESS
  P2.1 = COMPLETE
  P2.2 = COMPLETE
  P2.3 = COMPLETE
  P2.4 = COMPLETE
  P2.5 = NEXT / NOT IMPLEMENTED
  P2.6 = PLANNED / NOT IMPLEMENTED
P3-P7 = PLANNED / NOT IMPLEMENTED
```

因此不能因为 ASR + OCR + VLM raw Evidence 已存在，就声称**完整匿名 Draft、人物/场景/道具解析或最终拉片已经完成**。真正把三种 Evidence 合成用户可读的结构化拉片，仍然是 P2.5。

---

## 1. 用户确认的产品定义

### 1.1 “拉片”不等于“切镜头”

镜头切分只是拉片的技术准备。目标完整拉片要输出类似人工拉片师整理的带时间轴视听脚本，例如：

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

`Shot.id` 不是跨所有 Revision 永久稳定的历史锚点。Auto rerun / restore 会重建 Current Shots。

匿名 Breakdown 历史锚点：

```text
BreakdownRun → source_shot_revision_id
ShotSemanticDraft → source_shot_revision_item_id
+ source_shot_id_snapshot
```

P2 Provider 输入严格绑定 `BreakdownRun.source_shot_revision_id` 和 exact `ShotRevisionItem`，禁止重新从 Current `v2_shots` 猜历史输入。

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

P2 raw Evidence 中 `character_id / scene_id / prop_id / Final Binding ID` 泄漏必须 fail closed。

P2.4 进一步把模型输出压成匿名白名单；即使模型任意返回业务 ID，也不会原样进入 sidecar。

### 2.3 Semantic Prior 不能覆盖硬证据

```text
Breakdown Draft / context = soft prior / search hint
Detection / Track / Face / Person-ReID / Audio / OCR = measurable evidence
```

冲突时保持冲突/重新验证/unresolved，不能为了文案完整强制绑定。

### 2.4 Character V10.1 Contract 保护

P1/P2 已证明匿名 Draft/Evidence 可以独立落地而无需修改 Character V10.1。后续仍禁止：

- 放宽新 Character `>=3 Shot / >=3 model-usable images` 等硬 Gate；
- 绕过 same-sample cannot-link；
- 覆盖高质量 Face hard conflict；
- 让 VLM 文本直接创建 Character；
- 让 VLM 文本直接写 `ShotCharacterBinding`；
- 让 ASR speaker label 直接绑定 Character；
- 回到 `candidate.tracks` 推导新 Run Final Shot Binding。

P2.4 没有修改上述任何人物算法、阈值、Gate 或 Final Binding 来源。

### 2.5 Scene Segment 与 Final Scene 分离

```text
SceneSegmentDraft = 连续剧情戏，例如“走廊争执”
Final Scene Asset = 项目级可复用视觉环境，例如“住宅楼走廊”
```

多个 SceneSegmentDraft 可以最终解析到同一个 Final Scene。

VLM 的 `location_hint / environment_description` 仍只是语义 hint，不是 Final Scene。

### 2.6 Draft 必须结构化

底层不能只保存一篇 prose。核心事实保持可查询：

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

P2 raw Provider Evidence 与融合后 Draft rows 必须分层保存，不能在 Fusion 后丢失原始 ASR/OCR/VLM 证据。

### 2.7 Migration 先 ADD，不先 DROP

P1 已按此原则完成。P2.1–P2.4 没有删除旧表或历史数据；Provider/raw Evidence 继续走 sidecar + 现有 P1 数据 Contract。

后续继续：

```text
新增表/sidecar/API
→ 与旧项目并存
→ focused tests + Windows acceptance
→ 再考虑废弃旧路径
```

禁止删除旧 Run、历史 Revision、Reference Clip 或兼容读取能力。

---

## 3. 当前 → 目标改造地图

| 阶段 | CURRENT | TARGET / 下一步 |
|---|---|---|
| 项目/剧集 | `studio_v2` Project/Episode、多集排序 | 保留 |
| 预处理 | FFprobe/FFmpeg Proxy/Audio/完整解码 | 保留 |
| Shot | TransNetV2 + integer-us boundaries | 保留 |
| Shot history | ShotRevision/ShotRevisionItem + manual/split/merge/restore | 保留 |
| Reference Clip | 每 Shot 独立 Clip + thumbnail/keyframes | 保留，P2 VLM/OCR 输入 |
| Anonymous Draft storage | **P1 IMPLEMENTED** | **P2.5 自动填充/发布 NEXT** |
| P2 Provider/raw Evidence sidecar | **P2.1 IMPLEMENTED** | P2.5 消费已固化 sidecar |
| ASR producer | **P2.2 IMPLEMENTED** | segment/word Evidence；P2.5 Fusion |
| OCR producer | **P2.3 IMPLEMENTED** | shot/frame-grounded OCR Observation；P2.5 Fusion |
| VLM semantic producer | **P2.4 IMPLEMENTED** | shot-bound anonymous visual semantics；P2.5 Fusion |
| SceneSegmentDraft | **P1 entity IMPLEMENTED** | P2.5 生成剧情段；P3 UI 展示 |
| LocalSubject | **P1 entity IMPLEMENTED** | P2.5 匿名主体；P5 才安全映射 Character |
| TimelineEvent | **P1 entity IMPLEMENTED** | P2.5 用 ASR/OCR/VLM/FUSION 填充 |
| DraftPropHint | **P1 entity IMPLEMENTED** | P2.5 生成 hint；P4 定向视觉验证 |
| Run lifecycle/validator | **P1 IMPLEMENTED** | P2.5 必须复用并发布 |
| ShotRevision→STALE | **P1.6 IMPLEMENTED** | P2.5 写入/发布前继续复核 |
| read-only history API | **P1.4 IMPLEMENTED** | P3 消费 |
| ASR/OCR/VLM Fusion | NOT IMPLEMENTED | **P2.5 NEXT** |
| 02 拉片 structured UI | NOT IMPLEMENTED | P3 |
| Character | V10.1 implemented | P5 才允许解释性 Draft mapping；硬 Gate 不动 |
| Scene asset | 当前轻量候选 | P4/P6 增强 resolver/fill-back |
| Prop asset | data boundary + fail-closed | P4 定向 detector/tracker/OCR 验证 |
| Final DraftResolution | NOT IMPLEMENTED | P5/P6 |
| Final renderer | NOT IMPLEMENTED | P6 |
| downstream remake | partial/planned | P7 |

---

## 4. P1 已落地的数据层

P1 正式使用 `engine.app.studio_v2.Base + data_v2/studio_v2.sqlite3`。

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

Resolution 表延后到 P5/P6；P1 不向 Draft 表加入 Final Character/Scene/Prop FK。

正式 P1 模块：

```text
breakdown_models_v1.py
breakdown_service_v1.py
breakdown_validator_v1.py
breakdown_serializer_v1.py
breakdown_routes_v1.py
shot_revision_v2.py
```

详细字段/约束以 `docs/BREAKDOWN_DRAFT_DATA_CONTRACT.md` 为准。

---

## 5. 历史与 STALE 语义

任何产生新 Current ShotRevision 的操作：

```text
boundary edit / split / merge / record_manual_revision / auto rerun / restore
```

都会在同一 DB transaction 中把旧 Revision 的 active Breakdown 标为 STALE。旧 BreakdownRun / Draft rows / ShotRevisionItems / Reference Clips 继续可读；禁止按 ordinal/time 猜测迁移旧 Draft。

P2 Provider 在推理前、artifact 写入前、Run provenance 更新前复核 Current Revision，避免长耗时模型把旧结果登记为活动 Evidence。

P2.5 在读取 sidecar、写 Draft rows、validator/publish 前也必须再次确认 Run 仍然指向 Episode Current Revision。

---

## 6. 推荐技术方向（P2+）

| 目标能力 | 当前/候选方向 | 规则 |
|---|---|---|
| 媒体 | 当前 FFmpeg / FFprobe | 保留 |
| Shot boundary | 当前 TransNetV2 | 保留 |
| ASR | **P2.2 faster-whisper large-v3 baseline**；Qwen3-ASR + ForcedAligner 留作 P2.6 benchmark | segment + word timing；Provider 可替换 |
| Speaker | diarization + active speaker | 先匿名 Speaker，再映射 LocalSubject；禁止直连 Character |
| OCR | **P2.3 RapidOCR 3.9.2 + PP-OCRv6 small + ONNX Runtime** | exact historical Reference Clip 多帧采样；保存 box/polygon/raw observations |
| 视频理解 | **P2.4 Qwen/Qwen3-VL-4B-Instruct baseline** | exact historical Reference Clip；只产匿名视觉语义；不转写 ASR/OCR 内容 |
| Character | 当前 V10.1 | 硬身份验证核心不变 |
| Scene | visual embedding + VLM + OCR + object + temporal context | 不把 VLM location_hint 或轻量 HSV candidate 当 Final Scene |
| Prop | Draft hints + open-vocabulary detector + mask/track/OCR | 只物化剧情关键 Prop |
| Final 文案 | deterministic structured renderer + optional language polish | ID/时间/绑定不让语言模型重猜 |

任何 Provider 正式落地都必须检查：真实短剧效果、Windows、本地部署、CPU/GPU fallback、模型/权重来源、商业许可、缓存/下载和可替换 Contract。

P2.1 已建立 `BreakdownP2Provider / P2ProviderResult / P2EvidenceRecord` Contract；P2.2–P2.4 均通过该边界接入。

### 6.1 P2.2 ASR 核心规则

```text
faster-whisper==1.2.1
default model = large-v3
word_timestamps = true
ASR source timing = Episode integer microseconds
ASR shot_revision_item_id = NULL until P2.5 Fusion
```

### 6.2 P2.3 OCR 核心规则

```text
rapidocr==3.9.2
PP-OCRv6 small / ONNX Runtime
default cpu
sample_interval_us = 500000
max_frames_per_shot = 12
OCR_OBSERVATION binds exact historical ShotRevisionItem
source time = sampled frame point in Episode integer microseconds
polygon/bbox/normalized geometry preserved
repeated frame observations are NOT deduped before P2.5 Fusion
```

### 6.3 P2.4 VLM 核心规则

```text
provider = qwen3-vl
model = Qwen/Qwen3-VL-4B-Instruct
semantic schema = breakdown-p2-vlm-shot-semantics-v1
input = exact historical ShotRevisionItem Reference Clip
output = one normalized shot-bound VLM_OUTPUT per usable Shot
source time = full historical Shot source interval
confidence = NULL / provider-output-unscored
default device = cuda
video fps request = 2.0
max_new_tokens = 1536
max_pixels = 524288
```

运行边界：

```text
主应用 Python 3.11
→ 独立 P2.4 Provider
→ 复用 .runtime/TransVLM/inference 的隔离 Python 3.12/CUDA 环境
→ 但使用独立 base Qwen3-VL-4B-Instruct checkpoint
```

**不能把已有 TransVLM 转场微调 checkpoint 当成内容语义模型。** P2.4 只复用隔离运行环境，不复用其转场任务权重。

P2.4 Prompt/Adapter 明确分工：

```text
VLM：场景提示、镜头内容、匿名主体、视觉动作、剧情关键道具 hint
ASR：对白/语音文本与时间
OCR：字幕、路牌、屏幕、文档等可读文本
```

VLM 不重复转写对白/字幕/路牌/手机文字；`speaking_state` 仅是视觉 hint，不是 speaker identity。

VLM 持久化白名单：

```text
scene:
  location_hint / interior_exterior / time_of_day / environment_description
shot:
  summary / visual_description / shot_type_hint / camera_motion_hint
  narrative_function_hint / composition_hint
subjects:
  subject_A / subject_B / ...
  appearance/activity/screen_position/visibility/speaking_state
events:
  VISUAL / ACTION + normalized start/end ratios + anonymous subjects
props:
  plot-relevant label / importance / narrative reason / anonymous subjects
```

未知模型字段在 Adapter 边界丢弃，P2.1 递归 Final-ID 检查继续作为第二层 fail-closed 防线。

P2.6 仍需真实短剧比较：Qwen3-VL 4B 的视觉语义准确性、2fps 取样、VRAM/速度、长/短 Shot 行为、Windows GPU 稳定性，以及必要时与其它可商用 VLM 候选对比。

---

## 7. 正式 Phase 顺序

### P0 — Planning / Contract

**COMPLETE**。

### P1 — Draft data/runtime contract

**COMPLETE**：P1.1 models/tables → P1.2 lifecycle → P1.3 validator → P1.4 read API → P1.5 tests → P1.6 STALE → P1.7 Windows/docs closure。

### P2 — ASR / OCR / VLM anonymous Draft sidecar

**IN PROGRESS**。

```text
P2.1 unified Provider/raw Evidence sidecar              COMPLETE
P2.2 ASR Provider + segment/word timing                 COMPLETE
P2.3 OCR Observation Provider                           COMPLETE
P2.4 VLM anonymous Shot semantics                       COMPLETE
P2.5 ASR/OCR/VLM Fusion → P1 Draft → validator/publish NEXT
P2.6 real-video benchmark + Windows/docs closure        PLANNED
```

P2.1：

```text
PROCESSING BreakdownRun
→ exact source ShotRevision / ShotRevisionItems
→ Reference Clip / thumbnail / keyframes + Episode audio / source language
→ unified Provider Contract
→ validated raw Evidence
→ fingerprinted immutable sidecar
→ BreakdownRun component provenance
```

P2.2：

```text
Episode preprocess audio
→ FasterWhisperASRProvider
→ ASR_SEGMENT + ASR_WORD
→ source integer microseconds
→ P2.1 sidecar + provenance
```

P2.3：

```text
exact historical ShotRevisionItem Reference Clip
→ deterministic multi-frame sampling across the Shot
→ RapidOCROCRProvider
→ OCR_OBSERVATION(text/confidence/polygon/bbox)
→ exact ShotRevisionItem + Episode source point time
→ P2.1 sidecar + provenance
```

P2.4：

```text
exact historical ShotRevisionItem Reference Clip
→ Qwen3VLSemanticProvider
→ isolated Qwen3-VL base-model runtime
→ strict anonymous semantic whitelist
→ shot-bound VLM_OUTPUT
→ P2.1 sidecar + provenance
```

P2.2–P2.4 都只生产 raw Evidence，不写 P1 Draft rows。

P2 raw Evidence sidecar：

```text
workspace/<project>/episodes/<episode>/breakdown/<run>/evidence/
  asr/<sha256>.json
  ocr/<sha256>.json
  vlm/<sha256>.json
```

### P2.5 — ASR/OCR/VLM Fusion — NEXT

P2.5 正式职责：

```text
读取当前 PROCESSING BreakdownRun 已登记的 immutable ASR/OCR/VLM sidecars
↓
验证 fingerprint / component / source revision / evidence ownership
↓
ASR：按 exact ShotRevisionItem 边界拆分跨镜对白
OCR：按文本 + 几何 + 时间做 temporal stitching / dedupe / duration inference
VLM：消费 Shot-level 匿名视觉语义
↓
三模态 Fusion
↓
写 P1：
  SceneSegmentDraft
  ShotSemanticDraft
  LocalSubject / ShotLocalSubject
  TimelineEvent / TimelineEventSubject
  DraftPropHint / DraftPropOccurrence
  BreakdownEvidenceLink
↓
P1 validator
↓
publish READY / READY_WITH_WARNINGS
```

P2.5 必须保持这些事实：

- 不隐式重跑 ASR/OCR/VLM，默认消费已经固化并登记在 Run provenance 中的 sidecar；
- ASR 跨镜头 segment 必须按正式 source microseconds 与 ShotRevisionItem 边界拆分；
- OCR 重复帧是 raw observation，只有 Fusion 可以推断持续区间；
- `subject_A` 等是 Scene/Shot 语义主体，不是 Character；
- VLM 的 normalized event ratio 只能结合对应 Shot source interval 转换成正式 integer microseconds；
- 每个 READY ShotRevisionItem 必须最终获得 ShotSemanticDraft；
- 每个 Draft owner 只链接实际消费过的 raw Evidence；
- validator fail closed；失败 Run 不替换旧 Current；
- P2.5 仍然不能创建 Character/Scene/Prop Final Asset 或 Final Shot Bindings。

### P2.6 — real-video benchmark + closure

**PLANNED**。使用真实短剧素材验证：

```text
ASR：对白召回/错误率/word timing/跨镜头行为
OCR：字幕/手机/路牌，小字与持续时间，small vs medium，sampling interval
VLM：视觉主体/动作/场景/关键道具语义准确度，2fps/分辨率/4B 能力边界
Fusion：最终匿名拉片完整度、事件时间、重复/冲突处理
Runtime：Windows、CPU/GPU、显存、速度、模型缓存/offline readiness
```

P2.6 才能对“当前模型组合是否真实短剧效果最佳”做结论；fake-engine/fake-runner CI 不能替代真实素材验收。

### P3 — 02 拉片 structured Draft UI

**PLANNED**。显示 Scene Segment、人物A/B、时间轴事件、对白、动作、场景/道具 hints；点击时间回到对应历史/Current Reference Clip。

### P4 — Draft-guided Scene / Prop evidence

**PLANNED**。先增强当前较弱的 Scene/Prop，不碰 Character V10.1 硬身份门槛。

### P5 — Draft ↔ Character safe integration

**PLANNED**。先做可解释 mapping，不让 Draft 创建身份。

### P6 — Final fill-back + renderer

**PLANNED**。

```text
LocalSubject → Character
SceneSegmentDraft → Final Scene
DraftPropHint → Final Prop
```

### P7 — downstream remake integration

**PLANNED**。Final Breakdown contract 稳定后再让内容剧本/重制/生成消费。

---

## 8. 每个 Phase 的发布规则

```text
1. 先读取 CURRENT docs + 当前代码 + 本 Plan
2. 一次只进入一个明确 Phase / 子阶段
3. 旧项目兼容优先
4. 数据变化 ADD-only 优先
5. 新 Run 完整成功后才切 Current
6. focused tests + 原有回归
7. Windows acceptance
8. 同步 CURRENT docs / 本 Plan / 对应 Phase Contract
9. 新建 session handoff
10. 默认直接提交 main；仅在用户明确要求时再走新 PR
```

P1.7 固化 `breakdown-p1-windows`；P2.1 增加 `breakdown-p2-windows`；P2.2 ASR、P2.3 OCR、P2.4 VLM focused suites 均已纳入后者。后续不能移除这些兼容门槛。

P2.4 focused acceptance：

```text
Ubuntu compile: PASS
FastAPI import/version: PASS (2.4.1)
Ubuntu full pytest: 28 failed, 243 passed, 1 skipped
Windows Breakdown P2 provider suite: 37/37 PASS
```

相较 P2.3 新增的 6 个 pass 正好对应 6 个 P2.4 VLM focused tests；历史 28 个 backend 失败类别没有新增。Frontend 仍有既存 TypeScript/vue-tsc build failure，因此整个仓库仍不能宣称全绿。

---

## 9. 明确禁止的捷径

```text
禁止：把 Shot Detection 完成当成完整拉片完成
禁止：把 P1 表存在当成 P2 模型推理已实现
禁止：把 P2.1 sidecar 完成当成 P2.2-P2.5 已实现
禁止：把 P2.2 ASR 完成当成 OCR/VLM/Fusion 已完成
禁止：把 P2.3 OCR 完成当成 VLM/Fusion 已完成
禁止：把 P2.4 VLM 完成当成完整 Draft/Fusion 已完成
禁止：把 fake-provider/fake-runner focused tests 描述成 real-video 模型效果验收
禁止：把 TransVLM 转场 checkpoint 冒充 P2.4 内容语义 checkpoint
禁止：让 VLM 重复承担 ASR/OCR 的对白/文字转写职责
禁止：VLM 直接创建 Character / Scene / Prop Final Asset
禁止：VLM prose 直接写 ShotCharacterBinding
禁止：ASR speaker label 直接映射 CharacterCandidate
禁止：ASR 跨 Shot segment 按最大 overlap Shot 提前绑定
禁止：OCR 单帧 observation 冒充字幕持续区间
禁止：OCR Provider 直接把文字物化为 Final Scene / Prop
禁止：从 candidate.tracks 恢复新 Run Final 人物绑定
禁止：SceneSegmentDraft 与 Final Scene 共用身份概念
禁止：完整 Draft 只存一段 prose
禁止：Fusion 后丢失 raw ASR/OCR/VLM Evidence
禁止：剧情上下文覆盖可靠 Face/cannot-link 冲突
禁止：没有可靠 Prop Evidence 时伪造 Prop
禁止：删除旧 Breakdown/ShotRevision/Reference Clip 来“清理历史”
禁止：ShotRevision 变化后让旧 Breakdown 继续冒充 Current
禁止：P2 自己发明一套与 P1 平行的语义 Draft schema
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

当前工程已经把③所需的 **ASR / OCR / VLM 三种原始 Evidence Provider** 做齐，但③的“人类可读完整结构化拉片”还差 P2.5 Fusion。

后台保持证据分层，但前端最终应该能渲染成人类易读的带时间轴剧本。
