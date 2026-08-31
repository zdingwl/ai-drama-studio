# G1 Fusion read-only replay

Purpose: validate candidate Scene continuity and anonymous LocalSubject continuity against an
already-completed Fast Grounded Run **without running ASR/OCR/VLM again and without mutating the
formal BreakdownRun**.

Current candidate policies:

```text
Scene:
- UNKNOWN/generic/background-poor still inherits continuity.
- corridor family aliases are compatible:
  走廊 / 楼道 / 过道 / hallway / corridor
- qualifier-only drift such as 公寓走廊 -> 酒店走廊 does not cut by itself.
- Window shot_scene_hint NEW_SCENE + DIRECT still forces a cut.
- clear INT <-> EXT or incompatible spatial type still cuts.

Anonymous subject:
- Window subject_continuity_hints remain primary.
- fallback may reconnect a strongly matching person after a 3..6 Shot absence.
- longer gaps require more stable appearance features and a larger best-vs-second-best margin.
- same-Shot hard cannot-link is unchanged and remains transitive.
```

Run:

```powershell
python scripts/replay_breakdown_g1_fusion.py --run-id <BREAKDOWN_RUN_ID>
```

Full machine-readable output:

```powershell
python scripts/replay_breakdown_g1_fusion.py --run-id <BREAKDOWN_RUN_ID> --json
```

The replay only reads and verifies the immutable ASR/OCR/VLM sidecars registered on the source Run.
It reports:

```text
providers_executed=[]
mutates_breakdown_run=false
mutates_final_assets=false
```

Do not use this replay result as an automatic G1/P2.6 PASS. Human review is still required. The
candidate policy must be validated on the real Run before it is promoted into production Fusion.
