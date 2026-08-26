"""Shot V5.1 cached TransVLM runtime built on the proven V5 adapter.

The first run keeps the official execution order unchanged and merely captures the exact model RGB
and computed whole-video flow after the official per-video pipeline succeeds.  Later runs can feed
those exact files back through ``infer_video.py --video ... --flow ... --no-fps-resample
--no-pre-resize`` to skip the expensive preprocessing/NeuFlow stages without changing model input.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

from engine.app import media_v2 as v2
from engine.app import transvlm_runtime_v5 as base

# Explicitly pin every production argument that can affect cached model input/output.  Values match
# the current official defaults but are passed on the CLI so future upstream default changes cannot
# silently reinterpret an existing cache.
TRANSVLM_RUNTIME_PROFILE: dict[str, Any] = {
    "model": "TransVLM-Qwen3-VL-4B-Instruct",
    "backend": "hf",
    "fps": 25.0,
    "window_size": 10.0,
    "stride": 9.0,
    "strict_tail": False,
    "merge_eps": 0.02,
    "timestamp_format": "1f",
    "flow_codec": "libx264",
    "flow_viz_device": "gpu",
    "flow_mini_batch_size": 32,
    "max_pixels_override": 524288,
    "image_patch_size": 16,
    "nframes_for_resize": 250,
    "max_new_tokens": 2048,
    "prefix_caching": True,
}

RuntimeProgress = base.RuntimeProgress
TransVLMTransition = base.TransVLMTransition
runtime_config = base.runtime_config
runtime_status = base.runtime_status


def cache_driver_path() -> Path:
    return Path(__file__).resolve().parents[2] / "scripts" / "run_transvlm_cached.py"


def cache_signature_files() -> tuple[Path, ...]:
    return (cache_driver_path(), Path(__file__).resolve())


def parse_transition_output(path: Path) -> list[TransVLMTransition]:
    """Parse a previously successful official JSONL using the exact V5 parser contract."""

    return base._parse_output(Path(path))


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + ".tmp")
    temp.unlink(missing_ok=True)
    try:
        shutil.copy2(source, temp)
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)


def _official_profile_args() -> list[str]:
    p = TRANSVLM_RUNTIME_PROFILE
    args = [
        "--backend", str(p["backend"]),
        "--fps", str(p["fps"]),
        "--window-size", str(p["window_size"]),
        "--stride", str(p["stride"]),
        "--merge-eps", str(p["merge_eps"]),
        "--timestamp-format", str(p["timestamp_format"]),
        "--flow-codec", str(p["flow_codec"]),
        "--flow-viz-device", str(p["flow_viz_device"]),
        "--flow-mini-batch-size", str(p["flow_mini_batch_size"]),
        "--max-pixels-override", str(p["max_pixels_override"]),
        "--image-patch-size", str(p["image_patch_size"]),
        "--nframes-for-resize", str(p["nframes_for_resize"]),
        "--max-new-tokens", str(p["max_new_tokens"]),
    ]
    if p["strict_tail"]:
        args.append("--strict-tail")
    if not p["prefix_caching"]:
        args.append("--no-prefix-caching")
    return args


def detect_transition_segments(
    video_path: Path,
    work_dir: Path,
    progress: RuntimeProgress | None = None,
    *,
    model_rgb_path: Path | None = None,
    model_flow_path: Path | None = None,
    cache_rgb_path: Path | None = None,
    cache_flow_path: Path | None = None,
    output_cache_path: Path | None = None,
) -> list[TransVLMTransition]:
    """Run official TransVLM, optionally reusing/capturing exact RGB and flow artifacts.

    Modes:
    * no cached input: normal official source -> 25fps -> resize -> flow -> Qwen; capture RGB/flow;
    * RGB only: skip resample/resize, recompute flow in the official process, capture flow;
    * RGB + flow: skip resample/resize/NeuFlow and run only Qwen windows + merge.
    """

    status = base.runtime_status()
    if not status["ready"]:
        missing = "、".join(status["missing"])
        raise v2.MediaPipelineError(
            "TransVLM Runtime 尚未准备完成："
            f"{missing}。请先运行 scripts/setup_transvlm_runtime.ps1"
        )

    if model_flow_path is not None and model_rgb_path is None:
        raise ValueError("复用 Flow 时必须同时提供对应的 model RGB")

    config = base.runtime_config()
    driver = cache_driver_path()
    needs_capture_driver = cache_rgb_path is not None or cache_flow_path is not None
    if needs_capture_driver and not driver.is_file():
        raise v2.MediaPipelineError(f"TransVLM V5.1 缓存驱动缺失：{driver}")

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    output_jsonl = work_dir / "transvlm.jsonl"
    runtime_log = work_dir / "transvlm-runtime.log"
    temp_dir = work_dir / "tmp"
    output_jsonl.unlink(missing_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    input_video = Path(model_rgb_path) if model_rgb_path is not None else Path(video_path)
    runner = driver if needs_capture_driver else config.infer_script
    command = [str(config.python_executable), str(runner)]
    if needs_capture_driver:
        command += ["--ai-inference-root", str(config.inference_root)]
        if cache_rgb_path is not None:
            command += ["--ai-cache-rgb", str(cache_rgb_path)]
        if cache_flow_path is not None:
            command += ["--ai-cache-flow", str(cache_flow_path)]

    command += [
        "--video", str(input_video),
        "--ckpt-dir", str(config.checkpoint_dir),
        "--output-jsonl", str(output_jsonl),
        "--device", config.device,
        "--temp-dir", str(temp_dir),
        *_official_profile_args(),
    ]

    # A cached model RGB is already the official 25fps + smart-resize output.  Running those stages
    # again would be both wasteful and a different encode generation.
    if model_rgb_path is not None:
        command += ["--no-fps-resample", "--no-pre-resize"]
    if model_flow_path is not None:
        command += ["--flow", str(model_flow_path)]

    env = base._transvlm_subprocess_env(config)
    if progress is not None:
        mode = "RGB+Flow 缓存" if model_flow_path is not None else "RGB 缓存" if model_rgb_path is not None else "原片"
        progress(1.0, "transvlm", f"正在启动 TransVLM · {config.device} · {mode}", None, None)

    def on_line(line: str) -> None:
        if progress is None:
            return
        event = base._progress_from_log_line(line)
        if event is not None:
            progress(*event)

    try:
        return_code, output_tail = base._run_streaming_process(
            command,
            cwd=config.inference_root,
            env=env,
            log_path=runtime_log,
            on_line=on_line,
        )
    except FileNotFoundError as exc:
        raise v2.MediaPipelineError("TransVLM Python Runtime 不存在") from exc
    except subprocess.TimeoutExpired as exc:
        detail = base._error_tail(exc.stdout if isinstance(exc.stdout, str) else None, None)
        raise v2.MediaPipelineError("TransVLM 推理超时" + (f"：{detail}" if detail else "")) from exc
    except OSError as exc:
        raise v2.MediaPipelineError(f"TransVLM Runtime 启动失败：{exc}") from exc

    if return_code != 0:
        detail = base._error_tail(output_tail, None)
        raise v2.MediaPipelineError(
            "TransVLM 推理失败" + (f"：{detail}" if detail else f"，exit={return_code}")
        )

    if progress is not None:
        progress(99.0, "transvlm", "TransVLM 推理完成，正在解析转场区间", None, None)
    segments = base._parse_output(output_jsonl)

    # Raw window output is downstream of RGB/flow but upstream of our merged-transition cache.
    # Only publish it after the official process AND parser both succeeded.
    if output_cache_path is not None:
        _atomic_copy(output_jsonl, Path(output_cache_path))

    if progress is not None:
        progress(100.0, "transvlm", f"TransVLM 返回 {len(segments)} 个转场区间", len(segments), len(segments))
    return segments
