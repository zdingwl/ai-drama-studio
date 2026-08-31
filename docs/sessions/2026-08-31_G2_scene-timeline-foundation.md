# Session Handoff — G2 Scene Timeline Foundation

## Session

- Date: 2026-08-31
- Branch: `main`
- Scope: **G2.1 Scene Timeline Contract + G2.2 Deterministic Assembler**
- Status: **IMPLEMENTED / USER-LOCAL ACCEPTANCE PENDING**
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
SKILL.md                  -> 3.18.0
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
```

They now explicitly say:

```text
G2 Scene Timeline Contract = v1 / IMPLEMENTED / USER-LOCAL ACCEPTANCE PENDING
G2 Deterministic Assembler = v1 / IMPLEMENTED / USER-LOCAL ACCEPTANCE PENDING
G2 Scene-level LLM = NOT IMPLEMENTED
Scene Timeline UI = NOT IMPLEMENTED
```

Do not call G2.1/G2.2 PASS before the user-local acceptance below.

## 4. User-local acceptance

### A. Unit contract / assembler tests

From repository root:

```powershell
python -m pytest engine/tests/v2/test_breakdown_scene_timeline_v1.py -q
```

Expected: all tests PASS.

### B. Final accepted real Run smoke check

Use the existing local `studio_v2.sqlite3` that contains the final accepted Run:

```powershell
python -c "from engine.app.breakdown_serializer_v1 import get_breakdown_run; from engine.app.breakdown_scene_timeline_assembler_v1 import assemble_scene_timeline_v1; p=get_breakdown_run('BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4'); assert p is not None; r=assemble_scene_timeline_v1(p); print('scenes=',r['scene_count'],'shots=',r['shot_count']); print('people=',[len(s['people']) for s in r['scenes']]); s1=r['scenes'][0]['shots'][0]; print('shot1_people=',s1['people']); print('shot1_props=',[x['label'] for x in s1['props']]); print('warnings=',r['warnings'])"
```

Acceptance target:

```text
scenes = 2
shots = 30
people = [2, 2]
shot1_people = []
shot1_props contains 蓝色玫瑰花束
shot1_props contains 玻璃花瓶
```

Also inspect several dialogue/OCR rows if needed to confirm text remains identical to G1 source.

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

## 6. Next action after acceptance

If A + B pass:

```text
mark G2.1 / G2.2 PASS
→ implement G2.3 Scene-level pure-text LLM
→ implement G2.4 source/support validator
```

The LLM may improve readable Scene summary / wording only. It must not own timestamps, people count,
identity, dialogue, OCR, props, shot type or composition.

If acceptance fails, fix the G2 Contract/Assembler first. Do not retune frozen G1 unless the failure is proven to be a real G1 regression.
