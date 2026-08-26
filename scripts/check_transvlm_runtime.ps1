param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RuntimeRoot = Join-Path $RepoRoot '.runtime\TransVLM'
$InferenceRoot = Join-Path $RuntimeRoot 'inference'
$PythonExe = Join-Path $InferenceRoot '.venv\Scripts\python.exe'
$FfmpegPathFile = Join-Path $RuntimeRoot 'ffmpeg_shared_bin.txt'
$TorchLib = Join-Path $InferenceRoot '.venv\Lib\site-packages\torch\lib'
$CacheDriver = Join-Path $RepoRoot 'scripts\run_transvlm_cached.py'

function Require-Path([string]$PathValue, [string]$Label) {
    if (-not (Test-Path -LiteralPath $PathValue)) {
        throw "Missing $Label`: $PathValue"
    }
}

Write-Host '[TransVLM] Windows runtime self-check'
Write-Host "  Runtime: $RuntimeRoot"

Require-Path $PythonExe 'TransVLM Python'
Require-Path $FfmpegPathFile 'FFmpeg shared marker'
Require-Path $TorchLib 'PyTorch DLL directory'
Require-Path $CacheDriver 'V5.1 cache driver'

$SharedFfmpegBin = (Get-Content -LiteralPath $FfmpegPathFile -Raw -Encoding UTF8).Trim()
if (-not $SharedFfmpegBin) {
    throw "FFmpeg shared marker is empty: $FfmpegPathFile"
}
Require-Path $SharedFfmpegBin 'FFmpeg shared bin'

foreach ($name in @('ffmpeg.exe', 'ffprobe.exe')) {
    Require-Path (Join-Path $SharedFfmpegBin $name) $name
}
foreach ($pattern in @('avcodec-*.dll', 'avformat-*.dll', 'avutil-*.dll')) {
    $match = Get-ChildItem -LiteralPath $SharedFfmpegBin -Filter $pattern -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $match) {
        throw "FFmpeg shared runtime is missing $pattern in $SharedFfmpegBin"
    }
}

# Match the environment used by engine/app/transvlm_runtime_v5.py / v51.py.
$OriginalPath = $env:PATH
$env:PATH = "$SharedFfmpegBin;$TorchLib;$OriginalPath"

try {
    Write-Host "[TransVLM] Shared FFmpeg: $SharedFfmpegBin"
    & (Join-Path $SharedFfmpegBin 'ffmpeg.exe') -version | Select-Object -First 1
    if ($LASTEXITCODE -ne 0) {
        throw 'FFmpeg shared runtime failed to execute.'
    }

    Write-Host '[TransVLM] Checking CUDA / cuDNN.'
    & $PythonExe -c "import torch; print('torch=' + str(torch.__version__)); print('cuda_runtime=' + str(torch.version.cuda)); print('cuda_available=' + str(torch.cuda.is_available())); print('gpu=' + (torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO GPU')); print('cudnn=' + str(torch.backends.cudnn.version() or 0))"
    if ($LASTEXITCODE -ne 0) {
        throw 'PyTorch CUDA self-check failed.'
    }

    Write-Host '[TransVLM] Checking TorchCodec with the same DLL search path used by production inference.'
    & $PythonExe -c "from torchcodec.decoders import VideoDecoder; import torchcodec; print('torchcodec=OK')"
    if ($LASTEXITCODE -ne 0) {
        throw 'TorchCodec self-check failed. Re-run scripts/setup_transvlm_runtime.ps1.'
    }

    Write-Host '[TransVLM] Checking official infer_video.py CLI import path.'
    & $PythonExe (Join-Path $InferenceRoot 'infer_video.py') --help | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'infer_video.py self-check failed.'
    }

    Write-Host '[TransVLM] Checking V5.1 parity-safe cache driver import path.'
    & $PythonExe $CacheDriver --ai-inference-root $InferenceRoot --help | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'V5.1 cache driver self-check failed.'
    }

    Write-Host ''
    Write-Host '[TransVLM] RUNTIME CHECK PASSED' -ForegroundColor Green
    Write-Host '  CUDA/cuDNN: OK'
    Write-Host '  TorchCodec: OK'
    Write-Host '  FFmpeg shared DLLs: OK'
    Write-Host '  infer_video.py: OK'
    Write-Host '  V5.1 cache driver: OK'
} finally {
    $env:PATH = $OriginalPath
}
