# AI Drama Studio — Project State

> **Last synchronized:** 2026-08-31 +08:00  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Branch:** `main`  
> **Architecture:** Reference Video V2 + Breakdown Fast Grounded V2  
> **FastAPI app version:** `2.4.1`  
> **Formal Character runtime:** Character V10.1

## 1. Current truth

```text
P1/P2 implementation acceptance       = CONDITIONAL PASS
Fast Grounded V2 baseline             = APPROVED / G1 FROZEN
Window Context contract               = SEGMENT-INDEX V4 / REAL ACCEPTED / PRODUCTION / FROZEN
Exact-Shot contract                   = COMPACT-RECONSTRUCTION V3 / REAL ACCEPTED / PRODUCTION / FROZEN
P2-E6 Fusion                          = E6-V2 / REAL PRODUCTION ACCEPTED / FROZEN
P2.6 Windows / real-model acceptance  = PASS
G2 Scene Timeline Contract            = V1 / FINAL PASS / FROZEN FOUNDATION
G2 Deterministic Assembler            = V1 / FINAL PASS / FROZEN FOUNDATION
G2 Scene Narrative Core               = V1 / IMPLEMENTED / USER-LOCAL TEST PENDING
G2 Local Qwen text runtime            = V1 / IMPLEMENTED / USER-LOCAL TEST PENDING
G2 Source / Support Validator         = V1 / IMPLEMENTED / USER-LOCAL TEST PENDING
G2.3/G2.4 real-model acceptance       = PENDING
G2.5 Scene Timeline API               = NOT IMPLEMENTED
G2.6 ordinary-user result UI          = NOT IMPLEMENTED
P3 current 02 拉片 Shot-card UI        = IMPLEMENTED / NOT FINAL ACCEPTED
P4 Draft-guided Scene/Prop            = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character                  = PLANNED / PAUSED
same-Shot hard safety                 = PASS / conflicts=0
```

G1 performance/quality tuning is frozen. Do not change Window-v4, Exact-Shot-v3, E6-v2 thresholds,
same-Shot cannot-link, or Character V10.1 identity gates without a new concrete real regression.

G2.1/G2.2 regression tests and final accepted real-Run smoke passed. They are frozen.
G2.3/G2.4 code is implemented but is **not PASS yet**; user-local tests, runtime preflight and real text-model acceptance remain required.

## 2. Final P2.6 production acceptance Run

```text
Run = BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
Episode = EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
ShotRevision = SHOTREV_1462ac6d9f3948b994fc9bc575fee3a0
Shots = 30
status = READY
is_current = true
whole run ~= 841.039s = 14.017 min
ASR = 15.275958s
OCR = 264.916802s
VLM = 559.267248s
Window Context = 84.3492s
Exact-Shot = 455.284273s
Window = 4/4 READY
Exact-Shot = 6/6 READY
MAXED = 0
```

Fusion production truth:

```text
Fusion profile = breakdown-p2-fusion-episode-context-e6-v2
scene_segment = 2
local_subject = 4
same_shot_cluster_conflicts = 0
Scene1 = Shots 1-12 / 公寓走廊 / LocalSubjects=2
Scene2 = Shots 13-30 / 客厅 / LocalSubjects=2
Shot0001 subjects = 0
Shot0001 props = 遥控器 / 蓝色玫瑰花束 / 玻璃花瓶 / 书本
```

**P2.6 = PASS / G1 = FROZEN.**

## 3. Accepted production chain

```text
Episode Current ShotRevision
→ frozen PROCESSING BreakdownRun
→ Episode ASR (faster-whisper large-v3)
→ OCR (RapidOCR PP-OCRv6-small)
→ one-load Qwen3-VL Fast Grounded
   ├─ Window Segment-index v4
   └─ Exact-Shot Compact-Reconstruction v3
→ immutable VLM_OUTPUT sidecar
→ P2-E6-v2 Episode-context Fusion
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

## 4. Hard invariants

```text
Shot = smallest visual evidence/location unit
Exact-Shot visible fact > Window Context
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
subject_A/B = Shot-local labels only
same-Shot observations = hard cannot-link
G2 Scene-local P1/P2 != Character identity
G2 Scene Timeline != Final Character / Final Scene / Final Prop truth
ASR-origin dialogue text must remain verbatim in G2
OCR-origin visible text must remain verbatim in G2
```

Character V10.1 remains protected:

```text
YOLOX Person Detection
→ capture-first Person Evidence
→ mature MOT
→ YoutuReID project identity
→ RESOLVED / UNRESOLVED
→ explicit Shot × known-Character Assignment
→ Final Character Gate
```

## 5. G2.1 / G2.2 final acceptance

Frozen modules:

```text
engine/app/breakdown_scene_timeline_contract_v1.py
engine/app/breakdown_scene_timeline_assembler_v1.py
engine/tests/v2/test_breakdown_scene_timeline_v1.py
docs/BREAKDOWN_G2_SCENE_TIMELINE_CONTRACT.md
```

Acceptance evidence:

```text
python -m pytest engine/tests/v2/test_breakdown_scene_timeline_v1.py -q
4 passed

