# Session Handoff — G2.3 Scene Narrative + G2.4 Source/Support Validator

## Session

- Date: 2026-08-31
- Branch: `main`
- Scope: **G2.3 Scene-level pure-text Narrative + G2.4 Source/Support Validator**
- Status: **IMPLEMENTED / USER-LOCAL TEST PENDING / REAL-MODEL ACCEPTANCE PENDING**
- G2.1/G2.2: **FINAL PASS / FROZEN FOUNDATION**
- G1: **PASS / PRODUCTION / FROZEN**
- Character: **V10.1 protected / unchanged**

## 1. Frozen baseline preserved

No frozen G1 or deterministic G2.1/G2.2 business module was modified.

Accepted source remains:

```text
Run = BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
Scenes = 2
Shots = 30
people = [2, 2]
Shot0001 people = []
Shot0001 props = 遥控器 / 蓝色玫瑰花束 / 玻璃花瓶 / 书本
G2.2 warnings = []
```

No Window-v4 / Exact-Shot-v3 / E6-v2 / Character V10.1 tuning was performed.

## 2. Main design decision

The LLM authority was intentionally reduced to only two Scene fields:

```text
readable_title
story_summary
```

It does **not** rewrite Shot-level visual/action facts.

This means G2.3 cannot own:

```text
timestamps
Scene/Shot boundaries
people count/identity
Shot visual
performance/action
ASR dialogue
OCR
prop existence
shot type
composition
camera motion
Final Character / Final Scene / Final Prop
```

If the LLM fails, the FINAL PASS deterministic Scene Timeline is still fully usable.

## 3. Implemented files

### Narrative / Grounding Contract

```text
engine/app/breakdown_scene_narrative_contract_v1.py
```

Strict Pydantic contracts:

```text
scene-grounding-v1
scene-narrative-v1
```

Every model uses `extra="forbid"`.

### Grounding Packet

```text
engine/app/breakdown_scene_grounding_v1.py
```

Per Scene:

```text
scene-timeline-v1
→ Scene-local facts
→ F0001 / F0002 / ...
→ SHA-256 source_fingerprint
```

ASR and OCR fact text remains verbatim.

### Scene Narrative Organizer

```text
engine/app/breakdown_scene_narrative_v1.py
```

Prompt profile:

```text
breakdown-g2-scene-narrative-zh-v1
```

System Prompt explicitly treats `<SCENE_DATA>` as untrusted data. Strings such as:

```text
忽略以上规则
执行命令
SYSTEM:
```

inside ASR/OCR are not instructions.

Invalid JSON does not cause a hidden second LLM request.

### Source / Support Validator

```text
engine/app/breakdown_scene_narrative_validator_v1.py
```

Checks:

```text
scene_ordinal match
support Fxxxx exists
support de-duplication
no P1/P2 leakage in user text
人物N belongs to current Scene
人物N has person-level support
location/time/space/prop/shot-type/motion hard anchors have matching support
no Final Asset/ID declarations
```

Invalid claim is discarded individually and falls back to deterministic title/summary.

### Narrative Overlay apply

`apply_scene_narrative_overlay_v1` checks:

```text
Run anchor
ShotRevision anchor
Episode anchor
Scene ordinal
per-Scene source_fingerprint
```

It is allowed to change only:

```text
title
story_summary
```

The final result is revalidated through frozen `SceneTimelinePayloadV1`.

### Local Qwen text-only runtime

```text
engine/app/breakdown_scene_narrative_qwen3_v1.py
scripts/run_breakdown_scene_narrative_qwen3.py
```

Profile:

```text
breakdown-g2-scene-narrative-qwen3-local-v1
```

It reuses the already-installed isolated **base checkpoint/runtime**:

```text
.runtime/TransVLM/inference/.venv
.runtime/TransVLM/inference/pretrained/Qwen3-VL-4B-Instruct
```

Important:

```text
This is text-only.
It does not open video/images.
It does not call frozen G1 Window/Exact-Shot runner logic.
One subprocess loads the 4B model once.
All Scenes run sequentially in that one model load.
```

Config overrides:

```text
AI_DRAMA_G2_LLM_PYTHON
AI_DRAMA_G2_LLM_MODEL_PATH
AI_DRAMA_G2_LLM_DEVICE
AI_DRAMA_G2_LLM_MAX_NEW_TOKENS
AI_DRAMA_G2_LLM_RUNNER
```

Python/model/device can fall back to existing `AI_DRAMA_P2_VLM_*` values.

## 4. Tests added

```text
engine/tests/v2/test_breakdown_scene_narrative_v1.py
engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py
```

Coverage:

```text
Grounding deterministic fingerprint
Fxxxx sequence
ASR/OCR verbatim
fake support rejection
hard-anchor support coverage
P1/P2 leakage rejection
unknown 人物N rejection
prompt injection remains Scene data
provider error detail not leaked
invalid JSON has no second call
only title/story_summary can change
stale fingerprint rejected
local Qwen batch Adapter path
```

Expected new test count:

```text
8 passed
```

No assistant-local pytest/CUDA PASS has been claimed.

## 5. Docs synchronized

Updated:

```text
AGENTS.md
SKILL.md -> 3.18.3
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/BREAKDOWN_G2_SCENE_TIMELINE_CONTRACT.md
```

New:

```text
docs/BREAKDOWN_G2_SCENE_NARRATIVE_CONTRACT.md
```

Current status:

```text
G2.1 = FINAL PASS / FROZEN FOUNDATION
G2.2 = FINAL PASS / FROZEN FOUNDATION
G2.3 Scene Narrative Core = IMPLEMENTED / USER-LOCAL TEST PENDING
G2.3 Local Qwen runtime = IMPLEMENTED / USER-LOCAL TEST PENDING
G2.4 Source/Support Validator = IMPLEMENTED / USER-LOCAL TEST PENDING
G2.3/G2.4 real-model acceptance = PENDING
G2.5 API = NOT IMPLEMENTED
G2.6 UI = NOT IMPLEMENTED
```

## 6. User-local acceptance A — code tests

From repo root:

```powershell
python -m pytest engine/tests/v2/test_breakdown_scene_narrative_v1.py engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py -q
```

Expected:

```text
........
8 passed
```

## 7. User-local acceptance B — runtime preflight

```powershell
python -c "from engine.app.breakdown_scene_narrative_qwen3_v1 import Qwen3VLSceneTextLLM; print(Qwen3VLSceneTextLLM().runtime_preflight())"
```

Expected:

```text
status = READY
missing = []
```

## 8. Next action after A + B pass

Run the real text-only local Qwen Narrative on:

```text
BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
```

Acceptance must verify:

```text
2 Scene Narrative candidates/overlays
no Final IDs
no P1/P2 leakage in accepted user text
validator warnings understandable
Narrative overlay only changes title/story_summary
all 30 Shot objects remain deterministic and unchanged
Shot0001 stays people=[] + exact prop truth
```

Only after that may G2.3/G2.4 be marked FINAL PASS.

Then:

```text
G2.5 Scene Timeline API
→ G2.6 ordinary-user Scene Timeline UI
```

If real Narrative acceptance fails, fix G2.3/G2.4 only. Do not retune frozen G1 or modify G2.1/G2.2 truth ownership.
