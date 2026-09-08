# Seko 3.0 Skill 架构逆向分析

> 日期：2026-09-08  
> 用途：作为 AI Drama Studio V3 Skill 架构设计参考。  
> 重要声明：本文没有获得、泄露或声称持有 Seko 3.0 内部 System Prompt / 私有 Skill 原文。本文只依据官方公开信息、公开产品页面和公开实测行为，区分“已确认事实”和“架构推断”。

---

# 1. 研究结论

Seko 3.0 最值得学习的不是某个模型，而是四个东西被组合成了一个完整生产系统：

```text
Agent
+
Skill
+
无限画布 / 项目资产上下文
+
模型与媒体工具
```

官方公开信息已经明确：

- Agent 是智能工作流主轴；
- 无限画布负责沉淀剧本、角色、场景、视觉风格等项目资产和上下文；
- Skill 封装题材判断、叙事节奏、角色设计、分镜等专业创作经验；
- Agent 会按照创作意图自动匹配 Skill；
- Seko 3.0 已形成六大类、二十余款 Skill；
- Agent 能做多类型意图理解、任务自动拆解、模型智能匹配和工作流组装。

因此，Skill 应理解成：

> **一套可以被 Agent 执行、能够读取项目上下文、能够调用工具、能够产生正式创作资产、包含专业判断规则和完成标准的方法论。**

它不是一段普通 Prompt。

---

# 2. 证据等级

为了避免把推断冒充成 Seko 内部事实，本文使用三个等级。

## A：官方确认

来自商汤 / Seko 官方页面或官方新闻。

可以确认：

- Agent + 无限画布 + Skill 是 Seko 3.0 核心架构；
- Agent 自动匹配 Skill；
- 画布资产会被后续创作继续读取；
- Skill 来自头部创作者和成熟工作室的专业经验；
- 六大类二十余款 Skill；
- Agent 支持任务拆解、模型匹配和工作流组装。

## B：公开实测确认

来自实际使用 Seko 3.0 的公开教程 / 体验记录，以及项目使用者提供的可复核产品实测截图。

可以确认：

- Skill 页面会展示“使用场景、使用方法、输出信息、样片”等信息；
- 部分 Skill 会通过多轮对话逐步推进，而不是一次生成全部结果；
- Agent 会询问剧集规模、时长、语言等缺失配置；
- 剧本确认后会继续生成角色、场景、道具等资产；
- 分镜和资产可以写入画布；
- 单个分镜或资产可以局部修改而不是整项目重做；
- 精细化分步创作与 Agent 快速成片是两种并行使用方式；
- 在“完整视频 + 出海翻转创作意图”的公开实测中，画布保留完整视频节点，Agent 直接显示调用“多模态分析”，而不是要求用户先完成 Shot Boundary / ASR / OCR 等技术步骤；
- 该多模态分析首轮结果已经同时给出素材基线、整体故事分析、带时间窗口的画面/对白剧本、角色、场景和关键道具等结构化内容；
- 分析完成后，Agent 再建议将理解结果写入画布 / 文本节点。

## C：架构推断

以下属于根据产品行为推断，不代表 Seko 内部实现一定如此：

- Skill 内部很可能存在输入契约、步骤、判断条件、可调用工具、输出契约和完成标准；
- Skill 很可能有“缺少关键创作决策时先询问用户”的判断规则；
- Agent 很可能先解析 Skill，再根据项目上下文形成当前执行计划；
- 画布在系统内部很可能对应某种资产图 / 上下文图，而不仅是坐标 UI；
- Seko 的“多模态分析”产品动作内部可能组合视频抽帧、语音、文字、镜头结构或其他工具，但公开截图**不能证明**其内部具体是否使用 Shot Detection / ASR / OCR，也不能证明调用顺序。

V3 可以吸收这些思想，但不能把推断写成“Seko 原始代码结构”。

---

# 3. 官方确认的 Seko 3.0 核心关系

可以抽象成：

