# AI Drama Studio — Current Implementation Manifest

> Purpose: compact **code-aligned CURRENT manifest**.  
> Last synchronized: **2026-08-28 19:05 +08:00**

## Repository baseline

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Architecture: Reference Video V2
FastAPI app version: 2.4.1
Formal Character runtime: Character V10.1
P1/P2 implementation acceptance: CONDITIONAL PASS
P2-E1 Episode-context Fusion: IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E2 continuous-window VLM: IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2.6 Windows / real-model acceptance: NOT PASSED
P3 02 拉片 UI: IMPLEMENTED / UI ACCEPTANCE IN PROGRESS
P4 Draft-guided Scene/Prop: IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character: PLANNED / PAUSED UNTIL EPISODE-CONTEXT BASELINE
```

Core rule:

```text
Shot = smallest review/render unit
Shot != maximum AI semantic context
```

Semantic boundary remains:

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
raw Evidence / Draft != Final binding truth
ASR speaker != Character
```

## Current production Breakdown chain

```text
Episode Current ShotRevision
→ frozen PROCESSING BreakdownRun
→ Episode ASR
→ OCR observations
→ P2-E2 overlapping Episode-window Qwen3-VL
→ immutable existing VLM_OUTPUT sidecar contract
→ P2-E1 Episode-context Fusion
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Production modules:

```text
P2.1 engine/app/breakdown_p2_sidecar_v1.py
P2.2 engine/app/breakdown_p2_asr_v1.py
P2.3 engine/app/breakdown_p2_ocr_runtime_v1.py
legacy single-clip VLM engine/app/breakdown_p2_vlm_v1.py
P2-E2 provider engine/app/breakdown_p2_vlm_episode_v2.py
stable VLM runtime import engine/app/breakdown_p2_vlm_runtime_v1.py
E2 isolated runner scripts/run_breakdown_vlm_qwen3_episode_windows.py
legacy Fusion engine/app/breakdown_p2_fusion_v1.py
production E1 Fusion engine/app/breakdown_p2_fusion_episode_v2.py
orchestrator engine/app/breakdown_p2_pipeline_v1.py
acceptance engine/app/breakdown_p2_acceptance_v1.py
```

Top-level pipeline profile remains:

```text
breakdown-p2-full-v1
```

Production Fusion provenance profile:

```text
breakdown-p2-fusion-episode-context-e1-v2
```

Production VLM Episode-context profile:

```text
breakdown-p2-vlm-episode-window-e2-v1
window schema = breakdown-p2-vlm-episode-window-v1
prompt profile = breakdown-p2-vlm-episode-window-zh-v1
```

## P2-E1 behavior

Scene continuity:

```text
missing/UNKNOWN/generic environment → inherit current Scene
compatible specificity such as 客厅 → 家中客厅 → same Scene
strong location contradiction or explicit INT ↔ EXT contradiction → new Scene
```

Dialogue continuity:

```text
ASR_SEGMENT = Episode-time text truth
Shot DIALOGUE event = projection, not sentence truth
```

Cross-Shot projections share `dialogue_group_id/asr_segment_id` and continuation metadata. Raw ASR_WORD evidence remains immutable SUPPORT provenance.

## P2-E2 behavior

Default visual inference context:

```text
shot-aligned overlapping Episode windows
target 24 seconds
allowed 20..40 seconds
overlap 25%
allowed 10..50%
sequential window inference
prefer READY preprocess proxy, fallback Episode source
```

Each Qwen window sees the continuous video plus exact ShotRevisionItem boundaries. It first reasons about the window and then returns one anonymous semantic object per Shot.

When a Shot appears in multiple windows, E2 selects the candidate with the largest surrounding-context margin, then closest window center, then earlier window. The selected provenance is stored in `VLM_OUTPUT.payload.episode_window`.

E2 deliberately preserves the frozen sidecar contract:

```text
source_type = VLM_OUTPUT
shot_revision_item_id = exact frozen item
source time = exact Shot range
payload.semantic = existing P2.4 semantic shape
```

Therefore E1 Fusion, P1 serializer/validator, P3 and P4 do not require a destructive schema migration.

Chinese generation policy remains: VLM-generated descriptive prose is Simplified Chinese; machine keys/enums remain stable; ASR/OCR raw source text remains untouched.

## P2-E3 / E4 status

```text
P2-E3 contextual Shot refinement = PLANNED
P2-E4 final Episode-context Fusion = PLANNED
```

E3 is the next semantic implementation: combine selected/supporting E2 window context with Scene + previous/current/next Shot + overlapping ASR/OCR for final Shot-level refinement. E4 then makes continuous-window evidence the primary Scene/anonymous-subject continuity evidence and leaves E1 conservative rules as fallback.

## APIs / execution discipline

Formal APIs remain:

```text
POST /api/episodes/{episode_id}/tasks/breakdown
POST /api/projects/{project_id}/tasks/breakdown-batch
GET  /api/breakdown/p2/runtime-preflight
POST /api/breakdown-runs/{run_id}/p2-acceptance
```

Batch remains sequential by `Episode.sort_order`; heavy P2 work is globally serialized.

Local CLI now also supports:

```text
--vlm-window-seconds
--vlm-window-overlap-ratio
```

## P1 / media invariants

```text
FFprobe authoritative timing
FFmpeg preprocess/proxy/audio
integer microseconds
TransNetV2 Shot boundaries
ShotRevision / ShotRevisionItem history
Reference Clip / thumbnail / keyframes
PROCESSING / READY / READY_WITH_WARNINGS / FAILED / STALE
```

Historical semantic data always anchors to exact ShotRevision/ShotRevisionItem and historical BreakdownRuns/sidecars are never rewritten by E1/E2.

## P3 current UI

```text
02 拉片
├─ 镜头管理
└─ 拉片结果
   ├─ Scene / Shot results
   ├─ anonymous subjects
   ├─ dialogue / action / OCR
   ├─ prop hints
   └─ exact historical Reference Clip
