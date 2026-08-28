---
name: ai-drama-studio-reference-video-v2
version: 3.7.0
description: AI Drama Studio Reference Video 驱动的本地短剧重制工作台开发规则；Character V10.1 为正式人物基线；Breakdown P1 + P2.1-P2.5 已实现，P2.6 real-video/local-model closure 下一步。
---

# AI Drama Studio — Reference Video V2 / Breakdown-first / Character V10.1

## 0. 恢复项目上下文

项目事实必须来自 GitHub 当前 `main`，不能只依赖旧聊天。

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/CURRENT_IMPLEMENTATION_MANIFEST.md
→ docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
→ docs/BREAKDOWN_DRAFT_DATA_CONTRACT.md
→ docs/BREAKDOWN_P2_SIDECAR_CONTRACT.md
→ docs/ASSET_CHARACTER_RECOGNITION_V10_1.md（涉及人物时）
→ current code/tests
→ latest docs/sessions/*.md handoff
```

事实纪律：

```text
PROJECT_STATE + CURRENT_IMPLEMENTATION_MANIFEST + code/tests
= CURRENT

BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN
= TARGET + phase order
```

旧 Feature/Frozen 文档或旧聊天与当前 wiring 冲突时，以当前代码和 CURRENT docs 为准。

## 1. 当前基线

```text
Architecture: Reference Video V2
FastAPI: 2.4.1
Default branch: main
Formal Character runtime: Character V10.1
Breakdown: P1 + P2.1-P2.5 COMPLETE
Next: P2.6 real-video / real-model / Windows-local runtime closure
```

正式用户工作区：

```text
01 剧集管理
02 拉片
03 资产
04 内容剧本
05 重制设计
06 生成 / 导出
```

核心产品原则：

```text
先看懂，再识别，再回填
```

## 2. Breakdown-first 当前已实现链

```text
Original Video
→ Preprocess
→ Shot Detection
→ ShotRevision / ShotRevisionItem
→ Reference Clip / thumbnail / keyframes
→ ASR / OCR / VLM
→ immutable raw Evidence sidecars
→ deterministic P2.5 Fusion
→ anonymous structured P1 Draft
→ P1 validator
→ READY / READY_WITH_WARNINGS BreakdownRun
```

当前正式 P1 Draft 实体已经存在并由 P2.5 自动填充：

```text
SceneSegmentDraft
ShotSemanticDraft
LocalSubject
ShotLocalSubject
TimelineEvent
TimelineEventSubject
DraftPropHint
DraftPropOccurrence
BreakdownEvidenceLink
```

这些是当前数据库正式实体，不再只是 Target 概念。

仍未实现：

```text
P2.6 real-video/model quality closure
P3 structured 02 拉片 UI
P4 Draft-guided Scene / Prop evidence
P5 Draft ↔ Character safe resolution
P6 Final fill-back / renderers
P7 downstream remake integration
```

## 3. Shot / Revision Contract

Shot 是核心生产单元，Reference Clip 是 Shot 一级正式资产。

正式时间：integer microseconds。

```text
BreakdownRun.source_shot_revision_id
→ exact ShotRevision

ShotSemanticDraft.source_shot_revision_item_id
→ exact historical ShotRevisionItem
```

`Shot.id` 不是跨 Revision 永久历史锚点。

Provider/Fusion 必须消费 Run 冻结的 exact historical input，禁止重新从 Current `v2_shots` 猜历史数据。

任何产生新 Current ShotRevision 的 edit/split/merge/auto-rerun/restore 都必须让旧 active Breakdown STALE。旧历史 Draft/Revision/Reference Clip 保留可读。

## 4. Evidence / Draft / Final Asset 分离

```text
P2 raw Evidence
→ immutable model facts/observations

P1 anonymous Draft
→ soft semantic interpretation/search prior

Character / Scene / Prop + Final Shot Bindings
→ editable Final truth
```

永远保持：

```text
LocalSubject != Character
SceneSegmentDraft != Scene
DraftPropHint != Prop
BreakdownEvidenceLink != Final Binding
```

P2 不允许直接创建：

```text
Character
Scene
Prop
AssetRevision
ShotCharacterBinding
ShotSceneBinding
ShotPropBinding
```

## 5. P2.1 raw Evidence sidecar

正式模块：

```text
engine/app/breakdown_p2_sidecar_v1.py
```

统一 Provider components：

```text
ASR / OCR / VLM
```

统一 Evidence types：

```text
ASR_SEGMENT
ASR_WORD
OCR_OBSERVATION
VLM_OUTPUT
FRAME
AUDIO_RANGE
RULE
```

Raw Evidence 保存为 fingerprinted immutable JSON：

```text
workspace/<project>/episodes/<episode>/breakdown/<run>/evidence/<component>/<sha256>.json
```

必须：

- JSON 可稳定序列化；
- Final Asset/Binding ID leakage 递归 fail closed；
- 写前/写后确认 Run + source revision 仍可写；
- Fusion 只消费已登记 sidecar，不隐式重跑 Provider。

## 6. P2.2 ASR baseline

```text
engine/app/breakdown_p2_asr_v1.py
faster-whisper==1.2.1
default model = large-v3
beam_size = 5
vad_filter = true
word_timestamps = true
```

正式输出：`ASR_SEGMENT + ASR_WORD`，Episode source integer microseconds。

Dialogue 可以跨 Shot，因此 raw ASR 不提前绑定单个 `ShotRevisionItem`。P2.5 才按 exact Shot boundaries 拆分；有 word timing 时优先用 word timing 重建每个 Shot 的文本/时间。

ASR 不直接写 `studio_v2.Dialogue`，不把 speaker label 绑定 Character。

## 7. P2.3 OCR baseline — 保持稳定

```text
engine/app/breakdown_p2_ocr_v1.py
rapidocr==3.9.2
PP-OCRv6 small
ONNX Runtime
default device = cpu
```

每条 OCR Observation：

```text
exact historical ShotRevisionItem
+ sampled frame source microseconds
+ text/confidence
+ polygon/bbox/normalized geometry
```

单帧 OCR 是 point observation，不是字幕 duration。重复文字保留 raw observations；P2.5 才做 stitching。

除非有明确 regression，**不要重新设计或重写 P2.3 OCR**。

## 8. P2.4 VLM baseline

正式实现：

```text
engine/app/breakdown_p2_vlm_v1.py
scripts/run_breakdown_vlm_qwen3.py
scripts/setup_breakdown_vlm_runtime.ps1
```

当前 baseline：

```text
provider = qwen3-vl
model = Qwen/Qwen3-VL-4B-Instruct
semantic schema = breakdown-p2-vlm-shot-semantics-v1
default device = cuda
video fps request = 2.0
```

VLM 只产匿名视觉语义：

```text
scene hints
shot summary / visual description / shot language hints
subject_A / subject_B appearance/activity/screen position/visibility
visual speaking_state hint
VISUAL / ACTION ratio events
plot-relevant prop hints
```

不让 VLM 重做 ASR/OCR transcription，不让它识别真实人物身份。

特别注意：

```text
transvlm_runtime_v51.py / HeyGenAI TransVLM checkpoint
= transition detection

P2.4 base Qwen3-VL checkpoint
= content semantics
```

只能复用隔离 Python/CUDA runtime，不能把转场微调权重当内容语义模型。

## 9. P2.5 Fusion baseline

正式模块：

```text
engine/app/breakdown_p2_fusion_v1.py
profile = breakdown-p2-fusion-v1
```

入口只消费已登记 immutable sidecars，并验证：

```text
file:// artifact
sha256 fingerprint
sidecar schema
run/project/episode/source revision/component
provider/model/status/evidence_count
current revision
```

组件门槛：

```text
VLM READY required
ASR/OCR NO_EVIDENCE or NOT_AVAILABLE → warning-degraded
FAILED / NOT_CONFIGURED → fail closed
```

Fusion 策略：

```text
Scene:
  only consecutive Shots
  merge only exact normalized location + interior/exterior + time-of-day signature

Shot:
  exactly one ShotSemanticDraft per source ShotRevisionItem

ASR:
  intersect exact Shot source ranges
  word timestamps preferred

OCR:
  stitch same text by Shot + time + geometry
  inferred duration cannot cross Shot

VLM events:
  start_ratio/end_ratio → exact Shot source microseconds

Props:
  DraftPropHint + per-Shot occurrence only

Provenance:
  EvidenceLink only for actually consumed raw Evidence
```

## 10. Anonymous LocalSubject cannot-link

`appearance_summary` 是弱连续性，不是身份 embedding。

允许：

```text
同一 Segment 内 exact normalized appearance
→ 保守跨 Shot reuse LocalSubject
```

禁止：

```text
同一个 Shot 中两个人 appearance 一样
→ 合并成一个 LocalSubject
```

正式 P2.5 规则：只要一个 appearance signature 在同一 Shot 同时出现 2+ 次，这个 appearance 在整个 Segment 内禁用跨 Shot merge；相关 occurrence 使用 shot-local key。

宁可匿名人物暂时拆多，也不要在语义层误合并。

## 11. Character V10.1 正式链

```text
Shot / Reference Clip
→ Person Instance / Person Evidence
→ YoutuReID primary identity signal
→ mature MOT for Shot-local temporal organization
→ project-level identity classification
→ RESOLVED / UNRESOLVED
→ independent Shot × known-Character Assignment
→ Final Character Gate
→ Character + ShotCharacterBinding
```

正式 profile：

```text
runtime: character-v10.1-capture-first-model-classification
asset: f05-assets-v10.1-person-evidence-model-classification
resolver: person-evidence-model-classifier-v10.1
shot assignment: v10.1-shot-character-assignment-1
```

新人硬门槛保持：

```text
>= 3 independent Shots
>= 3 model-usable Person Images
stable cross-Shot Person-ReID
unique winner
same-sample cannot-link satisfied
no high-quality Face hard conflict
```

Face 是 optional support / known presence / conflict，不是新人创建必需条件。

带 `shot_assignment_version` 的当前 V10.1 Run：

```text
ShotCharacterBinding = explicit shot_presence_assignments ONLY
```

显式空 assignment 不允许 fallback 到 Candidate Track membership。

P2.1–P2.5 不改变人物阈值、same-sample cannot-link、Face conflict、identity Gate、explicit assignment 或 Final Gate。

## 12. Scene / Prop / Speaker 后续边界

当前：

```text
SceneSegmentDraft + scene semantic hints
DraftPropHint + occurrences
```

不是 Final Scene/Prop。

P4 才做 Draft-guided Scene/Prop evidence；P5/P6 才做 resolution/fill-back。

未来 Speaker 也必须先是匿名音频 Evidence，再安全映射 LocalSubject/Character；禁止 speaker label 直接变 Character。

## 13. Run / batch / runtime

- 新 Run 完整成功后才能切 Current；
- failed Run 不替换旧 Current；
- READY AI Evidence/Draft 保留不可变历史；
- MANUAL / RESTORE revision 默认保护；
- `Episode.sort_order` 是批量顺序；
- GPU/重模型默认 sequential，`concurrency = 1`；
- Reference Clip 是正式资产；
- 正式时间统一 integer microseconds。

## 14. 测试 / 验收现实

不要声称整仓 CI 全绿。

P2.5 初始 hosted focused result：

```text
5 passed / 1 failed
```

唯一新增失败是同 Shot identical-appearance subjects 被误合并。已做窄范围 same-Shot cannot-link 修复，并完成本地纯逻辑验证。

用户已经明确：**GitHub Actions 没有额度，不要主动运行、重跑或依赖 hosted CI。**

因此：

- 不声称修复后有新的 hosted 6/6；
- 不为“看绿灯”消耗 GitHub quota；
- P2.6 以用户本地 Windows / real-model / real short-drama 验收为核心。

Contract/fake-provider tests 不能证明 Qwen3-VL / faster-whisper / PP-OCRv6 是真实短剧永久最佳组合。

## 15. Git / 文档规则

默认分支 `main`。修改前确认当前 SHA；遵守当前 GitHub 工具安全规则，避免覆盖别人更新。

当前用户要求避免触发 GitHub Actions。同步 `main` 时不要主动运行或重跑 hosted workflow。

正式流程/Contract 修改结束前检查：

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
docs/BREAKDOWN_P2_SIDECAR_CONTRACT.md
docs/BREAKDOWN_DRAFT_DATA_CONTRACT.md if schema semantics changed
docs/ASSET_CHARACTER_RECOGNITION_V10_1.md if Character changed
latest docs/sessions/*.md handoff
```

P2.5 没有修改 P1 schema，因此 `BREAKDOWN_DRAFT_DATA_CONTRACT.md` 保持冻结；其 P1-close 时写下的旧 P2 status 不应覆盖当前 `PROJECT_STATE`。

## 16. 下一步唯一安全阶段

```text
P2.6
→ real short-drama clips
→ actual faster-whisper / RapidOCR / Qwen3-VL
→ inspect fused anonymous Draft
→ ASR timing/error analysis
→ OCR subtitle/phone/sign analysis
→ VLM subject/action/scene/prop analysis
→ Fusion conflict/timing/provenance analysis
→ Windows/local GPU/CPU/cache/offline runtime closure
```

P2.6 完成前不跳到 P3，不开始 Final Asset resolution，不把匿名 Draft 当最终资产真值。