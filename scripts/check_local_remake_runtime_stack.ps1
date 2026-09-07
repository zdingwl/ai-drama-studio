param(
    [string]$BaseUrl = 'http://127.0.0.1:8000',
    [string]$Qwen38Python = '',
    [string]$Qwen38ModelPath = '',
    # Deprecated compatibility parameters. Source visual no longer uses an HTTP VLM service.
    [string]$VlmBaseUrl = '',
    [string]$VlmModel = '',
    [double]$TimeoutSeconds = 5.0,
    [switch]$Json
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$CheckScript = Join-Path $PSScriptRoot 'check_local_remake_runtime_stack.py'
$VenvPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$Python = if (Test-Path -LiteralPath $VenvPython) { $VenvPython } else { 'python' }

if (-not (Test-Path -LiteralPath $CheckScript)) {
    throw "Runtime stack checker not found: $CheckScript"
}

if ($VlmBaseUrl -or $VlmModel) {
    Write-Host '[AI Drama Studio] -VlmBaseUrl/-VlmModel are deprecated and ignored. Source visual now uses local Qwen3.8-27B.' -ForegroundColor Yellow
}

$Arguments = @(
    $CheckScript,
    '--base-url', $BaseUrl,
    '--timeout', [string]$TimeoutSeconds
)
if ($Json) { $Arguments += '--json' }

$PreviousQwenPython = $env:AI_DRAMA_P2_VLM_PYTHON
$PreviousQwenModel = $env:AI_DRAMA_P2_VLM_MODEL_PATH
try {
    if ($Qwen38Python) {
        $env:AI_DRAMA_P2_VLM_PYTHON = $Qwen38Python
    }
    if ($Qwen38ModelPath) {
        $env:AI_DRAMA_P2_VLM_MODEL_PATH = $Qwen38ModelPath
    }

    Write-Host '[AI Drama Studio] Localized Remake runtime stack check'
    Write-Host "  Backend:       $BaseUrl"
    Write-Host '  Source visual: Qwen3.8-27B local provider'
    Write-Host ''

    & $Python @Arguments
    $RunnerExitCode = $LASTEXITCODE
}
finally {
    if ($null -eq $PreviousQwenPython) {
        Remove-Item Env:AI_DRAMA_P2_VLM_PYTHON -ErrorAction SilentlyContinue
    }
    else {
        $env:AI_DRAMA_P2_VLM_PYTHON = $PreviousQwenPython
    }
    if ($null -eq $PreviousQwenModel) {
        Remove-Item Env:AI_DRAMA_P2_VLM_MODEL_PATH -ErrorAction SilentlyContinue
    }
    else {
        $env:AI_DRAMA_P2_VLM_MODEL_PATH = $PreviousQwenModel
    }
}

exit $RunnerExitCode
