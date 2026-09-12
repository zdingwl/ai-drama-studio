param(
    [int]$Port = 8092,
    [string]$Model = "IndexTeam/IndexTTS-2.5"
)

$ErrorActionPreference = "Stop"

if ($Model -ne "IndexTeam/IndexTTS-2.5") {
    throw "P14 is locked to IndexTeam/IndexTTS-2.5."
}

$vllm = Get-Command vllm -ErrorAction SilentlyContinue
if ($vllm) {
    & vllm serve $Model --omni --trust-remote-code --port $Port
    exit $LASTEXITCODE
}

$wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
if ($wsl) {
    Write-Host "Native vllm not found; trying the WSL runtime..."
    $command = "command -v vllm >/dev/null 2>&1 || { echo 'ERROR: vllm is not installed inside WSL.' >&2; exit 1; }; exec vllm serve '$Model' --omni --trust-remote-code --port $Port"
    & wsl.exe bash -lc $command
    exit $LASTEXITCODE
}

throw "vllm was not found. Install the IndexTTS-2.5/vLLM-Omni runtime first (Windows users should use WSL2)."