```text
用户意图
   ↓
Agent
   ├─ 理解创作意图
   ├─ 自动拆解任务
   ├─ 匹配 Skill
   ├─ 选择模型 / 工具
   └─ 组装工作流
   ↓
Skill
   ├─ 专业方法
   ├─ 题材判断
   ├─ 叙事节奏
   ├─ 角色设计
   └─ 分镜经验
   ↓
无限画布
   ├─ 剧本
   ├─ 角色
   ├─ 场景
   ├─ 道具
   ├─ 分镜
   ├─ 图片 / 视频资产
   └─ 历史上下文
   ↓
继续生成 / 修改 / 下一集
```

关键不是“Agent 自动化”，而是 Agent 自动化有两个稳定依赖：

```text
Skill = 怎么做对
Canvas = 当前项目已经有什么
```

模型 / 工具解决的是：

```text
怎么执行
```

三者职责不应混在一起。

---

# 4. Seko Skill 公开可确认的六大类

公开信息中反复出现以下六类：

```text
1. 顶流超创
2. 热门短剧
3. 角色设计
4. 编剧导演
5. 营销广告
6. 自媒体
```

不同报道有时会使用“导演风格”“导演美学”等近似叫法，但核心分类方向一致。

这说明 Seko 的 Skill 并不只按“技术工具”分类，而是同时存在：

- 题材 Skill；
- 全流程创作 Skill；
- 角色 / 美术 Skill；
- 编剧 Skill；
- 分镜 / 导演 Skill；
- 商业内容 Skill。

也就是说，一个 Skill 可以覆盖一个完整项目，也可以只解决某一专业问题。

---

# 5. 公开可观察的代表 Skill 与实测行为

下面只记录公开资料或可复核产品实测中能确认名称或行为的部分。

## 5.1 山音编剧大师 / 山音编剧大师 2.0

公开实测显示，它不是简单“输入灵感 → 输出剧本”。

它会在关键创作节点持续询问用户，例如：

- 希望观众看完是什么感觉；
- 剪辑节奏是什么类型；
- 当前创意是否真正想清楚；
- 某些结局或方向是否过于俗套。

其价值是把编剧的思考过程变成可执行引导。

V3 吸收点：

```text
Skill 必须允许定义 Decision Questions。
关键创作问题没有答案时，不应该永远由模型擅自猜。
```

---

## 5.2 山音分镜大师

公开实测可以较明确还原出如下阶段：

```text
剧本输入
↓
导演定调
↓
节奏规划
↓
剧本微调
↓
分镜拆解
↓
导演方案设计
↓
具体分镜表
↓
写入画布 / 开始生成
```

在“导演定调”阶段还会引导用户考虑：

- 情绪基调；
- 视听风格；
- 叙事重心；
- 叙事视角。

这证明专业 Skill 可以包含多轮思考和阶段性产物，而不是只返回一个最终 JSON。

V3 吸收点：

```text
SkillStep 可以产生中间正式 Artifact。
后续步骤消费这些 Artifact，而不是把所有上下文塞进一个超长 Prompt。
```

---

## 5.3 第一视角催泪短片 Skill

公开资料确认此 Skill 来自创作者李让的创作经验，目标是把第一视角、临场感、情绪表达等成熟方法封装成可调用能力。

部分公开实测描述其输入可以是一句话主题、灵感或亲身经历，输出第一人称情感剧本和配套分镜方案。

V3 吸收点：

```text
Skill 可以同时约束：
故事表达方式
+
镜头语言
+
情绪目标
```

Skill 不一定只属于“编剧”或“分镜”单一阶段。

---

## 5.4 修仙漫剧角色设计 Skill

官方将其作为“角色设计方法论被封装成 Skill”的代表案例。

V3 吸收点：

角色设计应该是可复用的专业 Skill，并输出可长期引用的正式角色资产，而不是每个镜头重新写一遍人物外貌 Prompt。

---

## 5.5 出海爆款短剧 Skill

公开实测显示该 Skill 至少涉及：

- 海外题材方向；
- 核心爽点 / 情绪卖点；
- 人物关系；
- 剧情走向；
- 每集核心冲突；
- 视觉方向；
- 目标语言 / 地区创作。

