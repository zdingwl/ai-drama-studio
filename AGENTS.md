# AI Drama Studio V3 — 开发规则

## 1. 开发前读取顺序

任何代码修改前必须按顺序读取：

1. `docs/00_V3产品与系统详细规划.md`
2. `docs/03_Seko3.0_Skill架构逆向分析.md`
3. `docs/01_V3开发阶段与验收清单.md`
4. `docs/02_V3当前开发状态.md`
5. `docs/04_阶段人工验收规范.md`
6. 当前相关代码与测试

历史分支只能做参考，不能覆盖 V3 当前规划。

---

## 2. 产品边界

V3 只围绕六类项目建设：

```text
REPLICA              复刻
REDRAW               重绘
TRANSLATION          翻译
NOVEL_TO_DRAMA       小说生成短剧
SCRIPT_TO_DRAMA      剧本生成短剧
SCRIPT_LOCALIZATION  剧本本土化
```

`project_type` 是真实数据库字段。

每种 `project_type` 必须绑定自己的 Root Project Skill。

禁止只在前端显示六种类型，后端仍然走同一条旧流程。

---

## 3. V3 核心架构

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

Skill、Artifact、Agent、Tool、Guardrail 职责必须分开：

```text
Skill       = 怎么做对
Artifact    = 做出了什么
Agent       = 当前怎么规划
Tool        = 用什么执行
Guardrail   = 绝对不能违反什么
```

同时强制区分：

```text
Product Stage
= 用户关心的业务阶段

Internal PlanStep / Capability
= 为得到该业务结果而执行的内部步骤

P0/P1/P2/... Engineering Phase
= 我们开发和验收代码的切片
```

三者不能混为一谈。

### Skill 不是 Prompt

禁止实现成：

```text
Skill = 数据库里一段 Prompt
```

Skill 至少要有：

- 使用条件；
- 输入；
- 可读取 Artifact；
- required capabilities；
- 执行步骤；
- 决策规则；
- 用户询问规则；
- 输出契约；
- 校验；
- 完成标准；
- 失败处理。

### ProjectExecutionPlan 必须物化

Agent / Plan Compiler 生成的计划必须持久化、版本化和 fingerprint 化。

页面刷新不能重新临时规划。

Raw PlanStep 可以比普通用户看到的 Product Stage 更细；前端普通模式应按业务 phase 聚合，开发 / 排障模式才展开内部步骤。

---

## 4. Artifact Graph

V3 后端项目上下文必须由正式 Artifact 构成。

第一版不以无限画布 UI 为真相源。

```text
Artifact Graph = 正式业务关系
Canvas View    = Artifact Graph 的可视化
```

人物、场景、关键道具、剧本、分镜、音频和生成版本都必须成为可引用正式 Artifact 或正式领域对象。

禁止靠每次 Prompt 重复描述人物来维持一致性。

---

## 5. 统一硬规则

- 默认自动完成；只有真正需要创作选择或结构无法安全决定时询问用户。
- 普通用户只看业务结果，不展示 ASR/OCR/VLM/Shot Detector/Tracking/Fingerprint 等内部证据与工具名。
- 页面 GET 必须只读。
- 重任务必须由明确 POST / Command 启动。
- Skill 无权绕过 GET read-only。
- 外部计费 Provider 请求前必须先持久化 ProviderJob。
- API key 禁止写入 DB、日志、Artifact 或 Git。
- Source 与 Target 严格分离。
- Source Shot、Target Storyboard Shot、GenerationSegment 严格分离。
- GenerationAttempt 不是正式可用结果；只有 GenerationSelection 可以进入后期。
- 批量 Episode 默认顺序串行。
- 上游 revision / fingerprint 改变后，下游必须 STALE。
- 某个内部 Task succeeded 不等于整个 Product Stage 完成。

---

## 6. 视频类项目：原片理解编排

适用：REPLICA / REDRAW / TRANSLATION。

### 产品层

普通用户看到：

```text
导入完整 Episode
→ 原片理解
→ 业务可读理解结果
```

不得设计成普通用户必须依次操作：

```text
P5 Shot Boundary
→ P6 ASR/OCR
→ P7 VLM
→ P8 Shot Breakdown
```

P5/P6/P7/P8 是工程实现与内部能力切片。

### 完整 Episode 是 Source Truth

```text
SOURCE_VIDEO / 完整 Episode
= 权威原片输入
```

thumbnail / Reference Clip 是派生技术资产，只用于人工核对、局部精看或索引，不得替代完整 Episode。

### 内部执行关系

