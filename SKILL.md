---
name: ai-drama-studio-reference-video-v2
version: 3.6.0
description: AI Drama Studio Reference Video 驱动的本地短剧本地化重制工作台开发规则；当前人物基线 Character V10.1 explicit Shot Assignment；已接受 Breakdown-first Target Plan，尚未实施。
---

# AI Drama Studio — Reference Video V2 / Character V10.1

## 0. 新对话恢复规则

项目事实必须来自 GitHub 当前 `main`，不能只依赖旧聊天记录。

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/CURRENT_IMPLEMENTATION_MANIFEST.md
→ docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
→ docs/ASSET_CHARACTER_RECOGNITION_V10_1.md（涉及人物时）
→ 当前代码/测试
→ 最新 session handoff
```

必须区分：

```text
PROJECT_STATE + CURRENT_IMPLEMENTATION_MANIFEST + code/tests
= CURRENT executable truth

BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN
= accepted TARGET plan, NOT IMPLEMENTED unless CURRENT docs/code say so
```

旧 Feature/Frozen 文档和当前 wiring 冲突时，以当前正式架构文档 + 当前可执行代码为准，并先修正 CURRENT 文档。Target Plan 与 CURRENT 不同是正常待实施差距，不得把规划直接写成“已实现”。

## 1. 产品目标

把多集原短剧拆成可控制的 Shot，并把每个原 Shot 保存为 Reference Video。后续通过人物、场景、关键道具、目标语言 Dialogue、Voice 和替换资产控制重制，而不是丢失 Reference Video 后从零猜测动作与摄影。

正式用户工作区：

```text
01 剧集管理
→ 02 拉片
→ 03 资产
→ 04 内容剧本
→ 05 重制设计
→ 06 生成 / 导出
```

### 已接受的 Breakdown-first Target

“拉片”目标定义不再等同于 Shot Detection。目标流程是：

```text
原视频
→ Preprocess
→ Shot Detection
→ Shot + Reference Clip
→ ASR / OCR / Video Understanding
→ 第一版匿名结构化拉片 Draft
→ 根据 Draft 定向提取 Character / Scene / Prop Evidence
→ Global Asset Resolution + Final Shot Binding
→ 把真实资产身份回填 Draft
→ Final Breakdown
→ remake
```

一句话：

```text
先看懂，再识别，再回填
```

第一遍 Draft 使用 `人物A / subject_A` 等匿名 `LocalSubject`。Draft 是 soft semantic prior，不是 Final Character/Scene/Prop 真值。

完整改造地图与 Phase 顺序以：

```text
docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
```

为唯一 Target Plan。

当前代码尚未因为该计划改变 runtime baseline。

## 2. 核心实体

当前正式实体：

```text
Project
Episode
Shot
Character
Scene
Prop
Dialogue
Asset
Voice
Generation
```

Shot 是核心生产单元，Reference Clip 是 Shot 一级正式资产。AI Evidence 与 Final Asset / Binding / Revision 必须分离。

Target Plan 另外定义的规划概念：

```text
LocalSubject
ShotSemanticDraft
TimelineEvent
SceneSegmentDraft
DraftResolution
```

这些是**目标数据概念，不代表当前数据库已有对应表**。实施前必须冻结 schema / migration contract，优先 ADD-only。

`SceneSegmentDraft` 是剧情场景段，不等于项目级 `Scene` Asset。

## 3. Character V10.1 正式人物链

```text
Shot / Reference Clip
↓
YOLOX Person Detection
↓
每个检测人物拆成明确 Person Instance crop
↓
Capture-first Person Evidence
  YoutuReID = primary new-identity model signal
  clothing_upper / clothing_lower = support
  body_hist / body_structure = support
  YuNet + SFace Face = optional support / known-presence / conflict
↓
Mature MOT = Shot 内时序组织
↓
Project-level Person Evidence identity classification
↓
RESOLVED identities + UNRESOLVED visual evidence
↓
Independent Shot × known-Character Assignment
  from ALL original Track / Observation evidence
