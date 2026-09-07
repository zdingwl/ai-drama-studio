param(
    [string]$PythonExe = "",
    [string]$ModelPath = ""
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$InferenceRoot = Join-Path $RepoRoot '.runtime\TransVLM\inference'
if (-not $PythonExe) {
    $PythonExe = Join-Path $InferenceRoot '.venv\Scripts\python.exe'
}
if (-not $ModelPath) {
    $ModelPath = Join-Path $InferenceRoot 'pretrained\Qwen3.8-27B'
}
$Runner = Join-Path $RepoRoot 'scripts\run_breakdown_vlm_fast_grounded_qwen38.py'
$Config = Join-Path $ModelPath 'config.json'

function Require-Path([string]$PathValue, [string]$Label) {
    if (-not (Test-Path -LiteralPath $PathValue)) {
        throw "Missing $Label`: $PathValue"
    }
}

Write-Host '[Qwen3.8] Source visual runtime readiness check'
Write-Host "  Python: $PythonExe"
Write-Host "  Model:  $ModelPath"
Write-Host "  Runner: $Runner"

Require-Path $PythonExe 'isolated Python runtime'
Require-Path $ModelPath 'Qwen3.8-27B checkpoint directory'
Require-Path $Config 'Qwen3.8-27B config.json'
Require-Path $Runner 'Qwen3.8 Fast Grounded runner'

Write-Host '[Qwen3.8] Checking PyTorch/CUDA.'
& $PythonExe -c "import torch; print('torch=' + str(torch.__version__)); print('cuda=' + str(torch.cuda.is_available())); print('gpu=' + (torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO GPU'))"
if ($LASTEXITCODE -ne 0) {
    throw 'PyTorch runtime self-check failed.'
}

Write-Host '[Qwen3.8] Checking current Transformers multimodal loader and video utility.'
& $PythonExe -c "from transformers import AutoModelForMultimodalLM, AutoProcessor; from qwen_vl_utils import process_vision_info; print('AutoModelForMultimodalLM=OK'); print('AutoProcessor=OK'); print('qwen_vl_utils=OK')"
if ($LASTEXITCODE -ne 0) {
    throw 'Qwen3.8 Python dependencies are not compatible. Update the isolated visual runtime before real acceptance.'
}

Write-Host '[Qwen3.8] Checking checkpoint architecture metadata.'
& $PythonExe -c "import json, pathlib; p=pathlib.Path(r'$Config'); c=json.loads(p.read_text(encoding='utf-8')); print('model_type=' + str(c.get('model_type'))); print('architectures=' + str(c.get('architectures'))); assert c.get('model_type') in {'qwen3_5','qwen3.8','qwen3_8'} or any('Qwen3_5' in str(x) or 'Qwen3.8' in str(x) for x in c.get('architectures', [])), 'checkpoint does not look like Qwen3.8/Qwen3.5 architecture'"
if ($LASTEXITCODE -ne 0) {
    throw 'Checkpoint architecture metadata does not match the expected Qwen3.8 family.'
}

Write-Host '[Qwen3.8] Checking dedicated runner CLI import path.'
& $PythonExe $Runner --help | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Qwen3.8 Fast Grounded runner import/CLI check failed.'
}

Write-Host ''
Write-Host '[Qwen3.8] READINESS CHECK PASSED' -ForegroundColor Green
Write-Host '  This proves runtime/checkpoint/loader readiness only.'
Write-Host '  It does NOT prove real Episode video acceptance; run the actual P2 pipeline next.'
