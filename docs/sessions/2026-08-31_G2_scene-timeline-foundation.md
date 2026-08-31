# Session Handoff — G2 Scene Timeline Foundation

## Session

- Date: 2026-08-31
- Branch: `main`
- Scope: **G2.1 Scene Timeline Contract + G2.2 Deterministic Assembler**
- Status: **FINAL PASS / FROZEN FOUNDATION**
- G1 status: **PASS / PRODUCTION / FROZEN**
- Character: **V10.1 protected / unchanged**

## 1. Source baseline preserved

No G1 production file was modified.

Frozen baseline remains:

```text
Window Context v4 = PASS / FROZEN
Exact-Shot Compact v3 = PASS / FROZEN
Fusion E6-v2 = PASS / FROZEN
Final Run = BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
Scenes = 2
Scene1 LocalSubjects = 2
Scene2 LocalSubjects = 2
same-Shot conflicts = 0
Shot0001 subjects = 0
Shot0001 props include 蓝色玫瑰花束 + 玻璃花瓶
whole run ~= 14.02 min
```

No Window / Exact-Shot / Fusion / continuity / Character V10.1 tuning was performed.

## 2. Implemented files

### G2.1 Contract

```text
engine/app/breakdown_scene_timeline_contract_v1.py
```

Defines strict `scene-timeline-v1` Pydantic output for ordinary-user results.

Primary shape:

```text
Scene
→ Scene info
→ anonymous people
→ Shots
   → visual description
   → people
   → performance
   → dialogue
   → props
   → cinematography
   → on-screen OCR text
→ story summary
```

Debug/internal fields are excluded by design and Pydantic uses `extra="forbid"`.

### G2.2 Deterministic assembler

```text
engine/app/breakdown_scene_timeline_assembler_v1.py
```

Consumes the current `breakdown_serializer_v1` Draft payload only.

Hard rules:

```text
Exact-Shot visual_description > same-Shot summary fallback
Scene context never fills neighboring Shot people/actions/props
LocalSubject → Scene-local P1/P2/... only
DIALOGUE enters final output only when origin=ASR
ASR content_text is verbatim
OCR enters final output only when origin=OCR
OCR content_text is verbatim
Shot props come from current-Shot prop_occurrences only
composition comes from model_metadata.composition_hint
camera_motion UNKNOWN → null
no Final Character / Final Scene / Final Prop reads or writes
```

Structure conflicts fail closed instead of being guessed/fixed.

### Tests

```text
engine/tests/v2/test_breakdown_scene_timeline_v1.py
```

Covers:

- Scene-local P* reset;
- Shot0001-style zero people + roses/vase props;
- Exact-Shot visual/composition;
- grounded performance label cleanup;
- ASR text verbatim, including double spaces and source text containing `人物A`;
- non-ASR dialogue rejection;
- OCR verbatim;
- Evidence/confidence/LocalSubject IDs not leaking into primary output;
- STALE historical run preservation;
- duplicate Shot ordinal and Shot-outside-Scene fail closed.

### Contract doc

```text
docs/BREAKDOWN_G2_SCENE_TIMELINE_CONTRACT.md
```

## 3. CURRENT docs synchronized

Updated:

```text
AGENTS.md
SKILL.md                  -> 3.18.2
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
```

Current status:

```text
G2 Scene Timeline Contract = v1 / FINAL PASS / FROZEN FOUNDATION
G2 Deterministic Assembler = v1 / FINAL PASS / FROZEN FOUNDATION
G2 Scene-level LLM = NOT IMPLEMENTED
Scene Timeline UI = NOT IMPLEMENTED
```

## 4. User-local acceptance

### A. Unit contract / assembler tests — PASS

User-local command:

```powershell
python -m pytest engine/tests/v2/test_breakdown_scene_timeline_v1.py -q
```

Observed result on 2026-08-31:

```text
....
4 passed
```

### B. Final accepted real Run smoke check — PASS

User-local command exercised the deterministic assembler against:

```text
BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
```

Observed result on 2026-08-31:

```text
scenes= 2 shots= 30
people= [2, 2]
shot1_people= []
shot1_props= ['遥控器', '蓝色玫瑰花束', '玻璃花瓶', '书本']
warnings= []
```

Acceptance target was fully satisfied:

```text
Scenes = 2                       PASS
Shots = 30                       PASS
Scene1 people = 2                PASS
Scene2 people = 2                PASS
Shot0001 people = []             PASS
Shot0001 蓝色玫瑰花束             PASS
Shot0001 玻璃花瓶                 PASS
warnings = []                    PASS
```

Together with the regression suite that verifies ASR/OCR verbatim behavior and debug-field exclusion,
this closes G2.1/G2.2 acceptance.

Therefore:

```text
G2.1 Scene Timeline Contract = FINAL PASS / FROZEN FOUNDATION
G2.2 Deterministic Assembler = FINAL PASS / FROZEN FOUNDATION
```

## 5. Not implemented in this session

Deliberately not implemented:

```text
G2.3 Scene-level pure-text LLM
G2.4 LLM support/source validator
G2.5 Scene Timeline API
G2.6 ordinary-user frontend
G2 persistence tables
Final Character / Final Scene / Final Prop creation
```

Current P3 developer/acceptance Shot UI remains unchanged.

## 6. Next action

```text
G2.1/G2.2 FINAL PASS
→ implement G2.3 Scene-level pure-text LLM
→ implement G2.4 source/support validator + fail-closed fallback
→ validate on final accepted Run
→ G2.5 API
→ G2.6 ordinary-user Scene Timeline UI
```

The LLM may improve readable Scene summary / wording only. It must not own timestamps, people count,
identity, dialogue, OCR, props, shot type or composition.

If a later regression appears, fix the responsible G2 layer first. Do not retune frozen G1 or alter the accepted deterministic source-truth ownership without concrete evidence.
