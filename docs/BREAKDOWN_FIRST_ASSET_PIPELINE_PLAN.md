# AI Drama Studio — 拉片先行 / Breakdown-first 资产识别改造地图

> **Status:** ACCEPTED TARGET PLAN / **P1-P2 IMPLEMENTATION CONDITIONAL PASS** / **P2.6 REAL-MODEL ACCEPTANCE NOT PASSED** / **P3 IMPLEMENTED, UI ACCEPTANCE IN PROGRESS** / **P4 IMPLEMENTED, LOCAL ACCEPTANCE PENDING**  
> **Created:** 2026-08-27  
> **Last synchronized:** 2026-08-28 16:03 +08:00  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Current executable baseline:** Reference Video V2 / FastAPI 2.4.1 / Character V10.1 / Breakdown P1 + P2 + P3 + P4 backend

## 0. 产品定义

“拉片”不等于“切镜头”。镜头切分只是准备，目标是把原视频变成可追溯、可编辑、可用于重制的结构化视听 Draft：

```text
场景段
人物A / 人物B
镜头内容
动作
对白
OCR 文字
关键道具 hint
镜头语言
时间轴
Evidence provenance
```

第一遍 AI 拉片不假装知道全剧真实身份，因此先使用匿名主体。

核心原则：

> **先看懂，再识别，再回填。**

## 1. 目标主线

```text
原视频
↓
视频预处理
↓
Shot Detection
↓
Shot + Reference Clip + ShotRevision history
↓
ASR / OCR / VLM 看懂内容
↓
匿名结构化 Breakdown Draft
↓
Draft 指导 Character / Scene / Prop Evidence 搜索
↓
专用视觉/音频 Evidence 验证
↓
跨 Shot / 全项目资产归并
↓
Character / Scene / Prop + Final Shot Bindings
↓
真实资产身份回填 Draft
↓
Final Breakdown
↓
重制设计 / 视频生成
```

## 2. 不可破坏的架构原则

### 2.1 Reference Video V2 保留

```text
Project / Episode
FFmpeg / FFprobe
integer microseconds
TransNetV2 Shot boundaries
ShotRevision / ShotRevisionItem
Reference Clip / thumbnail / keyframes
```

Historical Breakdown must anchor to exact ShotRevision/ShotRevisionItem, not guessed Current Shot IDs.

### 2.2 Draft != Final identity/asset truth

```text
人物A / subject_A / LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
```

Draft is a soft semantic prior/search hint. Reliable measurable Evidence and later fail-closed resolution decide Final assets.

### 2.3 Character V10.1 hard gates remain authoritative

P2/P3/P4/P5 may not relax Character V10.1 identity gates, bypass same-sample cannot-link, ignore Face hard conflicts, let VLM/ASR create Character, or write Final Character binding from Draft prose.

### 2.4 Raw Evidence and Draft are separate

P2 Provider outputs remain immutable sidecars; Fusion must not erase raw evidence. Draft owners link only to evidence actually consumed. P4 consumes Draft read-only and writes only into the existing asset-side Candidate/Evidence layer.

### 2.5 Heavy jobs are sequential

Batch video/model work follows `Episode.sort_order` with `concurrency = 1` unless a later dedicated scheduler changes this with measured resource controls.

## 3. Current implementation map

| Area | Current | Next |
|---|---|---|
| Project/Episode | IMPLEMENTED | keep |
| FFmpeg/FFprobe preprocess | IMPLEMENTED | keep |
| Shot/Reference Clip | IMPLEMENTED | keep |
| ShotRevision/manual edit/history | IMPLEMENTED | keep |
| P1 anonymous Draft storage/lifecycle | CONDITIONAL PASS | keep |
| P2 raw Evidence sidecar | CONDITIONAL PASS | real-video verify |
| P2 ASR | IMPLEMENTED | real-video verify/tune only if needed |
| P2 OCR | IMPLEMENTED + Windows diagnostics | real-video verify |
| P2 VLM | IMPLEMENTED + Chinese Draft source policy | real-video verify |
| P2 Fusion | IMPLEMENTED | real-video verify |
| P2 full production orchestrator | IMPLEMENTED | real-video verify |
| P2 acceptance reports | IMPLEMENTED | produce real PASS report |
| 02 拉片 Structured Draft UI | IMPLEMENTED | finish browser/UI acceptance |
| Draft-guided Scene/Prop evidence | IMPLEMENTED P4 | local/model acceptance |
| Draft ↔ Character safe mapping | NOT IMPLEMENTED | P5 |
| Final fill-back/renderers | NOT IMPLEMENTED | P6 |
| downstream remake integration | PARTIAL/PLANNED | P7 |

