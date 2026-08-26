"""Run official TransVLM inference while safely capturing the exact RGB/flow inputs it used.

This driver intentionally does NOT reimplement TransVLM preprocessing or NeuFlow.  It imports the
runtime's official ``infer_video.py`` and calls its normal ``main()``.  The only instrumentation is:

* remember the flow file produced by ``OnlineFlowComputer.compute_flow_only``;
* after one video's official ``_process_video`` completes successfully, atomically copy the exact
  ``model_rgb`` and computed flow files into the Episode cache.

That ordering matters.  Official ``infer_video.main`` loads the Qwen engine before constructing and
running NeuFlow.  Running flow in a separate helper process could change whether ``flow_to_image``
uses GPU or falls back to CPU, which would no longer be the exact baseline signal.
"""
from __future__ import annotations

import argparse
import importlib
import os
from pathlib import Path
import shutil
import sys
from typing import Any


def _atomic_copy(source: Path, destination: Path) -> None:
    source = Path(source)
    destination = Path(destination)
    if source.resolve() == destination.resolve():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Keep the real media suffix so Windows/FFmpeg tooling can still recognize the temp file.
    temp = destination.with_name(f".{destination.stem}.tmp{destination.suffix}")
    temp.unlink(missing_ok=True)
    try:
        shutil.copy2(source, temp)
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)


def _driver_args(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--ai-inference-root", type=Path, required=True)
    parser.add_argument("--ai-cache-rgb", type=Path)
    parser.add_argument("--ai-cache-flow", type=Path)
    return parser.parse_known_args(argv)


def main() -> int:
    driver, official_argv = _driver_args(sys.argv[1:])
    inference_root = driver.ai_inference_root.resolve()
    if not (inference_root / "infer_video.py").is_file():
        raise SystemExit(f"official infer_video.py not found: {inference_root}")

    # The driver lives in the app repo, not in the official checkout.  Put the official inference
    # root first so ``import infer_video`` and ``import transvlm`` resolve exactly that runtime.
    sys.path.insert(0, str(inference_root))
    infer_video = importlib.import_module("infer_video")
    flow_module = importlib.import_module("transvlm.data.flow_computer")
    OnlineFlowComputer = flow_module.OnlineFlowComputer

    original_compute_flow_only = OnlineFlowComputer.compute_flow_only
    original_process_video = infer_video._process_video
    state: dict[str, Path | None] = {"computed_flow": None}

    def compute_flow_only(self: Any, video_path: Any, out_path: Any):
        result = original_compute_flow_only(self, video_path, out_path)
        state["computed_flow"] = Path(result[0])
        return result

    def process_video(*args: Any, **kwargs: Any):
        # Avoid carrying a previous item's flow path into another item.  The app currently invokes
        # single-video mode, but keeping this correct costs nothing and makes the driver safe for
        # future batch use.
        state["computed_flow"] = None
        result = original_process_video(*args, **kwargs)

        if driver.ai_cache_rgb is not None:
            model_rgb = Path(str(result["model_rgb"]))
            _atomic_copy(model_rgb, driver.ai_cache_rgb)
            print(f"[cache-rgb] captured {driver.ai_cache_rgb}", flush=True)

        computed_flow = state.get("computed_flow")
        if driver.ai_cache_flow is not None and computed_flow is not None:
            _atomic_copy(computed_flow, driver.ai_cache_flow)
            print(f"[cache-flow] captured {driver.ai_cache_flow}", flush=True)

        return result

    OnlineFlowComputer.compute_flow_only = compute_flow_only
    infer_video._process_video = process_video

    # Remove our private flags before the official argparse sees argv.  Everything else is passed
    # through unchanged, so the model protocol and defaults remain owned by the official script.
    sys.argv = [str(inference_root / "infer_video.py"), *official_argv]
    try:
        return int(infer_video.main())
    finally:
        OnlineFlowComputer.compute_flow_only = original_compute_flow_only
        infer_video._process_video = original_process_video


if __name__ == "__main__":
    raise SystemExit(main())
