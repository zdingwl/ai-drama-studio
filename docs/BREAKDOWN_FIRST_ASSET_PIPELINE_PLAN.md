# AI Drama Studio — 拉片先行 / Breakdown-first 资产识别改造地图

> **Status:** ACCEPTED TARGET PLAN / NOT IMPLEMENTED  
> **Created:** 2026-08-27 16:22 +08:00  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Branch:** `main`  
> **Current executable baseline remains:** Reference Video V2 / FastAPI 2.4.1 / Character V10.1 explicit Shot Character Assignment

## 0. 这份文档是什么

这份文档记录用户已经确认的**目标产品流程与改造顺序**。

它不是当前代码清单，也不能因为这里写了某个模块，就声称该模块已经实现。

项目的两个事实层必须始终分开：

```text
docs/PROJECT_STATE.md
+ docs/CURRENT_IMPLEMENTATION_MANIFEST.md
+ 当前代码 / 测试
= CURRENT：现在真正运行什么

本文件
= TARGET：下一步应该往哪里改
```

如果 TARGET 与 CURRENT 不同，这是正常的“待实施差距”。开发时必须按阶段把 CURRENT 逐步推进到 TARGET，而不是直接把 CURRENT 文档改成未来状态。

任何后续对话开始实现本计划前，必须先读取当前状态文档和当前代码，再读取本计划，禁止只根据聊天记录或旧 F01-F06 文档直接写代码。

---

## 1. 用户已经确认的产品定义

### 1.1 “拉片”不等于“切镜头”

镜头切分只是拉片的技术准备。

目标中的完整拉片应该能够输出类似人工拉片师整理的、带时间轴的视听脚本：

```text
场景 1 · 内 · 住宅楼走廊 · 00:00-00:22
人物：人物A、人物B
关键道具：蓝玫瑰、花瓶、黑色塑料袋

[00:00] 蓝玫瑰插在玻璃花瓶中，镜头特写。

[00:01] 镜头切到走廊，人物A拦住提着黑色塑料袋的人物B，面露不悦。

人物A（质问）[00:01]：
“王阿姨，我刚到的花怎么又在你家花瓶里？”

人物B（理直气壮）[00:04]：
“这花就在走廊，怎么就是你的了？”
```

第一遍拉片**不能假装已经知道全剧真实人物身份**，因此先使用 `人物A / 人物B / subject_A / subject_B` 等局部匿名主体。

### 1.2 已确认的目标主线

```text
原视频
↓
视频预处理
↓
自动切镜头
↓
Shot + Reference Clip
↓
AI 先看懂镜头内容
↓
第一版匿名结构化拉片 Draft
  场景段 / Shot / 人物A-B / 对白 / 动作 / 道具候选 / 镜头内容
↓
根据 Draft 有目的地寻找人物 / 场景 / 道具
↓
专用模型提取并验证真实 Evidence
↓
跨 Shot / 全项目资产归并
↓
Character / Scene / Prop + Shot Bindings
↓
把真实资产身份回填到 Draft
↓
Final 拉片
↓
重制设计 / 视频生成
```

一句话原则：

> **先看懂，再识别，再回填。**

---

## 2. 不可破坏的架构原则

### 2.1 Shot + Reference Clip 继续是核心生产单元

新规划不会推翻 Reference Video V2。

`Shot` 仍然保存精确 Source Timeline 和独立 `Reference Clip`；后续匿名拉片、资产 Evidence、Final Binding 和生成都围绕稳定 `shot_id` 关联。

### 2.2 第一遍拉片是 Semantic Prior，不是身份真值

第一遍 VLM 可以说：

```text
人物A：年轻女性，黑色上衣，左侧，正在说话
人物B：中年女性，提黑色塑料袋，右侧
```

但它不能直接宣布：

```text
人物A = Character_001 = 徐然
```

最终身份必须由专用视觉/音频 Evidence 证明。

### 2.3 文案只能帮助“找什么”，不能覆盖硬证据

```text
Semantic Draft / 上下文
= soft prior / search hint

Detection / Track / Face / Person-ReID / Audio / OCR
= measurable evidence
```

