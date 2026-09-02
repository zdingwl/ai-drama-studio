param(
    [string]$BindHost = '127.0.0.1',
    [ValidateRange(1, 65535)]
    [int]$Port = 7863,
    [string]$Model = 'UVR-MDX-NET-Inst_HQ_5.onnx'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$VenvPython = Join-Path $RepoRoot '.venv-audio-separator\Scripts\python.exe'

if (-not (Test-Path $VenvPython)) {
    throw 'Missing .venv-audio-separator. Run scripts\setup_audio_separator_runtime.ps1 first.'
}

$env:AI_DRAMA_BACKGROUND_AUDIO_BASE_URL = "http://${BindHost}:$Port"
$env:AI_DRAMA_BACKGROUND_AUDIO_MODEL = $Model
$env:AI_DRAMA_AUDIO_SEPARATOR_HOST = $BindHost
$env:AI_DRAMA_AUDIO_SEPARATOR_PORT = [string]$Port

Write-Host '[R10.1 Audio Separator] Starting local worker' -ForegroundColor Cyan
Write-Host "  URL: http://${BindHost}:$Port"
Write-Host "  Model: $Model"
Write-Host '  Stop: Ctrl+C'
Write-Host ''

Push-Location $RepoRoot
try {
    & $VenvPython -m uvicorn scripts.audio_separator_worker_v1:app --host $BindHost --port $Port
    if ($LASTEXITCODE -ne 0) {
        throw "audio-separator worker exited with code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}