## 4. P1 / P2 implementation acceptance

Current user review result:

```text
P1/P2 implementation acceptance = CONDITIONAL PASS
```

Meaning:

- data contracts, lifecycle, persistence and provenance direction are accepted;
- P2 Provider/Fusion/orchestration implementation is accepted conditionally;
- downstream phases may consume these contracts/APIs;
- this result is **not** a real-model quality PASS.

## 5. P2 formal implementation

### P2.1 raw Evidence sidecar

```text
PROCESSING BreakdownRun
→ exact source ShotRevision / ShotRevisionItems
→ Provider Contract
→ validated raw Evidence
→ fingerprinted immutable sidecar
→ provenance
```

### P2.2 ASR

```text
faster-whisper==1.2.1
large-v3
word timestamps
ASR_SEGMENT + ASR_WORD
Episode source integer microseconds
```

### P2.3 OCR

```text
rapidocr==3.9.2
PP-OCRv6 small
ONNX Runtime
multi-frame historical Reference Clip sampling
OCR_OBSERVATION + geometry + source point time
```

### P2.4 VLM

```text
Qwen/Qwen3-VL-4B-Instruct
exact historical Reference Clip
strict anonymous shot-semantic JSON
prompt_profile = breakdown-p2-vlm-zh-draft-v1
Draft natural-language output = Simplified Chinese
ASR/OCR raw source text = preserved
```

The production language gate fails closed when high-value VLM prose clearly ignores the Simplified-Chinese Draft policy.

### P2.5 Fusion

```text
immutable sidecar validation
→ ASR exact cross-Shot split
→ OCR stitch/dedupe
→ VLM ratio → source-us
→ SceneSegmentDraft
→ ShotSemanticDraft full coverage
→ LocalSubject / ShotLocalSubject
→ TimelineEvent
→ DraftPropHint / occurrences
→ precise EvidenceLink
→ P1 validator/publish
```

### P2.6 production + local acceptance tooling

Formal production profile:

```text
breakdown-p2-full-v1
ASR → OCR → VLM → Fusion → P1 validator
```

Background APIs:

```text
POST /api/episodes/{episode_id}/tasks/breakdown
POST /api/projects/{project_id}/tasks/breakdown-batch
GET  /api/breakdown/p2/runtime-preflight
POST /api/breakdown-runs/{run_id}/p2-acceptance
```

## 6. P2.6 real-model acceptance status

Current authoritative result remains:

```text
P2.6 Windows / real-model acceptance = NOT PASSED
```

Compatibility/provisioning code is not equivalent to a quality PASS. Required retest:

```text
strict preflight
+ real short-drama Episode
+ ASR → OCR → VLM → Fusion → P1 validator
+ acceptance report
+ human review required scores >= 4/5
+ no blocking issues
= P2.6 PASS
```

Until that evidence exists, forbidden wording includes `P2 ACCEPTED / P2 CLOSED / P2.6 PASS`.

## 7. P3 — implemented, UI acceptance in progress

Current workbench provides:

```text
Scene Segment
Shot + exact historical Reference Clip
人物A/B anonymous subjects
Timeline dialogue/action/OCR/visual/audio
scene/prop hints
Evidence provenance
Run history / STALE state
single/batch AI Breakdown task controls
```

It calls the formal P2 endpoints and does not duplicate Provider/Fusion logic in the frontend.

Status:

```text
P3 implementation = IMPLEMENTED
P3 browser/UI acceptance = IN PROGRESS
P3 accepted/closed = NO
```

