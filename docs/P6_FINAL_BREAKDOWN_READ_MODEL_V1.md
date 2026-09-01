# P6 Final Breakdown Read Model V1

> Status: **IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING**  
> Date: 2026-09-01 +08:00  
> Scope: final ordinary-user Breakdown identity/asset display composition only.

## 1. Why P6 exists

G2 Scene Timeline already owns the readable Scene / Shot / dialogue / OCR / prop / cinematography facts. P5 already owns the only accepted bridge from anonymous Scene-local people to existing Final Characters.

P6 does **not** add another recognition system. It only composes those frozen truths for the ordinary-user reading surface:

```text
Frozen G2 Scene Timeline
        +
Frozen P5 Breakdown ↔ Character resolution
        +
Current Final Character display asset
        ↓
P6 final Breakdown read model
```

## 2. Authority direction

The only allowed identity path is:

```text
G2 Scene-local P*
→ same Episode
→ same current BreakdownRun
→ same ShotRevision
→ same Scene ordinal
→ same P* ref / anonymous display row
→ P5 status = RESOLVED
→ P5 Character id/name
→ same current AssetRevision
→ existing Final Character id/name/cover
→ ordinary-user display
```

Any mismatch fails closed and keeps the G2 anonymous name (`人物N`).

P6 never uses the following as identity authority:

```text
Breakdown prose
ASR dialogue text
OCR text
speaker labels
relationship words
role hints
appearance summaries
action / pose / emotion
P1/P2 labels by themselves
subject_A/B
```

## 3. Frozen-data rule

The backend response keeps the complete G2 payload under `timeline` and puts identity in a separate `identity` overlay:

```json
{
  "schema_version": "breakdown-read-model-v1",
  "timeline": { "schema_version": "scene-timeline-v1" },
  "identity": {
    "asset_revision_id": "...",
    "resolved_count": 1,
    "unresolved_count": 3,
    "warnings": [],
    "scenes": []
  }
}
```

P6 is forbidden from rewriting G2 timestamps, Scene boundaries, Shot boundaries, visual descriptions, performance facts, ASR dialogue, OCR text, props, cinematography, or P* Shot membership.

The service contains an explicit equality guard that rejects any successful composition which changes the normalized frozen Timeline object.

## 4. Fail-closed checks

Before one Final Character name is rendered, P6 verifies:

1. Episode id matches.
2. BreakdownRun id matches the G2 source run.
3. ShotRevision id matches the G2 source revision.
4. P5 `asset_revision_id` is still the current project AssetRevision.
5. P5 aggregate Scene/person/resolved/unresolved counts are internally consistent.
6. Scene ordinal sets match exactly and contain no duplicates.
7. Every Scene P* ref set matches exactly and contains no duplicates.
8. P5 anonymous `local_display_name` matches the G2 anonymous display row.
9. Every P5 `RESOLVED` Character still exists in the current project.
10. Current Character id/name matches the P5 resolved Character id/name.

If any check fails, the **whole identity overlay** for the Episode is rendered anonymously. P6 never applies a questionable partial mapping.

## 5. Current implementation

Backend:

```text
engine/app/breakdown_read_model_contract_v1.py
engine/app/breakdown_read_model_v1.py
engine/app/breakdown_read_model_routes_v1.py
engine/app/main.py
```

Endpoint:

```http
GET /api/episodes/{episode_id}/breakdown-read-model
```

The endpoint is read-only. It does not start a model, create a Character, update a binding, or write an AssetRevision.

Frontend:

```text
frontend/src/types/breakdown-read-model.ts
frontend/src/types/scene-timeline.ts
frontend/src/utils/breakdownReadModelUi.ts
frontend/src/utils/breakdownReadModelUi.test.ts
frontend/src/utils/sceneTimelineUi.ts
frontend/src/utils/sceneTimelineUi.test.ts
frontend/src/api/scene-timeline.ts
frontend/src/components/SceneTimelineResultsV1.vue
```

Ordinary Episode reading uses the P6 endpoint. Historical/debug Run reading still uses the frozen G2.5 Run endpoint, so current Final Character assets cannot be accidentally projected onto a historical run.

The frontend applies a second fail-closed validation before projecting display names. Existing G2.6 rendering then uses the Final Character name wherever it resolves a Scene-local P* for:

