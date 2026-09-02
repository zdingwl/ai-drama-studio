param(
    [string]$BaseUrl = 'http://127.0.0.1:8000',
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

$Arguments = @(
    $CheckScript,
    '--base-url', $BaseUrl,
    '--timeout', [string]$TimeoutSeconds
)

if ($VlmBaseUrl) { $Arguments += @('--vlm-base-url', $VlmBaseUrl) }
if ($VlmModel) { $Arguments += @('--vlm-model', $VlmModel) }
if ($Json) { $Arguments += '--json' }

Write-Host '[AI Drama Studio] Localized Remake runtime stack check'
Write-Host "  Backend: $BaseUrl"
if ($VlmBaseUrl) { Write-Host "  VLM:     $VlmBaseUrl" }
Write-Host ''

& $Python @Arguments
exit $LASTEXITCODE
