# AI Drama Studio — Current Implementation Manifest

> Purpose: compact **code-aligned CURRENT manifest**.  
> Last synchronized: **2026-08-28 19:39 +08:00**

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
P2-E3 contextual Shot refinement: IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E4 final Episode-context Fusion: PLANNED / NEXT
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
→ P2-E3 contextual Shot refinement
→ one immutable exact-Shot VLM_OUTPUT sidecar
   payload.e2_semantic = preserved E2 visual semantic
   payload.semantic = E3 refined semantic used by Fusion
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
P2-E2 runner scripts/run_breakdown_vlm_qwen3_episode_windows.py
P2-E3 refiner engine/app/breakdown_p2_refinement_v1.py
P2-E3 runner scripts/run_breakdown_refinement_qwen3.py
stable composite VLM runtime engine/app/breakdown_p2_vlm_runtime_v1.py
legacy Fusion engine/app/breakdown_p2_fusion_v1.py
production E1 Fusion engine/app/breakdown_p2_fusion_episode_v2.py
orchestrator engine/app/breakdown_p2_pipeline_v1.py
acceptance engine/app/breakdown_p2_acceptance_v1.py
```

Top-level pipeline profile remains:

```text
breakdown-p2-full-v1
provider order = ASR → OCR → VLM
```

E3 deliberately remains inside the formal VLM Provider execution, so no fourth P2 component, API change or sidecar schema migration was introduced.

Production profiles:

```text
Fusion = breakdown-p2-fusion-episode-context-e1-v2
E2 VLM = breakdown-p2-vlm-episode-window-e2-v1
E2 window schema = breakdown-p2-vlm-episode-window-v1
E2 prompt = breakdown-p2-vlm-episode-window-zh-v1
E3 refinement = breakdown-p2-contextual-shot-refinement-e3-v1
E3 input schema = breakdown-p2-contextual-refinement-input-v1
E3 prompt = breakdown-p2-contextual-shot-refinement-zh-v1
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

Each Qwen window sees continuous video plus exact ShotRevisionItem boundaries. When a Shot appears in multiple windows, E2 selects the candidate with the largest surrounding-context margin, then closest window center, then earlier window. Selected/supporting provenance is stored in `VLM_OUTPUT.payload.episode_window`.

E2 visual output remains anonymous and exact-Shot bound.

## P2-E3 behavior

E3 is a text-only contextual Qwen pass after E2. Each exact Shot receives:

```text
provisional Scene context
previous/current/next E2 Shot semantics
selected/supporting E2 window summaries
overlapping Episode ASR_SEGMENT context
overlapping OCR observations
```

Grounding/safety:

```text
refine current Shot only
neighbor-only visual facts must not be imported
only current E2 subject labels are permitted
ASR and OCR source text remain read-only
no speaker identity inference
no Final Character/Scene/Prop/Binding IDs
scene ambiguity may be resolved only from supported context
shot type/camera/composition remain grounded in current E2 visual evidence
Simplified Chinese generated prose
```

Frozen compatibility:

```text
VLM sidecar schema stays breakdown-p2-evidence-v1
VLM_OUTPUT.source_type/source_id/exact Shot range remain the provenance anchor
payload.e2_semantic preserves E2
payload.semantic contains E3 and is consumed by existing Fusion
payload.contextual_refinement stores E3 provenance
```

Individual malformed E3 Shot output falls back to E2 with a warning. Missing E3 runtime or whole E3 inference failure makes the production VLM Provider FAILED.

## P2-E4 status

```text
P2-E4 final Episode-context Fusion = PLANNED / NEXT
```

Target: make E2 window continuity + E3 refined Shot semantics the primary Episode-time Scene/anonymous-subject continuity evidence, with E1 conservative continuity rules retained as fallback.

## APIs / execution discipline

Formal APIs remain:

```text
POST /api/episodes/{episode_id}/tasks/breakdown
POST /api/projects/{project_id}/tasks/breakdown-batch
GET  /api/breakdown/p2/runtime-preflight
POST /api/breakdown-runs/{run_id}/p2-acceptance
```

Batch remains sequential by `Episode.sort_order`; heavy P2 work is globally serialized.

Local CLI supports E2 tuning:

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

Historical semantic data always anchors to exact ShotRevision/ShotRevisionItem and historical BreakdownRuns/sidecars are never rewritten by E1/E2/E3.

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

E1/E2/E3 do not modify Character identity thresholds, same-sample cannot-link, face hard conflicts, explicit assignment or Final Gate.

## Acceptance / CI truth

```text
P1/P2 implementation = CONDITIONAL PASS
P2-E1 local-real acceptance = PENDING
P2-E2 local-real Qwen/Windows acceptance = PENDING
P2-E3 local-real contextual refinement acceptance = PENDING
P2.6 Windows / real-model acceptance = NOT PASSED
P3 UI acceptance = IN PROGRESS
P4 local/model acceptance = PENDING
GitHub hosted Actions = intentionally not used
```

Unit coverage present:

```text
engine/tests/v2/test_breakdown_p2_fusion_episode_v2.py
engine/tests/v2/test_breakdown_p2_vlm_episode_v2.py
engine/tests/v2/test_breakdown_p2_refinement_v1.py
```

E3 source/runner/runtime/test syntax was checked before remote write, but this connector session does not claim a fresh full local pytest/Qwen/CUDA PASS.

## Phase pointer

```text
P0 COMPLETE
P1 implementation CONDITIONAL PASS
P2 implementation CONDITIONAL PASS
P2-E1 Episode-context Fusion IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E2 continuous-window VLM IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E3 contextual Shot refinement IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E4 final Episode-context Fusion PLANNED / NEXT
P2.6 Windows / real-model acceptance NOT PASSED
P3 UI IMPLEMENTED / UI ACCEPTANCE IN PROGRESS
P4 Draft-guided Scene/Prop IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character PLANNED / PAUSED
P6 Final fill-back/renderers PLANNED
P7 remake integration PLANNED
```

Next safe work: run a new real short-drama BreakdownRun using the composite E2+E3 production VLM and inspect same-scene closeups/inserts, genuine scene changes, E3 current-Shot grounding, anonymous subject/prop continuity and E1 cross-Shot dialogue. If the new semantic behavior is sound, proceed to P2-E4; do not upgrade P2.6 or downstream acceptance status without real evidence.
