#!/usr/bin/env python3
"""Production Fast Grounded runner for local Qwen3.8-27B.

Qwen3.8 is the second-pass per-Shot visual/directing model.  The first-pass whole-Episode Source
Bible is produced by Gemini 3.1 Pro and passed through ``AI_DRAMA_EPISODE_INTELLIGENCE_PATH``.
This runner injects that global context into both continuous-window and exact-Shot prompts while
preserving the accepted visual grounding contracts and canonical-dialogue boundary.
"""
from __future__ import annotations

from functools import partial
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_breakdown_vlm_qwen3 as base

SOURCE_BIBLE_ENV = "AI_DRAMA_EPISODE_INTELLIGENCE_PATH"
SOURCE_BIBLE_PROMPT_PROFILE = "gemini31-pro-source-bible-context-v1"


def _load_source_bible() -> Mapping[str, Any]:
    raw_path = (os.getenv(SOURCE_BIBLE_ENV) or "").strip()
    if not raw_path:
        raise RuntimeError("per-Shot VLM requires Gemini Episode Intelligence artifact")
    path = Path(raw_path)
    if not path.is_file():
        raise FileNotFoundError("Gemini Episode Intelligence artifact missing")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping) or str(value.get("status") or "") != "READY":
        raise RuntimeError("Gemini Episode Intelligence artifact is not READY")
    data = value.get("data")
    if not isinstance(data, Mapping):
        raise RuntimeError("Gemini Episode Intelligence artifact has no data object")
    return data


def _compact_source_bible() -> str:
    data = _load_source_bible()
    compact = {
        "episode_summary": data.get("episode_summary"),
        "source_world": data.get("source_world"),
        "story_beats": data.get("story_beats"),
        "characters": data.get("characters"),
        "relationships": data.get("relationships"),
        "scenes": data.get("scenes"),
        "props": data.get("props"),
        "script_scenes": data.get("script_scenes"),
        "key_events": data.get("key_events"),
    }
    text = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
    # Protect the local per-Shot model from pathological upstream output while keeping the whole
    # short-drama Source Bible available in normal cases.
    return text[:24_000]


def _source_bible_instruction() -> str:
    return (
        "\n\n【Gemini整集Source Bible（逐镜分析的上游已知上下文）】\n"
        + _compact_source_bible()
        + "\n使用规则：这份资料用于理解剧情、已知角色候选、场景候选、关键道具和事件关系；"
          "当前Shot的可见人物/动作/表情/构图仍必须由当前画面证明，不能把上游剧情事实伪造成当前镜头可见事实。"
          "不得生成或改写canonical对白。"
    )


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
    processor.apply_chat_template = partial(
        processor.apply_chat_template,
        enable_thinking=False,
        preserve_thinking=False,
    )
    return model, processor


# The accepted timed Fast Grounded runner calls base._load_model once for the whole Episode.
# Replace only that loader before importing/running the production prompt adapters.
base._load_model = _load_qwen38_model

import run_breakdown_vlm_fast_grounded_qwen3_timed as timed
import run_breakdown_vlm_window_segment_index_v4 as window_v4
import run_breakdown_vlm_exact_shot_compact_v3 as exact_v3

_original_window_prompt = window_v4._segment_prompt
_original_exact_prompt = exact_v3._prompt


def _window_prompt_with_source_bible(source_language: str, window: Mapping[str, Any]) -> str:
    return _original_window_prompt(source_language, window) + _source_bible_instruction()


def _exact_prompt_with_source_bible(
    source_language: str,
    batch: Any,
    scene_contexts: Any,
) -> str:
    return _original_exact_prompt(source_language, batch, scene_contexts) + _source_bible_instruction()


window_v4._segment_prompt = _window_prompt_with_source_bible
exact_v3._prompt = _exact_prompt_with_source_bible

timed.compact = window_v4
timed.fast._grounding_adaptive = exact_v3.grounding_adaptive


if __name__ == "__main__":
    raise SystemExit(timed.main())
