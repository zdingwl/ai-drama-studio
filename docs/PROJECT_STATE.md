# AI Drama Studio — Project State

> **Last synchronized:** 2026-08-28 19:05 +08:00  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Branch:** `main`  
> **Architecture:** Reference Video V2  
> **FastAPI app version:** `2.4.1`  
> **Formal Character runtime:** Character V10.1

## 1. Current truth

```text
P1/P2 implementation acceptance      = CONDITIONAL PASS
P2-E1 Episode-context Fusion          = IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E2 continuous-window Qwen3-VL      = IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E3 contextual Shot refinement      = PLANNED / NEXT
P2-E4 final Episode-context Fusion    = PLANNED
P2.6 Windows / real-model acceptance  = NOT PASSED
P3 02 拉片 UI                         = IMPLEMENTED / UI ACCEPTANCE IN PROGRESS
P4 Draft-guided Scene/Prop            = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character                  = PLANNED / PAUSED
```

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

Executable CURRENT truth is `PROJECT_STATE + CURRENT_IMPLEMENTATION_MANIFEST + current code/tests`. `BREAKDOWN_EPISODE_CONTEXT_PLAN` is the accepted active Breakdown migration target.

## 2. Product principle

> **先看懂，再识别，再回填。**

> **Shot 是拉片结果的最小展示单位，不是 AI 理解内容的上下文边界。**

Accepted flow:

```text
Original Episode
→ Preprocess
→ Shot Detection + ShotRevision
→ Episode ASR / OCR
→ overlapping Episode-window Video Understanding
→ Episode-context Fusion
→ anonymous structured Breakdown Draft
→ Draft-guided Character / Scene / Prop evidence
→ Global Asset Resolution + Final Shot Bindings
→ identity/asset fill-back
→ Final Breakdown
→ remake
```

Semantic boundaries remain hard:

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
raw Evidence / Draft != Final binding truth
```

## 3. Media / history baseline

```text
FFprobe / FFmpeg preprocess
TransNetV2 Shot boundaries
integer microseconds
ShotRevision / ShotRevisionItem
Reference Clip / thumbnail / keyframes
manual boundary edit / split / merge / rerun / restore
```

Shot boundaries are authoritative editing/timing coordinates, not maximum semantic context. Historical Breakdown remains anchored to exact frozen ShotRevision/ShotRevisionItem and is never silently rebound to Current Shot IDs.

## 4. P1 contract

Formal Draft tables/lifecycle remain unchanged:

```text
BreakdownRun
SceneSegmentDraft
ShotSemanticDraft
LocalSubject / ShotLocalSubject
TimelineEvent / TimelineEventSubject
DraftPropHint / DraftPropOccurrence
BreakdownEvidenceLink

PROCESSING / READY / READY_WITH_WARNINGS / FAILED / STALE
```

E1/E2 deliberately avoid destructive P1/P2 schema migration.

## 5. Current P2 production chain

```text
Episode Current ShotRevision
→ create frozen PROCESSING BreakdownRun
→ Episode ASR
→ OCR observations
→ P2-E2 overlapping Episode-window Qwen3-VL
→ existing immutable per-Shot VLM_OUTPUT sidecar contract
→ P2-E1 Episode-context Fusion
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Production entry remains:

```text
engine/app/breakdown_p2_pipeline_v1.py
pipeline profile = breakdown-p2-full-v1
provider order = ASR → OCR → VLM
```

Production VLM stable import now resolves to E2:

```text
engine/app/breakdown_p2_vlm_runtime_v1.py
→ engine/app/breakdown_p2_vlm_episode_v2.py
profile = breakdown-p2-vlm-episode-window-e2-v1
runner = scripts/run_breakdown_vlm_qwen3_episode_windows.py
```

Production Fusion remains E1:

```text
engine/app/breakdown_p2_fusion_episode_v2.py
profile = breakdown-p2-fusion-episode-context-e1-v2
```

Formal APIs stay unchanged. Batch remains strictly sequential by `Episode.sort_order`; heavy P2 jobs remain globally serialized.

## 6. P2-E1 behavior

Scene continuity:

```text
UNKNOWN / missing / generic / background-poor closeup → inherit current Scene
compatible specificity → same Scene
strong location contradiction or explicit INT ↔ EXT contradiction → new Scene
```

