# F06 — P0 Checklist（LEGACY / SUPERSEDED）

> **Status:** LEGACY HISTORY — NOT THE CURRENT ACCEPTANCE GATE

The old F06 YuNet/SFace-only P0 checklist belongs to the superseded 35-Feature architecture.

Current Character acceptance is Character V10.1 and is defined by:

```text
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/ASSET_CHARACTER_RECOGNITION_V10_1.md
```

Current high-priority acceptance includes:

```text
1. every model-usable real person is captured as isolated Person Evidence
2. same-sample different people remain cannot-link
3. Final Character count is identity count, not Track/crop count
4. new identity requires >=3 independent Shots and >=3 model-usable Person Images
5. Face is optional; high-quality Face conflict is a hard negative
6. strong risky views require stricter cross-Shot confirmation
7. weak partial fragments never create a Character
8. unresolved Track may recover only to an already-confirmed identity
9. Track recovery requires repeated support and a unique winner
10. cannot-link / Face conflict blocks Track recovery
11. recovered Track is persisted before Final materialization so ShotCharacterBinding is correct
12. UNRESOLVED / unknown resolver / insufficient evidence fails closed at Final Gate
13. old analysis Run does not auto-change after code updates; explicit rerun is required
14. real Windows short-drama material validates both Character count and Shot bindings
```

The former checklist remains in Git history for archaeology only.
