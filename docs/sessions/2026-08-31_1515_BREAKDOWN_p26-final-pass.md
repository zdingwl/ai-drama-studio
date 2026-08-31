# Session Handoff — P2.6 Final PASS

Date: 2026-08-31

## Final accepted real production Run

```text
Run = BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
Episode = EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
ShotRevision = SHOTREV_1462ac6d9f3948b994fc9bc575fee3a0
status = READY
whole run ~= 841.039s = 14.017 min
```

Production profiles:

```text
Window = breakdown-p2-vlm-window-context-segment-index-zh-v4
Exact-Shot = breakdown-p2-vlm-exact-shot-compact-reconstruction-zh-v3
Fusion = breakdown-p2-fusion-episode-context-e6-v2
Pipeline = breakdown-p2-full-v1
```

Final quality/performance gates:

```text
Window 4/4 READY
Exact-Shot 6/6 READY
MAXED=0
Scenes=2
Scene1 LocalSubjects=2
Scene2 LocalSubjects=2
same-Shot conflicts=0
Shot0001 subjects=0
Shot0001 props include 蓝色玫瑰花束 + 玻璃花瓶
whole-run <30min
whole-run <=20min
```

Fusion continuity provenance:

```text
window_hint_resolution_policy = window-hint-positive-appearance-support-compact-alias-v2
compact_appearance_policy = compact-observation-stable-alias-normalization-v1
same_shot_cannot_link = hard
promotion_source = g1-read-only-replay-v5-real-accepted
```

## Decision

```text
P2.6 = PASS
Fast Grounded G1 = REAL ACCEPTED / PRODUCTION / FROZEN
G2 Scene-level text organization = UNBLOCKED
Scene Timeline UI = UNBLOCKED
```

Do not modify G1 unless a new real regression provides concrete evidence.

## Protected Character baseline

Character V10.1 remains unchanged:

```text
YOLOX -> capture-first evidence -> mature MOT -> YoutuReID
-> RESOLVED/UNRESOLVED -> explicit Shot Assignment -> Final Gate
```

LocalSubject remains Scene-scoped anonymous evidence and must never be treated as Character identity.

## Next safe work

Start G2 / Scene Timeline from current accepted Draft contracts:

```text
1. define user-facing Scene Timeline contract
2. deterministic assembler: Scene -> Shots -> people/actions -> dialogue -> props -> visual description
3. ASR_SEGMENT stays dialogue truth
4. Exact-Shot stays visual truth
5. optional Scene-level pure-text LLM only for organization/readability
6. build primary UI around direct results, with Evidence/debug internals hidden by default
```

Hosted GitHub Actions remain unused. Commits use `[skip ci]`.