用户可以继续修改叙事节奏、人物关系和冲突密度。

V3 吸收点：

“出海”不应做成单纯 Translation Skill，而应该拆成：

```text
目标市场理解
+
文化本土化
+
人物 / 场景 / 道具世界设计
+
目标语言对白
```

对于 V3 的 REPLICA 模式，还必须额外加“故事骨架锁”和“节奏骨架锁”，防止本土化变成随意重写。

---

## 5.6 BJD 古偶甜宠剧 / 女频甜宠 / 清朝宫斗等热门短剧 Skill

公开 Skill 页面实测显示，用户可以在 Skill 详情里查看：

```text
使用场景
使用方法
输出信息
样片
```

这对 V3 很重要：Skill 不应该只是系统内部文件，也应该有用户能理解的产品描述。

---

## 5.7 复古港风角色设计 / 都市乙女 / 原创真人影视等

这些公开案例说明“角色设计 Skill”不仅负责生图提示词，还承担统一风格和角色资产标准化的作用。

---

## 5.8 名人传记短片 Skill

公开实测显示，该 Skill 可以从一句“创作某人的传记短片”开始，生成结构化故事方向，再准备人物、场景、关键道具，并在生成前检查素材是否齐全。

V3 吸收点：

```text
Skill 在执行关键生成前必须支持 readiness check。
缺资产时应该补资产，而不是直接进入视频生成。
```

---

## 5.9 完整短剧“多模态分析”实测：工程子步骤被 Agent 封装

2026-09-08 项目使用者提供了 Seko 3.0 可复核实测截图。外部可观察流程为：

```text
完整竖屏短剧视频写入画布
+
用户提出“把这个现代都市短剧转绘成面向美国地区的本土化短剧”
↓
创作 Agent
↓
界面显示：正在调用工具「多模态分析」
↓
一次返回原片概览与结构化理解结果
↓
再建议写入画布 / 创建文本节点
```

首轮结果可观察到同时包含：

```text
素材基线
├─ 有效内容起止时间
├─ 总时长
├─ 画幅
├─ FPS / 时间基准
└─ 快速剪辑 / 闪白等视觉节奏描述

整体分析
├─ 故事背景 / 类型 / 世界规则
├─ 叙事结构
├─ 人物关系
├─ 视觉风格
└─ 节奏

时间化剧本
├─ 时间窗口
├─ 画面描述
└─ 对白

结构化资产候选
├─ 角色列表
├─ 场景列表
└─ 关键道具列表
```

截图里的剧本时间窗口存在重叠，例如一个窗口可以覆盖 `00:00–00:03`，下一个又从 `00:01–00:04` 开始。因此这些时间段更像**语义 / 剧情时间窗口**，不能据此声称 Seko 已公开输出精确 Shot Boundary。

同一实测还出现了平台文本审核导致某句原始台词相关“文本节点未能成功创建”的提示。这一点对 V3 非常重要：

> **多模态理解结果不是 canonical Source Evidence。模型输出可能因为安全策略、摘要、纠错或生成行为而与原始素材不同。**

因此 V3 必须保留两层正式数据：

```text
Source Evidence
= 原始素材里实际说了什么 / 写了什么
= ASR / OCR / subtitle reconciliation
= 可追溯、不可被理解模型反写覆盖

Source Understanding
= 这些事实意味着什么
= 剧情、人物、关系、场景、事件、节奏等语义理解
```

### 这组实测能确认什么

能确认的是**产品编排行为**：用户看到“完整视频 → Agent 多模态分析 → 原片理解结果”，而不是被要求依次点击 Shot Boundary、ASR、OCR、整集理解。

### 这组实测不能确认什么

不能确认 Seko 内部：

- 是否使用独立 ASR；
- 是否使用独立 OCR；
- 是否先做 Shot Detection；
- 各工具是串行还是并行；
- 使用了哪些私有模型 / Prompt / Skill 实现。

### V3 的吸收结论

