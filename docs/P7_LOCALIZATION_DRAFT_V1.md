# P7.2 Localization Draft V1

> Status: **IMPLEMENTED ON MAIN / USER-LOCAL ACCEPTANCE PENDING**  
> Date: 2026-09-01 +08:00  
> Product stage: **04 本土化剧本 is now executable; 05/06 remain locked.**

## 1. Purpose

P7.1 created a read-only, version-anchored source package. P7.2 adds the first real editable localization workflow without ever turning target-language copy into source truth.

```text
P6 Final Breakdown read model
→ P7.1 immutable localization-source-v1
→ P7.2 append-only Localization Revision
→ DRAFT
→ IN_REVIEW
→ FINAL
→ future Stage 05 remake plan
```

P7.2 does not call a translation model by itself. Automatic translation/localization providers can be added later, but they must write through the same target-side revision contract.

## 2. Source truth is not editable

HTTP edit requests accept:

```text
source_key
decision
translated_text
localized_text
final_text
note
```

They do **not** accept `source_text`.

`LocalizationDraftEditV1` uses `extra="forbid"`, so a request attempting to send source text is rejected before it can become a business write.

Read views still show the immutable source text from the P7.1 snapshot next to editable target-side fields.

## 3. Persistence model

Table:

```text
v2_localization_revisions
```

One row is one immutable Episode-level revision. Important columns:

```text
id
project_id
episode_id
revision
kind
status
is_current
source_schema_version
source_breakdown_run_id
source_shot_revision_id
source_asset_revision_id
source_fingerprint
source_snapshot_json
edits_json
note
created_at
```

`source_snapshot_json` and `edits_json` are deliberately separate.

Every successful write creates a new revision. Previous revisions remain read-only history and lose only `is_current`.

## 4. Target-side editing model

Each P7.1 `source_key` has one decision:

```text
PENDING      = not decided yet
LOCALIZE     = create target-language/localized copy
KEEP_SOURCE  = final output intentionally keeps source text
OMIT         = source item intentionally omitted from remake script
```

For `LOCALIZE`, P7.2 stores three target-side layers:

```text
translated_text = semantic/direct translation reference
localized_text  = target-region rewrite
final_text      = approved text that downstream remake may consume
```

DRAFT may save a partial LOCALIZE row before `final_text` exists. This is required for real editing work.

However, `IN_REVIEW` / `FINAL` are blocked until:

```text
no PENDING rows remain
AND every LOCALIZE row has non-empty final_text
```

This rule is enforced at the supported backend workflow boundary, not only by UI buttons.

## 5. Review state machine

Allowed product transitions:

```text
DRAFT -> IN_REVIEW
IN_REVIEW -> DRAFT
IN_REVIEW -> FINAL
FINAL -> no direct edit/status transition
```

A review draft cannot be PATCH-ed directly. It must explicitly return to DRAFT first.

This keeps review state meaningful and prevents a hidden edit from silently invalidating a review decision.

## 6. Optimistic concurrency

Every edit/status request carries:

```text
base_revision_id
```

The backend compares it with the current revision. If another write already created a newer revision, the stale client receives HTTP 409 and must refresh instead of overwriting newer work.

## 7. Source staleness and rebase

A Localization Revision carries P7.1 source anchors plus a deterministic SHA-256 source fingerprint.

If current P7.1 changes because Breakdown / ShotRevision / Final Asset source changes:

```text
current draft -> stale=true
editing -> blocked
review/finalize -> blocked
```

The user must explicitly run rebase.

Rebase creates a new DRAFT revision. An old target edit is carried forward only when all of the following still match exactly:

```text
source_key
entry kind
Scene ordinal
Shot ordinal
start_us
end_us
source_text
```

Anything else resets to `PENDING` rather than guessing that old copy still belongs to the new source.

## 8. API

Read:

```http
GET /api/episodes/{episode_id}/localization-draft
GET /api/episodes/{episode_id}/localization-revisions
GET /api/localization-revisions/{revision_id}
```

Write:

```http
POST  /api/episodes/{episode_id}/localization-draft
PATCH /api/episodes/{episode_id}/localization-draft
POST  /api/episodes/{episode_id}/localization-draft/status
POST  /api/episodes/{episode_id}/localization-draft/rebase
```

The existing P7.1 source endpoint remains read-only:

```http
GET /api/episodes/{episode_id}/localization-source
```

## 9. Stage 04 UI

Implemented:

```text
frontend/src/components/LocalizationStageV1.vue
frontend/src/api/localization.ts
frontend/src/types/localization.ts
```

Ordinary-user workflow:

```text
select Episode
→ create draft from current source
→ read source dialogue/OCR beside reference Shot
→ choose PENDING / LOCALIZE / KEEP_SOURCE / OMIT
→ optionally fill translation reference
→ fill localized rewrite
→ fill final text
→ save (new Revision)
→ send to review
→ return to edit OR finalize
```

The page also shows:

```text
Shot thumbnail/reference clip
Shot visual description
safe people display
processed / remaining counts
stale-source warning + explicit rebase
revision history
```

Stage 04 status is now truthful:

```text
no draft            -> 未开始
DRAFT/partial FINAL -> 编辑中
IN_REVIEW            -> 待复核
stale source         -> 阻塞
all Episodes FINAL   -> 已完成
```

## 10. Stage boundary

Stage 04 is now executable because it has:

```text
persistent versioned draft
editable target copy
source immutability guard
optimistic concurrency
review/finalize state
stale-source rebase
ordinary-user UI
revision history
```

This does **not** mean automatic translation is complete.

Stage 05 and 06 remain locked:

```text
05 no versioned remake-plan contract/workspace yet
06 no generation/QC/delivery executable workflow yet
```

## 11. Tests

Backend deterministic tests:

```text
engine/tests/v2/test_localization_draft_v1.py
engine/tests/v2/test_localization_draft_workflow_v1.py
engine/tests/v2/test_localization_draft_routes_v1.py
```

Frontend stage-state tests:

```text
frontend/src/utils/stageStatus.test.ts
```

P7.2 real Episode audit runner:

```text
scripts/run_localization_draft_acceptance_v1.py
```

The runner is read-only. It never creates or modifies a production draft. It checks:

```text
one current revision
revision history ordering
current source fingerprint
source dialogue/OCR text+timing against independently loaded P7.1
review/final readiness invariants
```

If no draft exists, it reports `NOT_STARTED` rather than silently creating one.

## 12. User-local acceptance

Backend:

```bash
python -m pytest \
  engine/tests/v2/test_localization_source_v1.py \
  engine/tests/v2/test_localization_source_routes_v1.py \
  engine/tests/v2/test_localization_draft_v1.py \
  engine/tests/v2/test_localization_draft_workflow_v1.py \
  engine/tests/v2/test_localization_draft_routes_v1.py -q
```

Real Episode, read-only:

```bash
python scripts/run_localization_source_acceptance_v1.py <EPISODE_ID>
python scripts/run_localization_draft_acceptance_v1.py <EPISODE_ID>
```

Frontend:

```bash
cd frontend
npm test -- src/utils/stageStatus.test.ts
npm run typecheck
npm run build
```

Visual acceptance should verify:

```text
04 is clickable
05/06 remain disabled
source text cannot be edited
partial LOCALIZE can be saved
unsaved/unfinished copy cannot be sent to review
IN_REVIEW cannot be edited until returned
FINAL is read-only
stale source forces rebase
homepage/project header show truthful Stage 04 state
```

Do not mark P7.2 FINAL PASS until user-local backend tests, real audit, frontend tests/typecheck/build and visual review are supplied.
