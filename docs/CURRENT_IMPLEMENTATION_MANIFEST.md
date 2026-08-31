# AI Drama Studio — Current Implementation Manifest

> Purpose: code-aligned CURRENT manifest.  
> Last synchronized: **2026-08-31 +08:00**

## Repository baseline

```text
Repository: zdingwl/ai-drama-studio
Branch: main
Architecture: Reference Video V2 + Breakdown Fast Grounded V2
FastAPI app version: 2.4.1
Formal Character runtime: Character V10.1
P1/P2 implementation acceptance: CONDITIONAL PASS
Fast Grounded G1: REAL ACCEPTED / PRODUCTION / FROZEN
Window Context: SEGMENT-INDEX V4 / REAL ACCEPTED / PRODUCTION / FROZEN
Exact-Shot: COMPACT-RECONSTRUCTION V3 / REAL ACCEPTED / PRODUCTION / FROZEN
P2-E6 Fusion: E6-V2 / REAL PRODUCTION ACCEPTED / FROZEN
P2.6 Windows / real-model acceptance: PASS
G2 Scene Timeline Contract: V1 / FINAL PASS / FROZEN FOUNDATION
G2 Deterministic Assembler: V1 / FINAL PASS / FROZEN FOUNDATION
G2 Scene Narrative Core: V1.5 / FINAL PASS / FROZEN
G2 Local Qwen text runtime: REAL ACCEPTED / FROZEN BASELINE
G2 Source / Support Validator: V1.5 / FINAL PASS / FROZEN
G2.3/G2.4 real-model acceptance: PASS
G2.5 Scene Timeline API: NOT IMPLEMENTED
G2.6 ordinary-user Scene Timeline UI: NOT IMPLEMENTED
P3 current 02 拉片 Shot-card UI: IMPLEMENTED / NOT FINAL ACCEPTED
P4 Draft-guided Scene/Prop: IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character: PLANNED / PAUSED
```

G1 and all accepted G2 layers are frozen until a concrete regression appears. Character V10.1 remains protected.

## Final real acceptance evidence — G1 / G2.1 / G2.2

```text
Run = BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
Episode = EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
ShotRevision = SHOTREV_1462ac6d9f3948b994fc9bc575fee3a0
status = READY
whole run ~= 841.039s = 14.017 min
ASR = 15.275958s
OCR = 264.916802s
VLM = 559.267248s
Window Context = 84.3492s
Exact-Shot = 455.284273s
Window = 4/4 READY
Exact-Shot = 6/6 READY
MAXED = 0
scene_segment = 2
local_subject = 4
same_shot_cluster_conflicts = 0
Scene1 = Shots 1-12 / 公寓走廊 / LocalSubjects=2
Scene2 = Shots 13-30 / 客厅 / LocalSubjects=2
Shot0001 subjects=0
Shot0001 props include 蓝色玫瑰花束 + 玻璃花瓶
```

G2.1/G2.2 accepted evidence:

```text
python -m pytest engine/tests/v2/test_breakdown_scene_timeline_v1.py -q
4 passed

scenes = 2
shots = 30
people = [2, 2]
shot1_people = []
shot1_props = ['遥控器', '蓝色玫瑰花束', '玻璃花瓶', '书本']
warnings = []
```

Therefore:

```text
G1/P2.6 = PASS / FROZEN
G2.1 Scene Timeline Contract = FINAL PASS / FROZEN FOUNDATION
G2.2 Deterministic Assembler = FINAL PASS / FROZEN FOUNDATION
```

## Frozen production chain

```text
Episode Current ShotRevision
→ frozen PROCESSING BreakdownRun
→ ASR
→ OCR
→ Qwen3-VL one model load
   ├─ Window Segment-index v4
   └─ Exact-Shot Compact-reconstruction v3
→ immutable VLM_OUTPUT sidecar
→ P2-E6-v2 Fusion
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Profiles:

```text
Window = breakdown-p2-vlm-window-context-segment-index-zh-v4
Exact-Shot = breakdown-p2-vlm-exact-shot-compact-reconstruction-zh-v3
Fusion = breakdown-p2-fusion-episode-context-e6-v2
Pipeline = breakdown-p2-full-v1
```

Production modules:

```text
P2 sidecar                         engine/app/breakdown_p2_sidecar_v1.py
ASR                                engine/app/breakdown_p2_asr_v1.py
OCR                                engine/app/breakdown_p2_ocr_runtime_v1.py
Production VLM provider            engine/app/breakdown_p2_vlm_fast_grounded_instrumented_v3.py
Production continuity wrapper      engine/app/breakdown_p2_vlm_continuity_v1.py
Window production v4               scripts/run_breakdown_vlm_window_segment_index_v4.py
Exact-Shot production v3           scripts/run_breakdown_vlm_exact_shot_compact_v3.py
Production E6-v2 Fusion            engine/app/breakdown_p2_fusion_episode_v6.py
Orchestrator                       engine/app/breakdown_p2_pipeline_v1.py
```

## Hard semantic invariants

```text
Shot = smallest visual evidence/location unit
Exact-Shot visible fact > Window Context
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
subject_A/B = Shot-local observation labels only
same-Shot observations = hard cannot-link
G2 Scene-local P1/P2 refs != Character identity
G2 Scene Timeline != Final Scene / Final Prop / Final Character truth
ASR-origin DIALOGUE text is copied verbatim by G2
OCR-origin text is copied verbatim by G2
```

Character V10.1 remains unchanged:

```text
YOLOX -> capture-first evidence -> mature MOT -> YoutuReID
-> RESOLVED/UNRESOLVED -> explicit Shot Assignment -> Final Gate
```

## G2 frozen Scene Timeline behavior

```text
Scene
→ scene info
→ anonymous people (P1/P2 internally, 人物1/人物2 for display)
→ Shots
   → Exact-Shot visual description
   → visible people / grounded performance
   → ASR-only dialogue
   → Shot prop occurrences
   → shot type / Exact-Shot composition / reliable camera motion
   → OCR-only on-screen text
