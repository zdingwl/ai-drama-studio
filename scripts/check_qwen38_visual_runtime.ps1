param(
    [string]$PythonExe = '',
    [string]$ModelPath = '',
    [switch]$Json
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RuntimeRoot = Join-Path $RepoRoot '.runtime\Qwen38Visual'
if (-not $PythonExe) {
    $PythonExe = Join-Path $RuntimeRoot '.venv\Scripts\python.exe'
}
if (-not $ModelPath) {
    $ModelPath = Join-Path $RuntimeRoot 'pretrained\Qwen3.8-27B'
}
$Runner = Join-Path $RepoRoot 'scripts\run_breakdown_vlm_fast_grounded_qwen38.py'
$Checker = Join-Path $RepoRoot 'scripts\check_qwen38_visual_runtime.py'

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Missing dedicated Qwen3.8 Python runtime: $PythonExe. Run scripts/setup_breakdown_vlm_runtime.ps1 first."
}
if (-not (Test-Path -LiteralPath $Checker)) {
    throw "Missing Qwen3.8 readiness checker: $Checker"
}

$Arguments = @(
    $Checker,
    '--python', $PythonExe,
    '--model-path', $ModelPath,
    '--runner', $Runner
)
if ($Json) {
    $Arguments += '--json'
}

& $PythonExe @Arguments
exit $LASTEXITCODE
