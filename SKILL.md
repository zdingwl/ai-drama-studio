---
name: ai-drama-studio-reference-video-v2
version: 3.11.0
description: AI Drama Studio Reference Video 本地短剧重制规则；Character V10.1 为正式人物基线；P2-E1 Episode-context Fusion、P2-E2 overlapping-window Qwen3-VL 与 P2-E3 contextual Shot refinement 已在 main，真实 Windows/短剧验收仍待完成，E4 为下一阶段。
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
BREAKDOWN_EPISODE_CONTEXT_PLAN = active Breakdown migration TARGET
BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN = wider downstream TARGET
```

Old Shot-centric assumptions, Frozen docs, old Character versions or old chat do not override current wiring.

## 1. Current baseline

```text
Architecture: Reference Video V2
FastAPI: 2.4.1
Default branch: main
Formal Character runtime: Character V10.1
P1/P2 implementation acceptance: CONDITIONAL PASS
P2-E1 Episode-context Fusion: IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E2 continuous-window VLM: IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E3 contextual Shot refinement: IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E4 final Episode-context Fusion: PLANNED / NEXT
P2.6 Windows / real-model acceptance: NOT PASSED
P3 02 拉片 UI: IMPLEMENTED / UI ACCEPTANCE IN PROGRESS
P4 Draft-guided Scene/Prop: IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character: PLANNED / PAUSED
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

Core rules:

> **先看懂，再识别，再回填。**

> **Shot 是拉片结果的最小展示单位，不是 AI 理解内容的上下文边界。**

## 2. Current Breakdown production flow

```text
Original Episode
→ Preprocess
→ Shot Detection + ShotRevision
→ frozen PROCESSING BreakdownRun
→ Episode ASR
→ OCR
→ P2-E2 overlapping Episode-window Qwen3-VL
→ P2-E3 contextual Shot refinement
→ one exact-Shot immutable VLM_OUTPUT sidecar
   payload.e2_semantic = preserved E2 visual result
   payload.semantic    = E3 result consumed by Fusion
→ P2-E1 Episode-context Fusion
→ anonymous P1 Draft
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Formal orchestrator:

```text
engine/app/breakdown_p2_pipeline_v1.py
profile = breakdown-p2-full-v1
ASR → OCR → VLM
```

E3 stays inside the formal `VLM` Provider boundary so the P2 component list, APIs and frozen sidecar schema do not change.

Production VLM:

```text
engine/app/breakdown_p2_vlm_runtime_v1.py
→ E2 engine/app/breakdown_p2_vlm_episode_v2.py
   profile = breakdown-p2-vlm-episode-window-e2-v1
   runner = scripts/run_breakdown_vlm_qwen3_episode_windows.py
→ E3 engine/app/breakdown_p2_refinement_v1.py
   profile = breakdown-p2-contextual-shot-refinement-e3-v1
   runner = scripts/run_breakdown_refinement_qwen3.py
```

Production Fusion:

```text
engine/app/breakdown_p2_fusion_episode_v2.py
profile = breakdown-p2-fusion-episode-context-e1-v2
```

Batch remains sequential by `Episode.sort_order` and heavy jobs remain globally serialized.

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

Shot boundaries remain exact timing/edit coordinates, but not semantic-context limits. Historical Breakdown always anchors to the exact frozen ShotRevision/ShotRevisionItem.

## 4. P1 / identity semantic boundaries

Formal P1 entities remain unchanged:

```text
BreakdownRun
SceneSegmentDraft
ShotSemanticDraft
LocalSubject / ShotLocalSubject
TimelineEvent / TimelineEventSubject
DraftPropHint / DraftPropOccurrence
BreakdownEvidenceLink
```

Lifecycle:

```text
PROCESSING / READY / READY_WITH_WARNINGS / FAILED / STALE
```

Hard semantic boundaries:

```text
LocalSubject / 人物A != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
raw Evidence / Draft != Final binding truth
```

E1/E2/E3 do not justify a destructive P1 schema migration.

## 5. P2-E1 rules

Scene:

```text
strong scene evidence establishes current Scene
missing / UNKNOWN / generic / background-poor closeup → inherit current Scene
compatible specificity → same Scene
strong location contradiction or explicit INT ↔ EXT contradiction → new Scene
```

Rule: `看不出来 != 换场`.

Dialogue:

```text
ASR_SEGMENT = Episode-time dialogue text truth
ASR_WORD = timing/confidence SUPPORT evidence
Shot DIALOGUE TimelineEvent = projection
```

Cross-Shot dialogue keeps the full sentence and shared `dialogue_group_id/asr_segment_id`, source/projection ranges and continuation flags. Historical ASR sidecars stay immutable.

## 6. P2-E2 rules

Default:

```text
window target = 24s
allowed config = 20..40s
overlap = 25%
allowed overlap = 10..50%
window edges = Shot-aligned
every Shot fully covered by >=1 window
window inference = sequential
media = READY preprocess proxy, then Episode source fallback
```

Each window passes continuous video + exact covered Shot boundaries to Qwen. Prompt requirements:

```text
cut != scene change
closeup/blur/insert may borrow adjacent context only with evidence
otherwise UNCERTAIN
no ASR/OCR transcription inside visual E2
anonymous subjects only
no Final Character/Scene/Prop/Binding IDs
Simplified Chinese generated prose
```

Window output contract includes:

```text
window_summary
scene_change_candidates
subject_continuity_hints
prop_continuity_hints
shots[]
  revision_item_id
  scene_continuity = SAME|NEW_SCENE|UNCERTAIN
  scene_basis = DIRECT|CONTEXT|MIXED|UNCERTAIN
  context_note
  semantic.scene/shot/subjects/events/props