工程实现阶段与用户产品阶段必须分离：

```text
用户产品流程
完整 Episode
→ 开始原片理解
→ 原片理解结果

系统内部执行
完整 Episode / Source Truth
├─ media preflight
├─ Shot Anchors
├─ ASR / Source Dialogue Evidence
├─ OCR / Visual Text Evidence
└─ Whole-Episode Multimodal Understanding
        ↓
Source Bible / Story / Rhythm
        ↓
带全局知识做逐镜精细拉片
```

其中 Shot Anchors 与 ASR 都可以直接消费完整 `SOURCE_VIDEO`；ASR 不应因为 Shot Boundary 未完成而被强制阻塞，也不应把每个 Reference Clip 分开识别。

---

# 6. 从公开行为反推的 Skill 通用契约

V3 不复制 Seko 内部未知格式，而是把公开行为转换成自己的正式规范。

建议每个 Skill 至少定义：

```yaml
id:
name:
version:
category:
description:

when_to_use:
when_not_to_use:

required_inputs:
optional_inputs:
readable_artifacts:

required_capabilities:
allowed_tools:
subskills:

steps:
  - id:
    goal:
    reads:
    decisions:
    actions:
    outputs:
    validation:

user_decision_policy:
auto_decision_policy:

output_contracts:
completion_criteria:
failure_policy:
next_recommended_skills:
```

`SKILL.md` 用于保存人类可读的方法论、规则和示例；机器可执行元数据建议配套结构化 manifest，而不是运行时靠正则解析 Markdown。

---

# 7. Skill 不等于 Prompt

V3 必须明确：

```text
Prompt
= 一次模型调用的指令

Skill
= 一套跨步骤、跨模型、跨 Artifact 的专业方法
```

Skill 可以：

- 读取项目已有正式资产；
- 询问用户关键决策；
- 调用子 Skill；
- 调用多个模型 / 工具；
- 产生多个阶段性 Artifact；
- 验证输出；
- 判断是否可以进入下一步；
- 推荐下一 Skill。

因此禁止把 Skill Engine 实现成“从数据库拿一段 Prompt → 调一次 LLM”。

---

# 8. Seko 的“画布”真正值得学什么

Seko 官方明确表示，续集生成时 Agent 会读取画布中已有的：

- 前序剧本；
- 角色设定；
- 场景资产；
- 视觉风格。

因此画布不是纯 UI。

V3 应学习其“资产上下文长期沉淀”思想，但不要一开始复制无限画布 UI。

V3 后端应该先建立：

```text
Artifact Graph
```

例如：

```text
TargetCharacter ETHAN
    ├─ used_by → StoryboardShot 12
    └─ used_by → StoryboardShot 18

TargetScene MANSION_LIVING_ROOM
    ├─ used_by → StoryboardShot 11
    └─ used_by → StoryboardShot 12

TargetProp DNA_REPORT
    └─ used_by → StoryboardShot 23
```

前端以后可以把 Artifact Graph 渲染成画布。

核心原则：

> **画布是 Artifact Graph 的视觉化，不是业务真相本身。**

---

# 9. Seko 的两种使用路径

公开实测表明存在两种并行方式。

## 快速 Agent 路径

```text
一句话 / 剧本 / 完整视频
↓
Agent 自动规划
↓
自动调用内部工具与专业 Skill
↓
产生业务可读资产
↓
继续生成
```

适合验证创意和批量生产。

## 专业分步路径

```text
编剧 Skill
↓
角色提取 / 角色设计 Skill
↓
分镜 Skill
↓
生成
↓
后期 Skill
```

适合精修。

注意：“专业分步”仍然是**业务步骤**，不等于把 ASR / OCR / Shot Detection 等工程工具逐个暴露给普通用户。

V3 也应该保留两种体验：

```text
自动模式
专业模式
```

但二者必须消费同一套正式 Artifact，不能做两套互不兼容的数据结构。

---

# 10. V3 应采用的核心架构

依据上述研究，V3 正式推荐：

