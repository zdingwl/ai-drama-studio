param(
    [Parameter(Mandatory = $true)]
    [string]$EpisodeId,
    [string]$ReviewJson = "",
    [string]$ReportOutput = "",
    [switch]$SkipPreflight
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }
$Runner = Join-Path $RepoRoot "scripts\run_breakdown_p2.py"

Push-Location $RepoRoot
try {
    if (-not $SkipPreflight) {
        & $Python $Runner preflight --strict
        if ($LASTEXITCODE -ne 0) {
            throw "Breakdown P2 runtime preflight failed. Fix the reported local runtime/model paths before inference."
        }
    }

    $ArgsList = @($Runner, "run", "--episode-id", $EpisodeId, "--acceptance")
    if ($ReviewJson) {
        $ArgsList += @("--review-json", $ReviewJson)
    }
    if ($ReportOutput) {
        $ArgsList += @("--report-output", $ReportOutput)
    }
    & $Python @ArgsList
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
