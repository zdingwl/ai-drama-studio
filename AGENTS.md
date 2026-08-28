# AI Drama Studio — Agent Entry Rules

Current formal architecture: **Reference Video V2**. Formal Character baseline: **Character V10.1 + explicit Shot Character Assignment**.

Current Breakdown truth:

```text
P1/P2 implementation acceptance      = CONDITIONAL PASS
P2.6 Windows / real-model acceptance = NOT PASSED
P3 Structured Draft UI               = IMPLEMENTED ON MAIN / UI ACCEPTANCE IN PROGRESS
```

P2.6 is currently blocked by incomplete **OCR + Qwen3-VL runtime/model provisioning**. Do not describe the project as P2 accepted/closed until a real short-drama full-chain run receives the required acceptance PASS.

Core product principle:

> **先看懂，再识别，再回填。**

## 1. New-conversation recovery order

Always read repository truth before relying on old chat/history:

```text
1. AGENTS.md
2. SKILL.md
3. docs/PROJECT_STATE.md
4. docs/CURRENT_IMPLEMENTATION_MANIFEST.md
5. docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
6. docs/BREAKDOWN_DRAFT_DATA_CONTRACT.md
7. docs/BREAKDOWN_P2_SIDECAR_CONTRACT.md
8. docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md
9. docs/ASSET_CHARACTER_RECOGNITION_V10_1.md when Character is involved
10. current code/tests
11. latest docs/sessions/*.md handoff
```

Truth priority:

```text
PROJECT_STATE + CURRENT_IMPLEMENTATION_MANIFEST + current code/tests
= executable CURRENT truth

BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN
= accepted target + phase order
```

Do not let historical F01–F06 documents, old Frozen snapshots or Character V1–V10 plans override current wiring.

## 2. Current baseline

```text
Architecture: Reference Video V2
Default branch: main
FastAPI: 2.4.1
Formal Character runtime: V10.1
Runtime profile: character-v10.1-capture-first-model-classification
Asset profile: f05-assets-v10.1-person-evidence-model-classification
Resolver: person-evidence-model-classifier-v10.1
Shot assignment: v10.1-shot-character-assignment-1
```

Breakdown status:

```text
P0 planning/contracts                    COMPLETE
P1 implementation                        CONDITIONAL PASS
P2.1 Provider/raw Evidence sidecar       IMPLEMENTED
P2.2 ASR Provider                        IMPLEMENTED
P2.3 OCR Observation Provider            IMPLEMENTED
P2.4 anonymous Shot VLM semantics        IMPLEMENTED
P2.5 deterministic multimodal Fusion     IMPLEMENTED
P2.6 production orchestrator/API         IMPLEMENTED
P2.6 Windows/preflight/acceptance tools  IMPLEMENTED
P2.6 Windows/real-model acceptance       NOT PASSED
P3 structured 02 拉片 UI                 IMPLEMENTED / UI ACCEPTANCE IN PROGRESS
P4 Draft-guided Scene/Prop               PLANNED
```

Do not equate “acceptance tooling exists” with “real short-drama quality was accepted”.

## 3. Breakdown production flow

Formal production chain:

```text
Episode Current ShotRevision
→ create frozen PROCESSING BreakdownRun
→ ASR
→ OCR
→ Qwen3-VL
→ immutable raw Evidence sidecars
→ deterministic Fusion
→ anonymous P1 Draft
→ real P1 validator
→ READY / READY_WITH_WARNINGS
```

Formal orchestrator:

```text
engine/app/breakdown_p2_pipeline_v1.py
profile = breakdown-p2-full-v1
provider order = ASR → OCR → VLM
```

Formal APIs:

```text
POST /api/episodes/{episode_id}/tasks/breakdown
POST /api/projects/{project_id}/tasks/breakdown-batch
GET  /api/breakdown/p2/runtime-preflight
POST /api/breakdown-runs/{run_id}/p2-acceptance
```

Batch Breakdown must remain sequential by `Episode.sort_order`; heavy P2 jobs are globally serialized.

