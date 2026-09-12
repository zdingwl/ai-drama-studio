param(
    [int]$Port = 8092,
    [string]$ModelDir = ""
)

$ErrorActionPreference = "Stop"
$ServedModel = "IndexTeam/IndexTTS-2.5"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $ModelDir) {
    $ModelDir = Join-Path $RepoRoot ".models\IndexTTS-2.5"
}

if (-not (Test-Path $ModelDir)) {
    throw "Local IndexTTS-2.5 model bundle not found at $ModelDir. Run scripts/download_indextts25_model.ps1 first."
}

$vllm = Get-Command vllm -ErrorAction SilentlyContinue
if ($vllm) {
    & vllm serve $ModelDir --served-model-name $ServedModel --omni --trust-remote-code --port $Port
    exit $LASTEXITCODE
}

$wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
if ($wsl) {
    $linuxModelDir = (& wsl.exe wslpath -a $ModelDir | Select-Object -First 1).Trim()
    Write-Host "Native vllm not found; using the WSL vLLM-Omni runtime..."
    $command = "command -v vllm >/dev/null 2>&1 || { echo 'ERROR: vllm is not installed inside WSL. Install vllm-omni[indextts2] first.' >&2; exit 1; }; exec vllm serve '$linuxModelDir' --served-model-name '$ServedModel' --omni --trust-remote-code --port $Port"
    & wsl.exe bash -lc $command
    exit $LASTEXITCODE
}

throw "vllm was not found. Install the IndexTTS-2.5/vLLM-Omni runtime first; Windows users should use WSL2."
