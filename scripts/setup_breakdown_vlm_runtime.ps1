param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$InferenceRoot = Join-Path $RepoRoot '.runtime\TransVLM\inference'
$PythonExe = Join-Path $InferenceRoot '.venv\Scripts\python.exe'
$ModelDir = Join-Path $InferenceRoot 'pretrained\Qwen3-VL-4B-Instruct'
$Runner = Join-Path $RepoRoot 'scripts\run_breakdown_vlm_qwen3_strict_reader.py'
$IsWindowsPlatform = [System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT

if (-not (Test-Path $PythonExe)) {
    throw 'Isolated TransVLM/Qwen runtime is missing. Run scripts/setup_transvlm_runtime.ps1 first.'
}
if (-not (Test-Path $Runner)) {
    throw "Missing P2.4 strict diagnostic runner: $Runner"
}

Write-Host '[Breakdown VLM] Verifying isolated Qwen3-VL runtime.'
& $PythonExe -c "import importlib.metadata as m; from packaging.version import Version; import torch, transformers, qwen_vl_utils, huggingface_hub, decord; from transformers import Qwen3VLForConditionalGeneration, AutoProcessor; qv=m.version('qwen-vl-utils'); assert Version(qv) >= Version('0.0.14'), 'qwen-vl-utils>=0.0.14 required'; print('runtime=OK'); print('torch=' + torch.__version__); print('transformers=' + transformers.__version__); print('qwen-vl-utils=' + qv); print('decord=' + getattr(decord, '__version__', 'unknown'))"
if ($LASTEXITCODE -ne 0) {
    throw 'The isolated runtime is missing the current Qwen3-VL/decord dependencies. Run scripts/setup_transvlm_runtime.ps1 again, then retry this setup.'
}

if (-not (Test-Path (Join-Path $ModelDir 'config.json'))) {
    New-Item -ItemType Directory -Force -Path $ModelDir | Out-Null
    $env:AI_DRAMA_P2_VLM_SETUP_MODEL = $ModelDir
    try {
        Write-Host '[Breakdown VLM] Downloading official Qwen/Qwen3-VL-4B-Instruct checkpoint.'
        & $PythonExe -c "import os; from huggingface_hub import snapshot_download; snapshot_download('Qwen/Qwen3-VL-4B-Instruct', local_dir=os.environ['AI_DRAMA_P2_VLM_SETUP_MODEL'])"
        if ($LASTEXITCODE -ne 0) {
            throw 'Failed to download Qwen3-VL-4B-Instruct.'
        }
    } finally {
        Remove-Item Env:AI_DRAMA_P2_VLM_SETUP_MODEL -ErrorAction SilentlyContinue
    }
} else {
    Write-Host '[Breakdown VLM] Qwen3-VL-4B-Instruct checkpoint already exists.'
}

Write-Host '[Breakdown VLM] Running production strict-reader runner CLI self-check.'
$PreviousReader = $env:FORCE_QWENVL_VIDEO_READER
try {
    if ($IsWindowsPlatform) {
        $env:FORCE_QWENVL_VIDEO_READER = 'decord'
    }
    & $PythonExe $Runner --help | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'P2.4 Qwen3-VL strict-reader runner self-check failed.'
    }
} finally {
    if ($null -eq $PreviousReader) {
        Remove-Item Env:FORCE_QWENVL_VIDEO_READER -ErrorAction SilentlyContinue
    } else {
        $env:FORCE_QWENVL_VIDEO_READER = $PreviousReader
    }
}

Write-Host ''
Write-Host '[Breakdown VLM] READY' -ForegroundColor Green
Write-Host "  Python: $PythonExe"
Write-Host "  Model:  $ModelDir"
Write-Host '  Provider: qwen3-vl'
Write-Host '  Draft 文案: 简体中文 (zh-CN)'
Write-Host '  Prompt Profile: breakdown-p2-vlm-zh-draft-v1'
Write-Host '  ASR / OCR: 保留原始语言与原始文字，不在 VLM 中翻译'
if ($IsWindowsPlatform) {
    Write-Host '  Video reader: decord (strict; torchvision fallback disabled)'
}
Write-Host '  Production inference is offline; model download occurs only in setup.'
