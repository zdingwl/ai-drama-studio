# AI Drama Studio — Project State

> **Last synchronized:** 2026-08-28 18:12 +08:00  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Branch:** `main`  
> **Architecture:** Reference Video V2  
> **FastAPI app version:** `2.4.1`  
> **Formal Character runtime:** Character V10.1  
> **Breakdown-first:** **P1/P2 IMPLEMENTATION CONDITIONAL PASS / P2-E1 EPISODE-CONTEXT FUSION IMPLEMENTED, LOCAL-REAL ACCEPTANCE PENDING / P2.6 REAL-MODEL ACCEPTANCE NOT PASSED / P3 UI ACCEPTANCE IN PROGRESS / P4 LOCAL ACCEPTANCE PENDING**

## 1. Current-state source of truth

New-conversation recovery order:

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
→ latest docs/sessions/* handoff
→ current code/tests
```

Truth split:

```text
PROJECT_STATE + CURRENT_IMPLEMENTATION_MANIFEST + current code/tests = executable CURRENT
BREAKDOWN_EPISODE_CONTEXT_PLAN = accepted current Breakdown migration target
BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN = wider Breakdown-first / asset phase plan
BREAKDOWN_DRAFT_DATA_CONTRACT = frozen P1 Draft contract
BREAKDOWN_P2_SIDECAR_CONTRACT = immutable P2 Evidence contract
BREAKDOWN_P2_LOCAL_ACCEPTANCE = real runtime / quality acceptance gate
```

## 2. Accepted product principle

Core principle remains:

> **先看懂，再识别，再回填。**

The Breakdown semantic principle is now explicit:

> **Shot 是拉片结果的最小展示单位，不是 AI 理解内容的上下文边界。**

Accepted flow:

```text
Original Episode
→ Preprocess
→ Shot Detection + ShotRevision
→ Episode ASR / OCR
→ continuous / contextual Video Understanding
→ Episode-context Fusion
→ anonymous structured Breakdown Draft
→ Draft-guided Character / Scene / Prop evidence extraction
→ Global Asset Resolution + Final Shot Bindings
→ identity/asset fill-back
→ Final Breakdown
→ remake
```

Semantic boundary is unchanged:

```text
人物A / LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
raw Evidence / Draft != Final binding truth
ASR speaker != Character
```

## 3. Reference Video V2 baseline — unchanged

Formal media chain:

```text
Project / Episode
→ FFprobe / FFmpeg preprocess
→ TransNetV2 Shot boundaries
→ integer microseconds
→ ShotRevision / ShotRevisionItem
→ per-Shot Reference Clip / thumbnail / keyframes
```

Shot boundaries remain authoritative timing/edit boundaries. They no longer imply the maximum semantic context for Breakdown analysis.

Historical Breakdown always anchors to the exact frozen ShotRevision/ShotRevisionItem. `Shot.id` is not a permanent historical anchor. Heavy media/model jobs remain sequential by default.

## 4. P1 Draft contract — unchanged

Formal tables remain:

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

Important: `SceneSegmentDraft` already supports an Episode-time range spanning multiple Shots. E1 therefore changes the derived Fusion policy rather than replacing the P1 schema.

P1 remains part of the **P1/P2 implementation CONDITIONAL PASS**; this is not real-model quality certification.

## 5. P2 current production chain

Production entry:

```text
engine/app/breakdown_p2_pipeline_v1.py
pipeline profile = breakdown-p2-full-v1
```

Execution now is:

```text
create frozen PROCESSING BreakdownRun
→ Episode ASR
→ OCR
→ current Qwen3-VL visual semantics
→ P2-E1 Episode-context Fusion
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Providers / components:

```text
P2.1 engine/app/breakdown_p2_sidecar_v1.py
P2.2 engine/app/breakdown_p2_asr_v1.py
P2.3 engine/app/breakdown_p2_ocr_runtime_v1.py
P2.4 engine/app/breakdown_p2_vlm_runtime_v1.py
legacy Fusion baseline engine/app/breakdown_p2_fusion_v1.py
production E1 Fusion engine/app/breakdown_p2_fusion_episode_v2.py
P2.6 orchestrator engine/app/breakdown_p2_pipeline_v1.py
P2.6 acceptance engine/app/breakdown_p2_acceptance_v1.py
```

Formal endpoints remain unchanged:

```text
POST /api/episodes/{episode_id}/tasks/breakdown
POST /api/projects/{project_id}/tasks/breakdown-batch
GET  /api/breakdown/p2/runtime-preflight
POST /api/breakdown-runs/{run_id}/p2-acceptance
```

Batch Breakdown remains sequential by `Episode.sort_order`; heavy P2 execution is globally serialized.

## 6. P2-E1 — Episode-context Fusion implemented

Current production Fusion profile:

```text
breakdown-p2-fusion-episode-context-e1-v2
```

Status:

```text
implementation = IMPLEMENTED ON MAIN
unit coverage  = ADDED
local-real short-drama acceptance = PENDING
```

### 6.1 Scene continuity

Old behavior could split a Scene whenever a Shot had no usable location signature. E1 changes this to conservative continuity:

```text
strong scene/location evidence establishes current Scene

UNKNOWN / missing / generic “室内/房间” / background-poor closeup
→ inherit current Scene

compatible specificity
病房 → 医院病房
客厅 → 家中客厅
→ remain same Scene; prefer the more specific anchor

strong location contradiction
or clear INT ↔ EXT contradiction
→ new Scene Segment
```

The rule is intentionally:

```text
看不出来 != 换场
```

### 6.2 Cross-Shot dialogue

Raw ASR is already Episode-level. E1 makes that Episode truth survive Fusion:

```text
ASR_SEGMENT = dialogue text truth
Shot-local DIALOGUE TimelineEvent = time projection of that dialogue
```

A sentence crossing a cut is no longer rewritten into partial sentence text. Each overlapping Shot projection keeps the full ASR segment text and shares:

```text
dialogue_group_id = asr_segment_id
dialogue_source_start_us / dialogue_source_end_us
projection_start_us / projection_end_us
projection_index / projection_count
continues_from_previous_shot / continues_to_next_shot
```

ASR_WORD evidence remains immutable and is attached to the appropriate projection as SUPPORT provenance/confidence evidence.

No historical sidecar is rewritten.

### 6.3 Compatibility strategy

P1 `TimelineEvent` is still Shot-local. E1 does not perform a destructive DB migration; cross-Shot dialogue grouping is represented through stable metadata while preserving all existing P1/P3/P4 readers.

The top-level pipeline profile remains `breakdown-p2-full-v1`; the exact Fusion sub-profile is stored in provenance.

## 7. P2-E2 / E3 / E4 — not yet implemented

The accepted target is documented in:

```text
docs/BREAKDOWN_EPISODE_CONTEXT_PLAN.md
```

Current limitation that must remain explicit:

```text
P2.4 Qwen3-VL still analyzes one historical Reference Clip at a time.
```

Therefore E1 is **not** full continuous Episode VLM yet.

Planned order:

```text
P2-E2 overlapping continuous-window Qwen3-VL
→ P2-E3 Scene/prev/current/next + ASR/OCR contextual Shot refinement
→ P2-E4 final Episode-context Fusion using window evidence
```

The long-term rule is:

```text
Shot boundary != dialogue sentence boundary
Shot boundary != scene boundary
Shot boundary != maximum semantic context
```

## 8. P2.4 Chinese Draft policy — unchanged

Production Qwen3-VL natural-language Draft policy remains:

```text
prompt_profile = breakdown-p2-vlm-zh-draft-v1
draft_text_language = zh-CN
```

VLM Scene / Shot / anonymous-subject / action / prop prose is generated in Simplified Chinese. Machine JSON/enums remain stable English tokens. ASR dialogue and OCR observations preserve raw source text.

## 9. P2 acceptance status — still NOT PASSED for real models

User implementation review remains:

```text
P1/P2 implementation acceptance = CONDITIONAL PASS
```

P2-E1 code status does not change the real-model gate:

```text
P2.6 Windows / real-model acceptance = NOT PASSED
real short-drama acceptance evidence = INCOMPLETE
human acceptance PASS report         = NOT AVAILABLE
```

Required close gate now includes E1 behavior:

```text
1. provision/verify OCR runtime + model
2. provision/verify Qwen3-VL runtime + model
3. run a real short-drama Episode
4. ASR → OCR → VLM → Episode-context E1 Fusion → P1 validator
5. verify cross-Shot dialogue remains whole
6. verify same-scene closeup/blurred shots inherit Scene
7. verify genuine scene changes still split
8. generate acceptance report + human review
9. required scores >=4/5 and no blocking issues
```

Only then may P2.6 become `PASS`.

## 10. P3 — 02 拉片 UI

Current user-facing split is:

```text
02 拉片
├─ 镜头管理
│  └─ simplified Shot review/edit workbench
└─ 拉片结果
   ├─ Scene / Shot results
   ├─人物 / anonymous subject semantics
   ├─ dialogue
   ├─ action
   ├─ prop hints
   └─ original Reference Clip
```

Technical Evidence/provenance remains stored but is not the primary normal-user presentation.

Status:

```text
implementation on main      = IMPLEMENTED
browser/local UI acceptance = IN PROGRESS
fully accepted/closed       = NO
```

P3 should later use E1 `dialogue_group_id` / continuation metadata to present a cross-Shot sentence as “对白继续” rather than visually treating each projection as an unrelated duplicate.

## 11. Formal Character V10.1 — unchanged/protected

```text
YOLOX Person Detection
→ capture-first Person Evidence
→ mature MOT
→ YoutuReID project-level identity
→ RESOLVED / UNRESOLVED
→ explicit Shot × known-Character Assignment
→ Final Character Gate
```

Protected invariants remain:

```text
new identity requires >=3 independent Shots / >=3 usable images
same-sample cannot-link
high-quality Face hard conflicts
explicit Shot Assignment is current Final binding source
VLM/Draft cannot create Character
ASR speaker cannot create Character
```

P2-E1 changes no Character code, identity threshold, resolver or Final Gate.

## 12. P4 — Draft-guided Scene / Prop Evidence

P4 remains implemented:

```text
engine/app/breakdown_asset_guidance_v1.py
profile = breakdown-asset-guidance-p4-v1
engine/app/asset_semantics_p4_v1.py
```

Safety gates remain:

```text
only current revision-safe READY Draft may guide
STALE/history/FAILED/PROCESSING Draft = never guidance
Draft Scene/Prop = hypothesis only
visual re-verification is mandatory
observed=false Draft prop = no PropCandidate
verified prop threshold >=0.45
unguided new prop threshold >=0.68
```

P4 status:

```text
implementation = IMPLEMENTED
local/model acceptance = PENDING
Final Scene/Prop quality PASS = NO
```

P5 Draft ↔ Character safe integration is paused until the new Episode-context Breakdown semantic baseline is locally accepted. This avoids building identity-context integration on top of known Shot-centric semantic errors.

## 13. Current phase pointer

```text
P0 planning/contracts                          = COMPLETE
P1 implementation                              = CONDITIONAL PASS
P2 implementation                              = CONDITIONAL PASS
  P2.1 sidecar                                 = IMPLEMENTED
  P2.2 Episode ASR                             = IMPLEMENTED
  P2.3 OCR                                     = IMPLEMENTED; real acceptance pending
  P2.4 single-Reference-Clip VLM               = IMPLEMENTED; limitation acknowledged
  P2-E1 Episode-context Fusion                 = IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
  P2-E2 continuous-window VLM                  = PLANNED
  P2-E3 contextual Shot refinement             = PLANNED
  P2-E4 final Episode-context Fusion           = PLANNED
  P2.6 orchestration/acceptance tooling        = IMPLEMENTED
P2.6 Windows/real-model acceptance             = NOT PASSED
P3 02 拉片 UI                                  = IMPLEMENTED / UI ACCEPTANCE IN PROGRESS
P4 Draft-guided Scene/Prop evidence            = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character safe integration          = PLANNED / PAUSED
P6 Final fill-back + renderers                 = PLANNED
P7 downstream remake integration               = PLANNED
```

## 14. Validation / CI truth

Hosted GitHub Actions are intentionally not used for this work. Historical CI remains historical.

New E1 tests are present at:

```text
engine/tests/v2/test_breakdown_p2_fusion_episode_v2.py
```

They cover the E1 rules, but this session does not claim a fresh locally executed pytest PASS because the user runtime was not available through this connector session.

Outstanding real gates:

```text
P2-E1 real Episode behavior
P2.6 full Windows/model acceptance
P3 browser/UI acceptance
P4 local/model acceptance
```

## 15. Next safe work

Immediate order:

```text
A. run/re-run AI 拉片 on one real short-drama Episode with current main
   → inspect a dialogue that crosses a cut
   → inspect a Scene with wide shot + closeups/inserts/blurred backgrounds
   → confirm genuine scene changes still split

B. after E1 local behavior is accepted
   → implement P2-E2 overlapping continuous-window Qwen3-VL

C. keep P3/P4 acceptance active
   → do not mark P2.6/P3/P4 PASS without real evidence
```

Do not advance P5 until the Episode-context semantic baseline has stopped producing the known cross-Shot dialogue and same-scene fragmentation errors.