```

Technical provenance remains backend truth but is not the primary normal-user presentation. P3 acceptance remains in progress. The UI should later use E1 dialogue continuation metadata to render “对白继续” instead of unrelated-looking duplicates.

## P4 / Character boundaries

P4 Draft-guided Scene/Prop remains implemented and requires current-revision visual re-verification. Draft cannot directly create Final Scene/Prop.

Character V10.1 remains protected:

```text
YOLOX person detection
→ capture-first evidence
→ mature MOT
→ YoutuReID project identity
→ explicit Shot × known-Character Assignment
→ Final Character Gate
```

E1/E2 do not modify Character identity thresholds, same-sample cannot-link, face hard conflicts, explicit assignment or Final Gate.

## Acceptance / CI truth

```text
P1/P2 implementation = CONDITIONAL PASS
P2-E1 local-real acceptance = PENDING
P2-E2 local-real Qwen/Windows acceptance = PENDING
P2.6 Windows / real-model acceptance = NOT PASSED
P3 UI acceptance = IN PROGRESS
P4 local/model acceptance = PENDING
GitHub hosted Actions = intentionally not used
```

Unit coverage added:

```text
engine/tests/v2/test_breakdown_p2_fusion_episode_v2.py
engine/tests/v2/test_breakdown_p2_vlm_episode_v2.py
```

This connector session does not claim a fresh executed pytest/Qwen/CUDA PASS.

## Phase pointer

```text
P0 COMPLETE
P1 implementation CONDITIONAL PASS
P2 implementation CONDITIONAL PASS
P2-E1 Episode-context Fusion IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E2 continuous-window VLM IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E3 contextual Shot refinement PLANNED / NEXT
P2-E4 final Episode-context Fusion PLANNED
P2.6 Windows / real-model acceptance NOT PASSED
P3 UI IMPLEMENTED / UI ACCEPTANCE IN PROGRESS
P4 Draft-guided Scene/Prop IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character PLANNED / PAUSED
P6 Final fill-back/renderers PLANNED
P7 remake integration PLANNED
```

Next safe work: run a new real short-drama BreakdownRun using E2 and inspect same-scene closeups/inserts, genuine scene changes, anonymous subject/prop continuity and E1 cross-Shot dialogue. If the E2 runtime behavior is sound, proceed to P2-E3; do not upgrade P2.6 or downstream acceptance status without real evidence.
