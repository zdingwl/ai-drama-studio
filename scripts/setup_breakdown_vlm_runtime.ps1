param(
    [ValidateSet('auto', 'cu128', 'cu130')]
    [string]$Cuda = 'auto',
    [switch]$SkipModelDownload
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Keep this script ASCII-only for Windows PowerShell 5.1 compatibility.
function Test-Command([string]$Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

$RequiredCommands = @('uv', 'nvidia-smi')
$MissingCommands = @($RequiredCommands | Where-Object { -not (Test-Command $_) })
if ($MissingCommands.Count -gt 0) {
    Write-Host ''
    Write-Host '[Qwen3.8 Visual] Missing required command(s):' -ForegroundColor Red
    foreach ($Item in $MissingCommands) {
        Write-Host "  - $Item" -ForegroundColor Red
    }
    if ($MissingCommands -contains 'uv') {
        Write-Host 'Install uv with: winget install --id astral-sh.uv -e --source winget' -ForegroundColor Yellow
    }
    throw "Missing required command(s): $($MissingCommands -join ', ')"
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RuntimeRoot = Join-Path $RepoRoot '.runtime\Qwen38Visual'
$VenvRoot = Join-Path $RuntimeRoot '.venv'
$PythonExe = Join-Path $VenvRoot 'Scripts\python.exe'
$ModelDir = Join-Path $RuntimeRoot 'pretrained\Qwen3.8-27B'
$Runner = Join-Path $RepoRoot 'scripts\run_breakdown_vlm_fast_grounded_qwen38.py'
$Readiness = Join-Path $RepoRoot 'scripts\check_qwen38_visual_runtime.py'
$ModelId = 'Qwen/Qwen3.8-27B'

if (-not (Test-Path -LiteralPath $Runner)) {
    throw "Missing Qwen3.8 production runner: $Runner"
}
if (-not (Test-Path -LiteralPath $Readiness)) {
    throw "Missing Qwen3.8 readiness checker: $Readiness"
}

if ($Cuda -eq 'auto') {
    $DriverText = (& nvidia-smi --query-gpu=driver_version --format=csv,noheader | Select-Object -First 1).Trim()
    if (-not $DriverText) {
        throw 'Could not read the NVIDIA driver version.'
    }
    $DriverMajor = [int]($DriverText.Split('.')[0])
    $Cuda = if ($DriverMajor -ge 570) { 'cu130' } else { 'cu128' }
    Write-Host "[Qwen3.8 Visual] NVIDIA Driver $DriverText -> $Cuda"
}

Write-Host '[Qwen3.8 Visual] Dedicated runtime setup'
Write-Host "  Runtime: $RuntimeRoot"
Write-Host "  Model:   $ModelId"
Write-Host "  CUDA:    $Cuda"
Write-Host ''
Write-Host 'The Qwen3.8-27B checkpoint is large (roughly 56 GB on Hugging Face).' -ForegroundColor Yellow
Write-Host 'Keep at least ~70 GB free for the checkpoint plus download/cache overhead.' -ForegroundColor Yellow
Write-Host 'This runtime is intentionally separate from .runtime\TransVLM.' -ForegroundColor Yellow
Write-Host ''

New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $ModelDir -Parent) | Out-Null

Write-Host '[Qwen3.8 Visual] Ensuring Python 3.12 through uv.'
uv python install 3.12
if ($LASTEXITCODE -ne 0) {
    throw 'uv failed to install/find Python 3.12.'
}

if (-not (Test-Path -LiteralPath $PythonExe)) {
    Write-Host '[Qwen3.8 Visual] Creating isolated Python 3.12 environment.'
    uv venv --python 3.12 $VenvRoot
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to create the dedicated Qwen3.8 virtual environment.'
    }
}

$TorchIndex = "https://download.pytorch.org/whl/$Cuda"
Write-Host "[Qwen3.8 Visual] Installing PyTorch 2.9.1 from $Cuda wheels."
uv pip install --python $PythonExe --index-url $TorchIndex 'torch==2.9.1' 'torchvision==0.24.1'
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to install the CUDA-enabled PyTorch runtime.'
}

Write-Host '[Qwen3.8 Visual] Installing isolated Qwen3.8 multimodal dependencies.'
uv pip install --python $PythonExe `
    'transformers==5.16.1' `
    'accelerate>=1.10.0,<2' `
    'qwen-vl-utils[decord]==0.0.14' `
    'huggingface-hub>=0.34,<2' `
    'safetensors>=0.5' `
    'packaging>=24' `
    'pillow>=11'
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to install Qwen3.8 multimodal dependencies.'
}

Write-Host '[Qwen3.8 Visual] Verifying the isolated multimodal import surface.'
& $PythonExe -c "import torch, transformers, qwen_vl_utils; from transformers import AutoModelForMultimodalLM, AutoProcessor; from qwen_vl_utils import process_vision_info; print('torch=' + str(torch.__version__)); print('transformers=' + str(transformers.__version__)); print('cuda=' + str(torch.cuda.is_available())); print('gpu=' + (torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO GPU')); print('AutoModelForMultimodalLM=OK'); print('process_vision_info=OK')"
if ($LASTEXITCODE -ne 0) {
    throw 'Qwen3.8 multimodal import self-check failed.'
}

if (-not $SkipModelDownload) {
    if (-not (Test-Path -LiteralPath (Join-Path $ModelDir 'config.json'))) {
        Write-Host "[Qwen3.8 Visual] Downloading $ModelId."
        $env:AI_DRAMA_QWEN38_SETUP_MODEL = $ModelDir
        try {
            & $PythonExe -c "import os; from huggingface_hub import snapshot_download; snapshot_download('Qwen/Qwen3.8-27B', local_dir=os.environ['AI_DRAMA_QWEN38_SETUP_MODEL'])"
            if ($LASTEXITCODE -ne 0) {
                throw 'Failed to download Qwen3.8-27B.'
            }
        }
        finally {
            Remove-Item Env:AI_DRAMA_QWEN38_SETUP_MODEL -ErrorAction SilentlyContinue
        }
    }
    else {
        Write-Host '[Qwen3.8 Visual] Qwen3.8-27B checkpoint already exists.'
    }
}
else {
    Write-Host '[Qwen3.8 Visual] Model download skipped by request.' -ForegroundColor Yellow
}

Write-Host '[Qwen3.8 Visual] Running readiness check (no checkpoint load / no video inference).'
$ReadinessArgs = @(
    $Readiness,
    '--python', $PythonExe,
    '--model-path', $ModelDir,
    '--runner', $Runner
)
if ($SkipModelDownload -and -not (Test-Path -LiteralPath (Join-Path $ModelDir 'config.json'))) {
    Write-Host '[Qwen3.8 Visual] Runtime packages are installed, but readiness stays BLOCKED until the checkpoint is present.' -ForegroundColor Yellow
}
else {
    & $PythonExe @ReadinessArgs
    if ($LASTEXITCODE -ne 0) {
        throw 'Qwen3.8 visual runtime readiness check failed.'
    }
}

Write-Host ''
Write-Host '[Qwen3.8 Visual] SETUP COMPLETE' -ForegroundColor Green
Write-Host "  Python:   $PythonExe"
Write-Host "  Model:    $ModelDir"
Write-Host "  Runner:   $Runner"
Write-Host '  Provider: qwen38-video-understanding'
Write-Host '  ASR/OCR remains canonical dialogue owner.'
Write-Host '  This setup does NOT count as real Episode/video acceptance.'
