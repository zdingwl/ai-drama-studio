# P6 人工对白裁决与 Canonical 可编辑

> 日期：2026-09-10  
> 状态：contract amendment，已实现并进入当前 P6 基线  
> 优先级：高于 `docs/11_P6字幕证据裁决与P8台词一致性整改.md` 中“只展示自动裁决结果”的产品限制；不改变 P6 v4 自动裁决规则。  
> 范围：P6 Source Evidence 的人工确认 / 选择 / 修改；不承担 P9 identity resolution。

---

# 1. 触发需求

P6 v4 已能把严格满足条件的 OCR 字幕 near-match 自动裁决为 canonical dialogue，并在验收 UI 同时展示：

```text
字幕校正
canonical text
ASR 原文
OCR span
```

真实人工验收进一步要求：这些自动结果不能只能“看”，还应允许用户自己确认、选择或修改。

---

# 2. 权威边界不变

继续保持：

```text
完整 Episode                         = Source Truth
raw ASR / raw OCR                    = 不可删除的机器 Evidence
SourceDialogueUtterance.text         = 下游唯一 canonical dialogue 正文
P7 / P8                              = P6 canonical Evidence 消费者
```

新增的是 **显式 Human Adjudication**：用户可以基于同一条 canonical utterance 的 ASR 原文、时间重叠 OCR span，或人工输入文字，发布一个新的 P6 canonical Evidence revision。

人工修改不是 raw Evidence，也不能覆盖 / 删除 raw ASR 或 raw OCR。

---

# 3. 用户可选择的三种来源

每条 canonical dialogue 在 P6 验收区都允许进入“人工确认 / 修改”：

```text
1. 使用 ASR 原文
2. 使用时间重叠的 OCR span
3. 自定义文本
```

其中：

- OCR 选择只允许引用当前 SourceEvidenceSet 中与该 utterance 时间真实重叠的 OCR canonical span；
- 自定义文本必须由用户显式输入并保存；
- 不允许 P7 / P8 / VLM 生成文本进入这个选择器；
- 不允许 GET 或页面刷新自动改变 canonical；
- 不允许静默保存。

---

# 4. Revision / Provenance

每次保存人工裁决必须：

```text
显式 POST Command
→ 新 SourceEvidenceSet revision
→ 新 SOURCE_DIALOGUE Artifact revision（项目 Episode 已完整时）
→ 旧 SOURCE_DIALOGUE 及其 P7/P8 下游递归 STALE
```

历史 revision 保留。

raw ASR / OCR 复制到新 Evidence Set 时正文、时间、置信度保持不变；只允许在 provenance 增加人工裁决审计信息。

人工裁决 provenance 至少记录：

```text
manual_adjudication_policy = human-dialogue-adjudication-v1
manual_choice = ASR | OCR | CUSTOM
manual_parent_evidence_set_id
manual_parent_utterance_id
manual_parent_canonical_text
manual_original_asr_text
manual_selected_ocr_span_numbers[]
manual_canonical_text
```

read contract 的 `text_source` 允许：

```text
ASR
OCR_SUBTITLE_ADJUDICATED
USER_ASR_SELECTED
USER_OCR_SELECTED
USER_EDITED
```

---

# 5. 并发与 Fail-closed

人工保存必须带 `expected_revision`。

若用户打开编辑器后 P6 已被另一轮 P6 / 人工修改更新，则：

```text
expected_revision != CURRENT SourceEvidenceSet.revision
→ 409 fail-closed
→ 用户刷新后重新选择
```

同时必须拒绝：

- utterance 不属于 CURRENT Evidence Set；
- OCR span 不属于 CURRENT Evidence Set；
- OCR span 与 utterance 时间不重叠；
- 自定义文本为空或超长；
- Source Video 已变化；
- 任何 P7/P8 内容反向写入 P6。

---

# 6. UI

P6 每条对白增加“人工确认 / 修改”入口。

展开后展示：

```text
当前 canonical
ASR 原文
时间重叠 OCR 候选（span / confidence / text）
自定义输入
取消
保存为新 revision
```

自动 OCR 裁决仍显示“字幕校正”；人工结果显示“人工确认”并明确标注来源。

保存后刷新到新 revision，并提示：P7 / P8 已因 P6 canonical 改变而 STALE，需要按正式链路重新运行。

---

# 7. P8 行为不变

P8 不增加编辑能力，也不增加 dialogue rewrite schema。

```text
CURRENT P6 SourceDialogueUtterance.text
→ P8 原样绑定
```

因此人工确认后的 canonical 会自然进入下一次 P7 / P8 重跑；P8 仍无权自行修改。

---

# 8. 自动测试最低覆盖

至少证明：

- 用户可选择 ASR 原文并生成新 P6 revision；
- 用户可选择时间重叠 OCR span并生成新 revision；
- 用户可输入自定义文本并生成新 revision；
- raw ASR / OCR 正文不变；
- provenance 记录人工选择；
- stale `expected_revision` 返回 409；
- 非重叠 / 非本 Evidence Set OCR span fail closed；
- 旧 SOURCE_DIALOGUE / SOURCE_BIBLE / SOURCE_SHOT_FACTS 正确 STALE；
- GET 仍只读；
- 前端选择器可取消，只有显式保存才 POST。

---

# 9. 当前门禁

P6 自动基线仍是：

```text
p6-source-evidence-v4
segment-preserving-dialogue-v4
ocr-subtitle-near-match-v1
```

人工增量契约：

```text
human-dialogue-adjudication-v1
```

P8 最终人工验收已于 2026-09-10 完成，最新状态以 `docs/13_P8最终验收与P9准入.md` 为准：

```text
SHOT_BREAKDOWN = AVAILABLE
P9 = 可以开始
```

本功能仍不承担 P9 identity / scene / prop resolution；P9 必须按 `docs/13` 重新设计新的 Professional Skill、typed schema 和验收门禁。
