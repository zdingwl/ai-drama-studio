# 2026-08-29 Dialogue projection display dedupe

## User-visible issue

A real Episode Breakdown completed successfully after the E2/E3 runtime hardening, but a dialogue segment crossing a Shot cut appeared twice in `02 拉片 → 拉片结果`. Example: the ASR segment `王阿姨` started in Shot 0001 and crossed the 0.800s cut, so E1 correctly kept the same full ASR text on both Shot projections; the normal UI printed both projections as if they were two dialogue lines.

## Root cause

This is a presentation-layer mismatch, not duplicate ASR truth.

`breakdown_p2_fusion_episode_v2.py` intentionally preserves full `ASR_SEGMENT` text on every intersecting Shot projection and records:

```text
dialogue_group_id / asr_segment_id
projection_index / projection_count
continues_from_previous_shot
continues_to_next_shot
```

That is required for immutable Episode-time dialogue truth and downstream provenance, but `BreakdownResultsV1.vue` previously rendered every `DIALOGUE` projection without interpreting those fields.

## Fix

Added `frontend/src/utils/dialogueProjection.ts` and changed `BreakdownResultsV1.vue` to apply a result-view policy:

```text
first projection of a dialogue group → render full dialogue once
later Shot projection             → do not repeat the sentence
Shot containing only continuation → show “承接上一镜对白”
duplicate rows with same dialogue_group_id inside one Shot → render once
historical rows without projection metadata → preserve previous behavior
```

The backend Draft/Evidence data is not rewritten or deleted. This is display-only deduplication, so an already-generated E1 result can benefit after frontend update/reload; the Episode does not need to be re-run solely for this fix.

## Coverage

Added `frontend/src/utils/dialogueProjection.test.ts` covering first projection, later projection suppression, same-group dedupe, and historical compatibility.

No hosted CI was triggered. Local frontend test/build was not executed in this connector environment, so this change is code-reviewed but still requires the user's local UI verification.

## Status

P2.6 remains NOT PASSED. E1/E2/E3 real-result review continues. P2-E4 remains planned and should not be started until current real-result issues are reviewed.