```

If a Shot is in multiple windows, rank candidates by strongest surrounding context, then center proximity, then earlier window. Store selected/supporting window provenance in `VLM_OUTPUT.payload.episode_window`.

Only new BreakdownRuns use E2/E3. Never rewrite historical sidecars.

CLI E2 tuning options:

```text
--vlm-window-seconds
--vlm-window-overlap-ratio
```

## 7. P2-E3 contextual Shot refinement

Status: implemented on `main`, local-real acceptance pending.

E3 is a second **text-only Qwen** pass after E2. It does not re-open video and cannot invent new visual truth. For each exact Shot it consumes:

```text
provisional Scene context
+ previous/current/next E2 Shot semantics
+ selected/supporting E2 window summaries
+ overlapping ASR_SEGMENT context
+ overlapping OCR observations
```

Output remains the same anonymous semantic shape used by Fusion:

```text
scene
shot
subjects
events
props
```

Safety/grounding rules:

```text
only current Shot may be refined
neighbor-only people/objects cannot be imported into current Shot
current E2 subject labels are the only allowed subject labels
ASR text is read-only dialogue truth; never rewrite/translate or bind speaker identity
OCR text is read-only observation
Scene UNKNOWN can be resolved from context only when evidence supports it
shot type/camera/composition stay grounded in current E2 visual evidence
no Final business IDs
Simplified Chinese generated prose
```

Compatibility/storage:

```text
final VLM sidecar remains breakdown-p2-evidence-v1
VLM_OUTPUT stays exact Shot-bound
payload.e2_semantic = original E2 visual semantic
payload.semantic = E3 refined semantic
payload.contextual_refinement = E3 provenance
```

A malformed individual E3 Shot may fall back to E2 with a warning. Missing E3 runtime or whole-pass inference failure makes the production VLM component fail closed.

## 8. P2-E4 target

Not implemented yet.

```text
P2-E4
E2 window continuity
+ E3 refined Shot semantics
+ Episode ASR/OCR
→ final Episode-context Scene / anonymous-subject / dialogue / Shot projection Fusion
```

E4 should make explicit E2/E3 continuity evidence primary and keep E1 conservative inheritance as fallback.

Long-term rules:

```text
Shot boundary != dialogue sentence boundary
Shot boundary != scene boundary
Shot boundary != maximum semantic context
```

Do not claim full Episode-context Breakdown is accepted/closed while E4 and real-model acceptance are outstanding.

## 9. Provider boundaries

ASR:

```text
FasterWhisperASRProvider
large-v3
word timestamps
Episode audio
```

OCR:

```text
RapidOCROCRProvider
PP-OCRv6 small
ONNX Runtime
```

VLM production runtime:

```text
Qwen3-VL-4B-Instruct
E2 overlapping Episode windows
→ E3 text-only contextual refinement
anonymous semantics only
```

VLM-generated prose is Simplified Chinese; machine JSON/enums remain stable English tokens; ASR/OCR raw source text remains untranslated.

## 10. Character V10.1 protected baseline

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
new identity >=3 independent Shots
new identity >=3 model-usable images
same-sample cannot-link
high-quality Face hard conflict
ambiguous winner remains unresolved/unassigned
current Final ShotCharacterBinding = explicit shot_presence_assignments
```

Episode-context semantics can guide later search but cannot override these identity gates.

## 11. P3 / P4 / P5

P3 is implemented with `镜头管理 + 拉片结果`; technical provenance is backend truth but not the normal-user primary display. UI acceptance remains in progress.

P4 Draft-guided Scene/Prop is implemented but requires current-revision visual re-verification; local/model acceptance is pending.

P5 Draft ↔ Character safe integration remains paused until E2/E3/E4 Episode-context semantics are locally stable.

## 12. P2.6 acceptance

Current:

```text
P1/P2 implementation = CONDITIONAL PASS
P2-E1 local-real = PENDING
P2-E2 local-real Qwen/Windows = PENDING
P2-E3 local-real contextual refinement = PENDING
P2.6 Windows/real-model = NOT PASSED
```

A real PASS still requires a new real short-drama run through `ASR → OCR → E2 VLM → E3 refinement → E1 Fusion → P1 validator`, human review, every required score >=4/5 and no blocking issue.

Never write `P2 ACCEPTED`, `P2 CLOSED` or `P2.6 PASS` without that evidence.

## 13. Testing / CI discipline

Do not consume hosted GitHub Actions quota. Prefer local verification and use `[skip ci]` for remote commits.

Current Episode-context unit coverage:

```text
engine/tests/v2/test_breakdown_p2_fusion_episode_v2.py
engine/tests/v2/test_breakdown_p2_vlm_episode_v2.py
engine/tests/v2/test_breakdown_p2_refinement_v1.py
```

Do not report tests/model quality as passed unless actually executed in the local project runtime.

## 14. Phase pointer

```text
P0 COMPLETE
P1 CONDITIONAL PASS
P2 implementation CONDITIONAL PASS
P2-E1 IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E2 IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E3 IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E4 PLANNED / NEXT
P2.6 NOT PASSED
P3 IMPLEMENTED / UI ACCEPTANCE IN PROGRESS
P4 IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 PLANNED / PAUSED
P6 PLANNED
P7 PLANNED
```

Immediate safe work: run a new real Episode on the composite E2+E3 production VLM, inspect Scene continuity/genuine changes/E3 grounding/anonymous subject and prop continuity/E1 dialogue, then implement E4 only after the new semantic baseline behaves correctly.
