# 2026-08-30 21:55 +08:00 — G1 VLM setup correction

## Correction

The local error is:

```text
VLM Provider status=NOT_AVAILABLE
完整匿名 Draft 要求 READY VLM semantics
fast-grounded VLM runtime is not available: Qwen3-VL-4B-Instruct checkpoint
```

The repository already had `scripts/setup_breakdown_vlm_runtime.ps1` before this incident. That script
already provisions `Qwen/Qwen3-VL-4B-Instruct` into the exact production default path and performs
strict Qwen3-VL/decord/reader checks.

An earlier follow-up commit mistakenly treated that script as newly absent and replaced it with a
weaker version during diagnosis. This handoff corrects that immediately: the original strict setup
script is restored unchanged.

## Actual user recovery

```powershell
git pull
.\scripts\setup_breakdown_vlm_runtime.ps1
python scripts\run_breakdown_p2.py preflight --strict
```

If the script reports that the isolated runtime is missing, first run:

```powershell
.\scripts\setup_transvlm_runtime.ps1
```

then rerun the Breakdown VLM setup command.

## What the error means

Fast Grounded production expects:

```text
.runtime/TransVLM/inference/pretrained/Qwen3-VL-4B-Instruct
```

with model identity:

```text
Qwen/Qwen3-VL-4B-Instruct
```

A TransVLM fine-tuned checkpoint is not a substitute for this path.

Once preflight is READY, the Episode run that failed with `VLM=NOT_AVAILABLE` must be rerun because
that failed Run has no complete VLM semantics / anonymous Draft.

No G1 algorithm, E4 Fusion, Character V10.1, database schema or Final Asset behavior changed.
G1/P2-E4/P2.6 remains pending/not passed until the successful real rerun is reviewed.

Targeted path/setup contract tests remain repository-only and were not executed here. Hosted GitHub
Actions remain unused.
