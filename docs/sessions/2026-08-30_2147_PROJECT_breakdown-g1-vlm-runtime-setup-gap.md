# 2026-08-30 21:47 +08:00 — Breakdown G1 VLM runtime setup gap

Current main before this fix:

```text
33b24545d799f125cbbdfe38af7d56860e035bef
feat(breakdown): expose read-only G1 diagnostics API [skip ci]
```

Observed local failure:

```text
VLM Provider status=NOT_AVAILABLE
完整匿名 Draft 要求 READY VLM semantics
fast-grounded VLM runtime is not available: Qwen3-VL-4B-Instruct checkpoint
```

Root cause: the current Fast Grounded provider defaults to
`.runtime/TransVLM/inference/pretrained/Qwen3-VL-4B-Instruct`, while the existing TransVLM setup
script only provisions the TransVLM fine-tuned checkpoint and NeuFlow. The original production
`Qwen/Qwen3-VL-4B-Instruct` checkpoint was never provisioned by repository setup.

Added a dedicated non-destructive provisioning helper:

```text
scripts/setup_breakdown_vlm_runtime.ps1
```

It reuses the isolated TransVLM Python runtime, downloads/resumes the original Qwen3-VL model into
the exact default production path (or `AI_DRAMA_P2_VLM_MODEL_PATH`), and performs local-only
AutoConfig/AutoProcessor + qwen_vl_utils verification. It does not load the full model for inference.

Added path/setup contract coverage:

```text
engine/tests/v2/test_breakdown_p2_vlm_setup_contract.py
```

Local recovery:

```powershell
git pull
.\scripts\setup_breakdown_vlm_runtime.ps1
python scripts\run_breakdown_p2.py preflight --strict
```

If the isolated runtime itself is missing, first run `.\scripts\setup_transvlm_runtime.ps1`.

Once preflight is READY, rerun the affected Episode Breakdown. A Run that stopped with
`VLM=NOT_AVAILABLE` has no complete VLM semantics and cannot be made complete by diagnostics alone.

No G1 algorithm, E4 Fusion, Character V10.1, Draft schema or Final Asset behavior changed.
G1/P2-E4/P2.6 acceptance remains pending/not passed until the successful real rerun is reviewed.
Tests were added but not executed here. Hosted GitHub Actions remain unused.
