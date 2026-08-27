# Session Handoff — Character V10.1 Known-Face Shot Presence

> Date: 2026-08-27 14:25 +08:00  
> Branch: `main`  
> Area: 03 资产 / Character V10.1 / ShotCharacterBinding

## User-visible regression result

After the first same-Shot fragment aggregation patch, the user reran the same real short-drama sample.

Observed result:

```text
SHOT 0001: no Character expected
SHOT 0002: young woman visible, still unbound
SHOT 0003: 人物001 correct
SHOT 0004: old woman + young woman visible, only 人物001 bound
SHOT 0005: 人物001 correct
SHOT 0006: 人物001 now correctly recovered
SHOT 0007: 人物002 now correctly recovered
```

This is important evidence:

```text
Global Character classes remain correct.
Pass-2 body/fragment aggregation improved real binding recall.
Remaining misses are concentrated in clear-face / close-up / two-person Face-presence cases.
```

Do not respond by lowering global new-identity or generic body ReID thresholds.

## Root cause found in current Pass 2

`engine/app/character_shot_presence_v101.py` previously used:

```text
FACE_STRONG = 0.52
FACE_POSITIVE_MIN_SCORE = 0.76
```

and returned a hard Face conflict if **any single** high-quality Gallery Face comparison fell below the conflict threshold.

That combination is too brittle for real SFace expression/viewpoint/crop variation:

- moderate but repeated Face matches could not contribute to known-person presence;
- one noisy Gallery Face crop could veto an otherwise correct identity;
- synthetic-body ReID around a face fallback could outrank the actual Face identity.

## Code patch

### `engine/app/character_shot_presence_v101.py`

Commit:

```text
15ea698dd95558546cf360560af0453cbd63570a
fix: improve known-face Shot presence recovery
```

Current behavior:

```text
FACE_SUPPORTED = 0.40
FACE_STRONG = 0.50
FACE_PAIR_MIN_SCORE = 0.76
MIN_FACE_SUPPORT_OBSERVATIONS = 2
MIN_FACE_SUPPORT_TIMESTAMPS = 2
MIN_FACE_GROUP_SCORE = 0.84
STRONG_FACE_PRESENCE_SCORE = 0.89
```

Rules:

1. Moderate Face support must repeat on >=2 current-Shot observations and >=2 timestamps.
2. Face support for one observation still requires >=2 independent confirmed Gallery Shots.
3. One genuinely strong Face observation can confirm presence of an already-known Character.
4. Face-supported candidate identities are ranked before synthetic-body ReID for close-up fallback observations.
5. A Face hard conflict now requires consistent conflict across >=2 independent Gallery Shots and no supported positive Face match.
6. Same-sample cannot-link remains an immediate hard rejection.
7. New identity creation is unchanged.

Pass-2 Track provenance now additionally records:

```text
face_support_count
```

### Focused tests

Commit:

```text
f9f1e19b5f20f7769f63ce4e8ee53c1c75dcf451
test: lock repeated Face Shot presence recovery
```

Added/updated cases:

```text
one strong Face → known presence may recover
repeated moderate Face below old 0.52 threshold → may recover
single moderate Face → stays unresolved
Face-supported identity outranks synthetic-body ReID
body fragment and cannot-link regressions remain locked
```

## Documentation sync

Updated:

```text
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/PROJECT_STATE.md
docs/ASSET_CHARACTER_RECOGNITION_V10_1.md
```

These documents now record the second real-video rerun and the repeated moderate known-Face presence path.

## CI reality

Do not claim the repository is green.

Before this latest Face patch, the backend full-test summary was:

```text
28 failed, 176 passed, 1 skipped
```

Existing failures are repository-level legacy/runtime/environment categories. CI for the latest Face-focused patch may still be pending.

## Next Windows acceptance

The user must pull latest `main`, restart backend, and run **a new asset extraction Run**. Old Runs do not gain new recovery metadata.

Priority checks:

```text
SHOT 0002 → should bind 人物002
SHOT 0004 → should bind 人物001 + 人物002
SHOT 0006 → should remain 人物001
SHOT 0007 → should remain 人物002
SHOT 0009 → verify every actually visible known Character
```

If 0002 or 0004 still miss, inspect these before changing thresholds:

```text
YuNet Face observation count
face_score
SFace support against >=2 Gallery Shots
CharacterTrack.evidence_json.identity_recovery.face_support_count
recovery score
winner margin to the next resolved identity
```

If `face_support_count == 0`, the failure is upstream Face observation/feature quality, not Shot binding threshold logic.

If Face support is present but no recovery occurs, inspect candidate ambiguity / winner margin / consistent conflict diagnostics.

Do not lower global Person-ReID identity confirmation thresholds unless the failure is proven to be identity-classification related.