## 8. P4 — Draft-guided Scene / Prop Evidence implemented

### P4.1 current-Draft guidance adapter

```text
engine/app/breakdown_asset_guidance_v1.py
profile = breakdown-asset-guidance-p4-v1
```

Only revision-safe current Draft is consumable:

```text
BreakdownRun.is_current = true
status = READY / READY_WITH_WARNINGS
BreakdownRun.source_shot_revision_id == current ShotRevision.id
ShotSemanticDraft -> exact ShotRevisionItem in that revision
Shot snapshot id == RevisionItem.original_shot_id
current Shot still exists
```

Forbidden fallback:

```text
STALE R2/R3 -> current Shot by ordinal        forbidden
history -> current Shot by nearest timestamp  forbidden
FAILED/PROCESSING Draft as guidance           forbidden
```

### P4.2 Scene verification

```text
SceneSegmentDraft soft hint
→ current Shot thumbnail
→ asset-side Qwen3-VL visual verification
→ actual scene label / indoor-outdoor / time
→ MATCH / CONFLICT / UNKNOWN against Draft
→ existing SceneCandidate / ShotSceneEvidence
→ P4 provenance in evidence_json
```

Draft conflict is allowed and must be reported; Draft is never forced onto the image.

### P4.3 Prop verification

```text
DraftPropOccurrence
→ temporary request target P1/P2/...
→ current Shot thumbnail verification
→ observed=false: reject hint
→ observed=true + confidence >= 0.45: verified Prop Candidate Evidence
```

New prop discovery is still allowed but uses a stricter confidence gate:

```text
confidence >= 0.68
```

When reliable localization is returned:

```text
ShotPropEvidence.bbox_json
format = xyxy_norm
bbox values = 0..1
```

Invalid/zero-area/out-of-range boxes are discarded.

### P4.4 fallback / failure behavior

```text
no current revision-safe Draft
→ legacy asset_semantics_v3 unguided path
```

Partial Shot failures keep successful Evidence but surface `READY_WITH_WARNINGS`. Scene/Prop semantic failure does not erase Character V10.1 Evidence.

P4 status:

```text
implementation = IMPLEMENTED
local/model acceptance = PENDING
quality PASS = NO
```

## 9. Formal phase order from here

```text
P0 Planning / Contract                         COMPLETE
P1 implementation                              CONDITIONAL PASS
P2 implementation                              CONDITIONAL PASS
P2.6 Windows / real-model acceptance           NOT PASSED
P3 02 拉片 Structured Draft UI                 IMPLEMENTED / UI ACCEPTANCE IN PROGRESS
P4 Draft-guided Scene / Prop evidence          IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character safe integration          PLANNED
P6 Final identity/asset fill-back + renderers   PLANNED
P7 downstream remake integration               PLANNED
```

Immediate work is now three-track acceptance: P2.6 full-chain, P3 browser UI, and P4 local Scene/Prop verification. After P4 behavior is accepted, P5 is the next implementation phase.

## 10. Forbidden shortcuts

```text
Shot Detection == complete Breakdown                    forbidden
VLM prose == Final identity                              forbidden
VLM subject_A → Character                                forbidden
ASR speaker → Character                                  forbidden
SceneSegmentDraft == Final Scene                         forbidden
DraftPropHint == Final Prop                              forbidden
P4 observed=false DraftPropHint -> PropCandidate         forbidden
STALE Breakdown -> current asset guidance                forbidden
Fusion deletes raw Evidence                              forbidden
semantic context overrides Face/cannot-link              forbidden
missing real acceptance but docs claim PASS              forbidden
```

## 11. User-facing simplified flow

```text
① 视频处理
② 镜头切分
③ AI 内容拉片
④ 人物 / 场景 / 道具识别
⑤ 资产确认与回填
⑥ 最终拉片
⑦ 重制
```

P2 implements the backend for step ③. P3 implements its main review UI. P4 now makes step ④ consume current Draft as a safe search prior for Scene/Prop Evidence instead of re-analyzing blindly.
