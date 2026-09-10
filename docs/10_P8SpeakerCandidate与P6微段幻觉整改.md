# P8 Speaker Candidate 与 P6 微段幻觉整改

> 日期：2026-09-10  
> 状态：整改决策已确认，工程实现与真实恢复验收进行中  
> 优先级：高于 `docs/09_P6CanonicalEvidenceV2与P8最终验收整改.md` 中与本次内容冲突的历史状态描述。

---

# 1. 触发问题

P8 最终 28 Shot 人工音画验收中，Shot #028（约 65.360–66.360）出现两条：

```text
说话人未确认
你还真去报警啊

说话人未确认
你还真去报警啊
```

而较早的 Shot #026 中，同样文本的正常对白已经由 P8 speaker candidate 标成 `周宇`。

结合 `docs/09` 已记录的真实 P6 v2 residual，可以确认 Shot #028 的两条不是“同一个 canonical utterance 跨 Shot 投影后 speaker 丢失”，而是 P6 v2 在片尾留下的两个独立 raw/canonical ASR segment：

```text
66.020–66.040  你还真去报警啊
66.040–66.220  你还真去报警啊
```

它们只有约 20ms / 180ms，却包含完整一句中文，时间密度本身已不具备可信的可说出性，因此不能为了让 UI 看起来完整，就把 Shot #026 的 `周宇` 按“相同文本”复制给它们。

---

# 2. 不允许的修法

本次明确禁止：

- 不允许 P8 用“文本相同”作为确定性 speaker 继承规则；
- 不允许把 Shot #026 的 speaker candidate 直接复制到 Shot #028；
- 不允许 P7/P8 删除、改写或纠正 P6 canonical text；
- 不允许写 `你还真去报警啊`、66 秒片尾或本真实样例专用硬编码；
- 不允许用 OCR / VLM 静默覆盖 ASR；
- 不进入 P9，不创建 SourceSpeaker，不做声纹或最终身份归一。

原因：不同人物完全可能在同一 Episode 中说出相同文本。P8 speaker candidate 必须仍然属于具体 canonical utterance，而不是属于一段字符串。

---

# 3. P8 Speaker Candidate 当前正式边界

P8 当前 speaker contract：

```text
shot-breakdown@1.1.0
p8-shot-breakdown-v2
SOURCE_SHOT_FACTS schema 1.1
source-bible-shot-facts-v2
```

规则：

- Provider 对本 Episode 每条 P6 canonical utterance 输出一次 `speaker_character_id`；
- candidate 只能来自 CURRENT P7 SOURCE_BIBLE characters；
- 无法可靠判断允许 `null`；
- 同一 `utterance_number` 跨多个 Shot 时，服务端注入同一个 speaker candidate；
- speaker 只是 P8 provisional candidate hint，不是 P9 Speaker Truth。

因此，Shot #028 的问题不应继续在 P8 speaker binding 层修。

---

# 4. P6 Canonical Evidence v3：微段重复幻觉防线

本次把 P6 canonical policy 升级为：

```text
P6 profile       = p6-source-evidence-v3
canonical policy = segment-preserving-dialogue-v3
```

v2 的“默认保留 raw segment 边界、仅明确 continuation 才合并”原则完全保留。

v3 只新增一条通用 canonical admission guard：

> **相邻 ASR segment 若 normalized text 完全相同，并且其中存在与文本信息量相比持续时间物理上不可信的 micro segment，则不可信 micro segment 不得进入 canonical SourceDialogueUtterance；若相邻两个重复 segment 都不可信，则两者都只保留为 raw ASR Evidence，不物化为 canonical dialogue。**

实现必须满足：

1. 只根据 ASR 自己的 `start_us / end_us / text` 做通用判断；
2. 必须同时要求“相邻近距离 + normalized text 完全相同 + micro duration 不可信”，不能只凭短时长删除；
3. 短促的单字 / 双字感叹、真实快速对白不能因为单独很短就被过滤；
4. raw `AsrEvidenceSegment` 永远保留，provenance 标记该 segment 是否进入 canonical；
5. canonical filter 不产生新文本、不使用 OCR 文本、不使用 P7/P8 semantic text；
6. 被过滤的 raw segment 不产生 `SourceDialogueUtterance`，自然也不产生 Shot projection / P8 dialogue binding。

这条规则解决的是“ASR 原始输出存在明显不可能成立的重复微段”这一类通用质量问题，不是针对本样例的词表纠错。

---

# 5. Revision / STALE

P6 canonical admission 语义改变后，旧结果不能继续冒充 CURRENT。

新增 migration：

```text
0014_p6_microduplicate_guard_v3
```

部署时：

```text
SOURCE_VIDEO          保持 CURRENT
SHOT_ANCHORS          保持 CURRENT
旧 SourceEvidenceSet  is_current = false
旧 SOURCE_DIALOGUE    STALE
旧 SOURCE_BIBLE       STALE
旧 STORY_SKELETON     STALE
旧 RHYTHM_SKELETON    STALE
旧 SOURCE_SHOT_FACTS  STALE
受影响 current plan   失效
```

历史 revision 保留，不删除。

正确恢复顺序只能是：

```text
P6 真实连续 ASR + OCR 重跑
→ P7 基于新 CURRENT P6 重跑
→ P8 基于新 CURRENT P6/P7 重跑
→ 继续 28 Shot 人工验收
```

不能为了省一次 P7 Provider 调用，让旧 P7 provenance 跨越新的 P6 canonical revision 继续 CURRENT。

---

# 6. 自动回归门槛

至少新增以下测试：

- 正常短 segment 不因为“短”本身被删除；
- 合理重复短词不因文本重复本身被删除；
- 一个可信 segment 后跟同文案不可信 micro duplicate：只过滤 micro duplicate；
- 两个相邻、同文案、都不可信的 micro duplicate：canonical 两条都过滤；
- raw ASR count 仍包含被过滤 segment；
- canonical dialogue count 不包含被过滤 segment；
- `canonical_included` provenance 可审计；
- P6 profile / canonical policy 已进入 v3 fingerprint / Artifact metadata；
- migration 0014 正确使旧 P6/P7/P8 与 Plan 失效，但不影响 SOURCE_VIDEO / SHOT_ANCHORS；
- P8 speaker v2 仍不得按相同文本强制复制 candidate。

---

# 7. 本轮人工验收目标

真实恢复后，Shot #028 的期望不是：

```text
周宇  对白  你还真去报警啊
周宇  对白  你还真去报警啊
```

而是：

```text
这两个不可信片尾 micro ASR 不再成为 canonical dialogue
→ Shot #028 不再显示这两条伪对白
```

Shot #026 的正常 canonical utterance 仍可由 P8 显示：

```text
周宇  对白  你还真去报警啊
```

最终仍需以完整 Episode 实际音画确认。

在本轮真实恢复与 28 Shot 人工验收完成前：

```text
SHOT_BREAKDOWN = PLANNED
禁止进入 P9
```
