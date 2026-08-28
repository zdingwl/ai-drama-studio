# P3 Shot Boundary Overflow Fix

## Status

IMPLEMENTED ON FIX BRANCH / BROWSER ACCEPTANCE PENDING

## Problem

After P3 added the `02 拉片工作区` switcher and the V5.1 shot cache controls above the legacy ShotWorkbench V4, the shot-boundary page still inherited the old near-full-viewport sizing assumptions. The global TaskProgressDock is also fixed to the bottom of the viewport. In the integrated P3 layout this could make lower ShotWorkbench content feel clipped or inaccessible.

## Fix

`frontend/src/studio-v3.css` now gives `studio-main.shot-stage-main` its own viewport-height vertical scroll container and reserves bottom scroll space for the fixed TaskProgressDock:

- `height: 100vh`
- `min-height: 0`
- `overflow-y: auto`
- `overflow-x: hidden`
- `padding-bottom: 108px`
- `scroll-padding-bottom: 108px`
- `overscroll-behavior: contain`
- `scrollbar-gutter: stable`

This keeps the left project navigation fixed while allowing the complete Stage 02 content, including the lower part of the Shot Boundary workbench, to remain reachable through the main-stage scrollbar.

## Scope

No changes were made to:

- Shot detection / boundary algorithms
- Shot Revision or Reference Clip semantics
- Shot Cache behavior
- Breakdown P2/P3 data contracts
- Structured Draft content
- Character V10.1

## Validation

- Fix branch is based directly on the current P3 merge commit `0a0f4fd267a8cb1649e44f810b42da960d0a39a3`.
- Diff is limited to the Stage 02 layout CSS plus this handoff note.
- Browser visual acceptance is still required on the user's local frontend.
- GitHub Actions were not triggered.