Final Run deterministic smoke:
scenes = 2
shots = 30
people = [2, 2]
shot1_people = []
shot1_props = ['遥控器', '蓝色玫瑰花束', '玻璃花瓶', '书本']
warnings = []
```

Therefore:

```text
G2.1 = FINAL PASS / FROZEN FOUNDATION
G2.2 = FINAL PASS / FROZEN FOUNDATION
```

## 6. G2.3 / G2.4 implementation

New modules:

```text
engine/app/breakdown_scene_narrative_contract_v1.py
engine/app/breakdown_scene_grounding_v1.py
engine/app/breakdown_scene_narrative_v1.py
engine/app/breakdown_scene_narrative_validator_v1.py
engine/app/breakdown_scene_narrative_qwen3_v1.py
scripts/run_breakdown_scene_narrative_qwen3.py
engine/tests/v2/test_breakdown_scene_narrative_v1.py
engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py
docs/BREAKDOWN_G2_SCENE_NARRATIVE_CONTRACT.md
```

Flow:

```text
FINAL PASS scene-timeline-v1
→ per-Scene Grounding Packet
→ deterministic Fxxxx facts
→ per-Scene SHA-256 source_fingerprint
→ local text-only Qwen3-VL-4B-Instruct
   one model load / Scenes sequential
→ Narrative Candidate
→ Source/Support Validator
→ Validated Narrative Overlay
→ apply title/story_summary only
```

LLM permission is intentionally minimal:

```text
MAY write:
  readable_title
  story_summary

MUST NOT write/own:
  Scene/Shot timestamps or boundaries
  people identity/count
  Shot visual facts
  performance/action facts
  ASR dialogue
  OCR
  prop existence
  shot type
  composition
  camera motion
  Final Character / Final Scene / Final Prop
```

Each non-null claim must cite valid current-Scene `Fxxxx` support. G2.4 rejects:

```text
missing/unknown support
internal P1/P2 leakage
人物N not in current Scene
人物N without person-level support
hard location/time/space/prop/shot-type/motion terms without matching support
Final Asset / ID declarations
stale source fingerprint
```

Bad claims fall back to deterministic title/summary. LLM/provider failures do not block the deterministic Scene Timeline.

## 7. Local Qwen text runtime

G2.3 uses the existing local isolated base runtime/checkpoint:

```text
.runtime/TransVLM/inference/.venv
.runtime/TransVLM/inference/pretrained/Qwen3-VL-4B-Instruct
```

The new runner is independent from frozen G1 inference and is **text-only**: no video/image input.
The full Episode uses one subprocess/model load, then processes Scenes sequentially.

Config:

```text
AI_DRAMA_G2_LLM_PYTHON
AI_DRAMA_G2_LLM_MODEL_PATH
AI_DRAMA_G2_LLM_DEVICE
AI_DRAMA_G2_LLM_MAX_NEW_TOKENS
AI_DRAMA_G2_LLM_RUNNER
```

Python/model/device may fall back to `AI_DRAMA_P2_VLM_*`.

## 8. Acceptance status and next action

No assistant-local pytest/CUDA PASS is claimed. Hosted GitHub Actions remain intentionally unused.

First user-local gate:

```powershell
python -m pytest engine/tests/v2/test_breakdown_scene_narrative_v1.py engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py -q
```

Expected:

```text
8 passed
```

Then local runtime preflight:

```powershell
python -c "from engine.app.breakdown_scene_narrative_qwen3_v1 import Qwen3VLSceneTextLLM; print(Qwen3VLSceneTextLLM().runtime_preflight())"
```

Expected status: `READY`.

After those pass:

```text
1. run real text-only Qwen Narrative on BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
2. inspect two Scene titles/summaries and validator warnings
3. verify all 30 Shot objects remain unchanged by Narrative overlay
4. mark G2.3/G2.4 FINAL PASS only after that acceptance
5. implement G2.5 Scene Timeline API
6. implement G2.6 ordinary-user Scene Timeline UI last
```

If a G2.3/G2.4 regression appears, fix those layers. Do not retune frozen G1 or alter G2.1/G2.2 truth ownership to hide it.
