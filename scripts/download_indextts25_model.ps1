param(
    [string]$ModelDir = ""
)

$ErrorActionPreference = "Stop"
$ModelId = "IndexTeam/IndexTTS-2.5"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $ModelDir) {
    $ModelDir = Join-Path $RepoRoot ".models\IndexTTS-2.5"
}

$modelscope = Get-Command modelscope -ErrorAction SilentlyContinue
if ($modelscope) {
    New-Item -ItemType Directory -Force -Path (Split-Path $ModelDir -Parent) | Out-Null
    Write-Host "Downloading $ModelId from ModelScope to $ModelDir"
    & modelscope download --model $ModelId --local_dir $ModelDir
    exit $LASTEXITCODE
}

$wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
if ($wsl) {
    $linuxModelDir = (& wsl.exe wslpath -a $ModelDir | Select-Object -First 1).Trim()
    Write-Host "Native modelscope not found; using WSL ModelScope."
    $command = "command -v modelscope >/dev/null 2>&1 || { echo 'ERROR: modelscope is not installed inside WSL. Run: pip install -U modelscope' >&2; exit 1; }; mkdir -p '$linuxModelDir'; modelscope download --model '$ModelId' --local_dir '$linuxModelDir'"
    & wsl.exe bash -lc $command
    exit $LASTEXITCODE
}

throw "modelscope was not found. Install ModelScope locally or inside WSL2 first."
