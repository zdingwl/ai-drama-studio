param(
    [ValidateSet('auto', 'cu128', 'cu130')]
    [string]$Cuda = 'auto'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Test-Command([string]$Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

$requiredCommands = @('git', 'uv', 'ffmpeg', 'nvidia-smi')
$missingCommands = @($requiredCommands | Where-Object { -not (Test-Command $_) })
if ($missingCommands.Count -gt 0) {
    Write-Host ''
    Write-Host '[TransVLM] Missing required command(s):' -ForegroundColor Red
    foreach ($item in $missingCommands) {
        Write-Host "  - $item" -ForegroundColor Red
    }
    if ($missingCommands -contains 'uv') {
        Write-Host ''
        Write-Host 'Install uv with:' -ForegroundColor Yellow
        Write-Host '  winget install --id=astral-sh.uv -e' -ForegroundColor Yellow
        Write-Host 'Then close and reopen PowerShell before running this script again.' -ForegroundColor Yellow
    }
    throw "Missing required command(s): $($missingCommands -join ', ')"
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RuntimeRoot = Join-Path $RepoRoot '.runtime\TransVLM'
$InferenceRoot = Join-Path $RuntimeRoot 'inference'
$PythonExe = Join-Path $InferenceRoot '.venv\Scripts\python.exe'
$CheckpointDir = Join-Path $InferenceRoot 'pretrained\TransVLM-v1'

Write-Host "[TransVLM] Runtime: $RuntimeRoot"

if (-not (Test-Path (Join-Path $RuntimeRoot '.git'))) {
    New-Item -ItemType Directory -Force -Path (Split-Path $RuntimeRoot -Parent) | Out-Null
    git clone https://github.com/heygen-com/TransVLM $RuntimeRoot
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to clone the official TransVLM repository.'
    }
} else {
    Write-Host '[TransVLM] Official repository already exists; updating with fast-forward only.'
    git -C $RuntimeRoot pull --ff-only
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to update the official TransVLM repository.'
    }
}

if ($Cuda -eq 'auto') {
    $driverText = (& nvidia-smi --query-gpu=driver_version --format=csv,noheader | Select-Object -First 1).Trim()
    if (-not $driverText) {
        throw 'Could not read the NVIDIA driver version.'
    }
    $driverMajor = [int]($driverText.Split('.')[0])
    $Cuda = if ($driverMajor -ge 570) { 'cu130' } else { 'cu128' }
    Write-Host "[TransVLM] NVIDIA Driver $driverText -> $Cuda"
}

Push-Location $InferenceRoot
try {
    Write-Host '[TransVLM] Ensuring Python 3.12 is available through uv.'
    uv python install 3.12
    if ($LASTEXITCODE -ne 0) {
        throw 'uv failed to install/find Python 3.12.'
    }

    if (-not (Test-Path $PythonExe)) {
        Write-Host '[TransVLM] Creating isolated Python 3.12 environment.'
        uv venv --python 3.12
        if ($LASTEXITCODE -ne 0) {
            throw 'Failed to create the TransVLM Python 3.12 environment.'
        }
    }

    Write-Host "[TransVLM] Installing official inference dependencies ($Cuda, HuggingFace backend only)."
    uv sync --group $Cuda --group dev
    if ($LASTEXITCODE -ne 0) {
        throw 'uv sync failed while installing TransVLM dependencies.'
    }

    if ($Cuda -eq 'cu130') {
        uv pip install --python $PythonExe nvidia-cudnn-cu13==9.16.0.29
    } else {
        uv pip install --python $PythonExe nvidia-cudnn-cu12==9.16.0.29
    }
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to install cuDNN 9.16 for TransVLM.'
    }

    $cudnnText = (& $PythonExe -c "import torch; print(torch.backends.cudnn.version() or 0)").Trim()
    Write-Host "[TransVLM] cuDNN = $cudnnText"
    if ([int]$cudnnText -lt 91600) {
        throw "TransVLM requires cuDNN >= 9.16; detected $cudnnText."
    }

    New-Item -ItemType Directory -Force -Path $CheckpointDir | Out-Null
    $env:AI_DRAMA_TRANSVLM_SETUP_CKPT = $CheckpointDir
    Write-Host '[TransVLM] Downloading TransVLM and NeuFlow checkpoints. This can take a while.'
    & $PythonExe -c "import os; from huggingface_hub import snapshot_download; snapshot_download('HeyGenAI/TransVLM-Qwen3-VL-4B-Instruct', local_dir=os.environ['AI_DRAMA_TRANSVLM_SETUP_CKPT']); snapshot_download('Study-is-happy/neuflow-v2')"
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to download the TransVLM / NeuFlow checkpoints.'
    }
    Remove-Item Env:AI_DRAMA_TRANSVLM_SETUP_CKPT -ErrorAction SilentlyContinue

    Write-Host '[TransVLM] Running infer_video.py import/CLI self-check.'
    & $PythonExe (Join-Path $InferenceRoot 'infer_video.py') --help | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'TransVLM infer_video.py self-check failed.'
    }

    Write-Host ''
    Write-Host '[TransVLM] READY' -ForegroundColor Green
    Write-Host "  Python: $PythonExe"
    Write-Host "  Checkpoint: $CheckpointDir"
    Write-Host '  Backend: hf'
    Write-Host "  CUDA group: $Cuda"
} finally {
    Remove-Item Env:AI_DRAMA_TRANSVLM_SETUP_CKPT -ErrorAction SilentlyContinue
    Pop-Location
}
