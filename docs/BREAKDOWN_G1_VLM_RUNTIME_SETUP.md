# Breakdown G1 VLM runtime setup

Production Fast Grounded uses the original model checkpoint:

```text
Qwen/Qwen3-VL-4B-Instruct
```

Default local path:

```text
.runtime/TransVLM/inference/pretrained/Qwen3-VL-4B-Instruct
```

Prepare it with:

```powershell
git pull
.\scripts\setup_breakdown_vlm_runtime.ps1
python scripts\run_breakdown_p2.py preflight --strict
```

If `.runtime\TransVLM\inference\.venv\Scripts\python.exe` is missing, run
`.\scripts\setup_transvlm_runtime.ps1` first.

`-CheckOnly` verifies an existing checkpoint without downloading:

```powershell
.\scripts\setup_breakdown_vlm_runtime.ps1 -CheckOnly
```

`AI_DRAMA_P2_VLM_MODEL_PATH` may override the default local path. The production provider and setup
helper use the same path contract.

A preflight READY result means the local runtime exists; it does not by itself make G1/P2.6 a quality PASS.
