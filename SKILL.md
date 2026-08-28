---
name: ai-drama-studio-reference-video-v2
version: 3.8.1
description: AI Drama Studio Reference Video 驱动的本地短剧重制工作台开发规则；Character V10.1 为正式人物基线；P1/P2 实现验收条件通过，P2.6 Windows 真实模型验收未通过，需补 OCR 与 Qwen；P3 Structured Draft UI 已在 main，UI 验收进行中。
---

# AI Drama Studio — Reference Video V2 / Breakdown-first / Character V10.1

## 0. 恢复项目上下文

必须先读取 GitHub 当前仓库事实：

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/CURRENT_IMPLEMENTATION_MANIFEST.md
→ docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
→ docs/BREAKDOWN_DRAFT_DATA_CONTRACT.md
→ docs/BREAKDOWN_P2_SIDECAR_CONTRACT.md
→ docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md
→ docs/ASSET_CHARACTER_RECOGNITION_V10_1.md when Character is involved
→ current code/tests
→ latest docs/sessions/*.md handoff
```

Truth discipline:

```text
PROJECT_STATE + CURRENT_IMPLEMENTATION_MANIFEST + code/tests = CURRENT
BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN = accepted TARGET / phase order
```

Old Frozen/Feature docs or old chat do not override current wiring.

## 1. Current baseline

```text
Architecture: Reference Video V2
FastAPI: 2.4.1
Default branch: main
Formal Character runtime: Character V10.1
P1/P2 implementation acceptance: CONDITIONAL PASS
P2.6 Windows / real-model acceptance: NOT PASSED
P3 Structured 02 拉片 UI: IMPLEMENTED ON MAIN / UI ACCEPTANCE IN PROGRESS
```

Formal user workspaces:

```text
01 剧集管理
02 拉片
03 资产
04 内容剧本
05 重制设计
06 生成 / 导出
```

Core product principle:

> **先看懂，再识别，再回填。**

## 2. Breakdown-first product flow

```text
Original Video
→ Preprocess
→ Shot Detection
→ Shot + Reference Clip
→ ASR / OCR / VLM
→ anonymous structured Breakdown Draft
→ Draft-guided Character / Scene / Prop evidence
→ Global Asset Resolution + Final Shot Bindings
→ identity/asset fill-back
→ Final Breakdown
→ remake
```

Anonymous Draft semantics are not Final truth:

```text
LocalSubject / 人物A != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
```

## 3. Reference Video V2 invariants

Keep:

```text
FFprobe authoritative media facts
FFmpeg preprocess/proxy/audio
integer microseconds
TransNetV2 Shot boundaries
ShotRevision / ShotRevisionItem history
per-Shot Reference Clip / thumbnail / keyframes
manual edit / split / merge / rerun / restore
```

Historical Breakdown always anchors to exact frozen ShotRevision/ShotRevisionItem.

## 4. P1 Draft contract

Formal entities:

```text
BreakdownRun
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

Lifecycle:

```text
PROCESSING / READY / READY_WITH_WARNINGS / FAILED / STALE
```

P1 validator remains mandatory. P1 is included in the current **implementation CONDITIONAL PASS**; that does not certify model quality.

## 5. P2 formal production chain

Formal orchestrator:

```text
engine/app/breakdown_p2_pipeline_v1.py
profile = breakdown-p2-full-v1
```

Execution:

```text
create frozen PROCESSING BreakdownRun
→ ASR
→ OCR
→ VLM
→ immutable sidecars
→ deterministic Fusion
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Formal components:

```text
P2.1 engine/app/breakdown_p2_sidecar_v1.py
P2.2 engine/app/breakdown_p2_asr_v1.py
P2.3 engine/app/breakdown_p2_ocr_v1.py
P2.4 engine/app/breakdown_p2_vlm_v1.py
P2.5 engine/app/breakdown_p2_fusion_v1.py
P2.6 engine/app/breakdown_p2_pipeline_v1.py
P2.6 engine/app/breakdown_p2_acceptance_v1.py
```

## 6. ASR / OCR / VLM responsibilities

### ASR

```text
FasterWhisperASRProvider
faster-whisper==1.2.1
large-v3
word timestamps
```

Speaker labels never directly create/map Character.

### OCR

```text
RapidOCROCRProvider
rapidocr==3.9.2
PP-OCRv6 small
ONNX Runtime
```

Current implementation remains the baseline. The current P2.6 acceptance blocker is **missing/incomplete OCR runtime/model provisioning**, not a reason to redesign the OCR contract.

### VLM

```text
Qwen3VLSemanticProvider
Qwen/Qwen3-VL-4B-Instruct
strict anonymous shot semantics
```

Current implementation remains the baseline. The current P2.6 acceptance blocker is **missing/incomplete Qwen3-VL model/runtime provisioning**.

## 7. Fusion rules

Fusion consumes registered immutable ASR/OCR/VLM sidecars and never implicitly reruns Providers.

Same-Shot anonymous cannot-link remains mandatory: if one normalized appearance is used by multiple simultaneous subjects, it cannot be used as a cross-Shot merge key in that Scene Segment.

## 8. Background tasks / batch

Formal APIs:

```text
POST /api/episodes/{episode_id}/tasks/breakdown
POST /api/projects/{project_id}/tasks/breakdown-batch
GET  /api/breakdown/p2/runtime-preflight
POST /api/breakdown-runs/{run_id}/p2-acceptance
```

Batch must follow `Episode.sort_order` and heavy P2 execution remains globally serialized.

## 9. P2.6 runtime / acceptance

Current status:

```text
P1/P2 implementation acceptance = CONDITIONAL PASS
P2.6 Windows / real-model acceptance = NOT PASSED
```

Before retrying final acceptance:

```text
1. complete OCR runtime/model provisioning
2. complete Qwen3-VL model/runtime provisioning
3. run strict preflight
4. run a real short-drama Episode through ASR → OCR → VLM → Fusion → P1 validator
5. generate acceptance report
6. complete human review
```

Formal states:

```text
STRUCTURAL_FAIL
NEEDS_HUMAN_REVIEW
NEEDS_TUNING
PASS
```

`PASS` requires structural success + all required human scores >=4/5 + no blocking issue. Machine checks cannot award PASS on their own.

Until then, never write `P2 ACCEPTED`, `P2 CLOSED`, `P2.6 PASS`, or equivalent quality claims.

## 10. Character V10.1 protected baseline

Formal chain:

```text
YOLOX Person Detection
→ capture-first Person Evidence
→ mature MOT
→ YoutuReID project-level identity
→ RESOLVED / UNRESOLVED
→ explicit Shot × known-Character Assignment
→ Final Character Gate
```

Hard invariants:

```text
new identity >=3 independent Shots
new identity >=3 model-usable images
same-sample cannot-link
high-quality Face hard conflict
ambiguous winner stays unresolved/unassigned
current Final ShotCharacterBinding = explicit shot_presence_assignments
```

Draft semantic context cannot override these rules.

## 11. P3 current UI

P3 is no longer `NEXT`.

Current main contains:

```text
02 拉片
├─ 镜头边界
│  ├─ ShotCacheManagerV51
│  └─ ShotWorkbenchV4
└─ Structured Draft
   ├─ P2 single/batch task controls
   ├─ Run history / STALE state
   ├─ SceneSegmentDraft / ShotSemanticDraft
   ├─ anonymous subjects
   ├─ dialogue/action/OCR timeline
   ├─ prop hints
   ├─ exact historical Reference Clip
   └─ Evidence provenance
```

P3 implementation is on `main`; browser/UI acceptance is still in progress. The Shot Boundary overflow issue was fixed in main merge commit `1cb8624b885850935e902cb6c9ac2273c490d2b3`.

## 12. P2 forbidden writes

P2 cannot create/update Final Character/Scene/Prop assets or Final Shot bindings. VLM/ASR/OCR cannot write Final identity truth.

## 13. Testing / CI discipline

User does not want hosted GitHub Actions quota consumed. Use `[skip ci]` for current remote development/documentation commits and prefer local verification. Historical CI results must remain historical.

## 14. Phase pointer

```text
P0 COMPLETE
P1 implementation CONDITIONAL PASS
P2 implementation CONDITIONAL PASS
P2.6 Windows / real-model acceptance NOT PASSED
P3 Structured 02 拉片 UI IMPLEMENTED / UI ACCEPTANCE IN PROGRESS
P4 Draft-guided Scene/Prop PLANNED
P5 Draft ↔ Character safe integration PLANNED
P6 Final fill-back/renderers PLANNED
P7 downstream remake integration PLANNED
```

Immediate safe work:

```text
A. provision OCR + Qwen and rerun P2.6 real short-drama acceptance
B. continue P3 browser/UI acceptance
```

Do not upgrade acceptance status without evidence.
