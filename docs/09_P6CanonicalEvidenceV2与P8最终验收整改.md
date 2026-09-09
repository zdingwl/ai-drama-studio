# P6 Canonical Evidence v2 与 P8 最终验收整改

> 日期：2026-09-09  
> 状态：工程实现完成；真实 P6 v2 → P7 → P8 恢复验收待执行  
> 触发原因：P8 真实短剧程序验收通过，但最终人工逐镜音画检查发现 P6 canonical dialogue 存在过度合并与明显 ASR 错词，导致 P8 虽严格原样绑定 P6，仍无法作为最终可靠逐镜对白事实输入。

---

# 1. 不变的架构边界

本次整改**不改变** V3 Source Understanding 总架构：

```text
完整 Episode / SOURCE_VIDEO
├─ P5 Shot Anchors
├─ P6 连续 ASR Evidence
└─ P6 全时间轴 OCR Evidence
        ↓
CURRENT canonical Source Evidence
        +
完整 Episode
        ↓
P7 SOURCE_BIBLE
        ↓
P8 SOURCE_SHOT_FACTS
```

继续强制：

- ASR 直接读取完整 Episode 连续音轨；
- 禁止按 Shot / Reference Clip 分别 ASR 后拼句；
- OCR 读取完整视频时间轴；
- Shot Anchors 只做 OCR 采样提示和时间投影；
- P7 / P8 无权静默改写 canonical ASR / OCR；
- P8 dialogue text 必须逐字来自 CURRENT P6 canonical Evidence；
- 不进入 P9。

---

# 2. 本次真实验收暴露的问题

真实 Episode：`货到付款惩治隔壁大妈-第01集.mp4`，约 66 秒。

P8 rev1 程序一致性、P5 时间、P7 candidate binding、Artifact / provenance 均通过，但 P6 v1 出现：

```text
50 个 raw ASR segment
↓ 过度 canonical merge
8 条 canonical utterance
```

典型后果：

- 多个不同人物的连续发言被合成一条 canonical utterance；
- 游戏喊话、角色对白、旁白可能被串成同一条 canonical text；
- P8 因遵守“正文只认 P6”而把同一大段文字 overlap 到多个 Shot；
- 存在 `收电人 / 坠须 / 一树花` 等明显 ASR 错词，P8 不允许自行修正。

根因代码是 P6 v1 `_canonical_dialogue()`：只要相邻 raw segment 间隔不超过 500ms、累计不超过 20 秒、前文没有终止标点，就持续合并。该规则在缺少 Speaker identity 的 P6 阶段过于激进。

---

# 3. P6 v2 Canonical Dialogue Policy

正式 profile：

```text
p6-source-evidence-v2
```

正式 canonical policy：

```text
segment-preserving-dialogue-v2
```

原则：

> **宁可保守拆成更多 canonical utterance，也不能把没有明确连续证据的不同发言回合合成一条。**

raw ASR segment 默认保持为 canonical 边界。

只有同时满足以下条件才允许跨 raw segment 合并：

1. 时间间隔足够短；
2. 语言兼容；
3. 合并后持续时间在保守上限内；
4. 前一 segment 末尾存在明确“继续说”的标点，例如逗号、顿号、冒号、分号；
5. 前一 segment 不是句号 / 问号 / 感叹号 / 省略号等终止语气。

不得仅因“两个 segment 距离很近”就合并。

跨 Shot 的一句话仍允许是一条 canonical utterance，但依据必须来自 ASR 自身连续 segment / 明确继续标点，而不是 Shot Boundary。

---

# 4. ASR 质量基线

P6 仍使用 `faster-whisper`，但默认模型从早期开发档提升为更高质量档：

```text
large-v3-turbo
```

模型仍由 `AI_DRAMA_P6_ASR_MODEL` 可配置；实际 Provider profile 必须进入 Task fingerprint / Evidence provenance。

本次不使用针对单个样例的硬编码词表，不允许把 `收件人 / 赘婿 / 一束花` 等正确答案写死到代码。

如模型仍有错词，后续可研究可追溯的字幕辅助解码或 ASR Provider qualification，但 OCR / VLM 仍不得静默覆盖 canonical ASR。

---

# 5. Revision / STALE / 重跑

P6 v2 改变 canonical Evidence 语义，因此部署时旧链必须失效：

```text
旧 SourceEvidenceSet        → is_current = false
旧 SOURCE_DIALOGUE          → STALE
依赖旧 P6 的 SOURCE_BIBLE  → STALE
旧 Story / Rhythm           → STALE
旧 SOURCE_SHOT_FACTS        → STALE
受影响 ProjectExecutionPlan → STALE / current pointer cleared
```

历史 revision 必须保留，不删除。`SOURCE_VIDEO` 与 `SHOT_ANCHORS` 不因本迁移失效。

正确恢复链：

```text
重新真实运行 P6
→ 新 CURRENT SOURCE_DIALOGUE
→ P7 重跑
→ P8 重跑
→ 最终 28 镜音画人工验收
```

P6 页面上的“重新运行真实 ASR + OCR”必须是真正的显式重跑：同一轮重复提交继续去重；已有正式 Evidence revision 后再次显式运行必须生成新 Task / SourceEvidenceSet revision，不能复用历史 succeeded Task。

---

# 6. P8 边界

本次不修改 P8 Provider 去“纠正”P6 文本。

P8 继续：

```text
P5 → Shot time
P6 → dialogue / OCR canonical text
P7 → character / scene / prop candidate
完整 Episode → visual / camera / sound observation
```

P6 v2 重跑后，旧 P8 应因上游变化自动 STALE；新 P8 必须基于新 CURRENT P6 重新生成。

---

# 7. 自动验收

已完成回归覆盖：

- `你好，` + `世界。` 这类明确 continuation 仍可合并；
- 无终止标点但没有明确 continuation 的相邻发言不得因短 gap 被合并；
- 不同语言 segment 不合并；
- 显式 P6 rerun 产生新 Task / Evidence revision；
- P6 v2 Provider profile 记录高质量默认模型与连续 Episode 输入；
- 旧 P6 / P7 / P8 CURRENT 链由 `0012_p6_canonical_evidence_v2` 失效；
- 受影响 ProjectExecutionPlan 同步失效；
- 完整 backend / frontend CI 全绿。

工程完成基线（2026-09-09）：

```text
P6 profile          = p6-source-evidence-v2
canonical policy    = segment-preserving-dialogue-v2
default ASR model   = large-v3-turbo
migration head      = 0012_p6_canonical_evidence_v2
latest verified CI = V3 CI #292 PASS
```

工程通过只证明代码与迁移契约成立，**不等于真实短剧的 P6 v2 内容质量已经通过**。真实质量仍必须在本机同一 Episode 上重新执行和人工核对。

---

# 8. 最终人工验收门槛

本次整改完成后必须重新用同一真实短剧验收：

1. P6 canonical dialogue 不再把多轮不同发言压成超长一条；
2. 明显错词较 v1 有实质改善；
3. 合理跨 Shot 语句仍保持 canonical 一致性；
4. P7 SOURCE_BIBLE 在新 P6 上仍成立；
5. P8 28 Shot 的 dialogue / voiceover / offscreen binding 可用于后续制作；
6. 最终人工音画逐镜验收通过。

在以上验收通过前：

```text
SOURCE_DIALOGUE_EVIDENCE = AVAILABLE   （已有能力，但本次真实样例需 v2 质量复验）
SHOT_BREAKDOWN            = PLANNED
```

禁止进入 P9，禁止提前把 `SHOT_BREAKDOWN` 改为 `AVAILABLE`。
