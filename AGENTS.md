# AI Drama Studio V3 — 开发规则

> 当前状态日期：2026-09-11。  
> 当前最高优先级：`docs/23_P10最终验收与P11准入.md`。  
> 原则：仓库当前 `main` + 编号更高、日期更新的状态/验收文档是唯一事实源；历史文档只能解释演进，不能覆盖最新口径。

## 1. 开发前读取顺序

任何代码修改前必须按以下顺序读取，并在最后读取当前相关代码与测试：

1. `docs/00_V3产品与系统详细规划.md`
2. `docs/03_Seko3.0_Skill架构逆向分析.md`
3. `docs/01_V3开发阶段与验收清单.md`
4. `docs/02_V3当前开发状态.md`
5. `docs/04_阶段人工验收规范.md`
6. `docs/05_Seko源作概览画布节点实测.md`
7. `docs/06_P7整集原片理解ProfessionalSkill与Grounding验收.md`
8. `docs/07_P7最终验收与ProviderReadiness.md`
9. `docs/08_P8逐镜精细拉片ProfessionalSkill与数据契约.md`
10. `docs/09_P6CanonicalEvidenceV2与P8最终验收整改.md`
11. `docs/10_P8SpeakerCandidate与P6微段幻觉整改.md`
12. `docs/10_P8说话人候选绑定与分镜表可读性修正.md`
13. `docs/11_P6字幕证据裁决与P8台词一致性整改.md`
14. `docs/12_P6人工对白裁决与Canonical可编辑.md`
15. `docs/13_P8最终验收与P9准入.md`
16. `docs/14_P9最终归一ProfessionalSkill与数据契约.md`
17. `docs/15_P9PropProviderSchemaV6整改.md`
18. `docs/16_P9SpeakerStagedCharacterEvidenceRef整改.md`
19. `docs/17_P9最终验收与P10准入.md`
20. `docs/18_P10SourceVideoSnapshotProfessionalSkill与数据契约.md`
21. `docs/19_P10工程验收与真实人工验收清单.md`
22. `docs/20_P10产品呈现整改_取消独立阶段.md`
23. `docs/21_原片解析一键编排与剧本分镜工作区.md`
24. `docs/22_P10一键原片解析最终产品验收.md`
25. `docs/23_P10最终验收与P11准入.md`
26. 当前相关代码与测试

冲突处理：**编号更高、日期更新、且明确声明替代旧口径的文档优先。**

关键当前事实：

- `docs/17`：P9 最终真实人工 PASS；
- `docs/20`：取消 P10 作为普通用户独立大面板；
- `docs/21`：REPLICA / REDRAW 的 P5~P10 收口为一次“解析原片”；
- `docs/22`：P10 一键产品最终验收清单；
- `docs/23`：用户已明确 `P10 PASS`，`SOURCE_SNAPSHOT = AVAILABLE`，P11 Replica Target Bible 正式准入。

历史分支只能参考，不能覆盖当前 V3 规划。

---

## 2. 当前阶段事实

当前已完成并通过对应真实人工验收：

```text
P0 仓库重建
P1 新工程骨架
P2 Project + Skill Kernel
P3 SourceAsset + 输入系统
P4 Task / ProviderJob
P5 Shot Anchors
P6 Source Evidence
P7 整集多模态原片理解
P8 逐镜精细拉片
P9 Character / Speaker / Scene / Prop 最终归一
P10 SourceVideoSnapshot / 一键原片解析产品链
```

当前 `AVAILABLE` 至少包括：

```text
SOURCE_VIDEO_INGEST
SOURCE_TEXT_INGEST
MEDIA_PREFLIGHT
SHOT_BOUNDARY
SOURCE_DIALOGUE_EVIDENCE
EPISODE_UNDERSTANDING
STORY_RHYTHM
SHOT_BREAKDOWN
IDENTITY_RESOLUTION
SCENE_RESOLUTION
PROP_RESOLUTION
SOURCE_SNAPSHOT
```

当前正式下一工程切片：

```text
P11 Replica Target Bible
```

P11 只“准入”，并未完成。以下仍为 `PLANNED`：

```text
Target Bible capability
Target Script
TARGET_STORYBOARD
TTS / Timing
Generation / QC / Selection
Post / Final Output
以及尚未完成的其他项目类型完整业务链
```

禁止跳过 P11 直接进入后续阶段。

---

## 3. 产品边界

V3 六类正式 `ProjectType`：

```text
REPLICA
REDRAW
TRANSLATION
NOVEL_TO_DRAMA
SCRIPT_TO_DRAMA
SCRIPT_LOCALIZATION
```

每种项目类型必须绑定自己的 Root Project Skill。

当前完整 Source Bible / P8 / P9 / P10 一键工作区只正式适用于：

```text
REPLICA
REDRAW
```

`TRANSLATION` 在明确接入对应契约前不得复用该工作区假装能力可用；route 和 service 都必须 fail closed。

P11 当前只开发：

```text
REPLICA Target Bible
```

