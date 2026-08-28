#!/usr/bin/env python3
"""Windows/local self-check for Breakdown P2 RapidOCR runtime.

Kept as a real Python file instead of PowerShell ``python -c`` so quoting is
identical across Windows PowerShell versions.
"""
from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import cv2
import numpy as np
import onnxruntime as ort

from engine.app.breakdown_p2_ocr_runtime_v1 import RapidOCROCRProvider


def _package_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "NOT_INSTALLED"


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Drama Studio P2 OCR runtime self-check")
    parser.add_argument("--device", choices=("cpu", "auto", "cuda"), default="cpu")
    args = parser.parse_args()

    print("rapidocr=" + _package_version("rapidocr"))
    print("onnxruntime=" + ort.__version__)
    print("opencv=" + cv2.__version__)
    print("onnx_providers=" + json.dumps(ort.get_available_providers()))

    provider = RapidOCROCRProvider(device=args.device)
    engine, actual_device, warnings = provider._load_engine("ch")

    # Engine construction resolves/downloads its PP-OCRv6 model cache. One tiny
    # blank frame then verifies ONNX Runtime can execute the loaded graph.
    image = np.full((128, 512, 3), 255, dtype=np.uint8)
    result = engine(image)

    print("engine=READY")
    print("actual_device=" + actual_device)
    print("warnings=" + json.dumps(list(warnings), ensure_ascii=False))
    print("blank_result_type=" + type(result).__name__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
