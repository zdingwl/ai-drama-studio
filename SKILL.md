---
name: ai-drama-studio-reference-video-v2
version: 3.8.0
description: AI Drama Studio Reference Video 驱动的本地短剧重制工作台开发规则；Character V10.1 为正式人物基线；Breakdown P1/P2 后台实现已完成，真实视频验收待用户 Windows 执行，P3 structured 02 拉片 UI 下一步。
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
P1: COMPLETE
P2 backend implementation: COMPLETE
P2 real-video acceptance execution: PENDING
P3 structured 02 拉片 UI: NEXT
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

Historical Breakdown always anchors to exact frozen ShotRevision/ShotRevisionItem. Do not migrate Draft between revisions by guessed ordinal/time similarity.

## 4. P1 Draft contract

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

Real validator is mandatory. Successful publish switches Current atomically; FAILED/STALE runs never replace the prior valid Current.

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

Produces anonymous ASR segment/word Evidence. Dialogue may cross cuts; Fusion handles exact Shot splitting. Speaker label never directly creates/maps Character.

### OCR — frozen baseline

```text
RapidOCROCRProvider
rapidocr==3.9.2
PP-OCRv6 small
ONNX Runtime
default CPU
```

Samples exact historical Reference Clips across Shots and stores point observations with text/confidence/geometry/source time. Fusion owns temporal stitch/dedupe.

**Do not redo OCR** unless a concrete regression requires a minimal fix.

### VLM

```text
Qwen3VLSemanticProvider
Qwen/Qwen3-VL-4B-Instruct
strict anonymous shot semantics
```

VLM returns scene hints, shot description, anonymous subjects, actions and plot-relevant prop hints. It does not own dialogue/subtitle/sign/phone transcription. It uses an isolated runtime and a separate base semantic checkpoint, not the transition-finetuned TransVLM checkpoint.

## 7. Fusion rules

Fusion consumes registered immutable ASR/OCR/VLM sidecars and never implicitly reruns Providers.

Core transformations:

```text
ASR cross-Shot word-timing split
OCR text/time/geometry stitching
VLM ratios → source-us
SceneSegmentDraft
one ShotSemanticDraft per frozen source Shot
LocalSubject / ShotLocalSubject
TimelineEvent / participants
DraftPropHint / occurrences
precise BreakdownEvidenceLink
P1 validator/publish
```

Same-Shot anonymous cannot-link:

```text
same normalized appearance used by >=2 simultaneous subjects
→ appearance is ambiguous for the segment
→ cannot cross-Shot merge by that appearance
→ use shot-local anonymous keys
```

Prefer duplicate anonymous subjects to false identity merging.

## 8. Background tasks / batch

Formal APIs:

```text
POST /api/episodes/{episode_id}/tasks/breakdown
POST /api/projects/{project_id}/tasks/breakdown-batch
```

Batch must follow:

```text
Episode.sort_order
concurrency = 1
```

Use the existing persistent BackgroundTask infrastructure; do not invent a second job system for P2/P3.

## 9. P2 runtime / acceptance

Formal local tools:

```text
scripts/run_breakdown_p2.py
scripts/run_breakdown_p2_windows.ps1
scripts/p2_acceptance_review_template.json
docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md
```

APIs:

```text
GET  /api/breakdown/p2/runtime-preflight
POST /api/breakdown-runs/{run_id}/p2-acceptance
```

Acceptance states:

```text
STRUCTURAL_FAIL
NEEDS_HUMAN_REVIEW
NEEDS_TUNING
PASS
```

`PASS` requires structural success + explicit real-video human scores >=4/5 for all required dimensions + no blocking issue. Machine checks cannot award PASS on their own.

Repository currently has no real short-drama sample, so do not claim real-model quality acceptance has run.

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
current Final ShotCharacterBinding = explicit shot_presence_assignments for current V10.1 Runs
```

Draft semantic context cannot override these rules.

## 11. P2 forbidden writes

P2 cannot create/update:

```text
Character
Scene
Prop
AssetRevision
ShotCharacterBinding
ShotSceneBinding
ShotPropBinding
```

Do not let VLM/ASR/OCR write Final identity/asset truth.

## 12. Testing / CI discipline

User explicitly requested not to consume GitHub Actions quota. For current P2.6 work:

```text
GitHub hosted CI: do not run/check
use [skip ci] for remote development commits
local syntax/focused verification is preferred
real Windows short-drama acceptance is the final external gate
```

Do not describe historical CI results as fresh current results.

## 13. Git workflow

Read current main before writes. Keep changes isolated. Follow the GitHub connector safety workflow. Do not force-update main. Do not create a PR unless requested.

## 14. Phase pointer

```text
P0 COMPLETE
P1 COMPLETE
P2 IMPLEMENTATION COMPLETE
P2 REAL-VIDEO ACCEPTANCE PENDING
P3 structured 02 拉片 UI NEXT
P4 Draft-guided Scene/Prop PLANNED
P5 Draft ↔ Character safe integration PLANNED
P6 Final fill-back/renderers PLANNED
P7 downstream remake integration PLANNED
```

P3 must consume the P2 production/read/task APIs instead of duplicating model/Fusion logic in the frontend.