Dialogue continuity:

```text
ASR_SEGMENT = Episode-time text truth
Shot DIALOGUE TimelineEvent = projection
```

Cross-Shot projections keep the full segment text and share dialogue-group/continuation metadata. Raw ASR_WORD evidence remains immutable.

## 7. P2-E2 behavior

Default window policy:

```text
24s target
20..40s allowed configuration
25% overlap
10..50% allowed overlap
shot-aligned boundaries
sequential inference
READY proxy preferred, Episode source fallback
```

Each window provides Qwen continuous video plus exact Shot boundaries. Qwen first reasons over the window and then produces anonymous per-Shot semantics. It is explicitly told that cut != scene change and that closeups may borrow adjacent visual context only when supported.

For a Shot covered by multiple windows, E2 selects the candidate with the strongest surrounding context. `VLM_OUTPUT.payload.episode_window` records selected/supporting windows plus:

```text
scene_continuity = SAME|NEW_SCENE|UNCERTAIN
scene_basis = DIRECT|CONTEXT|MIXED|UNCERTAIN
context_note
```

The final sidecar is still exact-Shot `VLM_OUTPUT`; no new Final Asset ID or direct binding path is introduced.

CLI supports optional:

```text
--vlm-window-seconds
--vlm-window-overlap-ratio
```

Historical Runs are immutable; only new AI 拉片 runs receive E2.

## 8. P2-E3 / E4

```text
P2-E3 = PLANNED / NEXT
P2-E4 = PLANNED
```

E3 will combine E2 window context with Scene + previous/current/next Shot + overlapping ASR/OCR for contextual Shot refinement. E4 will make window evidence the main Episode-time Scene/anonymous-subject continuity evidence and keep E1 rules as conservative fallback.

Do not describe E2 implementation as “full Episode-context Breakdown accepted/closed”.

## 9. P2.6 real-model acceptance

Still:

```text
P2.6 Windows / real-model acceptance = NOT PASSED
real short-drama acceptance evidence = incomplete
human PASS report = unavailable
```

Required next real run must verify both E1 and E2:

```text
strict runtime/model readiness
→ real short-drama Episode
→ ASR → OCR → E2 VLM → E1 Fusion → P1 validator
→ same-scene wide/closeup/insert continuity
→ genuine scene changes
→ anonymous subject / key-prop continuity
→ cross-Shot full dialogue truth
→ acceptance report + human review
→ every required score >=4/5
→ no blocking issues
```

Only then may P2.6 become PASS.

## 10. P3 / P4 / Character

P3 `02 拉片` remains implemented with 镜头管理 + user-facing 拉片结果. Technical Evidence/provenance is backend truth but not primary normal-user display. UI acceptance is still in progress.

P4 Draft-guided Scene/Prop remains implemented and requires current-revision visual re-verification; Draft cannot bypass Final Asset evidence.

Character V10.1 is unchanged/protected:

```text
YOLOX person detection
→ capture-first evidence
→ mature MOT
→ YoutuReID project identity
→ RESOLVED / UNRESOLVED
→ explicit Shot × known-Character Assignment
→ Final Character Gate
```

Same-sample cannot-link, face hard conflicts, >=3 independent Shots/images for new identity and explicit Shot Assignment remain protected. E1/E2 do not modify Character code.

## 11. Validation reality

Added unit coverage:

```text
engine/tests/v2/test_breakdown_p2_fusion_episode_v2.py
engine/tests/v2/test_breakdown_p2_vlm_episode_v2.py
```

Hosted GitHub Actions are intentionally not used. This connector session has not executed the user's local pytest/Qwen/CUDA runtime, so it does not claim fresh test PASS or model-quality PASS.

## 12. Current pointer

```text
P0 COMPLETE
P1 CONDITIONAL PASS
P2 implementation CONDITIONAL PASS
P2-E1 IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E2 IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E3 PLANNED / NEXT
P2-E4 PLANNED
P2.6 NOT PASSED
P3 IMPLEMENTED / UI ACCEPTANCE IN PROGRESS
P4 IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 PLANNED / PAUSED
P6 PLANNED
P7 PLANNED
```

Next safe work is a new real Episode BreakdownRun using E2. If runtime behavior is sound, proceed to E3; do not advance P2.6/P3/P4/P5 truth without the corresponding evidence.
