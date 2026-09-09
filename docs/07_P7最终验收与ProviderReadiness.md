# P7 最终验收与 Provider Readiness

> 日期：2026-09-09  
> 状态：**P7 已通过真实短剧人工验收**。  
> 本文是 P7 最终状态补充；若旧文档中的阶段状态与本文冲突，以本文和 `docs/02_V3当前开发状态.md` 的后续更新为准。

---

# 1. 最终结论

```text
P5 镜头技术锚点       ✅
P6 Source Evidence    ✅
P7 整集多模态原片理解 ✅
P8 逐镜精细拉片       ⏸ 尚未开始
```

P7 已验证能力：

```text
EPISODE_UNDERSTANDING = AVAILABLE
STORY_RHYTHM          = AVAILABLE
SHOT_BREAKDOWN        = PLANNED
```

P7 完成不代表每个可选 Provider 都已在当前硬件环境实测。Capability 是否可用，与单个 Provider 的本机 readiness 分开管理。

---

# 2. 本次真实验收素材

真实 Episode：

```text
货到付款惩治隔壁大妈-第01集.mp4
约 66 秒
1080x1920
```

真实运行输入：

```text
完整 immutable Episode
+
CURRENT P6 canonical ASR / OCR Source Evidence
+
CURRENT Shot Anchors（作为可选定位提示）
```

真实 Provider：

```text
Volcengine Ark
Doubao Seed 2.1 Pro
```

实际 P7 契约：

```text
source-video-understanding@1.1.0
p7-source-bible-v2
SOURCE_BIBLE schema 1.1
grounded-source-truth-v2
```

---

# 3. 人工验收通过项

最终真实结果已确认：

- 完整 Episode 直接进入整集多模态理解，不按 Shot / Reference Clip 独立猜剧情后拼接；
- P6 canonical dialogue / OCR 仍是文字事实源；
- SOURCE_BIBLE 能直接阅读，不只显示 Task succeeded；
- 素材基线、整体分析、时间化原作剧情、人物 / 关系、场景、关键道具、Story Skeleton、Rhythm Skeleton 均可读；
- 时间化原作剧情使用剧情语义窗口，不冒充 Shot Boundary；
- 真实结果中的 `128 元`、`结婚八年` 等关键事实能在 canonical Evidence 中反查；
- `world_rules` 在没有明确片内规则时正确显示为空 / “无明确片内世界规则”，不再输出社会泛化或法律结论；
- 黑色垃圾袋只保留可见外观事实，未确认独立剧情作用时保持 `null + UNKNOWN`，不再补成“倒垃圾时顺手拿花”等因果；
- FACT / INFERENCE / UNKNOWN Grounding Contract 生效；UNKNOWN 不能作为确定性正文的逃逸通道；
- Provider 与 Service publication 双层 fail-closed 生效；
- 模型 Evidence 引用使用短引用映射后再恢复 canonical Evidence ID，避免长 UUID 抄写脆弱性，同时未知引用仍 fail closed；
- P7 Retry 能真正重新调度 P7 runner；
- SOURCE_BIBLE 支持 revision / CURRENT / STALE / edit -> new revision；
- P6 Source Evidence 不因 P7 生成、Provider 切换、Runtime Profile 变化或人工编辑而被覆盖；
- 页面将 Evidence 默认折叠，保留按需查看 canonical 正文入口；
- “类型”和“世界规则”已经拆分显示；
- Revision / Provenance 区可展开查看 Provider / Model / ProviderJob / Prompt / Schema / Professional Skill / Grounding Contract / 上游 Artifact；
- API Key 默认使用密码遮罩，用户点击“显示”后才回显明文；保存仍写入被 `.gitignore` 排除的本机 `backend/.env`。

因此，P7 的数据契约、真实 Provider 路径、Source Truth 边界、用户可读结果和人工验收均已达到下一阶段输入要求。

---

# 4. Provider Readiness

P7 当前保留三个用户可选 Provider 档位，但 readiness 分开记录：

| Provider | 工程接入 | 自动测试 | 真实当前环境验收 | 当前定位 |
|---|---|---|---|---|
| Doubao Seed 2.1 Pro / Volcengine Ark | ✅ | ✅ | ✅ | 已验证生产 Provider |
| Qwen3.8-27B / local vLLM | ✅ | ✅ | ⏳ | 已接入，待本机 GPU / vLLM 实测 |
| Qwen3-VL-8B-Thinking / local vLLM | ✅ | ✅ | ⏳ | 已接入，低显存兼容候选，待本机实测 |

重要语义：

```text
Capability AVAILABLE
!=
所有 Provider 都已 QUALIFIED
```

只要至少一个真实生产 Provider 已对真实 Episode 端到端通过业务验收，业务 Capability 可以 AVAILABLE。新增 / 可选 Provider 应独立做 Provider readiness 验收，不应因为当前机器没有本地 GPU 阻塞后续业务阶段。

本地 Qwen 的真实 A/B 仍然值得后续补做，但它属于 Provider qualification / 性能优化，不再是 P8 开始的前置门槛。

---

# 5. P7 最终架构边界

```text
完整 Episode
+
CURRENT Source Evidence
+
可选 Shot Anchors
↓
source-video-understanding Professional Skill
↓
真实 Provider
↓
Grounding / Schema / Service Guardrail
↓
SOURCE_BIBLE《源作概览分析》
+
Story Skeleton
+
Rhythm Skeleton
```

仍然禁止：

- P7 直接输出逐镜景别 / 构图 / 运镜 / 焦距 / 音效表；
- 用 VLM 改写 canonical ASR / OCR；
- 把 Shot Anchors 当剧情段；
- 把 Reference Clip 替代完整 Episode；
- GET 自动调用模型；
- ProviderJob 未持久化就发起外部计费请求。

---

# 6. 下一阶段 P8 的固定输入契约

新聊天进入 P8 时，必须从当前 `main` 重新读取手册和代码，并以以下输入为准：

```text
完整 Episode / SOURCE_VIDEO
+
CURRENT SOURCE_BIBLE
+
CURRENT SHOT_ANCHORS
+
需要时读取 CURRENT canonical Source Evidence
↓
P8 逐镜精细拉片
```

P8 不能重新从零猜整集故事。

Seko 实测产品参考的逐镜结果形态包括：

```text
镜头编号
源片段 / Reference Clip
时长
画面描述
镜头语言（景别 / 构图 / 镜头类型 / 运镜 / 焦距景深）
绑定主体（角色 / 场景 / 道具）
对白 / 旁白
音效
```

其中 V3 仍坚持：

- Shot start / end 优先来自 P5 SHOT_ANCHORS；
- 对白正文必须来自 P6 canonical Evidence，P8 只做 Shot 绑定，不重新听写覆盖；
- P7 SOURCE_BIBLE 提供整集人物、关系、故事、场景、道具、Story / Rhythm 全局知识。

---

# 7. P7 后续可选优化（不阻塞 P8）

以下属于后续 Provider / 产品体验优化，不再是 P7 完成门槛：

- 在真实 GPU 环境补做 Qwen3.8-27B 与 Doubao 同源 A/B；
- 在低显存机器补做 Qwen3-VL-8B-Thinking 性能 / 质量验收；
- 收集更多长 Episode、复杂转场、多角色、弱字幕素材的回归样本；
- 将开发验收型 Provider 配置进一步收纳到高级 / 开发设置；
- 后续如引入统一模型网关，再抽象 Provider readiness / health 状态。

这些优化不改变当前结论：**P7 已完成，P8 可以作为下一独立工程阶段开始。**
