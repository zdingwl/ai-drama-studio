# 2026-08-30 22:05 +08:00 — Breakdown VLM setup PowerShell 5.1 parser fix

## Observed local error

Windows PowerShell failed before executing the setup script:

```text
scripts/setup_breakdown_vlm_runtime.ps1:69
MissingEndParenthesisInExpression
unexpected token ')'
string is missing the terminator: '
```

The failing area was after non-ASCII Chinese `Write-Host` strings near the end of the `.ps1` file.

## Root cause / compatibility decision

The script is valid UTF-8 source, but Windows PowerShell 5.1 may decode UTF-8-without-BOM scripts using the active ANSI code page. That can produce locale-dependent parser failures before any model/setup logic runs.

For this Windows-first setup entrypoint, the robust rule is now:

```text
scripts/setup_breakdown_vlm_runtime.ps1 = ASCII-only source
```

No production behavior was changed. The script still:

```text
- requires the isolated TransVLM/Qwen Python runtime
- verifies torch / transformers / qwen-vl-utils >= 0.0.14 / huggingface_hub / decord
- downloads Qwen/Qwen3-VL-4B-Instruct when missing
- writes it to .runtime/TransVLM/inference/pretrained/Qwen3-VL-4B-Instruct
- runs the strict-reader CLI self-check
```

Only human-readable Chinese terminal output was replaced with ASCII English text.

## Regression coverage

`engine/tests/v2/test_breakdown_p2_vlm_setup_contract.py` now also requires the setup script to encode as ASCII. This prevents non-ASCII text from being reintroduced into the Windows PowerShell 5.1 entrypoint.

Tests were added/updated but not executed in this environment. Hosted GitHub Actions remain unused.

## User recovery

```powershell
git pull
.\scripts\setup_breakdown_vlm_runtime.ps1
python scripts\run_breakdown_p2.py preflight --strict
```

Expected preflight after the model finishes downloading:

```text
vlm_model_path = true
vlm_runtime_probe = true
vlm_device = true
ready = true
```

If preflight becomes READY, rerun the Episode whose previous Breakdown Run had `VLM=NOT_AVAILABLE`, then inspect the new completed Fast Grounded Run.

G1 / P2-E4 / P2.6 acceptance remains pending until that successful real rerun is reviewed.