如果语义 Draft 与可靠硬证据冲突，系统必须保留冲突、重新验证或保持 unresolved，不能为了让文案看起来完整而强行绑定。

### 2.4 Character V10.1 当前身份与 Shot Assignment Contract 首阶段不动

当前正式 Character V10.1：

```text
Person Evidence
→ Track
→ Global Identity
→ explicit Shot × known-Character Assignment
→ Final Character / ShotCharacterBinding
```

在本目标计划的早期实施阶段，拉片上下文只能作为**额外辅助信息**，不得：

- 放宽创建新 Character 的 >=3 Shot / >=3 image 等 Final Gate；
- 绕过 same-sample cannot-link；
- 覆盖高质量 Face hard conflict；
- 直接写 `ShotCharacterBinding`；
- 把 `candidate.tracks` 再次当成 Final Shot Binding；
- 让 VLM 文本单独创建 Character。

只有在单独设计、测试、真实素材验收后，才能讨论是否让语义上下文参与 Character score；即使参与，也必须是可解释的软证据。

### 2.5 Scene Segment 与 Scene Asset 必须分离

```text
Scene Segment
= 剧情场景段 / 一段连续戏
例如：走廊争执 00:00-00:22

Scene Asset
= 项目级可复用真实视觉环境
例如：住宅楼走廊 / 电梯口
```

一个 Scene Asset 可以在多个 Scene Segment 中再次出现，禁止把两者合成一个实体。

### 2.6 最终拉片不能只存一篇自由文本

前端可以渲染成人类易读的剧本文案，但底层必须保留结构化事实，例如：

```text
shot_id
start_us / end_us
local_subject_id / character_id
event_type
action / target / prop_ref
dialogue text / emotion
scene_hint / scene_id
confidence / evidence source
```

这样改名字、合并人物、修正道具、翻译或生成时不需要重新让大模型重写整篇。

### 2.7 数据迁移先 ADD，不先 DROP

新流程实施前期采用兼容式扩展：

```text
先新增数据结构 / API / sidecar
→ 新旧流程并存
→ 真实素材与回归测试通过
→ 再考虑废弃旧字段
```

不得为了规划整洁直接删除当前稳定表、字段、路由或旧 Run 兼容能力。

---

## 3. 当前功能 → 目标流程完整改造地图

