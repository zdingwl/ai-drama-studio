param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$InferenceRoot = Join-Path $RepoRoot '.runtime\TransVLM\inference'
$PythonExe = Join-Path $InferenceRoot '.venv\Scripts\python.exe'
$ModelDir = Join-Path $InferenceRoot 'pretrained\Qwen3-VL-4B-Instruct'
$Runner = Join-Path $RepoRoot 'scripts\run_breakdown_vlm_qwen3.py'

if (-not (Test-Path $PythonExe)) {
    throw 'Isolated TransVLM/Qwen runtime is missing. Run scripts/setup_transvlm_runtime.ps1 first.'
}
if (-not (Test-Path $Runner)) {
    throw "Missing P2.4 runner: $Runner"
}

Write-Host '[Breakdown VLM] Verifying isolated Qwen3-VL runtime.'
& $PythonExe -c "import torch, transformers, qwen_vl_utils, huggingface_hub; from transformers import Qwen3VLForConditionalGeneration, AutoProcessor; print('runtime=OK'); print('torch=' + torch.__version__); print('transformers=' + transformers.__version__)"
if ($LASTEXITCODE -ne 0) {
    throw 'The isolated runtime does not contain the Qwen3-VL dependencies required by P2.4.'
}

if (-not (Test-Path (Join-Path $ModelDir 'config.json'))) {
    New-Item -ItemType Directory -Force -Path $ModelDir | Out-Null
    $env:AI_DRAMA_P2_VLM_SETUP_MODEL = $ModelDir
    try {
        Write-Host '[Breakdown VLM] Downloading official Qwen/Qwen3-VL-4B-Instruct checkpoint.'
        & $PythonExe -c "import os; from huggingface_hub import snapshot_download; snapshot_download('Qwen/Qwen3-VL-4B-Instruct', local_dir=os.environ['AI_DRAMA_P2_VLM_SETUP_MODEL'])"
        if ($LASTEXITCODE -ne 0) {
            throw 'Failed to download Qwen3-VL-4B-Instruct.'
        }
    } finally {
        Remove-Item Env:AI_DRAMA_P2_VLM_SETUP_MODEL -ErrorAction SilentlyContinue
    }
} else {
    Write-Host '[Breakdown VLM] Qwen3-VL-4B-Instruct checkpoint already exists.'
}

Write-Host '[Breakdown VLM] Running runner CLI self-check.'
& $PythonExe $Runner --help | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'P2.4 Qwen3-VL runner self-check failed.'
}

Write-Host ''
Write-Host '[Breakdown VLM] READY' -ForegroundColor Green
Write-Host "  Python: $PythonExe"
Write-Host "  Model:  $ModelDir"
Write-Host '  Provider: qwen3-vl'
Write-Host '  Production inference is offline; model download occurs only in setup.'
