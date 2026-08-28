param(
    [ValidateSet('cpu', 'auto', 'cuda')]
    [string]$Device = 'cpu'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$VenvPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$CheckScript = Join-Path $RepoRoot 'scripts\check_breakdown_ocr_runtime.py'

if (Test-Path $VenvPython) {
    $PythonExe = $VenvPython
} else {
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $PythonCommand) {
        throw 'Python not found. Activate the project .venv or create the project .venv first.'
    }
    $PythonExe = $PythonCommand.Source
}

if (-not (Test-Path $CheckScript)) {
    throw "Missing OCR runtime check script: $CheckScript"
}

Write-Host '[Breakdown OCR] Runtime self-check' -ForegroundColor Cyan
Write-Host "  Python: $PythonExe"
Write-Host "  Device: $Device"
Write-Host ''

Push-Location $RepoRoot
try {
    & $PythonExe $CheckScript --device $Device
    if ($LASTEXITCODE -ne 0) {
        throw 'P2 OCR runtime self-check failed. Read the Python exception above; the full P2 pipeline should not be rerun until this command is READY.'
    }

    Write-Host ''
    Write-Host '[Breakdown OCR] READY' -ForegroundColor Green
    Write-Host 'RapidOCR / PP-OCRv6 / ONNX Runtime can initialize and execute one frame.'
} finally {
    Pop-Location
}
