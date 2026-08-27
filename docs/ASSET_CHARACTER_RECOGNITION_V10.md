# Character V10 — SUPERSEDED BY V10.1

> **Status:** LEGACY IMPLEMENTATION HISTORY  
> **Current Character document:** `docs/ASSET_CHARACTER_RECOGNITION_V10_1.md`

Character V10 introduced the capture-first Person Evidence model-classification architecture:

```text
split detected people into isolated Person Instance crops
→ capture model-usable Person Evidence first
→ YoutuReID primary identity classification
→ clothing/body supporting channels
→ optional Face support/conflict
→ confirmed identity classes
→ RESOLVED-only Final Character
```

V10.1 keeps that foundation but supersedes V10 in two important ways:

1. strong `CONTAMINATED` / substantial `PARTIAL` Person crops may seed a new identity under stricter multi-Shot confirmation;
2. after global identity confirmation, an unresolved Track may recover to an already-confirmed identity when repeated observations produce one unique winner, fixing Shot-level Character binding gaps.

Current formal identifiers are:

```text
runtime:  character-v10.1-capture-first-model-classification
asset:    f05-assets-v10.1-person-evidence-model-classification
resolver: person-evidence-model-classifier-v10.1
```

Do not implement new changes from the old V10 document. The full prior V10 document remains available in Git history for archaeology.

Current authority:

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/ASSET_CHARACTER_RECOGNITION_V10_1.md
current code
```