不得借 P11 顺手铺开 REDRAW / TRANSLATION / 其他项目类型的 Target 链。

---

## 4. 核心架构

正式架构：

```text
Project Type
→ Root Project Skill
→ Agent / Plan Compiler
→ ProjectExecutionPlan
→ Professional Skills
→ Provider / Tools
→ Typed Artifacts
→ Artifact Graph
```

职责分离：

```text
Skill       = 怎么做对
Artifact    = 做出了什么
Agent       = 当前怎么规划
Tool        = 用什么执行
Guardrail   = 绝对不能违反什么
```

必须严格区分：

```text
Product Stage
Internal PlanStep / Capability
P0/P1/P2/... Engineering Phase
```

Skill 不是 Prompt。正式 Skill 至少要定义适用条件、输入、可读 Artifact、required capabilities、步骤、判断规则、用户决策策略、输出契约、校验、完成标准和失败处理。

---

## 5. 当前 Professional Skill 基线

P7：

```text
source-video-understanding@1.1.0
p7-source-bible-v2
SOURCE_BIBLE schema 1.1
grounded-source-truth-v2
```

P8：

```text
shot-breakdown@1.1.0
p8-shot-breakdown-v2
SOURCE_SHOT_FACTS schema 1.1
source-bible-shot-facts-v2
```

P9：

```text
character-resolution@1.0.0
speaker-attribution@1.0.0
scene-resolution@1.0.0
prop-resolution@1.0.0
p9-source-resolution-v8
P9 resolution schema 1.0
full-episode-global-resolution-v1
```

P10：

```text
source-video-snapshot@1.0.0
p10-source-video-snapshot-v1
SOURCE_VIDEO_SNAPSHOT schema 1.0
frozen-accepted-source-facts-v1
DETERMINISTIC_FREEZE
```

P11 尚未有正式运行契约。**必须先设计并落文档，再实现。**

---

## 6. Source Truth 与原片理解硬规则

完整 Episode 永远是视频 Source Truth：

```text
SOURCE_VIDEO / 完整 Episode = 权威原片输入
```

thumbnail / Reference Clip 只是派生技术资产，不能替代完整 Episode。

内部关系：

```text
完整 Episode
├─ P5 Shot Anchors
└─ P6 ASR / OCR / canonical Evidence
        ↓
P7 Whole-Episode Understanding + Story / Rhythm
        ↓
P8 Shot Breakdown
        ↓
P9 Character / Speaker / Scene / Prop Resolution
        ↓
P10 deterministic Source Snapshot
```

必须遵守：

- P5 Shot Boundary 读取完整 `SOURCE_VIDEO`；
- P6 ASR 读取完整连续音轨，不得按 Shot / Reference Clip 分开识别再拼句；
- P6 OCR 读取完整视频时间轴，Shot Anchors 只能辅助抽帧 / 去重；
- raw ASR / OCR 永久保留；
- canonical dialogue 的自动/人工裁决必须版本化、可追溯；
- P7/P8/P9/P10 无权静默覆盖 P6 canonical dialogue / OCR；
- P7 必须读取完整 Episode，先整集理解再逐镜；
- P8 Shot 时间只认 P5，对白正文只认 P6；
- P8 speaker / character / scene / prop 只是 provisional binding，不能冒充 P9 最终 identity；
- P9 Provider 以完整 Episode / 全集上下文做全局归一；
- Speaker 与 Character 分层，Speaker→Character 可以为空；
- UNKNOWN / UNRESOLVED 是正式状态，禁止最高相似度兜底；
- P9 不得反写 P5/P6/P7/P8 历史 revision；
- P10 只冻结 CURRENT Source Facts，不重新理解 Episode，不调用模型，不创建 ProviderJob；
- P10 必须保持 P5 Shot 时间、P6 canonical dialogue/OCR 原值；
- `SOURCE_SPEAKERS` 是独立冻结输入与独立 section；
- 任一上游新 revision 必须使依赖旧链的 Snapshot / draft 正确 STALE；
- Target / Production 不得反向写入 Source。

Source Evidence 与 Source Understanding 严格分离：

```text
Source Evidence      = 原片实际说了什么 / 写了什么
Source Understanding = 这些事实在故事、人物、关系、场景、事件、节奏上意味着什么
```

Grounding：

```text
FACT
INFERENCE
UNKNOWN
```

原则：**宁可 UNKNOWN，也不要合理补全。**

---

## 7. 当前普通用户原片流程

REPLICA / REDRAW 普通模式：

```text
上传完整原片
↓
解析原片（一次显式操作）
↓
原片剧本 + 分镜 + 人物 / 场景 / 道具
↓
分镜编辑草稿
```

P5/P6/P7/P8/P9/P10 是内部工程切片，不得堆成普通用户独立操作卡。

普通模式禁止要求用户理解：

```text
Artifact / ProviderJob
Fingerprint / Provenance
Frozen Inputs / SourceVideoSnapshot
```

开发 / 诊断入口继续通过：

```text
?debug=1
```

一键解析必须：

