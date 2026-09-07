#!/usr/bin/env python3
"""Production Fast Grounded runner for local Qwen3.8-27B.

Qwen3.8 is a native image/video multimodal model, but its current Transformers architecture is
loaded through ``AutoModelForMultimodalLM`` rather than the historical
``Qwen3VLForConditionalGeneration`` class. This entry keeps the already accepted Window-v4 +
Exact-Shot compact-v3 prompts, frame sampling, timing instrumentation and JSON contracts intact;
only the model-loading seam changes.
"""
from __future__ import annotations

from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_breakdown_vlm_qwen3 as base


def _load_qwen38_model(model_path: Path, device: str):
    import torch
    from transformers import AutoModelForMultimodalLM, AutoProcessor

    dtype = torch.bfloat16 if device == "cuda" and torch.cuda.is_bf16_supported() else (
        torch.float16 if device == "cuda" else torch.float32
    )
    model = AutoModelForMultimodalLM.from_pretrained(
        str(model_path),
        dtype=dtype,
        device_map="auto" if device == "cuda" else None,
        local_files_only=True,
    )
    if device == "cpu":
        model = model.to("cpu")
    model.eval()
    processor = AutoProcessor.from_pretrained(str(model_path), local_files_only=True)
    return model, processor


# The accepted timed Fast Grounded runner calls base._load_model once for the whole Episode.
# Replace only that loader before importing/running the production prompt adapters.
base._load_model = _load_qwen38_model

import run_breakdown_vlm_fast_grounded_qwen3_timed as timed
import run_breakdown_vlm_window_segment_index_v4 as window_v4
import run_breakdown_vlm_exact_shot_compact_v3 as exact_v3

timed.compact = window_v4
timed.fast._grounding_adaptive = exact_v3.grounding_adaptive


if __name__ == "__main__":
    raise SystemExit(timed.main())
