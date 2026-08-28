# AI Drama Studio — 拉片先行 / Breakdown-first 资产识别改造地图

> **Status:** ACCEPTED TARGET PLAN / **P1-P2 IMPLEMENTATION CONDITIONAL PASS** / **P2.6 REAL-MODEL ACCEPTANCE NOT PASSED** / **P3 IMPLEMENTED, UI ACCEPTANCE IN PROGRESS**  
> **Created:** 2026-08-27  
> **Last synchronized:** 2026-08-28 12:12 +08:00  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Current executable baseline:** Reference Video V2 / FastAPI 2.4.1 / Character V10.1 / Breakdown P1 + P2 + P3 first UI

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
专用视觉/音频模型验证
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

P2/P3/P4 may not relax Character V10.1 identity gates, bypass same-sample cannot-link, ignore Face hard conflicts, let VLM/ASR create Character, or write Final Shot bindings from Draft prose.

### 2.4 Raw Evidence and Draft are separate

P2 Provider outputs remain immutable sidecars; Fusion must not erase raw evidence. Draft owners link only to evidence actually consumed.

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
| P2 OCR | IMPLEMENTED; runtime/model provisioning incomplete | provision + real-video verify |
| P2 VLM | IMPLEMENTED; Qwen model provisioning incomplete | provision + real-video verify |
| P2 Fusion | IMPLEMENTED | real-video verify |
| P2 full production orchestrator | IMPLEMENTED | real-video verify |
| P2 sequential batch task | IMPLEMENTED | real-video verify |
| P2 Windows/runtime preflight | IMPLEMENTED | rerun after model provisioning |
| P2 acceptance reports | IMPLEMENTED | produce real PASS report |
| 02 拉片 Structured Draft UI | IMPLEMENTED ON MAIN | finish browser/UI acceptance |
| Draft-guided Scene/Prop evidence | NOT IMPLEMENTED | P4 |
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
- P3 may consume these contracts/APIs;
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

Provider implementation remains the accepted baseline. Current problem is not a redesign request: **the Windows acceptance environment still needs the OCR runtime/model provisioned before the real full chain can pass.**

### P2.4 VLM

```text
Qwen/Qwen3-VL-4B-Instruct
exact historical Reference Clip
strict anonymous shot-semantic JSON
```

Provider implementation remains the baseline. Current Windows acceptance is blocked because the required Qwen3-VL model/runtime is not fully provisioned.

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

Local tools:

```text
scripts/run_breakdown_p2.py
scripts/run_breakdown_p2_windows.ps1
scripts/p2_acceptance_review_template.json
docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md
```

## 6. P2.6 real-model acceptance status

Current result is no longer the vague phrase “not executed yet”. The user has performed the acceptance review and the result is:

```text
P2.6 Windows / real-model acceptance = NOT PASSED
```

Blocking conditions:

```text
OCR runtime/model is not fully provisioned
Qwen3-VL model/runtime is not fully provisioned
therefore a complete real short-drama chain has not been completed
```

Required retest:

```text
provision OCR
+ provision Qwen3-VL
+ choose real short-drama Episode
+ run ASR → OCR → VLM → Fusion → P1 validator
+ generate acceptance report
+ human review required scores >= 4/5
+ no blocking issues
= P2.6 PASS
```

Until that evidence exists, forbidden wording includes:

```text
P2 ACCEPTED
P2 CLOSED
P2.6 PASS
real-model quality accepted
```

## 7. P3 — implemented on main

P3 is no longer `NEXT`.

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
P3 implementation = IMPLEMENTED ON MAIN
P3 browser/UI acceptance = IN PROGRESS
P3 accepted/closed = NO
```

The Stage 02 Shot Boundary overflow regression discovered during acceptance was fixed in main merge commit `1cb8624b885850935e902cb6c9ac2273c490d2b3`.

## 8. Formal phase order from here

```text
P0 Planning / Contract                         COMPLETE
P1 implementation                              CONDITIONAL PASS
P2 implementation                              CONDITIONAL PASS
P2.6 Windows / real-model acceptance           NOT PASSED
P3 02 拉片 Structured Draft UI                 IMPLEMENTED / UI ACCEPTANCE IN PROGRESS
P4 Draft-guided Scene / Prop evidence          PLANNED
P5 Draft ↔ Character safe integration          PLANNED
P6 Final identity/asset fill-back + renderers   PLANNED
P7 downstream remake integration               PLANNED
```

The immediate acceptance work is **not** to redesign P2.3/P2.4. It is to provision the missing OCR/Qwen runtime assets and run the real full chain. P3 browser acceptance can continue in parallel.

## 9. Forbidden shortcuts

```text
Shot Detection == complete Breakdown                    forbidden
VLM prose == Final identity                              forbidden
VLM subject_A → Character                                forbidden
ASR speaker → Character                                  forbidden
SceneSegmentDraft == Final Scene                         forbidden
DraftPropHint == Final Prop                              forbidden
Fusion deletes raw Evidence                              forbidden
semantic context overrides Face/cannot-link              forbidden
P2 writes Final asset/binding                            forbidden
missing real models but docs claim acceptance PASS       forbidden
```

## 10. User-facing simplified flow

```text
① 视频处理
② 镜头切分
③ AI 内容拉片
④ 人物 / 场景 / 道具识别
⑤ 资产确认与回填
⑥ 最终拉片
⑦ 重制
```

P2 implements the backend for step ③. P3 now implements the first user-facing Structured Draft workbench for viewing and operating that result.
