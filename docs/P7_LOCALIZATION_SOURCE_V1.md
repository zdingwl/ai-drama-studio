# P7.1 Localization Source Package V1

> Status: **IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING**  
> Date: 2026-09-01 +08:00  
> Scope: immutable source handoff into future 04 本土化剧本 / 05 镜头重制方案.

## 1. Why this layer exists

P6 already gives the current ordinary-user truth:

```text
Frozen G2 Scene Timeline
+ safe Final Character display
+ exact Final Scene / Final Prop bindings
```

Downstream localization must not read raw Draft tables directly, and it must not write translated/localized copy back into ASR/OCR source fields. P7.1 therefore creates one deterministic, version-anchored source package.

```text
P6 current read model
+ Project source_language / target_language / target_region
→ P7.1 Localization Source Package
→ future revisioned localization draft
```

P7.1 performs no translation and writes no business state.

## 2. Source-of-truth rules

Immutable source fields:

```text
source_dialogue[].source_text       = P6/G2 ASR-origin dialogue text, verbatim
source_on_screen_text[].source_text = P6/G2 OCR-origin text, verbatim
visual_description                  = frozen G2 Shot fact
performance                         = frozen G2 Shot fact
observed_props                      = frozen G2 prop observation, not Final Prop identity
cinematography                      = frozen G2 fact
```

Safe display/final-asset fields:

```text
people       = P6 display only; RESOLVED may carry Final Character, otherwise anonymous
final_scene  = P6 Final Scene overlay only
final_props  = P6 Shot-local Final Prop bindings only
```

Forbidden shortcuts:

```text
ASR/OCR source text -> overwrite with translation/localization        forbidden
G2 prop label -> infer Final Prop                                    forbidden
G2 Scene title -> infer Final Scene                                  forbidden
P* ref -> treat as cross-Scene Character identity                    forbidden
old v2_dialogues rows -> silently become current Breakdown source    forbidden
```

## 3. Version anchors

Every package carries:

```text
project_id
 episode_id
source_breakdown_run_id
source_shot_revision_id
source_asset_revision_id (when current Final assets exist)
source_language
target_language
target_region
```

P7.1 only accepts a current P6 Timeline. If Character and Scene/Prop overlays carry conflicting non-null AssetRevision IDs, composition fails closed.

## 4. P* handling

Scene-local P* refs are used only internally to join frozen G2 Shot facts to the already-safe P6 person display row.

P7.1 output person objects contain only:

```json
{
  "display_name": "人物001",
  "character": {
    "id": "CHAR...",
    "name": "人物001",
    "cover_url": "..."
  }
}
```

or, when unresolved:

```json
{
  "display_name": "人物1",
  "character": null
}
```

P* is not exported as downstream business identity.

## 5. Stable source keys

Dialogue and OCR rows receive deterministic keys within the version anchors:

```text
S{scene}:H{shot}:D{dialogue_index}
S{scene}:H{shot}:T{ocr_index}
```

Example:

```text
S1:H3:D1
S1:H3:T1
```

A future localization revision may reference these keys, but the keys are meaningful only together with the package's BreakdownRun + ShotRevision anchors.

## 6. Implementation

Backend:

```text
engine/app/localization_source_contract_v1.py
engine/app/localization_source_v1.py
engine/app/breakdown_read_model_routes_v1.py
```

Read-only endpoint:

```http
GET /api/episodes/{episode_id}/localization-source
```

Deterministic tests:

```text
engine/tests/v2/test_localization_source_v1.py
engine/tests/v2/test_localization_source_routes_v1.py
```

Real Episode runner:

```text
scripts/run_localization_source_acceptance_v1.py
```

The runner independently reloads P6 and requires exact equality for source dialogue text/timing, OCR text/timing and Shot visual description. A mismatch exits with:

```text
FAILED_SOURCE_MUTATION_GUARD
```

## 7. Existing downstream placeholder tables

`engine/app/studio_v2.py` already contains historical/future-facing tables such as:

```text
Dialogue
Asset
Voice
Generation
```

and `Dialogue` has:

```text
original_text
translated_text
localized_text
final_text
```

These tables are **not** treated as current P7 source truth. They do not carry the full P6 BreakdownRun / ShotRevision / AssetRevision source anchors required by the current architecture, and current code does not provide an accepted localization workflow around them.

P7.1 does not delete or rewrite them.

## 8. Product-stage status

Stage 04 remains **规划中 / locked** after P7.1.

Why:

```text
P7.1 source package exists
but
no revisioned localization draft persistence yet
no editable localization UI yet
no translation/localization provider workflow yet
no review/finalize state yet
```

Therefore a source GET endpoint is not enough to claim “04 本土化剧本 implemented”.

Stage 05 and Stage 06 also remain locked.

## 9. User-local acceptance

```bash
python -m pytest \
  engine/tests/v2/test_localization_source_v1.py \
  engine/tests/v2/test_localization_source_routes_v1.py -q

python scripts/run_localization_source_acceptance_v1.py <EPISODE_ID>
```

Expected real runner safety signal:

```text
status = READY or READY_WITH_WARNINGS
schema_version = localization-source-v1
source_truth_preserved = true
source_breakdown_run_id = current P6 source run
source_shot_revision_id = current P6 source revision
```

Warnings are allowed for safe upstream partial states such as unresolved Final Character display. They must not cause source text mutation.

Do not mark P7.1 FINAL PASS until the user-local tests and real Episode runner are supplied.

## 10. Next safe frontier

After P7.1 acceptance, implement a separate **revisioned Localization Draft** layer:

```text
P7.1 immutable source package
→ create localization revision anchored to P7.1 source
→ translated_text / localized_text / final_text live only in that revision
→ edit/review/finalize
→ then unlock Stage 04
```

The source package itself must remain read-only throughout that work.
