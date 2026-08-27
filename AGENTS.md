# AI Drama Studio — Agent Entry Rules (Reference Video V2 / Character V10.1)

本仓库当前正式产品架构为 **Reference Video V2**。人物资产正式运行基线为 **Character V10.1**，当前 Final Shot 人物绑定已经采用 **独立 Shot Character Assignment**。

同时，用户已经确认新的**目标产品流程**：先生成匿名结构化拉片 Draft，再根据 Draft 定向识别人/场景/道具，最后把正式资产回填为 Final 拉片。完整目标改造地图见：

```text
docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
```

> **重要：该文件是 TARGET PLAN，不是 CURRENT IMPLEMENTATION。** 当前真正运行什么仍必须以 `PROJECT_STATE.md`、`CURRENT_IMPLEMENTATION_MANIFEST.md`、当前代码和测试为准。

> **不要从文件名猜当前算法版本。** `character_runtime_v6.py`、`asset_final_gate_v9.py` 等是兼容文件名；正式版本必须看当前 wiring、runtime profile 和本文件。

## 1. 新对话必须按这个顺序恢复上下文

```text
1. AGENTS.md
2. SKILL.md
3. docs/PROJECT_STATE.md
4. docs/CURRENT_IMPLEMENTATION_MANIFEST.md
5. docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md   # 已接受 TARGET，不代表已实现
6. docs/ASSET_CHARACTER_RECOGNITION_V10_1.md    # 涉及人物时必读
7. 当前相关代码与测试
8. 最新 docs/sessions/*.md handoff
```

严格区分：

```text
PROJECT_STATE + CURRENT_IMPLEMENTATION_MANIFEST + code/tests
= CURRENT executable truth

docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
= accepted TARGET plan
```

如果 TARGET 与 CURRENT 不一致，这是正常的待实施差距，**禁止为了让文档“看起来一致”而把未实现的目标写成 IMPLEMENTED**。

不要先拿旧 F01-F06 Frozen Snapshot 或 Character V1-V10 历史文档覆盖当前代码。当前状态文档与可执行 wiring 冲突时，先同步 CURRENT 文档；实现新目标时则按 Target Plan 的 Phase 逐步推进。

## 2. 当前唯一可执行产品基线

```text
Architecture: Reference Video V2
Default branch: main
FastAPI app version: 2.4.1
Formal Character runtime: V10.1
Runtime profile: character-v10.1-capture-first-model-classification
Asset profile: f05-assets-v10.1-person-evidence-model-classification
Resolver: person-evidence-model-classifier-v10.1
Shot assignment version: v10.1-shot-character-assignment-1
Shot assignment source: V10_1_SHOT_CHARACTER_ASSIGNMENT
```

**本次 Breakdown-first 规划没有修改以上 runtime baseline。**

## 3. V2 核心产品原则

当前可执行主线：

```text
Project
→ 多个 Episode（可拖动排序）
→ Preprocess
→ Shot
→ 每个 Shot 保存独立 Reference Clip
→ 人物 / 场景 / 道具 / Dialogue / Track / Mask 绑定 Shot
→ 替换资产 + Voice + 本地化 Dialogue
→ 按 Shot 选择重制策略
→ Reference Video 驱动生成
→ Production Timeline
→ QC / Export
```

已接受的 TARGET 主线是在不推翻 `Shot + Reference Clip` 的前提下，把 02 拉片从“只有 Shot 时间结构”逐步增强为：

```text
Shot + Reference Clip
→ ASR / OCR / Video Understanding
→ anonymous structured Breakdown Draft
→ Draft-guided Character / Scene / Prop evidence extraction
→ Global Asset Resolution + Final Shot Bindings
→ identity fill-back
→ Final Breakdown
→ remake
```

关键原则：

```text
先看懂，再识别，再回填
```

第一遍 Draft 的 `人物A / subject_A` 只是匿名语义主体，不能直接创建/绑定 Final Character。Semantic Draft 是 soft prior；可靠视觉/音频 Evidence 与现有 fail-closed Gate 才是事实验证层。

Reference Clip 已包含动作、构图、机位、空间关系、镜头运动和节奏；即使增加结构化拉片，也不要为了“更详细”无意义地把 Reference Video 已经可靠保存的信息全部重复文字化。

## 4. 正式用户工作区

```text
01 剧集管理
02 拉片
03 资产
04 内容剧本
05 重制设计
06 生成 / 导出
```

当前 `02 拉片` 的代码已经具备 Shot/Reference Clip 与人工镜头修正能力，但**目标中的匿名结构化内容拉片尚未实现**。不得把 Shot Detection 完成误报为完整 Breakdown-first 拉片已经实现。

