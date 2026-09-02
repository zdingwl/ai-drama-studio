param(
    [string]$Python = 'python',
    [switch]$Reinstall
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$VenvDir = Join-Path $RepoRoot '.venv-audio-separator'
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'
$Requirements = Join-Path $RepoRoot 'scripts\requirements_audio_separator_v1.txt'

if (-not (Test-Path $Requirements)) {
    throw "Missing requirements file: $Requirements"
}

$PythonCommand = Get-Command $Python -ErrorAction SilentlyContinue
if (-not $PythonCommand) {
    throw "Python command not found: $Python"
}
$BootstrapPython = $PythonCommand.Source

Write-Host '[R10.1 Audio Separator] Dedicated runtime setup' -ForegroundColor Cyan
Write-Host "  Repository: $RepoRoot"
Write-Host "  Bootstrap Python: $BootstrapPython"
Write-Host "  Runtime venv: $VenvDir"
Write-Host ''

Push-Location $RepoRoot
try {
    & $BootstrapPython -c "import sys; assert sys.version_info >= (3, 10), 'Python 3.10+ required'; print('Python', sys.version.split()[0])"
    if ($LASTEXITCODE -ne 0) {
        throw 'Python compatibility check failed.'
    }

    if ($Reinstall -and (Test-Path $VenvDir)) {
        Write-Host '[R10.1 Audio Separator] Removing existing dedicated environment...' -ForegroundColor Yellow
        Remove-Item -Recurse -Force $VenvDir
    }

    if (-not (Test-Path $VenvPython)) {
        Write-Host '[R10.1 Audio Separator] Creating dedicated virtual environment...'
        & $BootstrapPython -m venv $VenvDir
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPython)) {
            throw 'Failed to create .venv-audio-separator.'
        }
    }

    Write-Host '[R10.1 Audio Separator] Installing pinned worker dependencies...'
    & $VenvPython -m pip install --upgrade pip setuptools wheel
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to upgrade pip tooling.'
    }
    & $VenvPython -m pip install -r $Requirements
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to install audio-separator worker dependencies.'
    }

    Write-Host '[R10.1 Audio Separator] Import self-check...'
    & $VenvPython -c "from audio_separator.separator import Separator; import fastapi, uvicorn; print('audio-separator import READY')"
    if ($LASTEXITCODE -ne 0) {
        throw 'audio-separator import self-check failed.'
    }

    Write-Host ''
    Write-Host '[R10.1 Audio Separator] SETUP READY' -ForegroundColor Green
    Write-Host 'Next:'
    Write-Host '  powershell -ExecutionPolicy Bypass -File scripts\start_audio_separator_runtime.ps1'
    Write-Host 'Then in another terminal:'
    Write-Host '  powershell -ExecutionPolicy Bypass -File scripts\check_audio_separator_runtime.ps1'
    Write-Host ''
    Write-Host 'The check command performs one real model separation. Setup/import success alone is not model acceptance.' -ForegroundColor Yellow
} finally {
    Pop-Location
}
