# AI Drama Studio — P3 Structured Draft UI handoff

> Date: 2026-08-28  
> Branch: `feat/p3-breakdown-draft-ui`  
> Base: latest `main` at `acf4958e85380e1405101750b37d75b82811e60d`  
> Phase: **P3 IMPLEMENTATION IN PROGRESS — first frontend slice implemented / local UI acceptance pending**

## 1. What this slice implements

`02 拉片` now has two explicit sub-workspaces:

```text
镜头边界
→ existing ShotCacheManagerV51 + ShotWorkbenchV4

Structured Draft
→ P2 production task controls
→ Episode / Breakdown Run history
→ SceneSegmentDraft
→ ShotSemanticDraft + exact historical Reference Clip
→ anonymous LocalSubject / ShotLocalSubject
→ Timeline dialogue / action / OCR / visual / audio events
→ DraftPropHint / occurrences
→ BreakdownEvidenceLink provenance
```

This keeps the existing Shot boundary editor intact. P3 only consumes the frozen P1/P2 contract; it does not introduce another Breakdown schema.

## 2. Files added / changed

```text
frontend/src/types/breakdown.ts
frontend/src/api/breakdown.ts
frontend/src/components/BreakdownDraftV1.vue
frontend/src/components/BreakdownTaskBarV1.vue
frontend/src/components/BreakdownStageV1.vue
frontend/src/views/ProjectStudioV3.vue
```

## 3. Important UI behavior

### Draft history

The workbench lists all Breakdown Runs, including `READY`, `READY_WITH_WARNINGS`, `STALE`, `PROCESSING`, and `FAILED` history. Historical runs remain readable and are never silently replaced by Current.

### Historical media anchoring

Shot preview/player uses:

```text
ShotSemanticDraft.source_shot_revision_item.reference_url
```

Timeline clicks seek inside that exact historical Reference Clip using `shot_relative_start_us`. The UI does not guess timing from the current mutable Shot list.

### Draft != Final Asset

The UI explicitly labels the semantic layer as Draft:

```text
LocalSubject / 人物A-B != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
```

P3 does not write `Character`, `Scene`, `Prop`, `AssetRevision`, or Final Shot bindings.

### P2 production task entry

Structured Draft mode calls only the formal backend task endpoints:

```text
POST /api/episodes/{episode_id}/tasks/breakdown
POST /api/projects/{project_id}/tasks/breakdown-batch
```

No ASR/OCR/VLM/Fusion logic is duplicated in Vue. Task creation emits the existing `studio-task-created` browser event so the global `TaskProgressDock` owns progress polling and error display. On completed P2 tasks, `BreakdownStageV1` remounts the Draft view so the new Current/Run history is reloaded.

Backend concurrency and idempotency remain authoritative. The UI does not attempt its own scheduler.

## 4. Validation performed in this development session

- Branch was rebased logically onto the latest P2 production `main` using a merge commit; compare result became `ahead`, `behind_by = 0`.
- Diff was checked and is limited to the P3 frontend files plus this handoff.
- Breakdown TypeScript contracts and API module were checked with strict local TypeScript stubs.
- Component script blocks for the task controls/wrapper were also checked with strict local TypeScript stubs.
- Hosted GitHub Actions were intentionally not triggered.

Full `vue-tsc` / Vite build and browser visual acceptance were not executed in this tool environment because the repository frontend dependencies are not installed locally here. They remain required on the normal project checkout before P3 is marked complete.

## 5. Acceptance checklist for the local project checkout

```text
1. npm run build (frontend)
2. open an existing Project → 02 拉片
3. verify 镜头边界 still behaves exactly as before
4. switch to Structured Draft
5. run one Episode P2 task and confirm TaskProgressDock progress
6. confirm task completion refreshes Run history/current Draft
7. inspect READY_WITH_WARNINGS / STALE / FAILED history states
8. click dialogue/action/OCR events and verify the historical Reference Clip seeks correctly
9. verify anonymous 人物A/B are never shown as Final Character
10. run batch Breakdown and confirm Episode.sort_order sequential behavior through the existing task progress
```

## 6. Phase truth after this branch

```text
P2 implementation                         = COMPLETE
P2 real-video acceptance                  = PENDING
P3 first Structured Draft frontend slice  = IMPLEMENTED ON FEATURE BRANCH
P3 local build / browser acceptance        = PENDING
P4 Draft-guided Scene / Prop evidence      = NOT STARTED
P5 Draft ↔ Character safe integration      = NOT STARTED
```

Do not mark P2 quality accepted until a real short-drama run receives the required human-reviewed acceptance PASS. Do not start P4/P5 identity or asset fill-back work inside this P3 branch.
