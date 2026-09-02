param(
    [string]$BaseUrl = 'http://127.0.0.1:7863',
    [string]$Model = 'UVR-MDX-NET-Inst_HQ_5.onnx',
    [ValidateRange(30, 7200)]
    [int]$TimeoutSeconds = 3600
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$CheckScript = Join-Path $RepoRoot 'scripts\check_audio_separator_runtime.py'
$AudioVenvPython = Join-Path $RepoRoot '.venv-audio-separator\Scripts\python.exe'
$ProjectVenvPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $CheckScript)) {
    throw "Missing runtime check script: $CheckScript"
}

if (Test-Path $AudioVenvPython) {
    $PythonExe = $AudioVenvPython
} elseif (Test-Path $ProjectVenvPython) {
    $PythonExe = $ProjectVenvPython
} else {
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $PythonCommand) {
        throw 'Python not found. Run scripts\setup_audio_separator_runtime.ps1 first.'
    }
    $PythonExe = $PythonCommand.Source
}

Write-Host '[R10.1 Audio Separator] Real model self-check' -ForegroundColor Cyan
Write-Host "  Worker: $BaseUrl"
Write-Host "  Model: $Model"
Write-Host "  Python: $PythonExe"
Write-Host ''

Push-Location $RepoRoot
try {
    & $PythonExe $CheckScript --base-url $BaseUrl --model $Model --timeout $TimeoutSeconds
    if ($LASTEXITCODE -ne 0) {
        throw 'R10.1 audio-separator real inference check failed. Do not mark the runtime READY.'
    }

    Write-Host ''
    Write-Host '[R10.1 Audio Separator] REAL INFERENCE READY' -ForegroundColor Green
    Write-Host 'The configured model loaded and completed one actual separation request.'
} finally {
    Pop-Location
}
