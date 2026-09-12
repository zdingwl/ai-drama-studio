param(
    [int]$Port = 8092,
    [string]$ModelDir = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RuntimeRoot = Join-Path $RepoRoot ".runtime\indextts25-native-windows"
$SourceDir = Join-Path $RuntimeRoot "source"
$BackendPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$UvExe = Join-Path $RepoRoot ".venv\Scripts\uv.exe"
$UpstreamCommit = "ee40fa7d6c6b8a2c7f06105f9f1e65775b74868c"
$ModelId = "IndexTeam/IndexTTS-2.5"

if (-not $ModelDir) {
    $ModelDir = Join-Path $RepoRoot ".models\IndexTTS-2.5"
}

if (-not (Test-Path $BackendPython)) {
    throw "Studio backend virtual environment is missing. Run start.cmd so the unified launcher can prepare it first."
}

New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $ModelDir -Parent) | Out-Null

if (-not (Test-Path $UvExe)) {
    Write-Host "[IndexTTS Windows] installing uv into the Studio bootstrap environment..."
    & $BackendPython -m pip install --upgrade uv
    if ($LASTEXITCODE -ne 0) { throw "Failed to install uv" }
}

if (-not (Test-Path (Join-Path $SourceDir ".git"))) {
    Write-Host "[IndexTTS Windows] cloning official IndexTTS source..."
    & git clone https://github.com/index-tts/index-tts.git $SourceDir
    if ($LASTEXITCODE -ne 0) { throw "Failed to clone official IndexTTS source" }
}

Push-Location $SourceDir
try {
    $CurrentCommit = (& git rev-parse HEAD).Trim()
    if ($CurrentCommit -ne $UpstreamCommit) {
        Write-Host "[IndexTTS Windows] pinning official source to $UpstreamCommit..."
        & git fetch --depth 1 origin $UpstreamCommit
        if ($LASTEXITCODE -ne 0) { throw "Failed to fetch pinned IndexTTS source commit" }
        & git checkout --detach $UpstreamCommit
        if ($LASTEXITCODE -ne 0) { throw "Failed to checkout pinned IndexTTS source commit" }
    }

    Write-Host "[IndexTTS Windows] syncing the official uv environment (Python 3.10/3.11 is selected automatically)..."
    $IndexUrl = $env:AI_DRAMA_PYPI_INDEX
    if ($IndexUrl) {
        & $UvExe sync --default-index $IndexUrl
    } else {
        & $UvExe sync
    }
    if ($LASTEXITCODE -ne 0) { throw "IndexTTS uv sync failed" }
} finally {
    Pop-Location
}

$RuntimePython = Join-Path $SourceDir ".venv\Scripts\python.exe"
if (-not (Test-Path $RuntimePython)) {
    throw "IndexTTS uv environment was not created at $RuntimePython"
}

Write-Host "[IndexTTS Windows] ensuring local HTTP adapter dependencies..."
& $UvExe pip install --python $RuntimePython "fastapi>=0.115,<1" "uvicorn>=0.30,<1"
if ($LASTEXITCODE -ne 0) { throw "Failed to install IndexTTS HTTP adapter dependencies" }

$Config25 = Join-Path $ModelDir "config_v2_5.yaml"
$ConfigFallback = Join-Path $ModelDir "config.yaml"
if (-not (Test-Path $Config25) -and -not (Test-Path $ConfigFallback)) {
    Write-Host "[IndexTTS Windows] downloading IndexTTS-2.5 from ModelScope to $ModelDir ..."
    $DownloadCode = @"
from modelscope.hub.snapshot_download import snapshot_download
snapshot_download(model_id='$ModelId', local_dir=r'''$ModelDir''')
"@
    & $RuntimePython -c $DownloadCode
    if ($LASTEXITCODE -ne 0) { throw "ModelScope download failed" }
}

if (-not (Test-Path $Config25) -and -not (Test-Path $ConfigFallback)) {
    throw "IndexTTS-2.5 model bundle is incomplete: no config_v2_5.yaml/config.yaml under $ModelDir"
}

$env:PYTHONPATH = $SourceDir
$env:HF_ENDPOINT = $(if ($env:HF_ENDPOINT) { $env:HF_ENDPOINT } else { "https://hf-mirror.com" })
$Adapter = Join-Path $RepoRoot "scripts\indextts25_native_server.py"

Write-Host "[IndexTTS Windows] starting native CUDA runtime on 127.0.0.1:$Port ..."
& $RuntimePython $Adapter --model-dir $ModelDir --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
