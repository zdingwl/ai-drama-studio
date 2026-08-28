# AI Drama Studio — 拉片先行 / Breakdown-first 资产识别改造地图

> **Status:** ACCEPTED TARGET PLAN / P1 COMPLETE / **P2 IMPLEMENTATION COMPLETE** / REAL-VIDEO ACCEPTANCE PENDING / **P3 NEXT**  
> **Created:** 2026-08-27  
> **Last synchronized:** 2026-08-28 10:17 +08:00  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Current executable baseline:** Reference Video V2 / FastAPI 2.4.1 / Character V10.1 / Breakdown P1 + P2

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
  SceneSegmentDraft
  ShotSemanticDraft
  LocalSubject / ShotLocalSubject
  TimelineEvent
  DraftPropHint
  EvidenceLink
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

P2/P3/P4 may not:

```text
relax >=3 independent Shot / >=3 usable image identity gate
bypass same-sample cannot-link
ignore high-quality Face hard conflict
let VLM create Character
let ASR speaker create Character
let Draft prose write ShotCharacterBinding
restore Candidate Track ownership as current Final binding truth
```

Current Character chain remains:

```text
YOLOX Person
→ capture-first Person Evidence
→ mature MOT
→ YoutuReID project-level identity
→ RESOLVED / UNRESOLVED
→ explicit Shot × known-Character Assignment
→ Final Character Gate
```

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
| P1 anonymous Draft storage/lifecycle | IMPLEMENTED | P3 consume |
| P2 raw Evidence sidecar | IMPLEMENTED | keep |
| P2 ASR | IMPLEMENTED | real-video tune only if evidence requires |
| P2 OCR | IMPLEMENTED / frozen baseline | do not redo without concrete regression |
| P2 VLM | IMPLEMENTED | real-video tune only if evidence requires |
| P2 Fusion | IMPLEMENTED | P3 display |
| P2 full production orchestrator | IMPLEMENTED | P3 trigger |
| P2 sequential batch task | IMPLEMENTED | P3 trigger |
| P2 Windows/runtime preflight | IMPLEMENTED | execute on user machine |
| P2 acceptance reports | IMPLEMENTED | execute with real video |
| 02 拉片 structured UI | NOT IMPLEMENTED | **P3 NEXT** |
| Draft-guided Scene/Prop evidence | NOT IMPLEMENTED | P4 |
| Draft ↔ Character safe mapping | NOT IMPLEMENTED | P5 |
| Final fill-back/renderers | NOT IMPLEMENTED | P6 |
| downstream remake integration | PARTIAL/PLANNED | P7 |

## 4. P1 — COMPLETE

P1 formal entities:

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

P1 real validator is mandatory for publish. New ShotRevision makes incompatible active Breakdown Runs STALE while preserving history.

## 5. P2 — IMPLEMENTATION COMPLETE

### P2.1 raw Evidence sidecar

```text
PROCESSING BreakdownRun
→ exact source ShotRevision / ShotRevisionItems
→ Reference Clip / thumbnail / keyframes + Episode audio + source language
→ unified Provider Contract
→ validated raw Evidence
→ fingerprinted immutable sidecar
→ BreakdownRun provenance
```

### P2.2 ASR

```text
faster-whisper==1.2.1
large-v3
word timestamps
ASR_SEGMENT + ASR_WORD
Episode source integer microseconds
```

Cross-Shot dialogue is not prematurely assigned; Fusion performs exact splitting.

### P2.3 OCR

```text
rapidocr==3.9.2
PP-OCRv6 small
ONNX Runtime
default CPU
deterministic multi-frame exact Reference Clip sampling
OCR_OBSERVATION + geometry + source point time
```

OCR Provider keeps repeated observations raw. Fusion owns dedupe/duration inference. This baseline is frozen unless a concrete regression justifies a minimal change.

### P2.4 VLM

```text
Qwen/Qwen3-VL-4B-Instruct
exact historical Reference Clip
strict anonymous shot-semantic JSON
scene / shot / subjects / VISUAL|ACTION events / prop hints
confidence = NULL
```

P2.4 uses a separate base content-semantic checkpoint in the isolated TransVLM runtime. It does not reuse the transition-finetuned checkpoint and does not duplicate ASR/OCR transcription responsibilities.

