# AI Drama Studio — Agent Entry Rules

Current formal architecture: **Reference Video V2**. Formal Character baseline: **Character V10.1 + explicit Shot Character Assignment**. Breakdown-first backend implementation has completed **P1 + P2.1–P2.6 tooling**. Current truth is **P2 implementation complete / real-video acceptance pending / P3 next**.

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

Do not let historical F01–F06 documents, old Frozen snapshots or Character V1–V10 plans override current wiring. Compatibility filenames such as `character_runtime_v6.py` do not define the formal algorithm version.

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
P1 Draft data/runtime/history            COMPLETE
P2.1 Provider/raw Evidence sidecar       COMPLETE
P2.2 ASR Provider                        COMPLETE
P2.3 OCR Observation Provider            COMPLETE
P2.4 anonymous Shot VLM semantics        COMPLETE
P2.5 deterministic multimodal Fusion     COMPLETE
P2.6 production orchestrator/API         COMPLETE
P2.6 Windows/preflight/acceptance tools  COMPLETE
P2 real-video acceptance execution       PENDING
P3 structured 02 拉片 UI                 NEXT
```

Do not equate “acceptance tooling exists” with “real short-drama quality was accepted”. The repository has no real short-drama sample, so a real user Windows run is still needed for an acceptance `PASS` report.

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

Batch Breakdown must remain sequential by `Episode.sort_order`; do not parallelize heavy model work by default.

## 4. Anonymous Draft is not identity truth

```text
人物A / subject_A / LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
Breakdown Evidence != Final Asset/Binding truth
```

P2 must never write:

```text
Character
Scene
Prop
AssetRevision
ShotCharacterBinding
ShotSceneBinding
ShotPropBinding
```

VLM prose, ASR speaker labels and OCR text are context/evidence only.

## 5. Shot / history rules

Reference Video V2 remains authoritative:

```text
Project / Episode
FFmpeg / FFprobe
integer microseconds
TransNetV2 Shot boundaries
ShotRevision / ShotRevisionItem
Reference Clip / thumbnail / keyframes
```

`Shot.id` is not a permanent historical anchor across reruns/restores. Breakdown history anchors to exact ShotRevision/ShotRevisionItem.

New Current ShotRevision marks incompatible active Breakdown Runs STALE. Never guess-migrate old Draft by ordinal/time similarity.

## 6. P2 Provider boundaries

### ASR

```text
FasterWhisperASRProvider
faster-whisper==1.2.1
large-v3
word timestamps
```

Cross-Shot ASR stays unbound until Fusion. ASR speaker does not map directly to Character.

### OCR — frozen baseline

```text
RapidOCROCRProvider
rapidocr==3.9.2
PP-OCRv6 small
ONNX Runtime
default CPU
```

Exact historical Reference Clips are sampled across each Shot. OCR observations are point evidence with geometry; Fusion owns dedupe/duration inference.

**Do not redo OCR** unless a concrete regression requires a minimal fix.

### VLM

```text
Qwen3VLSemanticProvider
Qwen/Qwen3-VL-4B-Instruct
strict anonymous shot semantics
```

It reuses the isolated TransVLM Python/CUDA environment but not the transition-finetuned checkpoint. VLM does not duplicate ASR/OCR transcription.

## 7. P2 Fusion cannot-link rule

Draft-level subject grouping is deliberately conservative.

If one normalized appearance description appears for two simultaneous subjects in any Shot of a Scene Segment:

```text
that appearance signature is ambiguous
→ cannot be used for cross-Shot LocalSubject merge in that segment
→ fall back to shot-local anonymous keys
```

Prefer duplicate anonymous subjects over a false identity merge. Real identity resolution belongs to Character V10.1 / later P5.

## 8. Character V10.1 is protected

Formal chain:

```text
YOLOX Person Detection
→ capture-first Person Evidence
→ mature MOT
→ YoutuReID project-level identity
→ RESOLVED / UNRESOLVED
→ explicit Shot × known-Character Assignment
→ Final Character Gate
→ Character + ShotCharacterBinding
```

Never relax these current invariants for prettier Breakdown output:

```text
new identity requires >=3 independent Shots
new identity requires >=3 model-usable images
same-sample cannot-link is hard
high-quality Face conflict is hard negative
ambiguous winner remains unresolved/unassigned
current Final Shot binding comes from explicit shot_presence_assignments
```

Draft/VLM/ASR context may later be a soft search prior; it cannot override identity evidence/gates.

## 9. P2 local acceptance

See:

```text
docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md
```

Formal states:

```text
STRUCTURAL_FAIL
NEEDS_HUMAN_REVIEW
NEEDS_TUNING
PASS
```

A real-video `PASS` requires structural checks plus explicit human review with every required score >=4/5 and no blocking issue. Machine checks cannot self-certify quality.

Windows runner:

```text
scripts/run_breakdown_p2_windows.ps1
```

Do not require GitHub Actions for this local acceptance path. The user explicitly requested not to consume hosted CI quota.

## 10. Current test/reporting discipline

Do not claim whole-repository CI is green. Do not report historical CI results as fresh P2.6 results.

For this P2.6 work:

```text
GitHub hosted Actions: intentionally not run/checked
new P2.6 Python sources/tests: local syntax compilation performed during development
full repository pytest: no fresh claim in this execution environment
real-video Windows run: pending
```

## 11. Git work

Default branch is `main`.

When modifying repository remotely through the GitHub tool, follow the GitHub tool safety workflow: inspect current head/diff, isolate the intended changes, and fast-forward without force. Do not create a PR unless the user asks.

When hosted CI quota is unavailable, use `[skip ci]` for these development commits and do not query/re-run Actions.

## 12. Documentation sync rule

Formal architecture/Breakdown/Character changes must keep these aligned:

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
docs/BREAKDOWN_P2_SIDECAR_CONTRACT.md
docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md when P2 runtime/acceptance changes
docs/ASSET_CHARACTER_RECOGNITION_V10_1.md when Character changes
latest docs/sessions/*.md handoff
```

## 13. Next safe phase

P2 backend implementation is complete. Next code phase is **P3 — 02 拉片 structured Draft UI**.

P3 must consume the existing P2 background task/read APIs. It must not implement a second ASR/OCR/VLM/Fusion path in the frontend.
