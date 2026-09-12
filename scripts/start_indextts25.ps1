param(
    [int]$Port = 8092,
    [string]$ModelDir = ""
)

$ErrorActionPreference = "Stop"
$Native = Join-Path $PSScriptRoot "start_indextts25_native_windows.ps1"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Native -Port $Port -ModelDir $ModelDir
exit $LASTEXITCODE
