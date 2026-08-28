# AI Drama Studio — P3 Structured Draft Workbench V2 polish

> Date: 2026-08-28  
> Branch: `feat/p3-structured-draft-workbench-v2-polish`  
> Base: `main@cdd440e0af29c4d8f61e1fd28f35d016e3aa9a51`  
> Status: **IMPLEMENTED / LOCAL BROWSER ACCEPTANCE REQUIRED**

## 1. Scope

This is a P3 frontend-only polish on top of the already implemented Structured Draft Workbench V2.

It does not change:

```text
breakdown-draft-v1 contract
P1/P2 storage, providers, Fusion or APIs
P4 Draft-guided Scene/Prop asset evidence
Character V10.1
Final Character / Scene / Prop bindings
historical ShotRevision / Reference Clip anchoring
```

P3 remains read-only Draft inspection.

## 2. Changes

### Run state panel

Added `BreakdownRunStatePanelV1.vue` and wired it into `BreakdownDraftV2.vue`.

When a selected Run has no `SceneSegmentDraft` rows, P3 no longer renders a misleading empty Scene/Shot/Inspector workbench. It instead shows a dedicated state panel for:

```text
FAILED
PROCESSING
STALE / history without displayable Scene content
READY/READY_WITH_WARNINGS with no displayable Scene content
```

The panel shows:

```text
Run lifecycle status
Episode-current vs historical Run relationship
current vs historical source ShotRevision
ASR / OCR / VLM / Fusion status
error_message when present
unassigned count
pipeline/schema metadata
```

FAILED Runs explicitly state that the historical failure is preserved and does not overwrite an existing usable Draft.

### Viewed Run semantics

`BreakdownTaskBarV1.vue` previously labelled the selected Run as `当前草稿` even after the user selected a historical Run.

The task bar now distinguishes:

```text
当前采用草稿 / 当前采用
查看中的草稿 / 历史查看
来源镜头版本
历史 Run · 只读
```

This matches the existing contract distinction between:

```text
BreakdownRun.is_current
ShotRevision.is_current
```

### V2 readability polish

Added `frontend/src/breakdown-p3-v2-polish.css`, loaded after the existing P3 acceptance/layout styles.

It raises the remaining V2 microcopy / status / timeline / inspector typography so ordinary information is generally 12px+ while preserving the existing three-column/layout behavior and status colors.

## 3. Preserved behavior

```text
one authoritative selectedEpisodeId remains in BreakdownStageV1
Scene -> Shot navigation remains single-context
Timeline event click still seeks exact historical Reference Clip
Evidence provenance remains unchanged
READY / WARN / FAILED / PROCESSING / STALE history remains selectable
no Final Asset edit/create/bind action is introduced
```

## 4. Acceptance checklist

Run on the normal Windows checkout:

```text
1. npm run build (frontend)
2. open 02 拉片 -> 结构化草稿
3. verify normal READY Draft Scene/Shot/Timeline behavior is unchanged
4. select a FAILED Run with zero Scene rows -> dedicated failure panel appears
5. select PROCESSING/empty Run -> no misleading “选择镜头” state
6. select a historical Run -> top bar says 历史查看, not 当前采用草稿
7. switch back to Episode Current Draft -> top bar says 当前采用
8. verify ASR/OCR/VLM/Fusion chips remain correct
9. verify Scene/Shot/Timeline/Inspector text is comfortably readable at desktop widths
10. verify no horizontal overflow around 1920 / 1600 / 1400 widths
```

P3 remains `UI ACCEPTANCE IN PROGRESS` until explicit user browser acceptance. P2.6 and P4 local/model acceptance remain separate gates.