### P2.5 Fusion

```text
immutable sidecar validation
→ ASR exact cross-Shot word-timing split
→ OCR text/time/geometry stitch
→ VLM ratio → source-us
→ SceneSegmentDraft
→ one ShotSemanticDraft per source ShotRevisionItem
→ LocalSubject / ShotLocalSubject
→ TimelineEvent
→ DraftPropHint / occurrences
→ precise EvidenceLink
→ P1 validator/publish
```

Anonymous subject grouping is conservative. If one appearance signature refers to multiple simultaneous people in any Shot, that signature is forbidden as a cross-Shot merge key for that segment.

### P2.6 production + local acceptance tooling

Formal production profile:

```text
breakdown-p2-full-v1
```

Production module:

```text
engine/app/breakdown_p2_pipeline_v1.py
ASR → OCR → VLM → Fusion
```

Background APIs:

```text
POST /api/episodes/{episode_id}/tasks/breakdown
POST /api/projects/{project_id}/tasks/breakdown-batch
```

Batch uses strict `Episode.sort_order`, one episode at a time.

Runtime/acceptance APIs:

```text
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

Acceptance deliberately separates machine structure from human visual/audio quality review:

```text
STRUCTURAL_FAIL
NEEDS_HUMAN_REVIEW
NEEDS_TUNING
PASS
```

Machine checks cannot self-award `PASS`.

## 6. P2 status terminology

Engineering implementation is complete:

```text
P2.1 COMPLETE
P2.2 COMPLETE
P2.3 COMPLETE
P2.4 COMPLETE
P2.5 COMPLETE
P2.6 production orchestration COMPLETE
P2.6 Windows/preflight tooling COMPLETE
P2.6 acceptance/report/comparison tooling COMPLETE
```

Real-video acceptance execution is still pending because this repository contains no real short-drama video sample and this development environment is not the user's Windows GPU host.

Therefore use:

```text
P2 IMPLEMENTATION = COMPLETE
P2 REAL-VIDEO ACCEPTANCE = PENDING
```

Do not use `P2 ACCEPTED/CLOSED` until a real sample produces a human-reviewed PASS report.

## 7. Real-video acceptance procedure

See `docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md`.

A true PASS requires:

```text
Run READY / READY_WITH_WARNINGS
ASR/OCR/VLM sidecars + fingerprints valid
VLM READY
Fusion READY / READY_WITH_WARNINGS
full frozen Shot coverage
required human scores >= 4/5
no blocking issues
```

Provider/parameter candidates may be compared using separate Runs and acceptance JSON reports. Comparison never reruns models implicitly.

## 8. Formal Phase order from here

```text
P0 Planning / Contract                              COMPLETE
P1 Draft data/runtime/history                       COMPLETE
P2 Anonymous Breakdown backend implementation       COMPLETE
P2 real-video acceptance execution                  PENDING
P3 02 拉片 structured Draft UI                      NEXT
P4 Draft-guided Scene / Prop evidence               PLANNED
P5 Draft ↔ Character safe integration               PLANNED
P6 Final identity/asset fill-back + renderers        PLANNED
P7 downstream remake integration                    PLANNED
```

### P3 — next

P3 should provide a human-readable workbench for:

```text
Scene Segment
Shot + Reference Clip
人物A/B
Timeline dialogue/action/OCR
scene/prop hints
Evidence provenance
Run history / STALE state
single/batch AI Breakdown task progress
```

P3 must call the P2 production endpoint instead of duplicating Provider/Fusion logic in the frontend.

## 9. Forbidden shortcuts

```text
Shot Detection == complete Breakdown                    forbidden
VLM prose == Final identity                              forbidden
VLM subject_A → Character                                forbidden
ASR speaker → Character                                  forbidden
SceneSegmentDraft == Final Scene                         forbidden
DraftPropHint == Final Prop                              forbidden
OCR point observation == inferred full subtitle duration forbidden
Fusion deletes raw Evidence                              forbidden
semantic context overrides Face/cannot-link              forbidden
P2 writes Final asset/binding                            forbidden
real-video not run but docs claim quality accepted       forbidden
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

P2 now implements the backend for step ③. P3 is the user-facing structured workbench for viewing/operating that result.
