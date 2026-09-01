# P6 Final Breakdown Read Model V1

> Status: **IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING**  
> Date: 2026-09-01 +08:00  
> Scope: ordinary-user Breakdown read model + Final Character / Scene / Prop display fill-back only.

## 1. P6 role

P6 does not add another recognition system. It only composes already-owned truth:

```text
Frozen G2 Scene Timeline
        +
Frozen P5 Character resolution
        +
Current Final ShotSceneBinding / ShotPropBinding
        +
Current Final Character / Scene / Prop display assets
        ↓
P6 final ordinary-user Breakdown read model
```

Ownership remains unchanged:

```text
G2 owns Scene/Shot/dialogue/OCR/action/prop-observation/cinematography facts.
P5 owns the only safe anonymous P* -> Final Character bridge.
Final ShotSceneBinding owns Shot -> Final Scene truth.
Final ShotPropBinding owns Shot -> Final Prop truth.
P6 only reads and displays them.
```

## 2. Character authority

Only this path may produce a Final Character display:

```text
G2 Scene-local P*
→ same Episode / BreakdownRun / ShotRevision / Scene / P* row
→ P5 status = RESOLVED
→ same current AssetRevision
→ existing Final Character id/name/cover
→ ordinary-user display
```

`UNRESOLVED` stays `人物N`.

P6 never uses Breakdown prose, ASR names, OCR, speaker labels, relationships, role hints, appearance summaries, action/emotion/pose, P1/P2 labels themselves, or `subject_A/B` as identity authority.

## 3. Final Scene authority

Final Scene fill-back never uses G2 title/location text similarity.

For one G2 Scene:

```text
exact current ShotRevision mapping
→ collect Final ShotSceneBinding for every Shot in that G2 Scene
→ every Shot must have a binding
→ every binding must point to the same existing Final Scene
→ only then expose final_scene
```

If one Shot is missing a Scene binding or different Shots point to different Final Scenes:

```text
final_scene = null
G2 Scene title / summary / scene_info remain unchanged
```

This is an intentional conservative rule. P6 never guesses which Final Scene is “closest”.

## 4. Final Prop authority

Final Prop fill-back is Shot-local:

```text
current Shot
→ Final ShotPropBinding
→ existing Final Prop id/name/cover
→ final_props[]
```

G2 `props[]` remains a separate visual observation list. P6 never turns a G2 label such as `花瓶` into a specific Final Prop by name/string similarity.

Ordinary UI therefore keeps both concepts separate:

```text
最终道具 = Final ShotPropBinding assets
道具观察 = frozen G2 visible prop / interaction facts
```

## 5. Independent fail-closed domains

Character and Scene/Prop overlays fail closed independently.

```text
Character bridge invalid
→ people become anonymous
→ safe Final Scene/Prop may still display

Scene/Prop asset surface invalid
→ final_scene/final_props cleared
→ safe Final Character display remains
```

The Scene/Prop overlay additionally verifies:

```text
current AssetRevision
exact current source ShotRevision
every Timeline Shot ordinal maps one-to-one to a current Shot
no duplicate Shot/Scene overlay keys
Final Scene/Prop IDs exist in the current project
no duplicate Final Prop in one Shot
frontend Scene/Shot overlay surface exactly matches frozen Timeline
```

A corrupt Scene/Prop overlay is reduced to an empty asset overlay plus a user-readable warning; it does not make the whole Breakdown endpoint unavailable.

## 6. Frozen Timeline rule

Backend response keeps the full G2 object untouched under `timeline`:

```json
{
  "schema_version": "breakdown-read-model-v1",
  "timeline": { "schema_version": "scene-timeline-v1" },
  "identity": { "scenes": [] },
  "assets": {
    "asset_revision_id": "...",
    "scenes": [],
    "shots": []
  }
}
```

P6 must never rewrite:

```text
timestamps
Scene/Shot boundaries
G2 Scene title / scene_info / story_summary
visual_description
action/performance facts
ASR dialogue
OCR text
G2 props / interaction
cinematography
P* Shot membership
```

The real acceptance runner independently rebuilds frozen G2 and requires:

```text
timeline_preserved = true
```

## 7. Implementation

Backend:

```text
engine/app/breakdown_read_model_contract_v1.py
engine/app/breakdown_read_model_v1.py
engine/app/breakdown_read_model_routes_v1.py
engine/app/breakdown_final_asset_overlay_v1.py
engine/app/main.py
```

Read endpoint:

```http
GET /api/episodes/{episode_id}/breakdown-read-model
```

Frontend:

```text
frontend/src/types/breakdown-read-model.ts
frontend/src/types/scene-timeline.ts
frontend/src/utils/breakdownReadModelUi.ts
frontend/src/utils/sceneTimelineUi.ts
frontend/src/api/scene-timeline.ts
frontend/src/components/SceneTimelineResultsV1.vue
```

