# AI Drama Studio V3 — 开发规则

## 1. 开发前读取顺序

任何代码修改前必须按顺序读取：

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
12. 当前相关代码与测试

**阶段状态以编号更高、日期更新的状态文档为准。** `docs/07` 记录 P7 最终验收，`docs/08` 记录 P8 初始正式契约，`docs/09` 记录 P6 canonical Evidence v2 整改及真实 P6 v2 → P7 → P8 恢复验收，`docs/10` 记录 P8 speaker candidate v2 与 P6 canonical micro-duplicate v3 的最新整改。旧文档中“P8 尚未开始 / P7 待验收 / P6-P7 未开发 / P8 schema 1.0 / P6 v2 是当前最终 canonical policy”等历史描述不得覆盖当前 `main` 事实。

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

`project_type` 是真实数据库字段；每种 `project_type` 必须绑定自己的 Root Project Skill。

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

职责必须分开：

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
= 开发和验收代码的切片
```

三者不能混为一谈。

### Skill 不是 Prompt

Skill 至少要有使用条件、输入、可读取 Artifact、required capabilities、步骤、判断规则、用户询问规则、输出契约、校验、完成标准与失败处理。

P7 的正式 Professional Skill：

```text
skills/professional/episode-understanding/SKILL.md
skills/professional/episode-understanding/manifest.json
source-video-understanding@1.1.0
```

P8 的正式 Professional Skill：

```text
skills/professional/shot-breakdown/SKILL.md
skills/professional/shot-breakdown/manifest.json
shot-breakdown@1.1.0
```

P8 当前运行契约：

```text
p8-shot-breakdown-v2
SOURCE_SHOT_FACTS schema 1.1
source-bible-shot-facts-v2
```

Provider Prompt 必须执行 Professional Skill 规则，但 Professional Skill 本身不等于 Prompt。

---

## 4. Artifact Graph

V3 后端项目上下文必须由正式 Artifact 构成。

```text
Artifact Graph = 正式业务关系
Canvas View    = Artifact Graph 的可视化
```

人物、场景、关键道具、剧本、分镜、音频和生成版本必须成为可引用正式 Artifact 或正式领域对象。

禁止靠每次 Prompt 重复描述人物来维持一致性。

---

## 5. 统一硬规则

- 默认自动完成；只有真正需要创作选择或结构无法安全决定时询问用户。
- 普通用户按业务结果工作，不要求理解 P5/P6/P7/P8 技术切片。
- 页面 GET 必须只读。
- 重任务必须由明确 POST / Command 启动。
- Skill 无权绕过 GET read-only。
- 外部计费 Provider 请求前必须先持久化 ProviderJob。
- API key 禁止写入 DB、日志、Artifact、ProviderJob、provenance 或 Git。
- API Key UI 当前默认密码遮罩，用户显式点击“显示”后才回显明文；本机值仅写入被 `.gitignore` 排除的 `backend/.env`。
- Source 与 Target 严格分离。
- Source Shot、Target Storyboard Shot、GenerationSegment 严格分离。
- GenerationAttempt 不是正式可用结果；只有 GenerationSelection 可以进入后期。
- 批量 Episode 默认顺序串行。
- 上游 revision / fingerprint 改变后，下游必须 STALE。
- 某个内部 Task succeeded 不等于整个 Product Stage 完成。

---

## 6. 视频类项目：原片理解编排

完整 Episode 永远是 Source Truth：

```text
SOURCE_VIDEO / 完整 Episode
= 权威原片输入
```

thumbnail / Reference Clip 是派生技术资产，只用于人工核对、局部精看或索引，不得替代完整 Episode。

内部执行关系：

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
      SOURCE_BIBLE / Story / Rhythm
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
- P6 canonical dialogue 必须保守分段；没有明确连续证据时不得仅因相邻 segment 时间接近就跨段合并；
- P6 raw ASR Evidence 必须完整保留；canonical admission 可以拒绝通用规则判定为不可信的 ASR micro duplicate，但不得删除 raw provenance、不得依赖 OCR/VLM/P7/P8 文本进行静默纠错；
- 同文案不等于同一 utterance，更不等于同一 speaker；禁止按字符串相同传播 P8 speaker candidate；
- P7 整集理解必须读取完整 Episode；
- 先整集理解，再逐 Shot 精细拉片；
- 禁止先逐 Shot 猜完整剧情，再拼整集理解。

### Source Evidence 与 Source Understanding 分离

```text
Source Evidence
= 原片实际说了什么 / 写了什么
= canonical + provenance

Source Understanding
= 这些事实在剧情、人物、关系、场景、事件和节奏上意味着什么
```

VLM / Agent / 安全过滤后的文本无权静默覆盖 canonical ASR / OCR。

P7 Grounding：

```text
FACT
= 原片直接可见或 CURRENT Source Evidence 明确陈述

INFERENCE
= 合理推导，但原片未直接确认