```text
Project Type
↓
Root Project Skill
↓
Agent / Plan Compiler
↓
Project Execution Plan
↓
Professional Skills
↓
Tool / Provider Capabilities
↓
Typed Artifacts
↓
Artifact Graph
↓
下一步 Skill
```

同时存在硬约束层：

```text
Workflow Guardrails
Task / ProviderJob
Revision / Fingerprint / STALE
GET Read-only
Schema Validation
```

Agent 负责“规划和专业判断”。

Guardrail 负责“绝对不能违反的系统规则”。

两者不能混为一体。

产品展示还必须和内部计划分层：

```text
Product Stage
= 用户关心的业务结果，例如「原片理解」

Internal PlanStep
= 为得到该结果需要执行的技术 / 专业子步骤
```

不能再把开发阶段编号 P5 / P6 / P7 或内部 PlanStep 直接当成用户必须依次操作的产品工作流。

---

# 11. 六个项目类型应成为六个 Root Skill

```text
REPLICA
→ skills/projects/replica/SKILL.md

REDRAW
→ skills/projects/redraw/SKILL.md

TRANSLATION
→ skills/projects/translation/SKILL.md

NOVEL_TO_DRAMA
→ skills/projects/novel_to_drama/SKILL.md

SCRIPT_TO_DRAMA
→ skills/projects/script_to_drama/SKILL.md

SCRIPT_LOCALIZATION
→ skills/projects/script_localization/SKILL.md
```

Project Type 仍然是真实数据库枚举。

变化在于：

旧设计：

```text
project_type
→ 固定 stage graph
```

新设计：

```text
project_type
→ Root Skill
→ Root Skill 声明目标、能力和 Artifact 依赖
→ Plan Compiler 根据当前项目状态生成计划
```

---

# 12. V3 Skill 三层结构

## 12.1 项目 Skill

回答：

> 这个项目整体怎么完成？

六个 Root Skill 即属于这一层。

## 12.2 专业 Skill

回答：

> 某项专业工作应该怎么做对？

首批建议：

```text
source-video-understanding
story-rhythm-analysis
shot-breakdown
character-resolution
scene-resolution
prop-resolution
speaker-attribution
novel-adaptation
script-analysis
script-localization
target-world-design
character-design
scene-design
prop-design
dialogue-localization
storyboard-directing
timing-adaptation
video-generation-qc
post-production
```

## 12.3 Tool / Provider Playbook

回答：

> 具体模型或工具怎么正确调用？

例如：

```text
step37-agent-reasoning
step37-visual-understanding
faster-whisper
rapidocr
speaker-provider
qwen3-tts
minimax-h3
latentsync
ffmpeg
```

业务 Skill 应依赖 capability，不应依赖具体模型名。

例如：

```text
需要 capability = SOURCE_EPISODE_UNDERSTANDING
```

由 Provider Registry 决定当前实际使用 Step 3.7 Flash、其他云模型或本地模型。

---

# 13. Step 3.7 Flash 在该架构中的位置

Step 3.7 Flash 官方公开定位非常适合 Agent 工作流：长上下文、视觉理解、工具调用、Agent 平台适配。

V3 建议优先验收两个角色：

```text
1. AgentReasoningProvider
   用于：计划、Skill 推理、跨 Artifact 理解、结构化决策

2. SourceEpisodeUnderstandingProvider 候选
   用于：整集 / 长视频视觉剧情理解
```

但是：

- 是否直接承担完整视频输入必须以实际 API / 本地 Runtime 验收为准；
- 是否能可靠利用视频音频不能凭模型名假设；
- canonical source dialogue 仍归 ASR/OCR evidence；
- Speaker 仍归独立 Speaker evidence；
- 人物身份仍需 Identity Resolver。

因此 Step 3.7 Flash 是“Agent 大脑 / 视觉理解候选”，不是业务唯一真相源。

---

# 14. V3 不应该照搬 Seko 的地方

## 不照搬 1：不把无限画布作为数据库

UI 节点坐标不能成为业务真相。

## 不照搬 2：不把 Agent 变成无约束黑盒