Ordinary Episode reading uses P6. Historical/debug Run reading remains frozen G2.5, so current Final assets are never projected onto historical Breakdown runs.

## 8. Ordinary-user rendering

### Character

```text
RESOLVED -> Final Character cover + name
UNRESOLVED -> text avatar + 人物N
missing/broken cover -> text avatar fallback
```

Rendered in:

```text
Scene hero -> 本场人物
Shot inspector -> 人物
```

### Scene

When the exact unanimous ShotSceneBinding rule succeeds:

```text
Scene hero -> 独立“最终场景”卡片：cover + Final Scene name
```

The G2 Scene title remains visible as the actual Breakdown reading title and is not overwritten.

### Prop

When Final ShotPropBinding exists:

```text
Shot inspector -> “最终道具”：Final Prop cover/name cards
Shot inspector -> “道具观察”：original G2 labels/interactions
```

No technical IDs, P* refs, resolution basis, confidence or evidence internals are exposed in ordinary UI.

## 9. Tests added

Backend:

```text
engine/tests/v2/test_breakdown_read_model_v1.py
engine/tests/v2/test_breakdown_read_model_routes_v1.py
engine/tests/v2/test_breakdown_final_asset_overlay_v1.py
engine/tests/v2/test_breakdown_read_model_asset_independence_v1.py
```

Coverage includes:

```text
RESOLVED-only Character display
UNRESOLVED stays anonymous
verbatim Timeline preservation
Run / ShotRevision / AssetRevision mismatch
Scene/P* mismatch
Character snapshot mismatch
invalid aggregate counts
exact Final Scene unanimous binding
Scene binding conflict -> only that Scene unresolved
Shot-local Final Prop projection
no G2 label fallback to Final Prop
invalid asset surface -> only asset overlay cleared
invalid Character bridge -> safe Scene/Prop retained
invalid Scene/Prop overlay -> safe Character retained
safe HTTP 404/409 and GET-only route
```

Frontend:

```text
frontend/src/utils/breakdownReadModelUi.test.ts
frontend/src/utils/breakdownReadModelAssetsUi.test.ts
frontend/src/utils/sceneTimelineUi.test.ts
```

Coverage includes Character projection, independent Scene/Prop projection, malformed overlay fallback, input immutability, verbatim dialogue/OCR/Shot fact preservation, G2 prop observation preservation, `subject_A/B` display sanitization, person lookup and avatar fallback.

## 10. Real Episode runner

```text
scripts/run_breakdown_p6_read_model_acceptance_v1.py
```

It prints:

```text
Episode / BreakdownRun / ShotRevision
identity AssetRevision / final asset AssetRevision
resolved vs anonymous people
Final Character id/name/cover
G2 Scene title + Final Scene id/name/cover
G2 prop observations + Final Prop bindings per Shot
identity / asset warnings
timeline_preserved
```

Any Timeline mutation exits with `FAILED_TIMELINE_MUTATION_GUARD`.

## 11. Acceptance status

Implementation is on `main`.

Assistant-environment evidence only:

```text
P6 pure TypeScript display types/projection logic -> isolated `tsc --strict` PASS
person avatar helper -> isolated `tsc --strict` PASS
```

This is **not** full project acceptance. The assistant execution environment has no installed `vue`, `@vue/compiler-sfc` or `vue-tsc`, and cannot clone/install the project through GitHub DNS, so full pytest/Vitest/Vue typecheck/build are not claimed.

Required user-local acceptance:

```bash
python -m pytest \
  engine/tests/v2/test_breakdown_read_model_v1.py \
  engine/tests/v2/test_breakdown_read_model_routes_v1.py \
  engine/tests/v2/test_breakdown_final_asset_overlay_v1.py \
  engine/tests/v2/test_breakdown_read_model_asset_independence_v1.py -q

python scripts/run_breakdown_p6_read_model_acceptance_v1.py <EPISODE_ID>

cd frontend
npm install
npm test -- \
  src/utils/breakdownReadModelUi.test.ts \
  src/utils/breakdownReadModelAssetsUi.test.ts \
  src/utils/sceneTimelineUi.test.ts
npm run typecheck
npm run build
```

Expected runner safety signal:

```text
status = READY
timeline_preserved = true
RESOLVED Character may show Final Character asset
UNRESOLVED Character remains anonymous
Final Scene only appears under exact unanimous ShotSceneBinding
Final Props only appear from ShotPropBinding
```

Visual review must confirm:

```text
Final Character -> cover/name; broken cover -> fallback
Final Scene -> separate card, G2 Scene title remains unchanged
Final Props -> separate from G2 “道具观察”
no broken-image UI
Scene / Shot / dialogue / OCR / G2 prop facts unchanged
console = 0 errors
```

`npm install` is also expected to synchronize the existing TypeScript `6.0.3` `package.json` change into `package-lock.json` if that lockfile has not yet been regenerated locally.

Do not mark P6 FINAL PASS until these user-local commands and visual review are supplied.
