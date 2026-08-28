param(
    [ValidateSet('cpu', 'auto', 'cuda')]
    [string]$Device = 'cpu'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$VenvPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'

if (Test-Path $VenvPython) {
    $PythonExe = $VenvPython
} else {
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $PythonCommand) {
        throw 'Python not found. Activate the project .venv or create E:\ai-drama-studio\.venv first.'
    }
    $PythonExe = $PythonCommand.Source
}

Write-Host '[Breakdown OCR] Runtime self-check' -ForegroundColor Cyan
Write-Host "  Python: $PythonExe"
Write-Host "  Device: $Device"
Write-Host ''

$env:AI_DRAMA_P2_OCR_SETUP_DEVICE = $Device
Push-Location $RepoRoot
try {
    $CheckScript = @'
import importlib.metadata as metadata
import json
import os
import numpy as np
import cv2
import onnxruntime as ort

from engine.app.breakdown_p2_ocr_runtime_v1 import RapidOCROCRProvider

print("rapidocr=" + metadata.version("rapidocr"))
print("onnxruntime=" + ort.__version__)
print("opencv=" + cv2.__version__)
print("onnx_providers=" + json.dumps(ort.get_available_providers()))

provider = RapidOCROCRProvider(device=os.environ.get("AI_DRAMA_P2_OCR_SETUP_DEVICE", "cpu"))
engine, actual_device, warnings = provider._load_engine("ch")

# Instantiating the engine ensures the PP-OCRv6 small model cache exists. A tiny
# blank-frame call verifies that ONNX Runtime can actually execute the model.
image = np.full((128, 512, 3), 255, dtype=np.uint8)
result = engine(image)
print("engine=READY")
print("actual_device=" + actual_device)
print("warnings=" + json.dumps(list(warnings), ensure_ascii=False))
print("blank_result_type=" + type(result).__name__)
'@

    & $PythonExe -c $CheckScript
    if ($LASTEXITCODE -ne 0) {
        throw 'P2 OCR runtime self-check failed. Read the Python exception above; the full P2 pipeline should not be rerun until this command is READY.'
    }

    Write-Host ''
    Write-Host '[Breakdown OCR] READY' -ForegroundColor Green
    Write-Host 'RapidOCR / PP-OCRv6 / ONNX Runtime can initialize and execute one frame.'
} finally {
    Remove-Item Env:AI_DRAMA_P2_OCR_SETUP_DEVICE -ErrorAction SilentlyContinue
    Pop-Location
}
