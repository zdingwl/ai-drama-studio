# F06 — 自动人物识别（LEGACY / SUPERSEDED）

> **Status:** LEGACY HISTORY — DO NOT IMPLEMENT FROM THIS FILE  
> **Superseded by:** Reference Video V2 `03 资产` + Character V10.1  
> **Current docs:**
> - `docs/PROJECT_STATE.md`
> - `docs/CURRENT_IMPLEMENTATION_MANIFEST.md`
> - `docs/F05_CONTENT_ANALYSIS_V2.md`
> - `docs/ASSET_CHARACTER_RECOGNITION_V10_1.md`

## Why this file is retired

This file originally described an older 35-Feature architecture in which F06 was a planned YuNet/SFace-first, mostly face-based automatic character detection stage after a separate F05 Final Shot workbench.

That architecture is no longer the current executable product contract.

The repository now uses the Reference Video V2 workspace model:

```text
01 剧集管理
02 拉片
03 资产
04 内容剧本
05 重制设计
06 生成 / 导出
```

Character analysis currently runs inside the asset workflow with Character V10.1.

## Current formal Character facts

```text
runtime profile:
character-v10.1-capture-first-model-classification

asset profile:
f05-assets-v10.1-person-evidence-model-classification

resolver:
person-evidence-model-classifier-v10.1
```

Current pipeline:

```text
YOLOX Person Detection
→ isolated Person Instance crops
→ capture-first Person Evidence
→ YoutuReID primary identity classification
   + clothing/body support
   + optional Face support
→ temporal Track organization
→ project-level identity resolution
→ V10.1 known-identity Track recovery
→ fail-closed Final Gate
→ Character + ShotCharacterBinding
```

New identity creation requires at least 3 independent Shots and 3 model-usable Person Images. Face is optional.

The latest V10.1 recovery pass solves the case where a Character is already known globally but a particular Shot remains unresolved: a repeated Track may attach to an already-confirmed identity only when it has enough observations, a unique winner, and no cannot-link/Face conflict.

## Historical content

The previous full F06 plan remains available in Git history. Do not copy its old API, database, 4fps face-only sampling, YuNet/SFace-only identity semantics, or “F06 creates Character Candidates then F07 creates Final Character” architecture back into current code without a new explicit user decision.
