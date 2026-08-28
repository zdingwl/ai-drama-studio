# AI Drama Studio — Project State

> **Last synchronized:** 2026-08-28 19:39 +08:00  
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
P2-E3 contextual Shot refinement      = IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E4 final Episode-context Fusion    = PLANNED / NEXT
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
→ contextual Shot refinement
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

E1/E2/E3 deliberately avoid destructive P1/P2 schema migration.

## 5. Current P2 production chain

```text
Episode Current ShotRevision
→ create frozen PROCESSING BreakdownRun
→ Episode ASR
→ OCR observations
→ P2-E2 overlapping Episode-window Qwen3-VL
→ P2-E3 Scene + neighbor Shot + E2 window + ASR/OCR contextual refinement
→ one immutable per-Shot VLM_OUTPUT sidecar
   payload.e2_semantic = original E2 visual semantic
   payload.semantic = refined E3 semantic used by Fusion
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

E3 is intentionally implemented inside the production VLM Provider boundary. The formal component order and external APIs therefore stay unchanged.

Production VLM stable import now composes E2 + E3:

```text
engine/app/breakdown_p2_vlm_runtime_v1.py
→ E2 engine/app/breakdown_p2_vlm_episode_v2.py
   profile = breakdown-p2-vlm-episode-window-e2-v1
   runner = scripts/run_breakdown_vlm_qwen3_episode_windows.py
→ E3 engine/app/breakdown_p2_refinement_v1.py
   profile = breakdown-p2-contextual-shot-refinement-e3-v1
   runner = scripts/run_breakdown_refinement_qwen3.py
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

CLI supports optional:

```text
--vlm-window-seconds
--vlm-window-overlap-ratio
```

Historical Runs are immutable; only new AI 拉片 runs receive current E2/E3 behavior.

## 8. P2-E3 behavior

E3 is a second **text-only Qwen contextual refinement pass** after E2 visual analysis. It receives only validated structured context; it is not allowed to invent a new visual world.

Per exact Shot input:

```text
provisional Scene context
+ previous Shot E2 semantic
+ current Shot E2 semantic
+ next Shot E2 semantic
+ selected/supporting E2 window summaries
+ overlapping Episode ASR_SEGMENT context
+ overlapping OCR observations
```

Grounding rules:

```text
only current Shot is refined
neighbor-only people/objects cannot be imported into current Shot
only current E2 subject labels may remain in the refined Shot
ASR text stays read-only dialogue truth and cannot become speaker identity
OCR text stays read-only observation
Scene UNKNOWN may be resolved only when context supports it
shot type/camera/composition remain grounded in current E2 visual evidence
Final business IDs remain forbidden
Simplified Chinese generated prose
```

Compatibility is intentionally non-destructive:

```text
VLM_OUTPUT.source_id / exact Shot range stay stable inside the new sidecar
payload.e2_semantic preserves the E2 semantic
payload.semantic carries the E3 semantic consumed by existing Fusion
payload.contextual_refinement stores exact E3 provenance
```

A malformed individual E3 Shot can fall back to its E2 semantic with an explicit warning. Missing E3 runtime or whole E3 inference failure fails the production VLM component closed.

## 9. P2-E4

```text
P2-E4 = PLANNED / NEXT
```

E4 will make explicit E2 window continuity + E3 refined Shot semantics the primary Episode-time Scene/anonymous-subject continuity evidence and retain E1 conservative rules as fallback.

Do not describe E3 implementation as “full Episode-context Breakdown accepted/closed”.

## 10. P2.6 real-model acceptance

Still:

```text
P2.6 Windows / real-model acceptance = NOT PASSED
real short-drama acceptance evidence = incomplete
human PASS report = unavailable
```

Required next real run must verify E1 + E2 + E3 together:

```text
strict runtime/model readiness
→ real short-drama Episode
→ ASR → OCR → E2 window VLM → E3 refinement → E1 Fusion → P1 validator
→ same-scene wide/closeup/insert continuity
→ genuine scene changes
→ E3 improves Shot description/narrative context without importing neighbor-only visual facts
→ anonymous subject / key-prop continuity
→ cross-Shot full dialogue truth with unchanged ASR text
→ acceptance report + human review
→ every required score >=4/5
→ no blocking issues
```

Only then may P2.6 become PASS.

## 11. P3 / P4 / Character

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

Same-sample cannot-link, face hard conflicts, >=3 independent Shots/images for new identity and explicit Shot Assignment remain protected. E1/E2/E3 do not modify Character code.

## 12. Validation reality

Added unit coverage:

```text
engine/tests/v2/test_breakdown_p2_fusion_episode_v2.py
engine/tests/v2/test_breakdown_p2_vlm_episode_v2.py
engine/tests/v2/test_breakdown_p2_refinement_v1.py
```

The E3 source/runner/runtime/test files were syntax-checked in this connector session before remote write, but the user's full local repository pytest/Qwen/CUDA runtime was not available here. Hosted GitHub Actions are intentionally not used. Therefore this document does **not** claim fresh local test PASS or model-quality PASS.

## 13. Current pointer

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

Next safe work is a new real Episode BreakdownRun using the composite E2+E3 production VLM. If that semantic behavior is sound, proceed to P2-E4; do not advance P2.6/P3/P4/P5 truth without the corresponding evidence.