生成计划必须物化并版本化，不能每次刷新网页重新让模型临时决定。

## 不照搬 3：不让 Skill 绕过正式数据边界

Skill 无权直接修改 raw source evidence 或跳过 Snapshot / Artifact 校验。

## 不照搬 4：不让 Skill 页面加载自动花钱

GET 永远只读；远程付费调用仍必须先创建 ProviderJob。

## 不照搬 5：不靠 Prompt 保存人物一致性

人物、场景、关键道具必须成为正式可引用 Artifact。

## 不照搬 6：不把“模型理解文本”当原始证据

即使多模态分析一次能产生完整剧本、角色、场景和道具，也必须保持：

```text
Raw / Canonical Source Evidence
!=
Semantic Understanding Output
```

安全过滤、模型摘要或语义纠错都不能静默覆盖原始 ASR / OCR / subtitle evidence。

---

# 15. V3 比 Seko 通用方案额外必须强化的能力

V3 的旗舰“复刻”不是从零创作，因此必须增加两层强约束：

```text
Story Skeleton
+
Rhythm Skeleton
```

Replica Skill 必须默认锁定：

- Hook；
- 冲突顺序；
- 反转；
- 信息揭示顺序；
- 情绪峰值；
- Payoff；
- Cliffhanger；
- 场景顺序；
- Shot rhythm 基线。

本土化默认允许替换：

- 人物身份 / 外观；
- 场景文化环境；
- 道具外观；
- 货币 / 制度 / 称呼；
- 目标语言表达。

目标是：

> **把已经验证好看的短剧换一个国家、人物和语言重新拍一遍，而不是让 Agent 重新编一部。**

---

# 16. 研究来源

优先级从官方到公开实测：

1. 商汤官方：Seko 3.0“AI 视频梦工厂”  
   https://www.sensetime.com/cn/news/seko-3-0-ai-1

2. 商汤官方：徐立谈 Seko 3.0 Agent + Skill 体系  
   https://www.sensetime.com/cn/news/51170768

3. Seko 官方站  
   https://seko.sensetime.com/

4. 娱乐资本论：山音编剧 / 分镜大师公开体验  
   https://ylzbl.com/article/409092

5. UMAAX：Seko 3.0 Skill 页面与创作流程实测  
   https://umaax.com/shangtangseko30shiceyijianshengchengbaokuanaiduanmanju01jing/

6. Toolin：出海短剧 Skill 实操  
   https://toolin.ai/blog/seko-3-seedance-2-overseas-short-drama

7. 公开产品实测：六类 Skill 与两种创作路径  
   https://www.sohu.com/a/1056653724_122518389

8. 2026-09-08 项目使用者提供的 Seko 3.0 产品实测截图：完整短剧视频 → 出海翻转 → 多模态分析 → 原片概览 / 时间化剧本 / 角色 / 场景 / 道具。该材料用于记录可观察产品行为，不作为 Seko 私有内部实现证据。

---

# 17. 对 V3 的最终结论

V3 的核心不应该是：

```text
六种 project_type
→ 六套写死工作流
```

也不应该是：

```text
开发阶段 P5
→ 用户点一次
开发阶段 P6
→ 用户再点一次
开发阶段 P7
→ 用户再点一次
```

而应该是：

```text
六种 project_type
→ 六个 Root Skill
→ Agent / Plan Compiler
→ 用户业务阶段
→ 内部专业 Skill / Tool 编排
→ 正式 Artifact
→ Artifact Graph
```

视频类第一项用户业务能力统一表达为：

```text
完整原片
→ 原片理解
→ 可编辑、可追溯的 Source Facts
```

同时由系统硬规则保证：

```text
完整 Episode 是 Source Truth
Source Evidence / Semantic Understanding 分离
Source / Target 分离
GET 只读
ProviderJob 先持久化
Revision / Fingerprint / STALE
Task 可恢复
Schema Valid
Generation QC / Selection
```

这就是 V3 吸收 Seko 3.0 公开实测后应该采用的正式架构方向。