FFprobe、Embedding、MOT、Person Evidence、ASR 等技术步骤默认后台执行。

## 5. Character V10.1 正式人物链

```text
Shot / Reference Clip
↓
YOLOX Person Detection
↓
每个检测人物拆成独立 Person Instance crop
↓
Capture-first Person Evidence
  + YoutuReID Person embedding（主身份模型）
  + clothing_upper / clothing_lower
  + body_hist / body_structure
  + YuNet / SFace Face（可选支持）
↓
Mature MOT 做 Shot 内时序组织
↓
Project-level identity classification
↓
RESOLVED identities + UNRESOLVED visual evidence
↓
Independent Shot × known-Character Assignment
  using ALL original Track / Observation evidence
↓
Final Character Gate
↓
Character + ShotCharacterBinding from explicit assignments
```

正式 runtime **不再调用**旧的 `recover_unresolved_tracks()` / `recover_fragmented_shot_presence()`。历史模块保留只为兼容旧测试/旧 Run。

Breakdown-first 计划第一阶段**不改变这条正式人物链**。后续 Draft 最多先作为可追溯辅助上下文；不得绕过 identity gate / cannot-link / Face conflict / explicit assignment。

## 6. 四层语义不可混淆

```text
Observation / Person Evidence / CharacterTrack
= 视觉证据

CharacterCandidate / Identity Class
= 跨 Shot 项目级人物身份

Shot Character Assignment
= 某个已确认人物是否出现在当前 Shot

Character / ShotCharacterBinding
= 最终可编辑人物资产 / 分镜绑定
```

目标规划另外增加的：

```text
LocalSubject / ShotSemanticDraft / SceneSegmentDraft
= 拉片语义 Draft，不是 Final Asset
```

**Track 数、Face 数、Crop 数都不能直接当人物数量。Candidate Track 归属也不能直接当 Final Shot Binding。Draft 人物A 也不能直接当 Character。**

## 7. V10.1 Identity Contract

创建新人物的最低正式门槛：

```text
>= 3 independent Shots
>= 3 model-usable Person Images
stable cross-Shot Person-ReID class
unique winner
no cannot-link violation
no high-quality Face hard conflict
```

规则：

- Face 是可选支持，不是创建人物的必需条件；
- CLEAN 不是唯一可用人物图；
- 强 `CONTAMINATED` / substantial `PARTIAL` 可在更严格跨 Shot ReID 确认下提出新人；
- 弱、小、低质量 Partial 只能保存/分类，不能创建新人；
- 同一采样时刻不同 Person Instance 是硬 cannot-link；
- 高质量 Face 明确冲突必须阻断错误身份合并；
- Breakdown Draft 文案不能替代以上 Gate。

## 8. Explicit Shot Character Assignment 是正式绑定源

正式模块：

```text
engine/app/character_shot_assignment_v101.py
```

目的不是“把 unresolved Track 挪进 Character”，而是独立回答：

```text
已确认的人物001/002/003...
在这个 Shot 里分别是否 PRESENT？
```

输入必须使用当前 Run 的**全部原始 Track / Observation**，而不是只看已归类 Candidate Track。

正式模式：

```text
DIRECT_IDENTITY
FACE_STRONG
FACE_REPEATED
BODY_REID
```

关键不变量：

- 只能选择已 `RESOLVED` Character，不能创建新人；
- 不修改 `candidate.tracks` 归属；
- 多个短 Track 可在 Shot 内聚合成一次 presence；
- 同时出现的 cannot-link Person Instances 不能占用同一个 Character；
- Face 支持优先处理近景/大特写，但必须是唯一 known-identity winner；
- Body/ReID 恢复必须有重复时间证据；
- ambiguous winner / 强 Face conflict / 证据不足时不猜；
- 第一遍拉片 Draft 不能直接写 assignment。

## 9. Final Character Gate 与 Final Shot Binding

人物身份 Final Gate 保持 fail-closed：

```text
identity_status == RESOLVED
+ formal resolver
+ confirmed_gallery_shots >= 3
+ confirmed_gallery_images >= 3
+ final_asset_eligible is not false
```

对于带 `shot_assignment_version` 的当前 V10.1 Run：

```text
ShotCharacterBinding
= shot_presence_assignments ONLY
```

**禁止再从 `candidate.tracks` 反推当前 Run 的 Final Binding。** 显式 assignment 为空时也不允许 fallback。