- 只由显式 `POST /commands/source-analysis` 启动；
- 页面加载只 GET；
- 只执行缺失 / STALE 子步骤；
- 已 CURRENT 子结果幂等复用；
- P5/P6 按 Episode；
- P7 → P8 → P9 严格满足依赖；
- 最后确定性发布 P10；
- 子任务失败时顶层 fail closed；
- 可恢复中断走 resume；
- 已耗尽重试次数的终态中断允许新的显式解析创建新流水线。

---

## 8. Source Script 与 working draft

“原片剧本”是正式 Source Facts 的确定性可读视图，不是新一轮生成：

```text
P9 Scene Assignment
+ P9 Speaker / Character
+ P8 visual_description / camera language
+ P6 canonical dialogue
```

规则：

- Scene Assignment 变化开始新场次；
- 同 Scene 后续再次出现也形成新的连续场次；
- Episode 边界强制开始新场次；
- 跨 Shot 同一 canonical utterance 在剧本中只出现一次；
- 原片剧本必须保持 Source Truth，不得读取 working draft 覆盖正文。

“分镜编辑草稿”不是正式 `TARGET_STORYBOARD`：

- 每次显式保存生成 draft revision；
- 记录 base Source Snapshot；
- Source 更新后旧 draft STALE / 归档；
- 旧 draft 不自动套用到新 Source；
- 新 Source 首次编辑从当前原片分镜开始；
- 用户可显式“恢复原片”删除单 Shot override。

---

## 9. P11 Replica Target Bible 硬边界

P11 正式输入必须以：

```text
CURRENT SOURCE_VIDEO_SNAPSHOT
```

作为 Source 世界版本边界，而不是从散落的 P5~P9 Artifact 自行拼装“当前事实”。

需要细节时可以沿 Snapshot lineage 读取被冻结 Source Artifact，但必须保持 Snapshot revision 是唯一当前 Source 版本锚点。

P11 必须先设计：

```text
Professional Skill
manifest / SKILL.md
typed schema
Target Artifact
revision / fingerprint / provenance
CURRENT / STALE
Artifact Graph relations
GET / POST / Command
ProviderJob 策略
用户编辑 / 决策规则
自动测试
真实人工验收
```

Replica 默认目标：

> 故事不乱改，节奏不重做，文化和表达才本土化。

P11 默认锁定：

```text
Hook
冲突
反转
信息揭示顺序
情绪峰值
Payoff
Cliffhanger
Story Beat timing
Shot rhythm baseline
```

允许在 Target namespace 进行：人物身份 / 外形、场景、道具、文化信息、目标语言对白等本土化设计。

硬规则：

- Source Facts 绝不被 Target 创作反写；
- Target identity 不得冒充 Source identity；
- Source Snapshot STALE 时，基于旧 Snapshot 的 Target Bible 必须 STALE / BLOCKED；
- P11 不得提前实现正式 Target Storyboard；
- P11 不得提前实现 TTS / Timing；
- P11 不得提前实现 Generation / QC / Selection / Post。

---

## 10. Workflow / Provider / 安全硬规则

- 页面 GET 必须只读，不能写 DB、建 Task、运行 Agent、启动模型或自动重算；
- 重任务必须由明确 POST / Command 启动；
- 外部计费 Provider 请求前必须先持久化 `ProviderJob`；
- API Key 禁止写入 DB、日志、Artifact、ProviderJob、provenance 或 Git；
- API Key UI 默认遮罩，用户显式选择显示后才可回显；本机配置只能进入被 Git 忽略的本地环境文件；
- Task 必须支持有限 retry / cancel / resume，不允许无限重试；
- Task 技术 succeeded 不等于业务 Artifact READY；
- 失败不得覆盖旧 CURRENT Artifact；
- 上游 revision / fingerprint 改变，下游必须 STALE；
- Source / Target / Production 严格分离；
- Source Shot / TargetStoryboardShot / GenerationSegment 严格分离；
- GenerationAttempt 不是正式结果，只有 GenerationSelection 可进入后期；
- 多 Episode 重模型默认串行；同 Episode 内独立轻量能力可由 orchestration 按资源条件并行。

---

## 11. 完成定义

任何能力都必须分别说明并验证：

```text
1. 架构 / 数据模型
2. 自动测试
3. CI
4. Provider / 本地 Runtime 真实运行
5. 真实素材端到端
6. 输出结构正确性
7. 用户看 / 听质量
```

不能用其中一层替代另一层。

P11 只有在上述门禁和真实人工验收全部通过后，才能把对应 Target Bible capability 从 `PLANNED` 升为 `AVAILABLE`，并准入下一工程阶段。

---

## 12. Git 规则

```text
main = V3 当前稳定开发基线
backup/* = 历史回滚 / 参考
```

- 禁止 force push；
- 重大结构变化必须先更新规划 / 契约，再编码；
- 默认通过 branch → PR → CI → merge → main CI 验证；
- 合并前必须人工复核 diff，避免整文件替换引入无关改动；
- 文档状态变更不能替代代码测试；代码测试也不能替代真实人工验收。
