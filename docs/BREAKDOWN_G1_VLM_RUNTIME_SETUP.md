# Breakdown G1 VLM runtime setup

Fast Grounded production requires the original checkpoint:

```text
Qwen/Qwen3-VL-4B-Instruct
```

Default local path:

```text
.runtime/TransVLM/inference/pretrained/Qwen3-VL-4B-Instruct
```

The repository already provides the dedicated setup script:

```powershell
.\scripts\setup_breakdown_vlm_runtime.ps1
```

It reuses the isolated TransVLM/Qwen Python runtime, verifies the required Qwen3-VL/decord dependencies,
downloads the original Qwen3-VL checkpoint when it is missing, and runs the strict-reader CLI self-check.

If the isolated runtime itself is missing, first run:

```powershell
.\scripts\setup_transvlm_runtime.ps1
```

Then run:

```powershell
.\scripts\setup_breakdown_vlm_runtime.ps1
python scripts\run_breakdown_p2.py preflight --strict
```

The error:

```text
fast-grounded VLM runtime is not available: Qwen3-VL-4B-Instruct checkpoint
```

means the production checkpoint directory is not ready. Do not manually copy a TransVLM fine-tuned
checkpoint into this directory: Breakdown intentionally uses the original `Qwen/Qwen3-VL-4B-Instruct`.

After preflight becomes READY, rerun the affected Episode Breakdown. A Run that already stopped with
`VLM=NOT_AVAILABLE` cannot contain a complete anonymous Draft.

Preflight/runtime readiness is not G1/P2.6 quality acceptance.
