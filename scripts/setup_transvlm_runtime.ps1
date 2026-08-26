param(
    [ValidateSet('auto', 'cu128', 'cu130')]
    [string]$Cuda = 'auto'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Test-Command([string]$Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-FfmpegMajor([string]$BinDir) {
    if (-not $BinDir) {
        return $null
    }
    $exe = Join-Path $BinDir 'ffmpeg.exe'
    if (-not (Test-Path $exe)) {
        return $null
    }
    try {
        $firstLine = (& $exe -version 2>$null | Select-Object -First 1)
        if ($firstLine -match 'ffmpeg version\s+([0-9]+)') {
            return [int]$Matches[1]
        }
    } catch {
        return $null
    }
    return $null
}

function Test-SharedFfmpegBin([string]$BinDir) {
    if (-not $BinDir -or -not (Test-Path $BinDir)) {
        return $false
    }
    $major = Get-FfmpegMajor $BinDir
    # The TorchCodec wheel used by TransVLM ships loaders for FFmpeg 4..8.
    if ($null -eq $major -or $major -lt 4 -or $major -gt 8) {
        return $false
    }
    if (-not (Test-Path (Join-Path $BinDir 'ffprobe.exe'))) {
        return $false
    }
    foreach ($pattern in @('avcodec-*.dll', 'avformat-*.dll', 'avutil-*.dll')) {
        $match = Get-ChildItem -Path $BinDir -Filter $pattern -File -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -eq $match) {
            return $false
        }
    }
    return $true
}

function Add-SharedFfmpegCandidate([System.Collections.Generic.List[string]]$Candidates, [string]$PathValue) {
    if (-not $PathValue) {
        return
    }
    try {
        $full = [System.IO.Path]::GetFullPath($PathValue)
        if (-not $Candidates.Contains($full)) {
            $Candidates.Add($full)
        }
    } catch {
        return
    }
}

function Find-SharedFfmpegBin {
    $candidates = New-Object System.Collections.Generic.List[string]

    if ($env:AI_DRAMA_TRANSVLM_FFMPEG_BIN) {
        Add-SharedFfmpegCandidate $candidates $env:AI_DRAMA_TRANSVLM_FFMPEG_BIN
    }

    # WinGet portable packages normally expose an alias from Microsoft\WinGet\Links.
    # Resolve the alias target as well as checking the alias directory itself.
    $ffmpegCommand = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if ($ffmpegCommand -and $ffmpegCommand.Source) {
        Add-SharedFfmpegCandidate $candidates (Split-Path $ffmpegCommand.Source -Parent)
        try {
            $linkItem = Get-Item -LiteralPath $ffmpegCommand.Source -Force -ErrorAction Stop
            foreach ($target in @($linkItem.Target)) {
                if (-not $target) {
                    continue
                }
                $targetPath = [string]$target
                if (-not [System.IO.Path]::IsPathRooted($targetPath)) {
                    $targetPath = Join-Path (Split-Path $ffmpegCommand.Source -Parent) $targetPath
                }
                Add-SharedFfmpegCandidate $candidates (Split-Path $targetPath -Parent)
            }
        } catch {
            # It may be a regular executable rather than a symbolic link.
        }
    }

    foreach ($candidate in $candidates) {
        if (Test-SharedFfmpegBin $candidate) {
            return (Resolve-Path $candidate).Path
        }
    }

    $packageRoots = New-Object System.Collections.Generic.List[string]
    if ($env:LOCALAPPDATA) {
        $packageRoots.Add((Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'))
    }
    if ($env:ProgramFiles) {
        $packageRoots.Add((Join-Path $env:ProgramFiles 'WinGet\Packages'))
    }
    ${env:ProgramFiles(x86)}Value = [Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
    if (${env:ProgramFiles(x86)}Value) {
        $packageRoots.Add((Join-Path ${env:ProgramFiles(x86)}Value 'WinGet\Packages'))
    }

    foreach ($root in $packageRoots) {
        if (-not (Test-Path $root)) {
            continue
        }
        $executables = Get-ChildItem -Path $root -Recurse -File -Filter 'ffmpeg.exe' -ErrorAction SilentlyContinue
        foreach ($exe in $executables) {
            $binDir = $exe.Directory.FullName
            if (Test-SharedFfmpegBin $binDir) {
                return $binDir
            }
        }
    }
    return $null
}

$requiredCommands = @('git', 'uv', 'nvidia-smi')
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
        Write-Host '  winget install --id astral-sh.uv -e --source winget' -ForegroundColor Yellow
        Write-Host 'Then close and reopen PowerShell before running this script again.' -ForegroundColor Yellow
    }
    throw "Missing required command(s): $($missingCommands -join ', ')"
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RuntimeRoot = Join-Path $RepoRoot '.runtime\TransVLM'
$InferenceRoot = Join-Path $RuntimeRoot 'inference'
$PythonExe = Join-Path $InferenceRoot '.venv\Scripts\python.exe'
$CheckpointDir = Join-Path $InferenceRoot 'pretrained\TransVLM-v1'
$CudnnStageScript = Join-Path $RepoRoot 'scripts\stage_transvlm_cudnn_windows.py'
$FfmpegProvisionScript = Join-Path $RepoRoot 'scripts\provision_transvlm_ffmpeg_windows.ps1'
$FfmpegLocalRoot = Join-Path $RepoRoot '.runtime\ffmpeg-shared'
$FfmpegPathFile = Join-Path $RuntimeRoot 'ffmpeg_shared_bin.txt'
$IsWindowsPlatform = [System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT

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
        $CudnnPackage = 'nvidia-cudnn-cu13'
    } else {
        $CudnnPackage = 'nvidia-cudnn-cu12'
    }

    Write-Host "[TransVLM] Installing $CudnnPackage==9.16.0.29."
    uv pip install --python $PythonExe "$CudnnPackage==9.16.0.29"
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to install cuDNN 9.16 for TransVLM.'
    }

    if ($IsWindowsPlatform) {
        if (-not (Test-Path $CudnnStageScript)) {
            throw "Missing Windows cuDNN staging helper: $CudnnStageScript"
        }
        Write-Host '[TransVLM] Staging cuDNN 9.16 DLLs into the isolated PyTorch Windows runtime.'
        & $PythonExe $CudnnStageScript --package $CudnnPackage
        if ($LASTEXITCODE -ne 0) {
            throw 'Failed to stage/verify cuDNN 9.16 in the TransVLM Windows runtime.'
        }
    }

    $cudnnText = (& $PythonExe -c "import torch; print(torch.backends.cudnn.version() or 0)").Trim()
    Write-Host "[TransVLM] cuDNN = $cudnnText"
    if ([int]$cudnnText -lt 91600) {
        throw "TransVLM requires cuDNN >= 9.16; detected $cudnnText."
    }

    if ($IsWindowsPlatform) {
        Write-Host '[TransVLM] Checking for an FFmpeg shared build required by TorchCodec.'
        $SharedFfmpegBin = Find-SharedFfmpegBin

        if (-not $SharedFfmpegBin) {
            if (-not (Test-Path $FfmpegProvisionScript)) {
                throw "Missing FFmpeg provisioning helper: $FfmpegProvisionScript"
            }
            Write-Host '[TransVLM] No compatible installed shared FFmpeg was found.'
            Write-Host '[TransVLM] Provisioning a project-local FFmpeg shared runtime (8.1.2).'
            $SharedFfmpegBin = (& $FfmpegProvisionScript -OutputRoot $FfmpegLocalRoot | Select-Object -Last 1)
            if ($SharedFfmpegBin) {
                $SharedFfmpegBin = ([string]$SharedFfmpegBin).Trim()
            }
        }

        if (-not (Test-SharedFfmpegBin $SharedFfmpegBin)) {
            throw 'TorchCodec requires a compatible FFmpeg shared runtime (major 4..8) with avcodec/avformat/avutil DLLs.'
        }

        $SharedFfmpegBin = (Resolve-Path $SharedFfmpegBin).Path
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($FfmpegPathFile, $SharedFfmpegBin, $utf8NoBom)
        $TorchLib = Join-Path $InferenceRoot '.venv\Lib\site-packages\torch\lib'
        $env:PATH = "$SharedFfmpegBin;$TorchLib;$env:PATH"
        $ffmpegMajor = Get-FfmpegMajor $SharedFfmpegBin
        Write-Host "[TransVLM] Shared FFmpeg = $SharedFfmpegBin (major $ffmpegMajor)"

        Write-Host '[TransVLM] Verifying TorchCodec can load its FFmpeg-backed native library.'
        & $PythonExe -c "from torchcodec.decoders import VideoDecoder; import torchcodec; print('torchcodec=OK')"
        if ($LASTEXITCODE -ne 0) {
            throw 'TorchCodec still cannot load with the selected shared FFmpeg runtime.'
        }
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
    if ($IsWindowsPlatform) {
        Write-Host "  Shared FFmpeg: $SharedFfmpegBin"
    }
} finally {
    Remove-Item Env:AI_DRAMA_TRANSVLM_SETUP_CKPT -ErrorAction SilentlyContinue
    Pop-Location
}
