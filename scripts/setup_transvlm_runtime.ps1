param(
    [ValidateSet('auto', 'cu128', 'cu130')]
    [string]$Cuda = 'auto'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Require-Command([string]$Name) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "缺少命令：$Name"
    }
    return $command
}

$null = Require-Command 'git'
$null = Require-Command 'uv'
$null = Require-Command 'ffmpeg'
$null = Require-Command 'nvidia-smi'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RuntimeRoot = Join-Path $RepoRoot '.runtime\TransVLM'
$InferenceRoot = Join-Path $RuntimeRoot 'inference'
$PythonExe = Join-Path $InferenceRoot '.venv\Scripts\python.exe'
$CheckpointDir = Join-Path $InferenceRoot 'pretrained\TransVLM-v1'

Write-Host "[TransVLM] Runtime: $RuntimeRoot"

if (-not (Test-Path (Join-Path $RuntimeRoot '.git'))) {
    New-Item -ItemType Directory -Force -Path (Split-Path $RuntimeRoot -Parent) | Out-Null
    git clone https://github.com/heygen-com/TransVLM $RuntimeRoot
} else {
    Write-Host '[TransVLM] 官方仓库已存在，执行 fast-forward update'
    git -C $RuntimeRoot pull --ff-only
}

if ($Cuda -eq 'auto') {
    $driverText = (& nvidia-smi --query-gpu=driver_version --format=csv,noheader | Select-Object -First 1).Trim()
    if (-not $driverText) {
        throw '无法读取 NVIDIA Driver 版本'
    }
    $driverMajor = [int]($driverText.Split('.')[0])
    $Cuda = if ($driverMajor -ge 570) { 'cu130' } else { 'cu128' }
    Write-Host "[TransVLM] NVIDIA Driver $driverText -> $Cuda"
}

Push-Location $InferenceRoot
try {
    uv python install 3.12
    if (-not (Test-Path $PythonExe)) {
        uv venv --python 3.12
    }

    # 只安装官方 HuggingFace backend；不要把 vLLM / SGLang 混进这个环境。
    uv sync --group $Cuda --group dev

    if ($Cuda -eq 'cu130') {
        uv pip install --python $PythonExe nvidia-cudnn-cu13==9.16.0.29
    } else {
        uv pip install --python $PythonExe nvidia-cudnn-cu12==9.16.0.29
    }

    $cudnnText = (& $PythonExe -c "import torch; print(torch.backends.cudnn.version() or 0)").Trim()
    Write-Host "[TransVLM] cuDNN = $cudnnText"
    if ([int]$cudnnText -lt 91600) {
        throw "TransVLM 官方要求 cuDNN >= 9.16，当前为 $cudnnText"
    }

    New-Item -ItemType Directory -Force -Path $CheckpointDir | Out-Null
    $env:AI_DRAMA_TRANSVLM_SETUP_CKPT = $CheckpointDir
    & $PythonExe -c "import os; from huggingface_hub import snapshot_download; snapshot_download('HeyGenAI/TransVLM-Qwen3-VL-4B-Instruct', local_dir=os.environ['AI_DRAMA_TRANSVLM_SETUP_CKPT']); snapshot_download('Study-is-happy/neuflow-v2')"
    if ($LASTEXITCODE -ne 0) {
        throw 'TransVLM / NeuFlow 权重下载失败'
    }
    Remove-Item Env:AI_DRAMA_TRANSVLM_SETUP_CKPT -ErrorAction SilentlyContinue

    & $PythonExe (Join-Path $InferenceRoot 'infer_video.py') --help | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'TransVLM infer_video.py 自检失败'
    }

    Write-Host ''
    Write-Host '[TransVLM] READY' -ForegroundColor Green
    Write-Host "  Python: $PythonExe"
    Write-Host "  Checkpoint: $CheckpointDir"
    Write-Host '  Backend: hf'
    Write-Host "  CUDA group: $Cuda"
} finally {
    Pop-Location
}
