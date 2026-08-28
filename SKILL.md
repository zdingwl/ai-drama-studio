---
name: ai-drama-studio-reference-video-v2
version: 3.9.0
description: AI Drama Studio Reference Video 驱动的本地短剧重制工作台开发规则；Character V10.1 为正式人物基线；Breakdown 已进入整集上下文迁移，P2-E1 场景连续性与跨镜对白 Fusion 已在 main，P2-E2 连续窗口 VLM 尚未实现；P2.6 真实模型验收仍未通过。
---

# AI Drama Studio — Reference Video V2 / Episode-context Breakdown / Character V10.1

## 0. 恢复项目上下文

必须先读取 GitHub 当前仓库事实：

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/CURRENT_IMPLEMENTATION_MANIFEST.md
→ docs/BREAKDOWN_EPISODE_CONTEXT_PLAN.md
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
BREAKDOWN_EPISODE_CONTEXT_PLAN = accepted current Breakdown migration TARGET
BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN = wider downstream TARGET / phase order
```

Old Frozen/Feature docs, old Shot-centric assumptions or old chat do not override current wiring.

## 1. Current baseline

```text
Architecture: Reference Video V2
FastAPI: 2.4.1
Default branch: main
Formal Character runtime: Character V10.1
P1/P2 implementation acceptance: CONDITIONAL PASS
P2-E1 Episode-context Fusion: IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E2 continuous-window VLM: PLANNED / NOT IMPLEMENTED
P2.6 Windows / real-model acceptance: NOT PASSED
P3 02 拉片 UI: IMPLEMENTED / UI ACCEPTANCE IN PROGRESS
P4 Draft-guided Scene/Prop: IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character: PLANNED / PAUSED UNTIL EPISODE-CONTEXT BASELINE
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

Current Breakdown principle:

> **Shot 是拉片结果的最小展示单位，不是 AI 理解内容的上下文边界。**

## 2. Breakdown-first product flow

Accepted target:

```text
Original Episode
→ Preprocess
→ Shot Detection + ShotRevision
→ Episode ASR / OCR
→ continuous/contextual Video Understanding
→ Episode-context Fusion
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
ASR speaker != Character
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

Shot boundaries remain timing/edit boundaries but are no longer the maximum semantic context.

## 4. P1 Draft contract

Formal entities remain:

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

Do not introduce a destructive P1 schema migration merely to represent cross-Shot dialogue while E1 metadata grouping is sufficient.

## 5. P2 formal production chain

Formal orchestrator:

```text
engine/app/breakdown_p2_pipeline_v1.py
pipeline profile = breakdown-p2-full-v1
```

Current execution:

```text
create frozen PROCESSING BreakdownRun
→ Episode ASR
→ OCR
→ current Qwen3-VL visual semantics
→ immutable sidecars
→ P2-E1 Episode-context Fusion
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Formal components:

```text
P2.1 engine/app/breakdown_p2_sidecar_v1.py
P2.2 engine/app/breakdown_p2_asr_v1.py
P2.3 engine/app/breakdown_p2_ocr_runtime_v1.py
P2.4 engine/app/breakdown_p2_vlm_runtime_v1.py
legacy Fusion baseline engine/app/breakdown_p2_fusion_v1.py
production E1 Fusion engine/app/breakdown_p2_fusion_episode_v2.py
P2.6 engine/app/breakdown_p2_pipeline_v1.py
P2.6 engine/app/breakdown_p2_acceptance_v1.py
```

Production Fusion sub-profile:

```text
breakdown-p2-fusion-episode-context-e1-v2
```

Keep the top-level `breakdown-p2-full-v1` pipeline profile for Contract compatibility unless a future migration explicitly versions the whole pipeline.

## 6. P2-E1 scene continuity rules

E1 must follow:

```text
strong scene/location evidence establishes the current Scene

missing / UNKNOWN / generic environment hint
→ inherit current Scene

compatible specificity
病房 → 医院病房
客厅 → 家中客厅
→ same Scene; prefer more specific anchor

strong location contradiction
or explicit INT ↔ EXT contradiction
→ new Scene Segment
```

Product rule:

```text
看不出来 != 换场
```

E1 intentionally prefers under-segmentation over inventing a new Scene from a closeup or blurred background. P2-E2/E4 will later provide stronger continuity/change evidence.

## 7. P2-E1 dialogue continuity rules

Raw Episode ASR is authoritative for dialogue text:

```text
ASR_SEGMENT = dialogue text truth
ASR_WORD = timing/confidence SUPPORT evidence
Shot DIALOGUE TimelineEvent = projection of the ASR segment onto a Shot
```

A sentence crossing a cut must not become partial text fragments.

Every cross-Shot projection must preserve/share:

```text
dialogue_group_id = asr_segment_id
dialogue_source_start_us / dialogue_source_end_us
projection_start_us / projection_end_us
projection_index / projection_count
continues_from_previous_shot / continues_to_next_shot
```

Raw ASR sidecars are immutable. E1 may create a derived Fusion-consumption view but must never rewrite historical sidecar bytes/fingerprints.

## 8. P2-E2 / E3 / E4 target

Current Qwen3-VL still receives one historical Reference Clip at a time. This is an explicit temporary limitation.

Never claim “整集连续 VLM 拉片已经完成” until E2 exists and is accepted.