只有旧 persisted Run 不含 `shot_assignment_version` 时，才允许历史 Track-derived fallback。

正式入口：

```text
engine/app/asset_final_gate_v10.py
engine/app/asset_final_gate_v9.py
```

## 10. Evidence 与 Final Asset 分离

```text
ContentAnalysisRun / CharacterCandidate / CharacterTrack / Person Evidence
= immutable AI Evidence

Character / ShotCharacterBinding
= editable Final Asset / Binding
```

未来 Breakdown-first 也必须遵守同样思想：

```text
anonymous Draft / model observations
!=
Final Asset / Final Binding
```

旧 Run 不会因为代码更新自动获得新的 Shot assignment。人物绑定算法变化后必须重新执行资产提取产生新 Run。

MANUAL / RESTORE Asset Revision 默认受保护，新 AI Run 不得静默覆盖人工版本。

Gallery / Evidence-vs-Final 页面只是诊断工具，**不是绑定真值来源**。

## 11. 当前正式代码边界

```text
engine/app/main.py
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
```

历史兼容、当前正式 runtime 不调用：

```text
engine/app/character_shot_binding_v101.py
engine/app/character_shot_presence_v101.py
```

当前仓库还存在 `shot_detection.py` / `shot_workbench.py` 等历史阶段命名模块；不要因为其中 docstring 叫 F04/F05 就覆盖 Reference Video V2 当前 wiring。当前 FastAPI 主入口使用 `media_v2` 的 preprocess / Shot analysis 与 V2 Shot/Reference Clip 数据模型。

## 12. Model / License boundary

当前固定人物模型集：

```text
YOLOX
YoutuReID
YuNet
SFace
```

不要静默下载或打包仅限非商业研究用途的 InsightFace/ArcFace 预训练权重。未来替换 Face provider 时必须使用明确可商用/已有授权权重，并保持 Evidence → Identity → Shot Assignment → Final Asset Contract。

Target Plan 中列出的 ASR / OCR / VLM / open-vocabulary detector 只是候选方向；正式选型前必须验证效果、Windows runtime、显存/速度、权重来源和商业许可，并设计可替换 Provider。

## 13. Run / 时间 / 批量原则

- 新 Run 完整成功后才能切 Current；
- `Episode.sort_order` 是批量顺序唯一依据；
- GPU/重任务默认顺序执行，`concurrency = 1`；
- 正式媒体时间使用 integer microseconds；
- Reference Clip 是正式 Shot 资产，不是临时缓存；
- Character / Scene / Prop 是项目级实体，Shot 绑定实体 ID；
- 新 Breakdown Draft 实施时也必须有独立可追溯 Run/Revision，不能静默覆盖人工 Final 结果。

## 14. 当前测试现实

不要声称整个 CI 已通过。当前全量 GitHub Actions 仍有 legacy/environment 失败，包括 `cv2`、tracker runtime、FFmpeg、旧 V6 断言和 frontend `vue-tsc`/TypeScript compatibility。

当前 explicit Shot assignment 重点回归已覆盖：

```text
direct identity → explicit Shot assignment
strong Face close-up → known Character without moving Track
ambiguous body → no assignment
two-person cannot-link occupancy → keep two Characters distinct
explicit Final Gate assignment → no Track fallback
workspace explicit assignment → may show known Character without Candidate Track ownership
```

最终 Release Gate 仍是用户 Windows 本机真实短剧素材。

Target Plan 的每一个 Phase 都必须保留现有回归，并增加该 Phase 的 focused tests；没有测试/真实素材验收不能把状态改成 IMPLEMENTED。

## 15. Git 工作方式

```text
Default Branch: main
Development Branch: main
```

日常开发直接提交 `main`，不要主动新建 feature branch/PR，除非用户明确要求。

## 16. 文档与代码同步硬规则

任何正式产品流程、人物身份/绑定、Final Gate、拉片 Draft、Scene/Prop resolver 或下游数据 Contract 修改结束前，至少检查并同步：

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
docs/ASSET_CHARACTER_RECOGNITION_V10_1.md 或 successor（涉及人物时）
最新 docs/sessions/*.md
```

状态规则：

```text
规划确认但未写代码
→ Target Plan 可以是 ACCEPTED / PLANNED
→ PROJECT_STATE / Manifest 仍必须写真实 CURRENT

代码 + focused tests + 真实验收完成
→ 才能把对应 CURRENT 状态改成 IMPLEMENTED/STABLE
```

若代码和入口 CURRENT 文档不一致，本次开发视为没有收口；若只改 CURRENT 文档把未来规划伪装成已实现，同样视为错误。