```text
本场人物
Shot 人物
performance 人物标签
dialogue speaker label when G2 already has a speaker ref
```

Final Character `cover_url` is now rendered directly in the ordinary-user reading page for:

```text
本场人物
右侧镜头详情 -> 人物
```

If a person is anonymous, has no Final Character cover, or the cover image fails to load, the renderer falls back to a compact text avatar derived from the visible display name. It does not expose identity status, Character IDs, P* refs or technical resolution labels to the ordinary user.

The renderer reads only the P6 display-only `final_character` object. It does not mutate the frozen G2 Timeline or P5 resolution.

## 6. Ordinary-user behavior

Resolved:

```text
G2: 人物2
P5: RESOLVED -> Character CHAR1 / 人物001
P6 display: [Final Character cover] 人物001
```

Unresolved:

```text
G2: 人物1
P5: UNRESOLVED
P6 display: [text avatar] 人物1
```

Missing/broken cover:

```text
Final Character name is safely resolved but cover_url is empty or image load fails
→ keep Final Character display name
→ fall back to text avatar
```

Stale/mismatched:

```text
P5 or AssetRevision no longer matches current G2/current assets
→ all people remain anonymous
→ user-safe warning only
```

## 7. Tests and real acceptance runner

Backend deterministic coverage:

```text
engine/tests/v2/test_breakdown_read_model_v1.py
engine/tests/v2/test_breakdown_read_model_routes_v1.py
```

The tests cover:

```text
RESOLVED-only Final Character display
UNRESOLVED remains anonymous
verbatim G2 Timeline preservation
BreakdownRun mismatch
ShotRevision mismatch
AssetRevision mismatch
Scene/P* mismatch
Character snapshot missing/name mismatch
invalid aggregate counts
duplicate Scene/P* refs
safe HTTP 404/409 behavior
GET-only route registration
```

Frontend deterministic coverage:

```text
frontend/src/utils/breakdownReadModelUi.test.ts
frontend/src/utils/sceneTimelineUi.test.ts
```

It covers safe name/asset projection, anonymous fallback, mismatch handling, input immutability, preservation of dialogue/OCR/Shot facts, existing `subject_A/B` display sanitization, person ref lookup and avatar fallback text.

Real Episode runner:

```text
scripts/run_breakdown_p6_read_model_acceptance_v1.py
```

The runner prints the real Episode/Run/ShotRevision/AssetRevision, resolved vs anonymous people, Final Character id/name/cover URL and warnings. It also independently rebuilds the frozen G2 Scene Timeline and requires exact equality with P6 `timeline`; otherwise it exits with `FAILED_TIMELINE_MUTATION_GUARD`.

## 8. Acceptance status

Implemented code and Final Character cover rendering are on `main`.

Isolated strict TypeScript checks of the P6 frontend projection core and the new person avatar helpers passed in the assistant execution environment.

This is **not** full project acceptance. The execution environment cannot resolve `github.com`, so the current repository cannot be cloned there for full pytest/Vitest/Vue build execution. The Vue renderer therefore still requires user-local typecheck/build plus visual review.

Required user-local acceptance remains:

```bash
python -m pytest \
  engine/tests/v2/test_breakdown_read_model_v1.py \
  engine/tests/v2/test_breakdown_read_model_routes_v1.py -q

python scripts/run_breakdown_p6_read_model_acceptance_v1.py <EPISODE_ID>

cd frontend
npm install
npm test -- src/utils/breakdownReadModelUi.test.ts src/utils/sceneTimelineUi.test.ts
npm run typecheck
npm run build
```

Expected real runner safety signal:

```text
status = READY
timeline_preserved = true
RESOLVED people may show existing Final Character name/assets
all other people remain ANONYMOUS
```

Ordinary-user visual review should additionally confirm:

```text
resolved person -> cover + Final Character name
anonymous person -> text avatar + 人物N
broken/missing cover -> text avatar, no broken-image UI
Scene / Shot / dialogue / OCR contents unchanged
```

`npm install` is also expected to synchronize the existing TypeScript `6.0.3` `package.json` change into `package-lock.json`.

Do not mark P6 FINAL PASS until the user-local commands and ordinary-user visual review are supplied.