## 4. P2.6 current acceptance gate

Current user acceptance result:

```text
P1/P2 implementation = CONDITIONAL PASS
P2.6 Windows/real-model = NOT PASSED
```

Known blocker:

```text
OCR runtime/model provisioning incomplete
Qwen3-VL model/runtime provisioning incomplete
```

Required retry:

```text
provision OCR + Qwen
→ strict preflight
→ real short-drama sample
→ ASR → OCR → VLM → Fusion → P1 validator
→ acceptance report
→ human required scores >=4/5
→ no blocking issues
```

Only then may project truth say `P2.6 PASS` / `P2 ACCEPTED` / `P2 CLOSED`.

## 5. Anonymous Draft is not identity truth

```text
人物A / subject_A / LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
Breakdown Evidence != Final Asset/Binding truth
```

P2 must never write Final Character/Scene/Prop assets or Final Shot bindings. VLM prose, ASR speaker labels and OCR text are context/evidence only.

## 6. Shot / history rules

Reference Video V2 remains authoritative:

```text
Project / Episode
FFmpeg / FFprobe
integer microseconds
TransNetV2 Shot boundaries
ShotRevision / ShotRevisionItem
Reference Clip / thumbnail / keyframes
```

`Shot.id` is not a permanent historical anchor across reruns/restores. Breakdown history anchors to exact ShotRevision/ShotRevisionItem. New Current ShotRevision marks incompatible active Breakdown Runs STALE.

## 7. Provider boundaries

### ASR

```text
FasterWhisperASRProvider
faster-whisper==1.2.1
large-v3
word timestamps
```

ASR speaker does not map directly to Character.

### OCR

```text
RapidOCROCRProvider
rapidocr==3.9.2
PP-OCRv6 small
ONNX Runtime
```

Provider implementation is the baseline. Current P2.6 blocker is provisioning, not a request to redesign OCR.

### VLM

```text
Qwen3VLSemanticProvider
Qwen/Qwen3-VL-4B-Instruct
strict anonymous shot semantics
```

Current P2.6 blocker is Qwen model/runtime provisioning, not permission to replace the semantic contract casually.

## 8. P2 Fusion cannot-link rule

If one normalized appearance description appears for two simultaneous subjects in any Shot of a Scene Segment, that appearance is ambiguous and cannot be used for cross-Shot LocalSubject merging within that segment. Prefer duplicate anonymous subjects over a false identity merge.

## 9. Character V10.1 is protected

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

Never relax:

```text
new identity requires >=3 independent Shots
new identity requires >=3 model-usable images
same-sample cannot-link is hard
high-quality Face conflict is hard negative
ambiguous winner remains unresolved/unassigned
current Final Shot binding comes from explicit shot_presence_assignments
```

Draft/VLM/ASR context cannot override these gates.

## 10. P3 current UI truth

P3 is already on `main` and is no longer `NEXT`.

```text
02 拉片
├─ 镜头边界
└─ Structured Draft
   ├─ P2 single/batch tasks
   ├─ Run history / STALE
   ├─ Scene / Shot Draft
   ├─ anonymous subjects
   ├─ timeline dialogue/action/OCR
   ├─ prop hints
   ├─ historical Reference Clip
   └─ Evidence provenance
```

P3 browser/UI acceptance remains in progress. The Shot Boundary scrolling regression was fixed in main merge commit `1cb8624b885850935e902cb6c9ac2273c490d2b3`.

## 11. Testing / CI discipline

Do not consume hosted GitHub Actions quota for this work. Use `[skip ci]` for remote documentation/development commits where applicable. Historical CI must remain historical.

## 12. Documentation sync rule

Keep these aligned when current status changes:

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md when P2 runtime/acceptance changes
latest docs/sessions/*.md handoff
```

## 13. Next safe work

Two active acceptance tracks:

```text
A. provision OCR + Qwen and rerun P2.6 real short-drama acceptance
B. continue P3 browser/UI acceptance
```

P4 remains planned. Do not upgrade acceptance status without evidence.
