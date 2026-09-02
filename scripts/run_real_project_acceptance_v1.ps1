param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,
    [string]$BaseUrl = 'http://127.0.0.1:8000',
    [string]$VlmBaseUrl = '',
    [string]$VlmModel = '',
    [switch]$Run,
    [switch]$Json,
    [double]$PollSeconds = 3.0,
    [double]$TimeoutSeconds = 21600.0
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Script = Join-Path $PSScriptRoot 'run_real_project_acceptance_v1.py'
$VenvPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$Python = if (Test-Path -LiteralPath $VenvPython) { $VenvPython } else { 'python' }

if (-not (Test-Path -LiteralPath $Script)) {
    throw "Acceptance runner not found: $Script"
}

$Arguments = @(
    $Script,
    '--project-id', $ProjectId,
    '--base-url', $BaseUrl,
    '--poll-seconds', [string]$PollSeconds,
    '--timeout-seconds', [string]$TimeoutSeconds
)

if ($VlmBaseUrl) { $Arguments += @('--vlm-base-url', $VlmBaseUrl) }
if ($VlmModel) { $Arguments += @('--vlm-model', $VlmModel) }
if ($Run) { $Arguments += '--run' }
if ($Json) { $Arguments += '--json' }

Write-Host '[AI Drama Studio] Real-project acceptance'
Write-Host "  Project: $ProjectId"
Write-Host "  Backend: $BaseUrl"
Write-Host "  Mode:    $(if ($Run) { 'RUN existing production workflow' } else { 'READ-ONLY status check' })"
Write-Host ''

& $Python @Arguments
exit $LASTEXITCODE