| 阶段 | 当前已经有的功能 / 代码 | 当前输入 | 当前输出 | 能否保留 | 需要调整 | 需要新增 | 目标输入 | 目标输出 |
|---|---|---|---|---|---|---|---|---|
| 01 项目与剧集 | `studio_v2.py` / `main.py`：Project、Episode、多集导入、排序 | 项目配置、原视频 | Project + ordered Episodes | **直接保留** | 基本不动 | 无强制新增 | 同当前 | 同当前，作为全局上下文 |
| 02 视频预处理 | `media_v2.py`：FFprobe、FFmpeg Proxy、独立音频、完整解码校验 | Episode source | Proxy、Audio、MediaInfo | **直接保留** | 后续 ASR 可消费现有 Audio；必要时另建 ASR 派生音频，不能破坏原分析音轨 | Provider 需要的派生缓存 | Source/Proxy/Audio | 统一时间基准媒体事实 |
| 03 镜头切分 | `media_v2.detect_episode_shots()`：TransNetV2 + FFprobe PTS | READY Proxy + Source | Shot 边界 | **核心保留** | 产品术语逐步从“完整拉片”收敛为“镜头切分/Shot Detection” | 可选边界质量诊断 | Proxy + authoritative PTS | 精确 Shot boundaries |
| 04 Shot / Reference Clip | `studio_v2.Shot`、`shot_revision_v2`、`shot_edit_routes_v2`；每 Shot 有独立 Reference Clip / thumbnail / keyframes | Shot boundaries + Source | Final Shot、Reference Clip、缩略图 | **核心保留** | Shot 成为后续 Draft 的稳定外键；不能因为语义重跑重新生成 identity | 更丰富关键帧可后续加 | Final Shot | 稳定 `shot_id` + Reference Clip |
| 05 音频 / 文字事实 | 当前正式资产提取不跑 ASR/Speaker/Dialogue；`Dialogue` 模型和部分兼容 helper 已存在 | Audio / frames | 当前没有正式一体化拉片事实层 | **现有数据边界可复用** | 不能把历史 helper 当正式实现 | ASR Provider、对齐、Speaker、OCR Observation | Episode Audio + Shot 时间 + frames | SpeechSegment / words / SpeakerSegment / OCR Observation |
| 06 第一版匿名拉片 | 当前未正式实现；`Shot.short_description/shot_type/camera_motion` 存在但不足以表达完整结构 | 当前多数字段为空或轻量 | 无正式 Semantic Shot Draft | **需新增** | 禁止把完整 Draft 塞进一个 `short_description` 文本字段 | `ShotSemanticDraft`、`LocalSubject`、`TimelineEvent`、Scene/Prop hints、证据/置信度 | Reference Clip + keyframes + ASR + OCR + 邻接 Shot context | 匿名人物、画面、动作、对白、情绪候选、场景提示、道具提示、镜头描述 |
| 07 剧情 Scene Segment | 当前资产侧 `SceneCandidate` 是轻量视觉候选，不等于剧情 Scene Segment | Shot thumbnails | 连续 Shot Scene candidate | **不能混用概念** | 保留现有 Scene candidate 兼容；不要改名冒充剧情段 | 独立 `SceneSegmentDraft` / Shot membership / summary | 连续 Shot Draft + ASR剧情连续性 +视觉变化 | “走廊争执”等剧情段 + 包含 Shots |
| 08 人物 Evidence / Identity | Character V10.1 已正式实现 YOLOX + YoutuReID + clothing/body + YuNet/SFace + MOT + Global Identity | Shot/Reference Clip | Person Evidence、Tracks、RESOLVED/UNRESOLVED identities | **重点保护** | 后续可让 Draft 提供“本 Shot 预计有哪些 LocalSubject / 外观 /位置 /行为”作为定向辅助，但不改硬 Gate | LocalSubject ↔ Person Evidence 可追溯映射；语义 prior provenance | Shot + Draft local subjects + 当前 V10.1 visual input | 当前人物 Evidence/Identity + LocalSubject 映射 |
| 09 Shot 人物绑定 | `character_shot_assignment_v101.py` 已独立判断 Shot × known Character | 全部原始 Track/Observation + RESOLVED galleries | `shot_presence_assignments` → Final ShotCharacterBinding | **原样保护作为真值层** | 第一阶段不让拉片文案直接改变 assignment | 将 Draft subject 与 Final Character 进行回填映射 | 当前 assignment inputs + 已验证上下文（未来可选） | 已确认 Character presence + Draft fill-back refs |
| 10 Scene Asset | `content_analysis_v2.py` 当前主要是缩略图 HSV descriptor + Episode 连续性形成轻量 `SceneCandidate` | Shot thumbnail | SceneCandidate + ShotSceneEvidence | **数据边界保留，算法需升级** | 不能把 HSV candidate 当 Final Scene identity；需要多证据验证 | SceneHint + 视觉 embedding + VLM语义 + OCR + Object context + 跨 Segment resolver | Draft scene hints + Shot frames + OCR/objects +相邻关系 | project-level Scene + ShotSceneBinding + confidence/evidence |
| 11 Prop Asset | `PropCandidate` / `ShotPropEvidence` 数据边界已有；无可靠模型时允许 `NOT_CONFIGURED` | 当前模型配置 | Candidate 或无结果 | **数据边界保留** | 不允许把普通所有物体都做成剧情 Prop | Draft prop hints → 定向开放词汇检测 → mask/track/OCR/人物交互验证；可评估 Grounding DINO + SAM2 | Draft prop candidates + frames + OCR + dialogue | 关键 Prop Evidence → Final Prop + ShotPropBinding |
| 12 Speaker / Dialogue → 人物 | `Dialogue` 核心实体存在；正式完整 Speaker pipeline 尚未落地 | 当前无统一正式输入链 | partial/planned | **实体可保留** | Speaker identity 与 Character identity 必须分层 | ASR + diarization + active-speaker/视觉嘴动 + LocalSubject / Final Character mapping | Audio + Shot Tracks + Draft dialogue | 带精确时间、speaker ref、Character ref 的 Dialogue |
| 13 全局资产归并 | Character 已成熟到 V10.1；Scene/Prop 仍需增强 | Evidence | Character 已正式；Scene/Prop 不同成熟度 | **分模块保留** | Scene/Prop 不照搬 Character 阈值；分别设计 resolver | Scene / Prop Global Resolution 与状态管理 | 全项目 Evidence + Draft context | Character / Scene / Prop 项目级资产 |
| 14 身份回填 / Reconciliation | 当前没有统一“匿名 Draft → Final Asset”回填层 | 无 | 无 | **需新增** | 回填只能替换引用与确定事实，不让 VLM重新猜身份 | `DraftResolution` / mapping provenance / conflict handling | LocalSubject + SceneHint + PropHint + Final bindings | `人物A→Character001`、`场景提示→Scene003`、`道具候选→Prop005` |
| 15 Final 拉片 | 当前 02 拉片主要展示 Shot/Reference Clip，不是用户示例中的完整视听脚本 | Shot数据 | Shot列表/工作台 | **现有工作台保留并增强** | UI最终从结构化数据渲染，不以纯 AI prose 为唯一存储 | 标准格式 Renderer、国际格式 Renderer、时间轴事件 UI、点击时间跳 Reference Clip | Resolved structured breakdown | 用户可读的场景化最终拉片 |
| 16 重制下游 | 当前 04 内容剧本 partial/planned，05/06 planned | Shot / assets | 规划态 | **保持现有 Reference Video V2方向** | 等 Final breakdown contract稳定后再接 | Generation Package adapter | Final Shot + Reference Clip + Character/Scene/Prop/Dialogue | 重制设计、生成、QC/export 所需数据 |
| 17 Validator / QC | 当前各模块有 fail-closed 规则，但没有统一 Semantic-vs-Evidence reconciliation | 各模块结果 | 局部状态/置信度 | **现有 Gate 保留** | 不允许“一遍 VLM 输出即 Final” | cross-source conflict / confidence / NEEDS_REVIEW | Draft + visual/audio evidence + Final bindings | ACCEPTED / CONFLICT / UNRESOLVED / NEEDS_REVIEW |

