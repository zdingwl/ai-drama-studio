# AI Drama Studio V3 — 开发规则

## 1. 开发前读取顺序

任何代码修改前必须按顺序读取：

1. `docs/00_V3产品与系统详细规划.md`
2. `docs/03_Seko3.0_Skill架构逆向分析.md`
3. `docs/01_V3开发阶段与验收清单.md`
4. `docs/02_V3当前开发状态.md`
5. 当前相关代码与测试

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
- 普通用户只看业务结果，不展示 ASR/OCR/VLM/Tracking/Fingerprint 等内部证据。
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

---

## 6. 视频类项目原片理解顺序

适用：REPLICA / REDRAW / TRANSLATION。

正式顺序：

```text
导入原片
→ 媒体检查
→ Shot Boundary（只做时间锚点）
→ ASR + OCR
→ 整集理解
→ Source Episode Bible
→ Story Skeleton + Rhythm Skeleton
→ 带全局知识逐镜精细拉片
→ 人物 / 场景 / 道具 / Speaker 归一
→ SourceVideoSnapshot
```

禁止退回：

```text
先逐 Shot 猜完整剧情
→ 最后拼成整集理解
```

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
SOURCE_EPISODE_UNDERSTANDING
SHOT_BREAKDOWN
AGENT_REASONING
VIDEO_GENERATION
```

Provider Registry 决定实际实现。

当前重点候选：

- Agent reasoning：Step 3.7 Flash；
- 整集理解：Step 3.7 Flash 等真实 Episode A/B 后确定；
- 逐镜理解：Step 3.7 Flash / Qwen3.8 等真实镜头 A/B；
- ASR：faster-whisper；
- OCR：RapidOCR 或替代实现；
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
P5 视频技术预处理          ✅
P6 ASR / OCR               下一阶段，尚未开始
```

P5 已完成真实 Episode Shot Boundary、thumbnail、Reference Clip、Task 执行和 `SHOT_ANCHORS` Artifact，并保持 GET read-only、CURRENT/STALE、revision / fingerprint 等约束。

P6 开始前继续遵守：不得因为 P5 已有 Shot 时间锚点就提前做对白识别、OCR、剧情理解或 Step 3.7 Flash 调用。P6 只在其独立阶段开发 ASR / OCR / Source Dialogue；P7 才进入整集理解。

---

## 11. Git 规则

```text
main = V3 当前开发
backup/* = 历史回滚 / 参考
```

禁止 force push。

重大结构变化必须先更新规划，再编码。