UNKNOWN
= 无法可靠判断
```

原则：**宁可 UNKNOWN，也不要合理补全。**

`UNKNOWN` 不是确定性正文的逃逸通道；`world_rules` 只允许本作品内部已确认 FACT，禁止社会泛化、法律结论、道德训诫或片外常识扩写。

---

## 7. Replica 硬规则

Replica 默认目标：

> 故事不乱改，节奏不重做，文化和表达才本土化。

必须保留 / 锁定：Hook、冲突、反转、信息揭示顺序、情绪峰值、Payoff、Cliffhanger、Story Beat timing、Shot rhythm baseline。

允许本土化：人物身份 / 外形、场景、道具、文化信息、目标语言对白。

目标对白必须先获得真实 TTS 时长，再做 Timing。

---

## 8. Provider / Capability 原则

业务 Skill 只依赖 capability，不依赖具体模型名。

当前已完成既有真实验收并维持 `AVAILABLE` 的能力：

```text
SOURCE_DIALOGUE_EVIDENCE
EPISODE_UNDERSTANDING
STORY_RHYTHM
```

P6 当前工程 canonical 基线已升级为：

```text
p6-source-evidence-v3
segment-preserving-dialogue-v3
adjacent-duplicate-microsegment-v1
```

v3 保留 v2 的保守分段和完整 Episode 连续 ASR 架构，只新增“相邻同文案 + 物理不可信 micro duration”canonical admission guard。raw ASR 仍完整保存。该升级部署后会使依赖旧 canonical set 的 P6/P7/P8 Artifact STALE，必须按 P6 → P7 → P8 显式恢复并完成真实音画复验；在恢复完成前不得把旧 CURRENT 结果冒充新基线验收结果。

仍为 `PLANNED`：

```text
SHOT_BREAKDOWN
IDENTITY_RESOLUTION
SCENE_RESOLUTION
PROP_RESOLUTION
SOURCE_SNAPSHOT
以及后续目标创作 / 生成能力
```

### Provider readiness 与 Capability availability 分离

```text
Capability AVAILABLE
!=
所有 Provider 都已在当前环境实测
```

P7 当前三个用户可选 Provider：

- Doubao Seed 2.1 Pro / Volcengine Ark：真实短剧 + Grounding v2 已通过，当前已验证生产 Provider；
- Qwen3.8-27B / local vLLM：工程接入和自动测试完成，真实本机 GPU / vLLM 质量验收待补；
- Qwen3-VL-8B-Thinking / local vLLM：工程接入和自动测试完成，低显存真实本机验收待补。

新增 / 可选 Provider 的 readiness 不应阻塞一个已经由真实生产 Provider 验收通过的业务 Capability。

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

Task 必须逐步支持 input fingerprint、Idempotency-Key、checkpoint、heartbeat、finite retry、cancel / resume。

---

## 10. 当前开发顺序

```text
P0 仓库重建                ✅
P1 新工程骨架              ✅
P2 Project + Skill Kernel  ✅
P3 SourceAsset + 输入系统  ✅
P4 Task / ProviderJob      ✅
P5 镜头技术锚点            ✅（真实 Episode 人工验收通过）
P6 Source Evidence         🔁（能力既有验收 AVAILABLE；canonical v3 micro-duplicate guard 工程整改与真实恢复复验进行中）
P7 整集多模态原片理解      ✅（能力 AVAILABLE；v3 P6 部署后需基于新 canonical Evidence 恢复 revision）
P8 逐镜精细拉片            🔁（speaker candidate v2 已实现；等待 P6 v3 → P7 → P8 恢复与最终 28 Shot 音画人工验收）
P9 身份/场景/道具归一       ⛔ 禁止进入
```

P7 最终验收基线：

```text
source-video-understanding@1.1.0
p7-source-bible-v2
SOURCE_BIBLE schema 1.1
grounded-source-truth-v2
```

P8 当前工程基线：

```text
shot-breakdown@1.1.0
p8-shot-breakdown-v2
SOURCE_SHOT_FACTS schema 1.1
source-bible-shot-facts-v2
```

P6 当前工程基线：

```text
p6-source-evidence-v3
segment-preserving-dialogue-v3
adjacent-duplicate-microsegment-v1
migration head = 0014_p6_microduplicate_guard_v3
```

本轮 v3 部署/迁移后的正确恢复状态应是：

```text
SOURCE_VIDEO / SHOT_ANCHORS         保持 CURRENT
旧 SOURCE_DIALOGUE                  STALE
旧 SOURCE_BIBLE / Story / Rhythm    STALE
旧 SOURCE_SHOT_FACTS                STALE
↓
显式 P6 → P7 → P8 重跑
↓
生成新 CURRENT revision
↓
继续最终 28 Shot 音画人工验收
```

只有最终 28 Shot 音画人工验收通过后，才允许评估把 `SHOT_BREAKDOWN` 从 `PLANNED` 改为 `AVAILABLE`。在此之前禁止进入 P9。

P8 固定输入契约：

```text
完整 Episode / SOURCE_VIDEO
+
CURRENT SOURCE_BIBLE
+
CURRENT SHOT_ANCHORS
+
CURRENT canonical Source Evidence
↓
逐镜精细拉片
```

P8 不能重新从零猜整集故事；Shot 时间只来自 P5；对白正文来自 P6 canonical Evidence；P8 不得为了修正文质量而自行重听写。P8 speaker candidate 只能绑定具体 P6 utterance 到 CURRENT P7 character candidate，不能按相同文本跨 utterance 复制，更不能冒充 P9 最终 Speaker Truth。

---

## 11. Git 规则

```text
main = V3 当前开发
backup/* = 历史回滚 / 参考
```

禁止 force push。

重大结构变化必须先更新规划，再编码。
