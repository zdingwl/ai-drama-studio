param(
    [string]$ModelId = 'Qwen/Qwen3-VL-4B-Instruct',
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$InferenceRoot = Join-Path $RepoRoot '.runtime\TransVLM\inference'
$PythonExe = Join-Path $InferenceRoot '.venv\Scripts\python.exe'
$DefaultModelDir = Join-Path $InferenceRoot 'pretrained\Qwen3-VL-4B-Instruct'
$ModelDir = if ($env:AI_DRAMA_P2_VLM_MODEL_PATH) {
    [System.IO.Path]::GetFullPath($env:AI_DRAMA_P2_VLM_MODEL_PATH)
} else {
    $DefaultModelDir
}

function Require-File([string]$PathValue, [string]$Label) {
    if (-not (Test-Path -LiteralPath $PathValue -PathType Leaf)) {
        throw "Missing $Label`: $PathValue"
    }
}

function Test-Checkpoint([string]$PathValue) {
    if (-not (Test-Path -LiteralPath $PathValue -PathType Container)) {
        return $false
    }
    if (-not (Test-Path -LiteralPath (Join-Path $PathValue 'config.json') -PathType Leaf)) {
        return $false
    }
    $weights = Get-ChildItem -LiteralPath $PathValue -Filter '*.safetensors' -File -ErrorAction SilentlyContinue | Select-Object -First 1
    return $null -ne $weights
}

Write-Host '[Breakdown G1 VLM] Runtime setup'
Write-Host "  Python: $PythonExe"
Write-Host "  Model:  $ModelId"
Write-Host "  Path:   $ModelDir"

if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "Missing isolated Qwen runtime: $PythonExe`nRun .\scripts\setup_transvlm_runtime.ps1 first."
}

if (-not $CheckOnly) {
    New-Item -ItemType Directory -Force -Path $ModelDir | Out-Null
    $env:AI_DRAMA_P2_VLM_SETUP_MODEL_ID = $ModelId
    $env:AI_DRAMA_P2_VLM_SETUP_MODEL_PATH = $ModelDir
    try {
        Write-Host '[Breakdown G1 VLM] Downloading/resuming the production Qwen3-VL checkpoint.'
        & $PythonExe -c "import os; from huggingface_hub import snapshot_download; snapshot_download(os.environ['AI_DRAMA_P2_VLM_SETUP_MODEL_ID'], local_dir=os.environ['AI_DRAMA_P2_VLM_SETUP_MODEL_PATH'])"
        if ($LASTEXITCODE -ne 0) {
            throw 'Failed to download the Breakdown G1 VLM checkpoint.'
        }
    } finally {
        Remove-Item Env:AI_DRAMA_P2_VLM_SETUP_MODEL_ID -ErrorAction SilentlyContinue
        Remove-Item Env:AI_DRAMA_P2_VLM_SETUP_MODEL_PATH -ErrorAction SilentlyContinue
    }
}

if (-not (Test-Checkpoint $ModelDir)) {
    throw "Breakdown G1 VLM checkpoint is incomplete: $ModelDir"
}

Require-File (Join-Path $ModelDir 'config.json') 'Qwen3-VL config.json'

Write-Host '[Breakdown G1 VLM] Verifying local-only Transformers/processor load.'
$env:AI_DRAMA_P2_VLM_VERIFY_PATH = $ModelDir
try {
    & $PythonExe -c "import os; from transformers import AutoConfig, AutoProcessor; p=os.environ['AI_DRAMA_P2_VLM_VERIFY_PATH']; AutoConfig.from_pretrained(p, local_files_only=True); AutoProcessor.from_pretrained(p, local_files_only=True); import qwen_vl_utils; print('qwen3-vl-runtime=OK')"
    if ($LASTEXITCODE -ne 0) {
        throw 'Qwen3-VL local-only processor/config verification failed.'
    }
} finally {
    Remove-Item Env:AI_DRAMA_P2_VLM_VERIFY_PATH -ErrorAction SilentlyContinue
}

Write-Host ''
Write-Host '[Breakdown G1 VLM] READY' -ForegroundColor Green
Write-Host "  Checkpoint: $ModelDir"
Write-Host '  Production profile: breakdown-p2-vlm-fast-grounded-v1'
Write-Host 'Next: python scripts\run_breakdown_p2.py preflight --strict'