---

## 4. 当前代码中必须保护的已有成果

以下能力是新规划的基础，不是重写目标：

```text
Project / Episode / sort_order
Source media 与文件哈希
FFmpeg / FFprobe 预处理
完整 Proxy 解码校验
integer microseconds 正式时间
TransNetV2 Shot boundary
Shot Revision
稳定 shot_id
Reference Clip / thumbnail / keyframes
Character V10.1 Person Evidence
YoutuReID project-level Identity
same-sample cannot-link
explicit Shot Character Assignment
Final Character Gate
Character / Scene / Prop Final Asset 数据边界
Shot Binding / Manual / Restore Revision 保护
旧 Run 可读兼容
顺序批处理 / heavy task concurrency = 1
```

实施新拉片流程不能用“重做架构”为理由破坏这些已经可工作的 Contract。

---

## 5. 目标中的新结构化数据概念

这些是**目标概念**，不是当前数据库已经存在的表名。正式实施前必须单独冻结 schema / migration contract。

### 5.1 `LocalSubject`

只在 Draft 分析范围内标识匿名人物：

```text
local_subject_id: subject_A
shot_id / scene_segment_id
appearance hints
screen position
actions
speaking state
confidence
```

它不是 Character，不具备跨项目身份语义。

### 5.2 `ShotSemanticDraft`

每个 Shot 的第一遍结构化理解：

```text
shot_id
summary
local_subjects[]
scene_hint
prop_hints[]
timeline_events[]
shot_language
confidence
evidence_refs
```

### 5.3 `TimelineEvent`

统一表达：