```text
完整 Episode
        │
        ↓
Media Preflight
        │
        ├────────────────┬────────────────┐
        ↓                ↓                ↓
Shot Anchors         ASR Evidence      OCR Evidence
        │                │                │
        └────────────┬───┴────────────────┘
                     ↓
              Source Evidence
                     +
               完整 Episode
                     ↓
          整集多模态原片理解
                     ↓
      Source Episode Bible / Story / Rhythm
                     ↓
        带全局知识做逐镜精细拉片
                     ↓
人物 / 场景 / 道具 / Speaker 归一
                     ↓
             SourceVideoSnapshot
```

硬规则：

- Shot Boundary 与连续 ASR 都直接读取 `SOURCE_VIDEO`，可并行；
- `SOURCE_DIALOGUE_EVIDENCE` 不得依赖 `SHOT_ANCHORS` 才能开始；
- ASR 不得按每个 Reference Clip 分开识别后拼句子；
- OCR 可以读取 Shot Anchors 作为抽帧提示，但完整 Episode 时间轴仍是 Source Truth；
- 整集理解必须能读取完整 Episode；
- 先整集理解，再逐 Shot 精细拉片；
- 禁止先逐 Shot 猜完整剧情，再拼整集理解。

### Source Evidence 与理解结果分离

```text
Source Evidence
= 原片实际说了什么 / 写了什么
= canonical + provenance

Source Understanding
= 这些事实在剧情、人物、关系、场景、事件和节奏上意味着什么
```

VLM / Agent / 安全过滤后的生成文本无权静默覆盖 canonical ASR / OCR / subtitle evidence。

---

## 7. Replica 硬规则

Replica 的默认目标：

> 故事不乱改，节奏不重做，文化和表达才本土化。

必须保留 / 锁定：

- Hook；
- 冲突；
- 反转；
- 信息揭示顺序；
- 情绪峰值；
- Payoff；
- Cliffhanger；
- Story Beat timing；
- Shot rhythm baseline。

允许本土化：

- 人物身份 / 外形；
- 场景；
- 道具；
- 文化信息；
- 目标语言对白。

目标对白必须先获得真实 TTS 时长，再做 Timing。

---

## 8. Provider 原则

业务 Skill 只依赖 capability，不依赖具体模型名。

例如：

```text
EPISODE_UNDERSTANDING
SHOT_BREAKDOWN
VIDEO_GENERATION
```

Provider Registry 决定实际实现。

当前重点候选：

- Agent reasoning：Step 3.7 Flash；
- 整集理解：Step 3.7 Flash 等真实 Episode A/B 后确定；
- 逐镜理解：Step 3.7 Flash / Qwen3.8 等真实镜头 A/B；
- ASR：faster-whisper 等候选，P6 真实验收后确定；
- OCR：RapidOCR 或替代实现，P6 真实验收后确定；
- TTS：Qwen3-TTS Provider；
- Video：MiniMax H3 Provider → local runtime；
- Lip Sync：LatentSync 或替代实现。

任何候选模型都不能因为“代码接入”就写成“真实验收通过”。

---

## 9. 状态与任务

正式 Artifact / 重阶段继续采用：

```text
Validity:
NOT_BUILT | CURRENT | STALE

Readiness:
READY | BLOCKED_DEPENDENCY | WAITING_RUNTIME | BLOCKED_TECHNICAL | NEEDS_USER_DECISION

Execution:
IDLE | QUEUED | PROCESSING | SUCCEEDED | FAILED | INTERRUPTED
```

只有：

```text
CURRENT + READY
```

才能下游消费。

Task 必须逐步支持：

- input fingerprint；
- Idempotency-Key；
- checkpoint；
- heartbeat；
- finite retry；
- cancel / resume。

---

## 10. 当前开发顺序

```text
P0 仓库重建                ✅
P1 新工程骨架              ✅
P2 Project + Skill Kernel  ✅
P3 SourceAsset + 输入系统  ✅
P4 Task / ProviderJob      ✅
P5 镜头技术锚点            ✅（原片理解内部能力）
P6 Source Evidence         下一工程切片，尚未开始
P7 整集多模态原片理解      尚未开始
P8 逐镜精细拉片            尚未开始
```

P5 已完成真实 Episode Shot Boundary、thumbnail、Reference Clip、Task 执行和 `SHOT_ANCHORS` Artifact，并保持 GET read-only、CURRENT/STALE、revision / fingerprint 等约束。

当前真实短剧已经跑通一条约 1:06 Episode 并产生 28 个 Shot Anchors，但这只代表 P5 技术能力通过，不代表“原片理解完成”。

P6 开发时必须作为“原片理解”内部 Source Evidence 能力接入，不新增要求普通用户单独操作的 P6 页面。P7 才进入真实整集多模态理解，P8 才进入带全局知识的逐镜精细拉片。

---

## 11. Git 规则

```text
main = V3 当前开发
backup/* = 历史回滚 / 参考
```

禁止 force push。

重大结构变化必须先更新规划，再编码。