↓
persist identity + explicit Shot presence metadata
↓
Final Character Gate
↓
ShotCharacterBinding from explicit assignments
```

正式 profile：

```text
runtime:  character-v10.1-capture-first-model-classification
asset:    f05-assets-v10.1-person-evidence-model-classification
resolver: person-evidence-model-classifier-v10.1
shot assignment: v10.1-shot-character-assignment-1
source: V10_1_SHOT_CHARACTER_ASSIGNMENT
```

Breakdown-first P1-P4 不改变这条人物链。后续 Draft 与 Character 联动必须先保持现有硬 Gate 与 explicit assignment 权威。

## 4. 语义层不可混淆

当前正式四层：

```text
Observation / Person Evidence / CharacterTrack = 视觉证据
CharacterCandidate / Identity Class = 跨 Shot 人物身份
Shot Character Assignment = 已知人物在某 Shot 的存在判定
Character / ShotCharacterBinding = Final 人物资产 / 分镜绑定
```

Target 语义 Draft：

```text
LocalSubject / ShotSemanticDraft / SceneSegmentDraft
= 拉片理解层
```

它与 Character 身份层是不同语义。

Track 数、Face 数、Crop 数不能当人物数量。Candidate Track membership 不能当当前 V10.1 Final Shot Binding。`subject_A` 也不能因为 VLM 写得像“男主”就直接变成 Character。

## 5. Capture-first / Identity 规则

所有 model-usable Person Instance 应先捕获和保存，再决定身份归属。

```text
CLEAN
OCCLUDED
CONTAMINATED
PARTIAL
```

创建新身份正式最低门槛：

```text
>= 3 independent Shots
>= 3 model-usable Person Images
stable cross-Shot Person-ReID consistency
unique identity class
same-sample cannot-link satisfied
no high-quality Face hard conflict
```

风险视角规则：

- 强 `CONTAMINATED` / substantial `PARTIAL` 可以提出新人，但需要更严格跨 Shot ReID 确认；
- 弱、小、低质量 Partial 只能 save/classify，不能创建新人物；
- Face 不是 RESOLVED 必需条件；
- 高质量 Face 明确冲突是 hard negative；
- Semantic Draft 不能绕过这些规则。

## 6. Explicit Shot Character Assignment

正式模块：

```text
engine/app/character_shot_assignment_v101.py
```

正式 call order：

```text
resolve_global_identities(tracks)
→ assign_shot_characters(all_original_tracks, candidates)
→ update_person_evidence_classification()
→ persist CharacterCandidate / CharacterTrack + assignment metadata
→ Final Gate
→ ShotCharacterBinding
```

旧的：

```text
recover_unresolved_tracks()
recover_fragmented_shot_presence()
```

不再属于正式 runtime call path，只保留历史兼容代码/测试。

Assignment 只回答：

```text
这个已经确认的人物，是否出现在这个 Shot？
```

不能创建新 Character，也不能为了绑定去修改 `candidate.tracks`。

Target Draft 的人物文案第一阶段不能直接写 assignment；最多在后续专门 Phase 中作为辅助 search/context evidence，并且必须单独测试。

## 7. Shot Assignment 证据规则

正式模式：

```text
DIRECT_IDENTITY
FACE_STRONG
FACE_REPEATED
BODY_REID
```

Face known-presence gates：

```text
FACE_PAIR_MIN_SCORE = 0.72
FACE_SUPPORTED = 0.36
FACE_STRONG = 0.50
FACE_WINNER_MARGIN = 0.08
MIN_FACE_REPEAT_OBSERVATIONS = 2
MIN_FACE_REPEAT_TIMESTAMPS = 2
MIN_FACE_REPEAT_MEDIAN = 0.40
```

Face 必须与 >=2 independent confirmed Gallery Shots 比较。强 Face 可单观察确认 known presence；中等 Face 必须在当前 Shot 重复。

Body/ReID gates：

```text
REID_STRONG = 0.84
REID_SUPPORTED = 0.74
RISKY_REID_SUPPORTED = 0.80
RISKY_APPEARANCE_CHANNELS = 2
REID_WINNER_MARGIN = 0.07
MIN_BODY_SUPPORT_OBSERVATIONS = 3
MIN_BODY_SUPPORT_TIMESTAMPS = 3
MIN_BODY_MEDIAN = 0.76
```

Body/ReID 非 direct presence 必须有 Shot 内重复时间证据。

同一采样时刻的 cannot-link Person Instances 是 occupancy 约束：一个 Character 已由其中一人占用时，另一个 simultaneous Person Instance 不能再次绑定同一 Character。

Ambiguous winner / repeated high-quality Face conflict / 不足证据必须保持 unassigned。

## 8. Assignment persistence / confidence

RESOLVED Candidate 持久化：

```text
shot_assignment_version
shot_assignment_source
shot_assignment_policy
shot_presence_assignments[]
shot_presence_shot_ids
shot_presence_count
shot_presence_recovered_count
```

每条 assignment 可记录：

```text
shot_id
confidence
mode
support_count
support_timestamp_count
track_count
face_support_count
winner_margin
```

`CharacterCandidate.confidence` 是项目级身份置信度；`shot_presence_assignments[].confidence` 是已知人物在当前 Shot 的 presence 置信度。两者不可混用。

未来 DraftResolution 也必须有独立 provenance/confidence，不能覆盖这两个概念。

## 9. Final Character Gate / Final Binding

身份 Final Gate：

```text
identity_status == RESOLVED
+ formal resolver
+ confirmed_gallery_shots >= 3
+ confirmed_gallery_images >= 3
+ final_asset_eligible is not false
```

当前 V10.1 Run 如果存在 `shot_assignment_version`：

```text
ShotCharacterBinding = shot_presence_assignments ONLY
```

显式空 assignment 不允许 fallback 到 Candidate Track membership。

只有旧 persisted Run 没有 `shot_assignment_version` 时才保留 Track-derived fallback。

正式入口：

```text
engine/app/asset_final_gate_v10.py
engine/app/asset_final_gate_v9.py
```

## 10. Evidence / Final Asset / Revision

```text
ContentAnalysisRun
CharacterCandidate
CharacterTrack
Person Evidence manifest/gallery
= immutable AI Evidence

