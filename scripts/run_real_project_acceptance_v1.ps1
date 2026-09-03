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
exit $LASTEXITCODE
