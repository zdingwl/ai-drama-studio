param(
    [Parameter(Mandatory = $true)]
    [string]$OutputRoot
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Version = '8.1.2'
$ArchiveName = "ffmpeg-$Version-full_build-shared.zip"
$ExtractedName = "ffmpeg-$Version-full_build-shared"
$DownloadUrl = "https://github.com/GyanD/codexffmpeg/releases/download/$Version/$ArchiveName"
$ExpectedSha256 = '274923C68904A9B76C73B908F57923DAFBA81155856CD742138515DED570D066'

function Test-SharedFfmpegBin([string]$BinDir) {
    if (-not $BinDir -or -not (Test-Path $BinDir)) {
        return $false
    }
    if (-not (Test-Path (Join-Path $BinDir 'ffmpeg.exe'))) {
        return $false
    }
    if (-not (Test-Path (Join-Path $BinDir 'ffprobe.exe'))) {
        return $false
    }
    foreach ($pattern in @('avcodec-*.dll', 'avformat-*.dll', 'avutil-*.dll')) {
        $match = Get-ChildItem -Path $BinDir -Filter $pattern -File -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -eq $match) {
            return $false
        }
    }
    return $true
}

$OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
$TargetRoot = Join-Path $OutputRoot $ExtractedName
$TargetBin = Join-Path $TargetRoot 'bin'
$ArchivePath = Join-Path $OutputRoot $ArchiveName

if (Test-SharedFfmpegBin $TargetBin) {
    Write-Output $TargetBin
    exit 0
}

New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

Write-Host "[TransVLM] Downloading pinned FFmpeg shared runtime $Version."
Write-Host "[TransVLM] Source: $DownloadUrl"
Invoke-WebRequest -Uri $DownloadUrl -OutFile $ArchivePath -UseBasicParsing

$ActualSha256 = (Get-FileHash -Path $ArchivePath -Algorithm SHA256).Hash.ToUpperInvariant()
if ($ActualSha256 -ne $ExpectedSha256) {
    Remove-Item -Force $ArchivePath -ErrorAction SilentlyContinue
    throw "FFmpeg shared archive SHA256 mismatch. Expected $ExpectedSha256, got $ActualSha256."
}

if (Test-Path $TargetRoot) {
    Remove-Item -Recurse -Force $TargetRoot
}
Expand-Archive -Path $ArchivePath -DestinationPath $OutputRoot -Force
Remove-Item -Force $ArchivePath -ErrorAction SilentlyContinue

if (-not (Test-SharedFfmpegBin $TargetBin)) {
    throw "Downloaded FFmpeg shared runtime is incomplete: $TargetBin"
}

Write-Output $TargetBin