```text
VISUAL
ACTION
DIALOGUE
OCR
AUDIO_EVENT
```

每条事件绑定精确 `start_us/end_us` 与 `shot_id`，有主体/客体/道具时保存结构化 reference。

### 5.4 `SceneSegmentDraft`

剧情场景段：

```text
scene_segment_id
episode_id
start_us / end_us
shot_ids[]
location_hint
interior_exterior
time_of_day
local_subject_ids[]
prop_hints[]
summary
```

它不能替代 `Scene` 项目级视觉资产。

### 5.5 `DraftResolution`

记录匿名 Draft 与正式资产的回填关系：

```text
subject_A → Character001
scene_hint_01 → Scene003
prop_hint_02 → Prop005
resolution_source
confidence
evidence_refs
```

该映射必须可追溯、可撤销、可人工修正。

---

## 6. 推荐技术方向（均为 TARGET 候选，不代表已安装/已实现）

| 目标能力 | 当前/推荐方向 | 规划规则 |
|---|---|---|
| 媒体处理 | 当前 FFmpeg / FFprobe | 保留 |
| Shot boundary | 当前 TransNetV2 | 保留；不要混成“完整拉片” |
| ASR | 评估 Qwen3-ASR 与 WhisperX | 用真实短剧做准确率/时间对齐 benchmark 后再定 Provider |
| Speaker | pyannote 类 diarization + 后续 active speaker | 先匿名 Speaker，再映射 LocalSubject/Character |
| OCR | PaddleOCR 系列 | OCR 是场景/道具/剧情的 Evidence，不只是字幕 |
| 第一遍视频理解 | 独立 VLM Provider，优先评估 Qwen3-VL 系列 | 当前 `transvlm_runtime_v51.py` 是转场检测用途，**不能误认为已实现语义拉片** |
| Character | 当前 Character V10.1 | 保留为身份验证核心 |
| Scene | 视觉 embedding + VLM语义 + OCR + Object +时间连续性 | 替代“只靠HSV就是最终场景”的错误做法 |
| Prop | Draft hints + open-vocabulary detector；可评估 Grounding DINO + SAM2 | 只物化剧情关键 Prop，不把所有背景 object 资产化 |
| Final 文案 | 结构化 Renderer；VLM只用于必要的语言润色/校验 | 真实 ID /时间/绑定不能靠润色模型重猜 |

所有新增模型正式选型前必须检查：

```text
效果
显存/速度
本地部署
Windows兼容
权重来源
商业许可
可替换 Provider Contract
```

---

## 7. 最安全的实施顺序

### Phase P0 — 规划与 Contract（本次工作）

```text
只同步文档
不修改业务代码
不修改数据库
不改变当前 runtime
```

### Phase P1 — 新增 Draft 数据 Contract，旧流程完全不受影响

先冻结：

```text
LocalSubject
ShotSemanticDraft
TimelineEvent
SceneSegmentDraft
DraftResolution
```

优先采用 ADD-only migration / 独立 Analysis Run；不能先复用一个自由文本字段硬塞所有数据。

### Phase P2 — ASR / OCR / VLM 第一遍 Draft

新增 read-only sidecar 流程：

```text
Final Shot / Reference Clip
→ ASR + OCR + VLM
→ anonymous Draft
```

此阶段**不向 Character / Scene / Prop Final Asset 写数据**，先用真实短剧评估 Draft 是否可信。

### Phase P3 — 02 拉片显示结构化 Draft

前端先能看见：

```text
Scene Segment
人物A/B
时间轴画面事件
对白
动作
场景提示
道具候选
```

点击时间可回到对应 Reference Clip；人工修正 Draft 不修改原 Shot 时间证据。

### Phase P4 — Draft 驱动 Scene / Prop 定向验证

优先将 Draft 用于当前较弱的 Scene / Prop：

```text
Draft 说“医院 / 合同”
→ 专用视觉/OCR/开放词汇模型定向验证
→ Evidence
→ Scene / Prop resolver
```

先提升弱模块，不碰 Character V10.1 硬门槛。

### Phase P5 — Draft 与 Character 的安全联动

