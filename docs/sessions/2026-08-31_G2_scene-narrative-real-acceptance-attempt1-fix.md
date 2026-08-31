# Session Handoff — G2.3/G2.4 Real Acceptance Attempt 1 + Fix

## Status

- Date: 2026-08-31
- Branch: `main`
- G1 / P2.6: **PASS / PRODUCTION / FROZEN**
- G2.1 Scene Timeline Contract: **FINAL PASS / FROZEN FOUNDATION**
- G2.2 Deterministic Assembler: **FINAL PASS / FROZEN FOUNDATION**
- G2.3 Scene Narrative: **USER-LOCAL TEST PASS / REAL-MODEL ACCEPTANCE RETEST REQUIRED**
- G2.4 Source/Support Validator: **USER-LOCAL TEST PASS / REAL-MODEL ACCEPTANCE RETEST REQUIRED**
- Character V10.1: protected / unchanged

## 1. Accepted preconditions

User-local tests before the first real-model attempt:

```text
python -m pytest engine/tests/v2/test_breakdown_scene_narrative_v1.py engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py -q
........ [100%]
8 passed
```

Runtime preflight:

```text
profile = breakdown-g2-scene-narrative-qwen3-local-v1
status = READY
device = cuda
max_new_tokens = 512
missing = []
```

## 2. Real-model attempt 1 evidence

Command:

```powershell
python scripts/run_breakdown_g2_scene_narrative_acceptance_v1.py
```

Frozen structural truth remained correct:

```text
scenes = 2
shots = 30
people = [2, 2]
shot1_people = []
shot1_props = ['遥控器', '蓝色玫瑰花束', '玻璃花瓶', '书本']
shot_objects_unchanged = YES
```

Therefore the important safety boundary passed:

```text
Narrative overlay did NOT change any Shot object.
G1/G2.1/G2.2 source truth remained intact.
```

But Narrative acceptance did NOT pass.

Observed overlay:

```text
overlay_status = READY_WITH_WARNINGS
```

Warnings:

```text
Scene 1 title rejected because “纠纷” used characters not literally present in support.
Scene 1 summary rejected because it mentioned “公寓走廊” but omitted the location Fxxxx from support.
Scene 1 therefore fell back completely to deterministic title/summary.
Scene 2 model result was missing and fell back completely to deterministic title/summary.
```

Attempt 1 conclusion:

```text
STRUCTURE SAFETY = PASS
NARRATIVE QUALITY / COMPLETENESS = FAIL
G2.3/G2.4 FINAL PASS = NO
```

The old acceptance runner printed `acceptance_machine_gate=PASS` because it only checked frozen Shot invariants. That gate was too weak and has now been corrected.

## 3. Root causes

### A. Validator was over-constrained for titles

The v1 validator required every substantive Chinese character in title/summary to already occur in the cited source text.

That safely blocked hallucinations, but it also blocked legitimate high-level title abstraction:

```text
质问 + 对峙 + 愤怒
→ 纠纷
```

The title is a soft Narrative label, so this was stricter than the intended G2 authority model.

### B. Hard-anchor support omission was recoverable

If a claim text literally contains an existing frozen anchor such as:

```text
公寓走廊
夜晚
客厅
```

and the model forgot to list the corresponding Fxxxx, the Validator can determine the missing source fact without guessing. Rejecting the whole claim was unnecessarily destructive.

### C. Scene 2 runner failure was hidden

The local adapter discarded FAILED runner rows and only returned READY candidates. The Organizer therefore surfaced only:

```text
文本模型未返回可用结果
```

without a safe `error_type`, making real-model diagnosis unnecessarily opaque.

### D. Prompt contained more facts than Narrative needs

The model was receiving the full Grounding Packet, including cinematography/OCR and other facts that are not useful for Scene title/summary. This increased context noise, especially for the longer Scene 2.

## 4. Fix implemented after attempt 1

### Prompt profile

Updated to:

```text
breakdown-g2-scene-narrative-zh-v1.1
```

The model now receives a compact narrative projection:

```text
Scene location / space / time / environment
Scene deterministic base summary
ASR dialogue
```

If base summary is absent, Shot visual/performance/prop-interaction facts are used as fallback.

OCR, shot type, composition and camera motion are no longer sent to the text Narrative model because they are not needed for the two allowed output fields.

### Title validator

Titles remain grounded but may use a small controlled abstraction vocabulary such as:

```text
冲突 / 争执 / 纠纷 / 对话 / 交流 / 对峙 / 质问 / 回应 / 矛盾
```

Arbitrary new title characters are still rejected, so ASR/OCR names do not gain an unrestricted path into user-visible output.

### Summary validator

Story summary remains conservative:

```text
real support required
known Scene-local people only
narrative/visual/action support required
new concrete lexical content still rejected
new numeric literals rejected
```

So the fix does NOT weaken the rule that a real support id cannot be used as cover for a fabricated concrete action.

### Hard-anchor support completion

If the generated text literally contains an existing frozen hard anchor, G2.4 now deterministically appends its matching Fxxxx support instead of rejecting the whole claim.

This is source completion, not inference.

### Runner diagnostics

`Qwen3VLSceneTextLLM.last_batch_diagnostics()` now exposes only safe per-Scene fields:

```text
status
error_type
```

No prompts, model output, paths, tokens or secrets are included.

### Acceptance gate

The real acceptance runner now prints separate gates:

```text
structure_gate
narrative_gate
acceptance_machine_gate
```

Final machine PASS requires:

```text
all frozen Shot objects unchanged
AND
both Scenes have an accepted readable_title
AND
both Scenes have an accepted story_summary
AND
no Scene runner failure
AND
overlay_status = READY
```

A structural-only success can no longer be mistaken for complete G2.3/G2.4 acceptance.

## 5. Files changed in the fix

```text
engine/app/breakdown_scene_narrative_validator_v1.py
engine/app/breakdown_scene_narrative_v1.py
engine/app/breakdown_scene_narrative_qwen3_v1.py
engine/tests/v2/test_breakdown_scene_narrative_v1.py
scripts/run_breakdown_g2_scene_narrative_acceptance_v1.py
```

Frozen files were not changed:

```text
engine/app/breakdown_scene_timeline_contract_v1.py
engine/app/breakdown_scene_timeline_assembler_v1.py
Window v4
Exact-Shot v3
Fusion E6-v2
Character V10.1
```

## 6. Required retest

First re-run the unit/contract gate because Validator/Prompt behavior changed:

```powershell
python -m pytest engine/tests/v2/test_breakdown_scene_narrative_v1.py engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py -q
```

Expected:

```text
8 passed
```

Then run real-model acceptance again:

```powershell
python scripts/run_breakdown_g2_scene_narrative_acceptance_v1.py
```

Target final lines:

```text
shot_objects_unchanged= YES
structure_gate= PASS
narrative_gate= PASS
acceptance_machine_gate= PASS
```

Also inspect both Scene titles/summaries for factual readability before marking FINAL PASS.

If Scene 2 still fails, use the new `runner_diagnostics` / `runner_scene_status` output to identify its safe error type. Fix G2.3 only; do not retune frozen G1 or G2.1/G2.2.