→ deterministic Scene summary baseline
→ validated Narrative title/story_summary overlay
```

Primary ordinary-user output excludes Evidence IDs, cluster data, confidence, LocalSubject DB IDs, support Fxxxx and provider/model diagnostics.

## G2.3 / G2.4 frozen architecture

Modules:

```text
Narrative Contract                  engine/app/breakdown_scene_narrative_contract_v1.py
Grounding Packet builder            engine/app/breakdown_scene_grounding_v1.py
Scene Narrative organizer           engine/app/breakdown_scene_narrative_v1.py
Source / Support Validator          engine/app/breakdown_scene_narrative_validator_v1.py
Local Qwen text adapter             engine/app/breakdown_scene_narrative_qwen3_v1.py
Local one-load text runner          scripts/run_breakdown_scene_narrative_qwen3.py
Real acceptance runner              scripts/run_breakdown_g2_scene_narrative_acceptance_v1.py
Narrative tests                     engine/tests/v2/test_breakdown_scene_narrative_v1.py
Qwen adapter tests                  engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py
Real regression tests               engine/tests/v2/test_breakdown_scene_narrative_real_regression_v1.py
Contract document                   docs/BREAKDOWN_G2_SCENE_NARRATIVE_CONTRACT.md
```

Formal flow:

```text
FINAL PASS scene-timeline-v1
→ one Scene Grounding Packet
→ stable Fxxxx facts
→ per-Scene SHA-256 source_fingerprint
→ text-only local Qwen3-VL-4B-Instruct
   one model load / Scenes sequential
→ Narrative Candidate
→ deterministic Source/Support Validator
→ Validated Narrative Overlay
→ apply overlay to title/story_summary only
```

Prompt profile:

```text
breakdown-g2-scene-narrative-zh-v1.5
```

LLM authority:

```text
MAY write:
  readable_title
  story_summary

MUST NOT own or rewrite:
  timestamps
  Scene/Shot boundaries
  people count/identity
  Shot visual facts
  performance/action facts
  ASR dialogue
  OCR
  prop existence
  shot type
  composition
  camera motion
  Final Character / Scene / Prop
```

ASR remains a restricted Narrative source: ordinary claims need attribution; sensitive event terms need topic/attribution; relationship identity terms are topic-only; dialogue names cannot bind anonymous people; numeric quantities must be provenance-backed.

## G2.3 / G2.4 final acceptance evidence

```text
python -m pytest engine/tests/v2/test_breakdown_scene_narrative_v1.py engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py engine/tests/v2/test_breakdown_scene_narrative_real_regression_v1.py -q
15 passed
```

Real-model acceptance on `BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4`:

```text
preflight = READY / cuda / missing=[]
runner Scene1 = READY
runner Scene2 = READY
overlay_status = READY
warnings = []
shot_objects_unchanged = YES
structure_gate = PASS
narrative_gate = PASS
acceptance_machine_gate = PASS
```

Accepted output:

```text
Scene1 = 走廊争花
老年女性质问年轻女性为何将花放在自家花瓶，年轻女性称花在走廊，双方争执并最终以给钱解决，年轻女性愤怒指责对方。

Scene2 = 客厅争执
人物2指责人物1对邻居偷花一事不作为，称其结婚八年从未支持过自己，人物1则表示自己会自行解决。
```

Human review = PASS. No Final identity/relationship binding was created and all frozen Shot objects remained unchanged.

Therefore:

```text
G2.3 = FINAL PASS / FROZEN
G2.4 = FINAL PASS / FROZEN
Local Qwen text runtime = REAL ACCEPTED / FROZEN BASELINE
```

## Testing / CI discipline

Do not claim assistant-local pytest/CUDA execution. User-local results are acceptance truth. Hosted GitHub Actions remain unused; commits use `[skip ci]`.

## Next required action

```text
1. implement G2.5 Scene Timeline API
2. return the accepted user-readable Scene Timeline + Narrative overlay
3. hide support Fxxxx / Evidence IDs / model diagnostics from ordinary API/UI surfaces
4. test API determinism and fallback behavior
5. implement G2.6 ordinary-user Scene Timeline UI after API acceptance
```
