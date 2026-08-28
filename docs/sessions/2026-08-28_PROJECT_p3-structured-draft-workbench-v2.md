# AI Drama Studio — P3 Structured Draft Workbench V2 handoff

> Date: 2026-08-28  
> Branch: `feat/p3-structured-draft-workbench-v2`  
> Base: `main@ea1ff161a280bfb3238dc1d1a93f41de6686aaaa`  
> Status: **UI V2 IMPLEMENTED / LOCAL BUILD + BROWSER ACCEPTANCE REQUIRED**

## 1. Scope

This change implements the approved P3 Structured Draft Workbench V2 UI only.

It does **not** change:

```text
breakdown-draft-v1 contract
P1/P2 database or Fusion
ASR / OCR / VLM providers
Character V10.1
Final Character / Scene / Prop bindings
P4 / P5 / P6 behavior
```

P3 remains a read-only Draft inspection surface.

## 2. New UI structure

```text
BreakdownStageV1
├─ BreakdownTaskBarV1
│  ├─ one authoritative Episode selection
│  ├─ selected Run / ShotRevision context
│  ├─ ASR / OCR / VLM / Fusion status
│  └─ single / batch P2 controls
│
└─ BreakdownDraftV2
   ├─ BreakdownNavigatorV1
   │  ├─ Scene → Shot tree
   │  ├─ Scene / Shot search
   │  └─ full Run history including FAILED / STALE
   ├─ BreakdownShotWorkspaceV1
   │  ├─ single Scene context
   │  ├─ single Shot detail
   │  ├─ anonymous subjects / Draft prop hints
   │  └─ filterable Evidence Timeline
   └─ BreakdownInspectorV1
      ├─ exact historical Reference Clip
      ├─ selected Event detail
      ├─ Evidence provenance
      └─ Unassigned summary
```

`BreakdownDraftV1.vue` is intentionally retained for comparison/rollback, but Stage 02 now mounts `BreakdownDraftV2.vue`.

## 3. Important behavior preserved

### Exact historical media anchoring

The inspector still plays:

```text
ShotSemanticDraft.source_shot_revision_item.reference_url
```

Event click uses `shot_relative_start_us` and seeks within that historical Reference Clip. It does not infer time from current mutable Shot rows.

### Draft != Final

The new workbench continues to expose:

```text
LocalSubject / 人物A-B != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
```

No edit/create/bind action for Final Asset is introduced.

### Run history

`READY`, `READY_WITH_WARNINGS`, `PROCESSING`, `FAILED`, and `STALE` Runs remain selectable. Historical Run selection updates the workbench and does not silently substitute Current.

### Task refresh

Existing `studio-task-finished` handling remains authoritative. Completed P2 single/batch tasks remount the Draft V2 container and reload Current + history.

## 4. Structural bug fixed

Previously both `BreakdownTaskBarV1` and `BreakdownDraftV1` owned independent `selectedEpisodeId` refs. This could allow the task selector to target one Episode while the viewer displayed another.

V2 moves the authoritative Episode selection to `BreakdownStageV1` and passes the same value to TaskBar and DraftV2.

## 5. UI acceptance targets

Local checkout should verify:

```text
1. frontend build passes
2. 02 拉片 → 镜头边界 remains unchanged
3. 02 拉片 → Structured Draft mounts Workbench V2
4. Episode select changes both task context and Draft context together
5. Scene → Shot navigation selects exactly one Scene / Shot workspace
6. search locates Scene / Shot by label / ordinal / summary
7. Timeline filter ALL / VLM / 对白 / OCR / 动作 / 声音 works
8. Event click highlights Event and seeks exact historical Reference Clip
9. right inspector switches between Shot Quick Stats and selected Evidence detail
10. Evidence provenance remains readable
11. READY / WARN / FAILED / STALE history remains selectable
12. desktop three-column layout has no horizontal overflow
13. browser widths around 1400 / 1180 / 860 follow the planned responsive collapse
14. all primary copy remains readable (no 8px/9px text regression)
```

## 6. Validation truth

Hosted GitHub Actions were not queried or run.

The tool environment cannot resolve public GitHub from the container, so a local `npm build` / browser run could not be executed here. Do not mark P3 UI V2 accepted until the normal Windows checkout passes build and visual/interaction acceptance.

P2.6 real-model acceptance remains a separate gate and is **NOT PASSED** until the real short-drama chain plus human acceptance report passes.
