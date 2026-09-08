param(
    [string]$ProjectId = '',
    [string]$BaseUrl = 'http://127.0.0.1:8000',
    [string]$Qwen38Python = '',
    [string]$Qwen38ModelPath = '',
    # Deprecated compatibility parameters. The source visual provider is no longer an HTTP VLM.
    [string]$VlmBaseUrl = '',
    [string]$VlmModel = '',
    [switch]$Run,
    [switch]$Json,
    [double]$PollSeconds = 3.0,
    [double]$TimeoutSeconds = 21600.0
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Keep this wrapper ASCII-only. Windows PowerShell 5.1 may decode UTF-8 files without a BOM
# through the active ANSI code page, which can corrupt quoted strings on non-English systems.
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Script = Join-Path $PSScriptRoot 'run_real_project_acceptance_v1.py'
$VenvPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$Python = if (Test-Path -LiteralPath $VenvPython) { $VenvPython } else { 'python' }

if (-not (Test-Path -LiteralPath $Script)) {
    throw "Acceptance runner not found: $Script"
}

if ($VlmBaseUrl -or $VlmModel) {
    Write-Host '[AI Drama Studio] -VlmBaseUrl/-VlmModel are deprecated and ignored. Source visual now uses local Qwen3.8-27B.' -ForegroundColor Yellow
}

if (-not $ProjectId.Trim()) {
    try {
        $Projects = @(Invoke-RestMethod -Method Get -Uri "$($BaseUrl.TrimEnd('/'))/api/projects" -TimeoutSec 15)
    }
    catch {
        throw "Cannot reach local backend $BaseUrl to auto-select a project. Start the backend first. Error: $($_.Exception.Message)"
    }

    $Candidates = @($Projects | Where-Object {
        $_ -and $_.id -and $_.episodes -and @($_.episodes).Count -gt 0
    })

    if ($Candidates.Count -eq 1) {
        $ProjectId = [string]$Candidates[0].id
        Write-Host "[AI Drama Studio] Auto-selected the only project with imported video: $($Candidates[0].name) ($ProjectId)"
    }
    elseif ($Candidates.Count -eq 0) {
        throw 'No acceptance-ready project was found. At least one project with an imported Episode is required.'
    }
    else {
        Write-Host '[AI Drama Studio] Multiple projects with imported video were found. Select one explicitly:'
        foreach ($Project in $Candidates) {
            Write-Host "  $($Project.name)  $($Project.id)"
        }
        throw 'Multiple real projects exist. Re-run with -ProjectId <PROJECT_ID> to avoid running the wrong project.'
    }
}

$Arguments = @(
    $Script,
    '--project-id', $ProjectId,
    '--base-url', $BaseUrl,
    '--poll-seconds', [string]$PollSeconds,
    '--timeout-seconds', [string]$TimeoutSeconds
)
if ($Run) { $Arguments += '--run' }
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

    Write-Host '[AI Drama Studio] Real-project acceptance'
    Write-Host "  Project:       $ProjectId"
    Write-Host "  Backend:       $BaseUrl"
    Write-Host '  Source visual: Qwen3.8-27B local provider'
    Write-Host "  Mode:          $(if ($Run) { 'RUN existing production workflow' } else { 'READ-ONLY status check' })"
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

# Exit code 2 is a deliberate business gate, not a wrapper execution failure. Print enough
# source truth to continue E2E debugging without manually querying several APIs.
if ($RunnerExitCode -eq 2) {
    Write-Host ''
    Write-Host '[AI Drama Studio] Current business gate: OPEN ReviewIssue'
    try {
        $Issues = @(Invoke-RestMethod -Method Get -Uri "$($BaseUrl.TrimEnd('/'))/api/projects/$ProjectId/review-issues?status=OPEN" -TimeoutSec 15)
        if ($Issues.Count -eq 0) {
            Write-Host '  The runner reported an open review gate, but the refreshed queue is now empty. Re-run the same command.'
        }
        else {
            $Index = 0
            foreach ($Issue in $Issues) {
                $Index += 1
                $LocationParts = @()
                if ($Issue.episode_id) { $LocationParts += "episode=$($Issue.episode_id)" }
                if ($Issue.shot_id) { $LocationParts += "shot=$($Issue.shot_id)" }
                $Location = if ($LocationParts.Count) { $LocationParts -join ' / ' } else { 'project-level' }
                Write-Host "  [$Index] $($Issue.issue_type) / $($Issue.severity)"
                Write-Host "      $($Issue.reason)"
                Write-Host "      $Location"
            }
        }
        Write-Host ''
        Write-Host "  Source confirm: $($BaseUrl.TrimEnd('/').Replace(':8000', ':5173'))/projects/$ProjectId/source-confirm"
        Write-Host "  Remake:         $($BaseUrl.TrimEnd('/').Replace(':8000', ':5173'))/projects/$ProjectId/remake"
    }
    catch {
        Write-Host "  Failed to read ReviewIssue details: $($_.Exception.Message)"
    }
}

exit $RunnerExitCode
