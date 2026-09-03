param(
    [string]$ProjectId = '',
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

if (-not $ProjectId.Trim()) {
    try {
        $Projects = @(Invoke-RestMethod -Method Get -Uri "$($BaseUrl.TrimEnd('/'))/api/projects" -TimeoutSec 15)
    }
    catch {
        throw "无法连接本地后端 $BaseUrl，不能自动选择真实项目。请先启动后端。原始错误：$($_.Exception.Message)"
    }

    $Candidates = @($Projects | Where-Object {
        $_ -and $_.id -and $_.episodes -and @($_.episodes).Count -gt 0
    })

    if ($Candidates.Count -eq 1) {
        $ProjectId = [string]$Candidates[0].id
        Write-Host "[AI Drama Studio] 自动选择唯一有视频的项目：$($Candidates[0].name) ($ProjectId)"
    }
    elseif ($Candidates.Count -eq 0) {
        throw '当前本地后端没有可验收的项目（至少需要一个已导入视频的项目）。'
    }
    else {
        Write-Host '[AI Drama Studio] 检测到多个有视频的项目，请明确选择一个：'
        foreach ($Project in $Candidates) {
            Write-Host "  $($Project.name)  $($Project.id)"
        }
        throw '存在多个真实项目。请重新运行并传入 -ProjectId <项目ID>，避免误跑其他项目。'
    }
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
$RunnerExitCode = $LASTEXITCODE

# Exit code 2 is a deliberate business gate, not an execution failure. Print enough source
# truth to continue E2E debugging without asking the user to manually query several APIs.
if ($RunnerExitCode -eq 2) {
    Write-Host ''
    Write-Host '[AI Drama Studio] 当前真实业务阻塞（OPEN ReviewIssue）'
    try {
        $Issues = @(Invoke-RestMethod -Method Get -Uri "$($BaseUrl.TrimEnd('/'))/api/projects/$ProjectId/review-issues?status=OPEN" -TimeoutSec 15)
        if ($Issues.Count -eq 0) {
            Write-Host '  Runner 检测到待确认，但刷新后队列已为空；可直接重新运行本命令。'
        }
        else {
            $Index = 0
            foreach ($Issue in $Issues) {
                $Index += 1
                $LocationParts = @()
                if ($Issue.episode_id) { $LocationParts += "episode=$($Issue.episode_id)" }
                if ($Issue.shot_id) { $LocationParts += "shot=$($Issue.shot_id)" }
                $Location = if ($LocationParts.Count) { $LocationParts -join ' · ' } else { 'project-level' }
                Write-Host "  [$Index] $($Issue.issue_type) / $($Issue.severity)"
                Write-Host "      $($Issue.reason)"
                Write-Host "      $Location"
            }
        }
        Write-Host ''
        Write-Host "  原片确认：$($BaseUrl.TrimEnd('/').Replace(':8000', ':5173'))/projects/$ProjectId/source-confirm"
        Write-Host "  视频重做：$($BaseUrl.TrimEnd('/').Replace(':8000', ':5173'))/projects/$ProjectId/remake"
    }
    catch {
        Write-Host "  读取 ReviewIssue 详情失败：$($_.Exception.Message)"
    }
}

exit $RunnerExitCode