前置条件：当前 V10.1 real-video Shot binding baseline 已验收。

第一步只增加：

```text
LocalSubject ↔ Person Track / Character Assignment 的解释性映射
```

不把 VLM 文案作为创建人或 Final binding 的独立条件。

任何进一步 score fusion 必须另做文档、阈值测试、cannot-link/Face conflict 回归和真实素材验收。

### Phase P6 — Final 回填 + 双格式 Renderer

```text
subject_A → 徐然
subject_B → 王桂香
scene_hint → 正式 Scene
prop_hint → 正式 Prop
```

渲染：

```text
标准格式
国际格式
```

底层仍是同一份结构化数据。

### Phase P7 — 接入内容剧本 / 重制设计 / 生成

只在 Final Breakdown contract 稳定以后，让后续模块消费：

```text
Shot + Reference Clip
Character / Appearance
Scene
Prop
Dialogue / Voice
Structured Events
```

---

## 8. 每个 Phase 必须遵守的发布规则

每次真正写代码时：

```text
1. 先读取 CURRENT 文档 + 当前代码 + 本 TARGET Plan
2. 明确只实现哪个 Phase
3. 先保留旧路径，新增能力默认不得破坏旧项目
4. 新数据库改动优先 ADD-only
5. 新 Run 完整成功后才切 Current
6. 跑本 Phase focused tests + 原有回归
7. 用真实短剧做 Windows 验收
8. 验收后再把 PROJECT_STATE / Manifest 中对应项改成 IMPLEMENTED
9. 同步本文件 Phase 状态
10. 新建 session handoff
```

如果只写了代码，没有同步以上文档，本 Phase 不算完成。

如果只改了文档说“已实现”，但代码/测试没有对应实现，也属于错误。

---

## 9. 明确禁止的实现捷径

```text
禁止：把“Shot Detection 完成”当成“完整拉片完成”
禁止：让第一遍 VLM 直接创建 Character / Scene / Prop Final Asset
禁止：让 VLM 文案直接写 ShotCharacterBinding
禁止：重新从 candidate.tracks 推导当前 V10.1 Final人物绑定
禁止：SceneSegment 与 Scene Asset 共用同一个身份概念
禁止：把完整 Draft 只存成一段无法追踪实体的 prose
禁止：因为 Draft 说2个人就删除 Detector 看到的第3个人
禁止：因为剧情“应该是某人”就覆盖可靠 Face/cannot-link 冲突
禁止：没有可靠 Prop 模型时伪造 Prop
禁止：为了新流程删除旧 Run / Manual / Restore 兼容
禁止：在未验证前一次性重写 F01-F06 / V2 全链路
```

---

## 10. 最终用户应该感知到的简单流程

后台可以复杂，但用户只需要理解：

```text
① 视频处理
② 镜头切分
③ AI 内容拉片
④ 人物 / 场景 / 道具识别
⑤ 资产确认与回填
⑥ 最终拉片
⑦ 重制
```

最终拉片页面目标接近：

```text
场景 1     内 / 住宅楼走廊                00:00-00:22
人物：徐然、王桂香
道具：蓝玫瑰、玻璃花瓶、黑色塑料袋

[00:00] 镜头特写——蓝玫瑰插在玻璃花瓶中。

[00:01] 镜头切到走廊，徐然拦住提着黑色塑料袋的王桂香，面露不悦。

徐然（质问）[00:01]：
“王阿姨，我刚到的花怎么又在你家花瓶里？”

王桂香（理直气壮）[00:04]：
“这花就在走廊，怎么就是你的了？”
```

但这个显示结果必须来自可追溯的结构化数据，而不是一段无法验证来源的模型自由作文。

---

## 11. 当前状态说明

截至创建本文件时：

```text
本文件 = 已确认目标规划
代码 = 未因本规划做任何修改
数据库 = 未因本规划做任何修改
Reference Video V2 = 当前正式架构
Character V10.1 explicit Shot Character Assignment = 当前正式人物基线
```

后续开发不得把本文件中的 TARGET 模块误报为 CURRENT IMPLEMENTED。