Character / Scene / Prop
ShotCharacterBinding / ShotSceneBinding / ShotPropBinding
= Final Asset / Final Binding
```

旧 Run 不会自动获得新的 assignment。验证新绑定逻辑必须重新跑资产提取。

MANUAL / RESTORE Revision 默认保护，新 AI Run 不静默覆盖人工版本。

Gallery / Evidence comparison 只是诊断 UI，不是 Final binding source。

Breakdown-first 同样必须：Draft/Evidence 与 Final 可编辑结果分离；新 Draft Run 不得静默改掉人工确认结果。

## 11. 当前 Shot / 拉片边界与 Target 差距

当前 FastAPI 正式入口通过 `media_v2`：

```text
preprocess_episode
→ detect_episode_shots
→ TransNetV2 boundary
→ Shot + Reference Clip + thumbnail
```

当前 `Shot` 已有：

```text
start_us / end_us / duration_us
reference_clip_path
thumbnail_path
keyframes_json
short_description
shot_type
camera_motion
```

但当前没有正式完整的：

```text
ASR/OCR facts
anonymous LocalSubject
structured TimelineEvent
SceneSegmentDraft
context-directed asset resolution
Draft → Final Asset fill-back
标准/国际格式 Final Breakdown renderer
```

所以“当前 02 拉片 IMPLEMENTED”应理解为 Shot/Reference Clip/镜头工作能力已实现，**不是 Breakdown-first 最终产品形态已经实现**。

历史 `shot_detection.py` / `shot_workbench.py` 的 F04/F05 命名不能覆盖当前 V2 wiring；其中 `shot_workbench.py` 自己也明确不负责人、ASR、Scene、Qwen3-VL。

## 12. Tracking / 时间原则

Tracking 只做时序组织，不决定跨 Shot 身份，也不直接决定 Final Shot binding。

长 Shot tracker 使用真实时间：

```text
timestamp = local_time_us / 1_000_000
```

Mature MOT 运行时缺失不能静默发布人物结果。

正式媒体时间统一 integer microseconds。未来 ASR/OCR/TimelineEvent/Draft 也必须最终映射到同一正式时间基准。

## 13. 模型与授权边界

当前固定人物模型：

```text
YOLOX Person Detection
YoutuReID Person Re-identification
YuNet Face Detection
SFace Face Embedding
```

YoutuReID 是人物身份主模型。Face 是可选支持/known presence/conflict。

不要静默下载或打包仅限非商业研究用途的 InsightFace/ArcFace 权重。未来 Face provider 只能使用明确可商用或已有授权权重，并保持 Evidence → Identity → Shot Assignment → Final Asset Contract。

Target Plan 中的新增模型都只是候选方向。正式选型前必须验证：

```text
真实短剧效果
本地/Windows runtime
显存与速度
模型/权重来源
商业许可
Provider 可替换性
```

特别注意：当前 `transvlm_runtime_v51.py` 使用 `TransVLM-Qwen3-VL-4B-Instruct` 做**转场区间检测**，它不等于“语义拉片已经实现”。未来内容理解必须作为独立 VLM Provider / Analysis Run 设计。

## 14. Run / 批量原则

当前人物：

```text
Person Evidence
→ Track
→ Global Identity
→ Shot Character Assignment
→ persistence
→ Current Run
→ Final Asset materialization
```

其它原则：

- 新 Run 完整成功后才能切 Current；
- `Episode.sort_order` 是批量顺序唯一依据；
- GPU/模型重任务默认 `concurrency = 1`；
- Reference Clip 是正式资产，不是缓存；
- 新语言时长最终由 Production Timeline 重建，不要求等于原语言；
- Target Breakdown Draft 必须有独立 Run/Revision/provenance，不能只覆盖一段 text。

## 15. Breakdown-first 实施顺序

完整 Phase 定义见 Target Plan，顺序固定为：

```text
P0 文档/Contract（当前）
P1 Draft 数据 Contract，ADD-only，不影响旧流程
P2 ASR/OCR/VLM anonymous Draft read-only sidecar
P3 02 拉片 UI 展示/编辑结构化 Draft
P4 Draft 驱动 Scene / Prop 定向验证
P5 Draft 与 Character 安全联动（V10.1 baseline 验收后）
P6 Final fill-back + 标准/国际格式 renderer
P7 接 04/05/06 下游重制
```

禁止跳过 P1/P2，直接让一段 VLM prose 控制 Final Asset。

## 16. 当前主代码

```text
engine/app/studio_v2.py
engine/app/media_v2.py
engine/app/content_models_v2.py
engine/app/content_analysis_v2.py
engine/app/character_visual_v2.py
engine/app/character_runtime_v6.py
engine/app/character_observation_v10.py
engine/app/character_person_evidence_v10.py
engine/app/character_person_features_v9.py
engine/app/character_tracking_v10.py
engine/app/character_identity_v10.py
engine/app/character_identity_v101.py
engine/app/character_shot_assignment_v101.py
engine/app/character_persistence_v6.py
engine/app/character_gallery_v10.py
engine/app/character_evidence_store_v10.py
engine/app/asset_final_gate_v10.py
engine/app/asset_final_gate_v9.py
engine/app/asset_workspace_character_v101.py
engine/app/asset_routes_v3.py
engine/app/main.py
```

历史兼容、正式 runtime 不调用：

```text
engine/app/character_shot_binding_v101.py
engine/app/character_shot_presence_v101.py
```

## 17. 测试与真实验收

默认测试目录：

```text
engine/tests/v2
```

V10.1 当前必须重点锁住：

- identity 仍要求严格 >=3 Shot / images；
- Face optional；
- weak Partial 不创建人；
- same-sample cannot-link 不被绕过；
- direct identity 生成显式 Shot assignment；
- strong Face close-up 可绑定 known Character 但不移动 Track；
- repeated moderate Face 可恢复 known presence；
- ambiguous body 不绑定；
- two-person cannot-link occupancy 保持两个人物独立；
- explicit Final assignment 不 fallback 到 Track；
- workspace 可显示“无 Candidate Track ownership 但 explicit assignment 已确认”的 known Character；
- UNRESOLVED 只进 diagnostics。

当前整仓 CI **不是全绿**。真实短剧必须在用户 Windows 本机验证最终人物数和 Shot 绑定。

Breakdown-first 每个新 Phase 必须增加 focused tests，并继续跑原有回归。没有真实素材验收，不得修改 CURRENT 状态声称稳定。

## 18. 重制策略

```text
REUSE_REFERENCE
AUDIO_ONLY
LIPSYNC_ONLY
CHARACTER_REPLACE
SCENE_REPLACE
PROP_REPLACE
PARTIAL_EDIT
FULL_VIDEO_REGEN
```

不是所有 Shot 都调用最昂贵的视频生成模型。Final Breakdown 是为重制提供结构化上下文，不取代 Reference Clip。

## 19. Git 工作方式

```text
Default Branch: main
Development Branch: main
```

日常开发直接提交 `main`，不主动新建 feature branch/PR，除非用户明确改变要求。

## 20. 文档同步硬规则

任何正式产品流程、人物身份/绑定、Final Gate、Breakdown Draft、Scene/Prop resolver 或下游 Contract 变化时，本次工作结束前必须检查并同步：

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
docs/ASSET_CHARACTER_RECOGNITION_V10_1.md 或 successor（涉及人物时）
最新 docs/sessions/*.md
```

状态纪律：

```text
只完成规划
→ Target Plan = ACCEPTED / PLANNED
→ CURRENT 文档仍写实际旧 runtime

代码 + tests + acceptance 完成
→ 才把对应 CURRENT 项改成 IMPLEMENTED
```

代码改了而 CURRENT 文档仍描述旧版本，视为开发没有完成；反过来，只改 CURRENT 文档把 TARGET 伪装成实现也属于错误。

## Legacy

旧 35 Feature、Frozen Snapshot、Workflow Versioning、Character V1-V10 历史资料都不是当前正式 Contract。

禁止重新接回“检测到脸就创建 Character”“Track 数≈人物数”“Face 必须存在才能发布 V10.1 人物”“从 Candidate Track ownership 直接推导当前 V10.1 Final Shot Binding”的旧逻辑。
