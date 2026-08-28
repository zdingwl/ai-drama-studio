# AI Drama Studio — Agent Entry Rules

Current formal architecture: **Reference Video V2**. Formal Character baseline: **Character V10.1 + explicit Shot Character Assignment**.

Current Breakdown truth:

```text
P1/P2 implementation acceptance      = CONDITIONAL PASS
P2-E1 Episode-context Fusion          = IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E2 continuous-window VLM           = PLANNED / NOT IMPLEMENTED
P2.6 Windows / real-model acceptance = NOT PASSED
P3 02 拉片 UI                        = IMPLEMENTED / UI ACCEPTANCE IN PROGRESS
P4 Draft-guided Scene/Prop            = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character                  = PLANNED / PAUSED UNTIL EPISODE-CONTEXT BASELINE
```

Do not describe the project as P2 accepted/closed until a real short-drama full-chain run receives the required acceptance PASS.

Core product principle:

> **先看懂，再识别，再回填。**

Current Breakdown semantic principle:

> **Shot 是拉片结果的最小展示单位，不是 AI 理解内容的上下文边界。**

## 1. New-conversation recovery order

Always read repository truth before relying on old chat/history:

```text
1. AGENTS.md
2. SKILL.md
3. docs/PROJECT_STATE.md
4. docs/CURRENT_IMPLEMENTATION_MANIFEST.md
5. docs/BREAKDOWN_EPISODE_CONTEXT_PLAN.md
6. docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
7. docs/BREAKDOWN_DRAFT_DATA_CONTRACT.md
8. docs/BREAKDOWN_P2_SIDECAR_CONTRACT.md
9. docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md
10. docs/ASSET_CHARACTER_RECOGNITION_V10_1.md when Character is involved
11. current code/tests
12. latest docs/sessions/*.md handoff
```

Truth priority:

```text
PROJECT_STATE + CURRENT_IMPLEMENTATION_MANIFEST + current code/tests
= executable CURRENT truth

BREAKDOWN_EPISODE_CONTEXT_PLAN
= accepted current Breakdown migration target

BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN
= wider accepted target + downstream phase order
```

Do not let historical F01–F06 documents, old Frozen snapshots, old Shot-centric Breakdown assumptions, or Character V1–V10 plans override current wiring.

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
P0 planning/contracts                         COMPLETE
P1 implementation                             CONDITIONAL PASS
P2.1 Provider/raw Evidence sidecar            IMPLEMENTED
P2.2 Episode ASR                              IMPLEMENTED
P2.3 OCR Observation Provider                 IMPLEMENTED
P2.4 single-Reference-Clip Qwen VLM           IMPLEMENTED; current limitation
P2-E1 Episode-context Fusion                  IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E2 continuous-window Qwen VLM              PLANNED
P2-E3 contextual Shot refinement              PLANNED
P2-E4 final Episode-context Fusion            PLANNED
P2.6 production orchestrator/API              IMPLEMENTED
P2.6 Windows/preflight/acceptance tools       IMPLEMENTED
P2.6 Windows/real-model acceptance            NOT PASSED
P3 02 拉片 UI                                 IMPLEMENTED / UI ACCEPTANCE IN PROGRESS
P4 Draft-guided Scene/Prop                    IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character safe integration         PLANNED / PAUSED
```

Do not equate “implementation exists” or “acceptance tooling exists” with real short-drama quality acceptance.

## 3. Breakdown production flow

Current production chain:

```text
Episode Current ShotRevision
→ create frozen PROCESSING BreakdownRun
→ Episode ASR
→ OCR
→ current Qwen3-VL visual semantics
→ immutable raw Evidence sidecars
→ Episode-context E1 Fusion
→ anonymous P1 Draft
→ real P1 validator
→ READY / READY_WITH_WARNINGS
```

Formal orchestrator:

```text
engine/app/breakdown_p2_pipeline_v1.py
pipeline profile = breakdown-p2-full-v1
provider order = ASR → OCR → VLM
production Fusion = engine/app/breakdown_p2_fusion_episode_v2.py
Fusion profile = breakdown-p2-fusion-episode-context-e1-v2
```

Formal APIs remain:

```text
POST /api/episodes/{episode_id}/tasks/breakdown
POST /api/projects/{project_id}/tasks/breakdown-batch
GET  /api/breakdown/p2/runtime-preflight
POST /api/breakdown-runs/{run_id}/p2-acceptance
```

Batch Breakdown must remain sequential by `Episode.sort_order`; heavy P2 jobs are globally serialized.

## 4. P2-E1 rules

### Scene continuity

```text
missing / UNKNOWN / generic environment hint
→ inherit current Scene Segment

compatible specificity
病房 → 医院病房
客厅 → 家中客厅
→ same Scene

