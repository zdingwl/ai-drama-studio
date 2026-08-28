# AI Drama Studio — P3 V2 continuous Shot review handoff

> Date: 2026-08-28  
> Branch: `feat/p3-v2-continuous-shot-review`  
> Base: `main@b963e723ce2539d06f1a7a20241e91ab56512dde`  
> Status: **IMPLEMENTED / LOCAL BROWSER ACCEPTANCE REQUIRED**

## 1. Scope

This is a P3 Structured Draft Workbench V2 interaction improvement only.

It does not change:

```text
breakdown-draft-v1
P1/P2 persistence or Fusion
ASR / OCR / VLM
ShotRevision history semantics
P4 asset guidance
Character V10.1
Final Character / Scene / Prop bindings
```

## 2. Continuous Shot review

The center workbench now exposes:

```text
上一镜
当前 Shot position / total
下一镜
```

The sequence comes from the already-loaded Draft in exact serialized order:

```text
draft.scene_segments.flatMap(segment => segment.shots)
```

Selecting an adjacent Shot reuses the existing `selectShot()` behavior:

```text
selectedSceneId = shot.scene_segment_id
selectedShotId = shot.id
selectedEventId = ''
seekUs = 0
seekToken += 1
```

Therefore cross-Scene review does not guess by mutable Current Shot IDs, ordinal matching, or source timestamps.

Reference Clip behavior remains unchanged and continues to use the selected Draft Shot's exact historical `ShotRevisionItem.reference_url`.

## 3. Return to Current Draft

`BreakdownDraftV2` now remembers the Run returned by the formal current endpoint:

```text
GET /api/episodes/{episode_id}/breakdown-current
```

When the user browses a historical/FAILED/STALE Run, the summary bar exposes:

```text
返回当前采用草稿
```

The action reloads that persisted current Run through the existing read API. It does not rerun P2 and does not mutate history.

## 4. Files

```text
frontend/src/components/BreakdownDraftV2.vue
frontend/src/components/BreakdownShotReviewShellV1.vue
```

## 5. Local browser acceptance

Verify:

```text
1. open a READY Draft with multiple Shots
2. click 下一镜 repeatedly and confirm Shot ordinal progresses in serialized Draft order
3. cross a Scene boundary and confirm left Scene/Shot selection follows the new Shot
4. confirm right Reference Clip switches to that Shot's exact historical clip and starts at 0
5. select a Timeline event, then click 下一镜 and confirm the previous event selection is cleared
6. first Shot disables 上一镜
7. last Shot disables 下一镜
8. open FAILED / STALE history and confirm 返回当前采用草稿 is visible when a Current Draft exists
9. click it and confirm the persisted Current Draft is restored without starting a background task
```

## 6. Acceptance truth

P3 remains `IMPLEMENTED / UI ACCEPTANCE IN PROGRESS` until the user explicitly accepts the browser behavior.

Hosted GitHub Actions were not queried or run.