Accepted next sequence:

```text
P2-E2
overlapping Episode video windows, roughly 20–40s with overlap
+ exact Shot boundaries

→ P2-E3
Current Scene
+ Previous Shot
+ Current Shot
+ Next Shot
+ overlapping ASR/OCR
+ window context

→ P2-E4
final Episode-context Scene / dialogue / anonymous-subject / Shot projection Fusion
```

Long-term invariants:

```text
Shot boundary != dialogue sentence boundary
Shot boundary != scene boundary
Shot boundary != maximum semantic context
```

## 9. ASR / OCR / VLM responsibilities

### ASR

```text
FasterWhisperASRProvider
faster-whisper==1.2.1
large-v3
word timestamps
Episode audio
```

Speaker labels never directly create/map Character.

### OCR

```text
RapidOCROCRProvider
rapidocr==3.9.2
PP-OCRv6 small
ONNX Runtime
```

### VLM

```text
Qwen3VLSemanticProvider
Qwen/Qwen3-VL-4B-Instruct
anonymous semantics only
current input scope = single historical Reference Clip
```

P2-E2 may change VLM input scope to overlapping Episode windows but cannot change the Final identity boundary.

Chinese Draft policy remains:

```text
prompt_profile = breakdown-p2-vlm-zh-draft-v1
draft_text_language = zh-CN
```

ASR/OCR raw source text remains untranslated.

## 10. Fusion / identity safety rules

Fusion consumes registered immutable ASR/OCR/VLM sidecars and never implicitly reruns Providers.

Same-Shot anonymous cannot-link remains mandatory: if one normalized appearance is used by multiple simultaneous subjects, it cannot be used as a cross-Shot merge key in that Scene Segment.

Episode-context continuity may increase semantic context but must never relax identity cannot-link or Face conflict rules.

## 11. Background tasks / batch

Formal APIs:

```text
POST /api/episodes/{episode_id}/tasks/breakdown
POST /api/projects/{project_id}/tasks/breakdown-batch
GET  /api/breakdown/p2/runtime-preflight
POST /api/breakdown-runs/{run_id}/p2-acceptance
```

Batch must follow `Episode.sort_order` and heavy P2 execution remains globally serialized.

## 12. P2.6 runtime / acceptance

Current status:

```text
P1/P2 implementation acceptance = CONDITIONAL PASS
P2-E1 local-real acceptance = PENDING
P2.6 Windows / real-model acceptance = NOT PASSED
```

Before final acceptance:

```text
1. complete/verify OCR runtime/model provisioning
2. complete/verify Qwen3-VL model/runtime provisioning
3. run strict preflight
4. run a real short-drama Episode through ASR → OCR → VLM → E1 Fusion → P1 validator
5. verify cross-Shot dialogue stays whole
6. verify same-scene closeups/inserts/blurred backgrounds do not fragment Scene
7. verify genuine scene changes still split
8. generate acceptance report
9. complete human review
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

## 13. Character V10.1 protected baseline

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

## 14. P3 current UI

Current main user-facing structure:

```text
02 拉片
├─ 镜头管理
│  └─ simplified Shot review/edit workbench
└─ 拉片结果
   ├─ Scene / Shot result
   ├─ anonymous subjects
   ├─ dialogue/action/OCR
   ├─ key prop hints
   └─ exact historical Reference Clip
```

P3 implementation is on `main`; browser/UI acceptance is still in progress.

E1 continuation metadata should later be rendered as one continuing dialogue instead of visually presenting projections as unrelated duplicate lines.

## 15. P4 / downstream status

P4 Draft-guided Scene/Prop Evidence is implemented but local/model acceptance is pending. It must visually re-verify Draft hints and cannot turn Draft prose directly into Final assets.

P5 Draft ↔ Character safe integration is planned but paused until the Episode-context Breakdown semantic baseline is locally accepted.

## 16. P2 forbidden writes

P2 cannot create/update Final Character/Scene/Prop assets or Final Shot bindings. VLM/ASR/OCR cannot write Final identity truth.

## 17. Testing / CI discipline

User does not want hosted GitHub Actions quota consumed. Use `[skip ci]` for current remote development/documentation commits and prefer local verification. Historical CI results must remain historical.

Current E1 test file:

```text
engine/tests/v2/test_breakdown_p2_fusion_episode_v2.py
```

Do not report tests as passed unless they were actually run in the local project environment.

## 18. Phase pointer

```text
P0 COMPLETE
P1 implementation CONDITIONAL PASS
P2 implementation CONDITIONAL PASS
P2-E1 Episode-context Fusion IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E2 continuous-window VLM PLANNED
P2-E3 contextual Shot refinement PLANNED
P2-E4 final Episode-context Fusion PLANNED
P2.6 Windows / real-model acceptance NOT PASSED
P3 02 拉片 UI IMPLEMENTED / UI ACCEPTANCE IN PROGRESS
P4 Draft-guided Scene/Prop IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character safe integration PLANNED / PAUSED
P6 Final fill-back/renderers PLANNED
P7 downstream remake integration PLANNED
```

Immediate safe work:

```text
A. locally re-run one real short-drama Episode on current main and accept/reject E1 behavior
B. after E1 acceptance, implement P2-E2 overlapping continuous-window Qwen3-VL
C. continue P3/P4 local acceptance without upgrading status prematurely
```
