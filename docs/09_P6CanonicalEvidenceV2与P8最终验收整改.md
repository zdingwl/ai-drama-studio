# P6 Canonical Evidence v2 与 P8 最终验收整改

> 日期：2026-09-09  
> 状态：工程实现完成；真实 P6 v2 → P7 → P8 恢复链已通过；最终 28 镜音画人工验收待执行  
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

工程通过只证明代码与迁移契约成立，不等于真实短剧的内容质量已经通过；真实恢复链结果见下一节。

---

# 8. 最终人工验收门槛

本次整改完成后必须重新用同一真实短剧验收：

1. P6 canonical dialogue 不再把多轮不同发言压成超长一条；
2. 明显错词较 v1 有实质改善；
3. 合理跨 Shot 语句仍保持 canonical 一致性；
4. P7 SOURCE_BIBLE 在新 P6 上仍成立；
5. P8 28 Shot 的 dialogue / voiceover / offscreen binding 可用于后续制作；
6. 最终人工音画逐镜验收通过。

前 1–5 项已在 2026-09-09 真实恢复链中完成程序与内容复核；第 6 项仍待用户逐镜播放原片 / Reference Clip 完成。

在最终音画人工验收通过前：

```text
SOURCE_DIALOGUE_EVIDENCE = AVAILABLE
SHOT_BREAKDOWN            = PLANNED
```

禁止进入 P9，禁止提前把 `SHOT_BREAKDOWN` 改为 `AVAILABLE`。

---

# 9. 2026-09-09 真实恢复链结果

真实项目：

```text
project_id = 99f7036f-cce8-4700-a717-683278107866
Episode    = 货到付款惩治隔壁大妈-第01集.mp4
时长       = 66.36 秒
Shot       = 28
Migration  = 0012_p6_canonical_evidence_v2
```

迁移后旧链正确失效：

- `SOURCE_VIDEO rev1` / `SHOT_ANCHORS rev1` 保持 CURRENT；
- 旧 `SourceEvidenceSet rev1` 不再 current；
- `SOURCE_DIALOGUE rev1` STALE；
- `SOURCE_BIBLE / STORY_SKELETON / RHYTHM_SKELETON rev1–3` STALE；
- `SOURCE_SHOT_FACTS rev1` STALE；
- Project current plan 清空。

恢复完成后的 CURRENT：

```text
SOURCE_DIALOGUE rev2
SOURCE_BIBLE rev4
STORY_SKELETON rev4
RHYTHM_SKELETON rev4
SOURCE_SHOT_FACTS rev2
```

## 9.1 P6 v2

真实 P6 结果：

```text
Raw ASR              = 56
Canonical dialogue   = 56
Canonical OCR        = 73
ASR model            = large-v3-turbo
Evidence profile     = p6-source-evidence-v2
Canonical policy     = segment-preserving-dialogue-v2
timeline_source      = FULL_EPISODE
```

与旧 v1 相比：

```text
v1: 50 raw → 8 canonical
v2: 56 raw → 56 canonical
```

真实复核确认：

- 00:00–00:15 多轮争执不再串成长 utterance；
- 00:15–00:22 要钱、报数、辱骂、报警回应已分离；
- 00:22–00:43 游戏喊话、徐然叙述、周宇回应已分离；
- 最长 canonical 约 1.82 秒；
- 不再存在约 20 秒的多人 canonical utterance；
- P8 对话 overlap 已基于短 canonical utterance 正常工作。

ASR 质量较 v1 有实质改善：

- `这花就在走了` → `这花就在走廊`；
- `一树花` → `一束花`；
- `收电人` → 当前仍为 `收店人`，同时间 OCR 明确为 `收件人`；
- `临包入住的坠须` → 当前为 `我拿拎包入住的坠绪`，同时间 OCR 为 `我那拎包入住的赘婿`。

片尾另有两条极短重复 ASR：

```text
66.020–66.040  你还真去报警啊
66.040–66.220  你还真去报警啊
```

当前定级：

- MEDIUM：两处明显 ASR 错词，最终人工音画验收必须确认；
- LOW：片尾两条极短重复 ASR，需人工确认是否为有效对白；
- BLOCKER / HIGH：未发现。

这些残余问题不得由 P7 / P8 静默改写 canonical text，也不得通过真实样例硬编码词表修正。

## 9.2 P7 恢复

真实 P7 已基于新 P6 rev2 重跑：

```text
SOURCE_BIBLE rev4      CURRENT
STORY_SKELETON rev4    CURRENT
RHYTHM_SKELETON rev4   CURRENT
Provider               Doubao Seed 2.1 Pro / Volcengine Ark
```

P7 provenance 正确引用 CURRENT：

- `SOURCE_VIDEO rev1`；
- `SOURCE_DIALOGUE rev2`；
- `SHOT_ANCHORS rev1`；
- `SourceEvidenceSet rev2`。

故事、人物、关系、场景、道具以及 Story / Rhythm 在新 Evidence 上仍成立。

## 9.3 P8 恢复

真实 P8 已基于新 CURRENT 上游重跑：

```text
SOURCE_SHOT_FACTS rev2 CURRENT
旧 rev1                STALE
```

程序一致性结果：

- 28/28 Shot 集合、编号、`shot_anchor_id` 完整；
- 28/28 start / end / duration 与 P5 完全一致；
- 28/28 dialogue overlap 集合一致；
- dialogue text 与 P6 v2 canonical 逐字一致；
- OCR evidence ID 全部属于 CURRENT P6；
- character / scene / prop 全部属于 SOURCE_BIBLE rev4；
- 越界 candidate = 0；
- 引用 STALE 上游 = 0；
- Task / Artifact fingerprint 一致；
- provenance / ProviderJob / Artifact Graph / SUPERSEDES 完整；
- orphan revision / relation = 0；
- 同类型多个 CURRENT = 0。

完整工程测试也再次通过：backend 104 tests、frontend 11 files / 38 tests、typecheck、production build 均 PASS。

因此恢复链当前判定：

```text
P6 v2 真实恢复与分段整改      PASS
P7 新 CURRENT 恢复            PASS
P8 工程验收                   PASS
P8 真实数据库一致性            PASS
P8 真实 Provider 执行          PASS
P8 最终用户逐镜音画人工验收     PENDING

SHOT_BREAKDOWN = PLANNED
P9             = 禁止进入
```

下一步只做最终 28 Shot 音画人工验收；在用户签字前不再扩大工程范围。