strong location contradiction
or explicit INT ↔ EXT contradiction
→ new Scene Segment
```

Key rule:

```text
看不出来 != 换场
```

### Dialogue continuity

```text
ASR_SEGMENT = Episode-time dialogue text truth
Shot DIALOGUE TimelineEvent = projection, not sentence truth
```

A sentence crossing a cut must keep the full sentence text in each overlapping projection and share:

```text
dialogue_group_id = asr_segment_id
dialogue_source_start_us / dialogue_source_end_us
projection_start_us / projection_end_us
continues_from_previous_shot / continues_to_next_shot
```

Raw ASR_WORD Evidence remains immutable and is attached as SUPPORT provenance.

Historical BreakdownRuns/sidecars are never rewritten; users must re-run AI 拉片 to receive new E1 semantics.

## 5. Current known limitation — P2-E2 not done

Current Qwen3-VL still analyzes each historical Reference Clip independently. Do **not** claim full Episode continuous VLM understanding is complete.

Accepted next semantic architecture:

```text
P2-E2 overlapping 20–40s Episode video windows
→ P2-E3 Scene + previous/current/next + ASR/OCR contextual refinement
→ P2-E4 final Episode-context Fusion
```

The long-term invariants are:

```text
Shot boundary != dialogue sentence boundary
Shot boundary != scene boundary
Shot boundary != maximum semantic context
```

## 6. P2.6 current acceptance gate

Current result:

```text
P1/P2 implementation = CONDITIONAL PASS
P2-E1 local-real acceptance = PENDING
P2.6 Windows/real-model = NOT PASSED
```

Required retry must now include E1-specific checks:

```text
provision OCR + Qwen
→ strict preflight
→ real short-drama Episode
→ ASR → OCR → VLM → Episode-context E1 Fusion → P1 validator
→ verify cross-Shot dialogue remains whole
→ verify wide shot + closeups/inserts remain one Scene when appropriate
→ verify genuine scene changes still split
→ acceptance report
→ human required scores >=4/5
→ no blocking issues
```

Only then may project truth say `P2.6 PASS` / `P2 ACCEPTED` / `P2 CLOSED`.

## 7. Anonymous Draft is not identity truth

```text
人物A / subject_A / LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
Breakdown Evidence != Final Asset/Binding truth
```

P2 must never write Final Character/Scene/Prop assets or Final Shot bindings. VLM prose, ASR speaker labels and OCR text are context/evidence only.

## 8. Shot / history rules

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

Shot boundary is still an edit/timing boundary, but no longer the maximum semantic-analysis boundary.

## 9. Provider boundaries

### ASR

```text
FasterWhisperASRProvider
faster-whisper==1.2.1
large-v3
word timestamps
Episode audio
```

ASR speaker does not map directly to Character.

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
current production input = single historical Reference Clip per Shot
```

This single-Clip input is now an explicit temporary limitation, not the target architecture. P2-E2 will introduce overlapping Episode windows without allowing VLM to create Final assets.

## 10. P2 subject cannot-link rule

If one normalized appearance description appears for two simultaneous subjects in any Shot of a Scene Segment, that appearance is ambiguous and cannot be used for cross-Shot LocalSubject merging within that segment. Prefer duplicate anonymous subjects over a false identity merge.

E1 scene continuity must not weaken this rule.

## 11. Character V10.1 is protected

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

## 12. P3 current UI truth

Current normal-user structure:

```text
02 拉片
├─ 镜头管理
│  └─ simplified Shot review/edit workbench
└─ 拉片结果
   ├─ Scene / Shot result
   ├─ 人物 / anonymous subject semantics
   ├─ 对白
   ├─ 动作
   ├─ 关键道具
   └─ original Reference Clip
```

Evidence/provenance remains available internally but is not the primary user-facing content.

P3 browser/UI acceptance remains in progress. Future E1 UI polish should use `dialogue_group_id` continuation metadata so cross-Shot projections render as one continuing line rather than unrelated duplicates.

## 13. P4 current truth

P4 Draft-guided Scene/Prop is implemented but local/model acceptance is pending. It must still re-verify Draft hints against actual visual Evidence and cannot turn Draft prose directly into Final Scene/Prop.

P5 is paused until Episode-context Breakdown semantics are locally accepted.

## 14. Testing / CI discipline

Do not consume hosted GitHub Actions quota for this work. Use `[skip ci]` for remote documentation/development commits where applicable. Historical CI must remain historical.

E1 test file:

```text
engine/tests/v2/test_breakdown_p2_fusion_episode_v2.py
```

Do not claim it passed locally unless an actual local pytest run was executed.

## 15. Documentation sync rule

Keep these aligned when current status/architecture changes:

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/BREAKDOWN_EPISODE_CONTEXT_PLAN.md
docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md when runtime/acceptance changes
latest docs/sessions/*.md handoff
```

## 16. Next safe work

```text
A. locally re-run one real short-drama Episode on current main
   → cross-Shot dialogue check
   → same-scene closeup/blur check
   → genuine scene-change check

B. if E1 behavior is accepted
   → implement P2-E2 overlapping continuous-window Qwen3-VL

C. continue P3/P4 acceptance in parallel
```

Do not upgrade acceptance status without evidence and do not advance P5 before the Episode-context semantic baseline is stable.
