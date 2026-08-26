# Stage 02 / Shot V5.1 Cache

V5.1 adds a dependency-aware Episode cache without changing the V5 Shot boundary algorithm.

## Directory

```text
data_v2/workspace/<project>/episodes/<episode>/
├─ source/
├─ shots/
└─ cache/
   └─ shot_v51/
      ├─ manifest.json
      ├─ preprocess/
      │  └─ model_rgb.mp4
      ├─ flow/
      │  └─ model_flow.mp4
      ├─ transvlm/
      │  └─ transvlm.jsonl
      └─ transitions/
         └─ segments.json
```

`cache/shot_v51` is the only directory cache-management code may delete.  Source videos, Shot Runs,
Current Revision, Reference Clips and manual revisions are not cache artifacts.

## Dependency graph

```text
Source + runtime/profile manifest
        ↓
model_rgb.mp4
        ↓
model_flow.mp4
        ↓
raw TransVLM window output
        ↓
transition segments
        ↓
Source PTS boundary resolution
        ↓
frame-exact Reference Clips
```

Only the first four model-side layers are cached.  Source PTS boundary resolution and Reference Clip
production continue to run for each new automatic Shot Revision.

## First-run parity rule

The first run does **not** move NeuFlow into a separate helper process.  The app invokes the official
TransVLM pipeline in its original order (Qwen engine load -> preprocessing -> NeuFlow -> windows) and
only captures the exact `model_rgb` and computed flow after the official per-video operation succeeds.

This matters because the official flow visualisation may choose GPU or CPU based on free VRAM.  A
separate flow-only process would have a different VRAM state and could therefore produce a slightly
different visualisation signal.

## Recompute scopes

| Scope | Keeps | Recomputes |
| --- | --- | --- |
| `auto` | deepest valid cache | only missing/invalid downstream work |
| `transitions` | RGB, Flow, raw Qwen output | transition parse/merge |
| `transvlm` | RGB, Flow | Qwen windows + transitions |
| `flow` | RGB | NeuFlow + Qwen + transitions |
| `preprocess` | Source only | model RGB + Flow + Qwen + transitions |
| `all` | Source / Shots / Revisions | same model work as full rebuild; also removes cache manifest/root |

Clearing an upstream layer always clears all downstream layers.

## Automatic invalidation

The manifest is an exact contract.  It includes:

- source SHA-256 recorded at import;
- current source file size and mtime;
- official TransVLM inference / flow / resize / prompt / checkpoint config signatures;
- app-side V5.1 cache driver signature;
- FPS, smart-resize pixel budget, image patch size and resize frame budget;
- Flow codec, visualisation device and mini-batch size;
- model/backend, window size, stride, merge epsilon, timestamp format, max output tokens and prefix-caching policy.

Any change invalidates old cache before reuse.

## API

```text
GET    /api/episodes/{episode_id}/shot-cache
DELETE /api/episodes/{episode_id}/shot-cache?scope=transitions
DELETE /api/episodes/{episode_id}/shot-cache?scope=transvlm
DELETE /api/episodes/{episode_id}/shot-cache?scope=flow
DELETE /api/episodes/{episode_id}/shot-cache?scope=preprocess
DELETE /api/episodes/{episode_id}/shot-cache?scope=all
DELETE /api/projects/{project_id}/shot-cache?scope=all
```

Cache deletion returns HTTP 409 while an Episode or Project Shot task is active.

## Troubleshooting rule

Use the narrowest recompute scope that owns the suspected fault:

```text
Transition merge/parser changed     -> transitions
Prompt/model/window inference changed -> transvlm
NeuFlow/flow visualisation changed  -> flow
FPS/resize/model RGB changed        -> preprocess
Unknown cache corruption            -> all
Source PTS / Reference renderer only -> keep cache; normal rerun is enough
```

Do not manually delete `source/` or `shots/` to fix a cache problem.
