# 2026-08-30 13:20 +08:00 — G1 compact acceptance summary handoff

## Base

```text
7025bc783f0c09845bdbc9e9521300197fe84d11
feat(breakdown): auto-select Fast Grounded G1 acceptance run [skip ci]
```

G1/P2.6 status remains pending/not passed. No inference, Fusion, Character or UI behavior is changed.

## Goal

The full diagnostic JSON is intentionally detailed but awkward to paste/read during acceptance.
A compact terminal formatter is added so the real Run can be reviewed in one screen while preserving
the JSON artifact for deeper investigation.

Added:

```text
engine/app/breakdown_g1_acceptance_summary_v1.py
engine/tests/v2/test_breakdown_g1_acceptance_summary_v1.py
```

Updated:

```text
scripts/inspect_breakdown_g1_run.py
```

Recommended local command:

```powershell
git pull
python scripts/inspect_breakdown_g1_run.py --latest --summary
```

By default the complete JSON artifact is still written under the selected Run acceptance directory.
`--summary` changes terminal output only. `--stdout-only` can still suppress artifact writing.

The compact output exposes:

```text
selected Run / Episode / Fast Grounded VLM profile
whole-run elapsed + <30m / <=20m target flags
ASR/OCR/VLM provider timings
Shot 0001 subjects/props/summary/visual description
all Scene boundaries and LocalSubject counts
Scene 04 focused LocalSubject count
Scene 04 per-LocalSubject shot ordinals + source subject_A/B labels
same-Shot hard-conflict count/details
short OCR noise samples
```

The formatter explicitly says machine diagnostics do not auto-PASS G1/P2.6. Human review remains
required for Scene04 cluster meaning and Scene boundary correctness.

Targeted test coverage is present in the repository but was not executed in this environment.
Hosted GitHub Actions remain unused.
