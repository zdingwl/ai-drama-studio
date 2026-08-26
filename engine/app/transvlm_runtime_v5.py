"""02 拉片 V5：TransVLM 独立 Runtime 适配器。

职责：
- 不把 TransVLM 的 Python 3.12 / torch 2.9.1 / cuDNN 9.16+ 依赖塞进主工程 .venv；
- 默认从 ``.runtime/TransVLM/inference`` 调官方 ``infer_video.py``；
- 使用官方 HuggingFace backend，读取 transition segments；
- Windows 下显式注入 TorchCodec 所需的 FFmpeg shared-build ``bin``；
- 实时读取官方 infer_video 日志，把 resample / resize / NeuFlow / window inference
  回传给业务 Task，避免整段推理期间 UI 长时间停在同一个百分比；
- 与官方 parser 语义保持一致：允许 ``start_time == end_time`` 的零长度 hard cut，
  ``end_time < start_time`` 时交换两端而不是丢弃；
- 运行失败时把 stderr/stdout 尾部转换为稳定的 MediaPipelineError；
- 只接受本地已准备好的 Runtime / checkpoint，不在正式拉片过程中静默安装依赖。

可覆盖环境变量：
- AI_DRAMA_TRANSVLM_INFERENCE
- AI_DRAMA_TRANSVLM_PYTHON
- AI_DRAMA_TRANSVLM_CKPT
- AI_DRAMA_TRANSVLM_DEVICE
- AI_DRAMA_TRANSVLM_FFMPEG_BIN
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
from typing import Any, Callable

from engine.app import media_v2 as v2

TRANSVLM_TIMEOUT_SECONDS = 4 * 60 * 60
RuntimeProgress = Callable[[float, str, str, int | None, int | None], None]
_WINDOW_LOG_RE = re.compile(r"\[window\s+(\d+)/(\d+)\]")
_WINDOWS_PLAN_RE = re.compile(r"->\s*(\d+)\s+window\(s\)")


@dataclass(frozen=True)
class TransVLMRuntimeConfig:
    inference_root: Path
    python_executable: Path
    checkpoint_dir: Path
    infer_script: Path
    device: str
    ffmpeg_shared_bin: Path | None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in (
            "inference_root",
            "python_executable",
            "checkpoint_dir",
            "infer_script",
            "ffmpeg_shared_bin",
        ):
            value = payload[key]
            payload[key] = str(value) if value is not None else None
        return payload


@dataclass(frozen=True)
class TransVLMTransition:
    start_us: int
    end_us: int

    @property
    def duration_us(self) -> int:
        return self.end_us - self.start_us


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _configured_shared_ffmpeg_bin(inference_root: Path) -> Path | None:
    override = os.environ.get("AI_DRAMA_TRANSVLM_FFMPEG_BIN")
    if override:
        return Path(override).expanduser()

    marker = inference_root.parent / "ffmpeg_shared_bin.txt"
    if not marker.is_file():
        return None
    try:
        value = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return Path(value).expanduser() if value else None


def _is_windows_shared_ffmpeg_bin(path: Path | None) -> bool:
    if path is None or not path.is_dir():
        return False
    if not (path / "ffmpeg.exe").is_file():
        return False
    required = ("avcodec-*.dll", "avformat-*.dll", "avutil-*.dll")
    return all(any(path.glob(pattern)) for pattern in required)


def runtime_config() -> TransVLMRuntimeConfig:
    repo_root = _repo_root()
    default_inference = repo_root / ".runtime" / "TransVLM" / "inference"
    inference_root = Path(os.environ.get("AI_DRAMA_TRANSVLM_INFERENCE", str(default_inference))).expanduser()

    if os.name == "nt":
        default_python = inference_root / ".venv" / "Scripts" / "python.exe"
    else:
        default_python = inference_root / ".venv" / "bin" / "python"

    python_executable = Path(os.environ.get("AI_DRAMA_TRANSVLM_PYTHON", str(default_python))).expanduser()
    checkpoint_dir = Path(
        os.environ.get(
            "AI_DRAMA_TRANSVLM_CKPT",
            str(inference_root / "pretrained" / "TransVLM-v1"),
        )
    ).expanduser()
    return TransVLMRuntimeConfig(
        inference_root=inference_root,
        python_executable=python_executable,
        checkpoint_dir=checkpoint_dir,
        infer_script=inference_root / "infer_video.py",
        device=os.environ.get("AI_DRAMA_TRANSVLM_DEVICE", "cuda:0"),
        ffmpeg_shared_bin=_configured_shared_ffmpeg_bin(inference_root),
    )


def runtime_status() -> dict[str, Any]:
    config = runtime_config()
    missing: list[str] = []
    if not config.inference_root.is_dir():
        missing.append("official inference repository")
    if not config.python_executable.is_file():
        missing.append("Python 3.12 TransVLM venv")
    if not config.infer_script.is_file():
        missing.append("infer_video.py")
    if not config.checkpoint_dir.is_dir():
        missing.append("TransVLM checkpoint")
    elif not (config.checkpoint_dir / "config.json").is_file():
        missing.append("checkpoint config.json")
    if os.name == "nt" and not _is_windows_shared_ffmpeg_bin(config.ffmpeg_shared_bin):
        missing.append("FFmpeg shared runtime for TorchCodec")

    return {
        "ready": not missing,
        "profile": "TransVLM-Qwen3-VL-4B-Instruct",
        "backend": "hf",
        "device": config.device,
        "missing": missing,
        "config": config.to_dict(),
    }


def _transvlm_subprocess_env(config: TransVLMRuntimeConfig) -> dict[str, str]:
    env = os.environ.copy()
    # 模型与 NeuFlow 权重必须在 setup 阶段准备；正式业务 Run 禁止静默联网改变运行状态。
    env.setdefault("HF_HUB_OFFLINE", "1")
    env.setdefault("TRANSFORMERS_OFFLINE", "1")

    if os.name == "nt":
        shared = config.ffmpeg_shared_bin
        if not _is_windows_shared_ffmpeg_bin(shared):
            raise v2.MediaPipelineError(
                "TransVLM Windows Runtime 缺少 TorchCodec 所需的 FFmpeg shared DLL。"
                "请重新运行 scripts/setup_transvlm_runtime.ps1"
            )
        torch_lib = config.inference_root / ".venv" / "Lib" / "site-packages" / "torch" / "lib"
        prefixes = [str(shared)]
        if torch_lib.is_dir():
            prefixes.append(str(torch_lib))
        existing = env.get("PATH", "")
        env["PATH"] = os.pathsep.join(prefixes + ([existing] if existing else []))
    return env


def _error_tail(stdout: str | None, stderr: str | None, limit: int = 5000) -> str:
    text = "\n".join(part.strip() for part in (stdout or "", stderr or "") if part and part.strip())
    return text[-limit:] if text else ""


def _progress_from_log_line(line: str) -> tuple[float, str, str, int | None, int | None] | None:
    """把官方 infer_video.py 的稳定日志转换为 Runtime 内部真实阶段进度。

    这里不伪造 NeuFlow 的逐 batch 百分比：官方 whole-video flow 在该阶段没有逐 batch
    进度日志，所以只明确告诉 UI 当前正在做整集光流。进入 ``[windows]`` 后说明光流已完成，
    再使用官方 ``[window x/N]`` 日志提供可验证的连续 Qwen3-VL 推理进度。
    """

    text = line.strip()
    if not text:
        return None
    if "[resample]" in text:
        return 5.0, "transvlm", "TransVLM 正在准备 25fps 模型输入", None, None
    if "[resize]" in text:
        return 10.0, "transvlm", "TransVLM 正在缩放模型输入视频", None, None
    if "[flow] computing whole-video NeuFlow" in text:
        return (
            15.0,
            "transvlm",
            "NeuFlow 正在计算整集光流；该阶段会大量占用内存/磁盘，期间百分比可能暂时不连续更新",
            None,
            None,
        )
    if "[windows]" in text:
        match = _WINDOWS_PLAN_RE.search(text)
        total = int(match.group(1)) if match else None
        message = f"NeuFlow 已完成，准备 {total} 个 Qwen3-VL 推理窗口" if total else "NeuFlow 已完成，正在准备 Qwen3-VL 推理窗口"
        return 55.0, "transvlm", message, 0 if total else None, total

    match = _WINDOW_LOG_RE.search(text)
    if match:
        current = int(match.group(1))
        total = max(1, int(match.group(2)))
        ratio = max(0.0, min(1.0, current / total))
        percent = 55.0 + ratio * 43.0
        return percent, "transvlm", f"Qwen3-VL 正在分析 Shot Transition 窗口 {current} / {total}", current, total

    if "Done in " in text and "failed" in text:
        return 99.0, "transvlm", "TransVLM 模型推理完成，正在读取并合并转场结果", None, None
    return None


def _run_streaming_process(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log_path: Path,
    on_line: Callable[[str], None] | None = None,
) -> tuple[int, str]:
    """实时消费 TransVLM stdout/stderr，避免 capture_output 让业务层整段失去进度。

    stderr 合并到 stdout，因为官方 logging 默认写 stderr；JSONL 结果本身写到独立文件，不依赖 stdout。
    使用 reader thread + Queue，既能逐行消费，又能在官方进程完全无输出时仍执行 4 小时超时检查。
    """

    try:
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except FileNotFoundError:
        raise
    except OSError:
        raise

    output_queue: queue.Queue[str | None] = queue.Queue()

    def reader() -> None:
        assert process.stdout is not None
        try:
            for raw_line in process.stdout:
                output_queue.put(raw_line)
        finally:
            output_queue.put(None)

    thread = threading.Thread(target=reader, name="transvlm-log-reader", daemon=True)
    thread.start()
    deadline = time.monotonic() + TRANSVLM_TIMEOUT_SECONDS
    tail_lines: deque[str] = deque(maxlen=240)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with log_path.open("w", encoding="utf-8", errors="replace") as log_file:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                tail = "\n".join(tail_lines)
                raise subprocess.TimeoutExpired(command, TRANSVLM_TIMEOUT_SECONDS, output=tail)

            try:
                item = output_queue.get(timeout=min(1.0, remaining))
            except queue.Empty:
                if process.poll() is not None and not thread.is_alive():
                    break
                continue

            if item is None:
                break

            line = item.rstrip("\r\n")
            log_file.write(item)
            log_file.flush()
            if line:
                tail_lines.append(line)
                if on_line is not None:
                    on_line(line)

    return_code = process.wait(timeout=max(1.0, deadline - time.monotonic()))
    return return_code, "\n".join(tail_lines)


def _parse_output(path: Path) -> list[TransVLMTransition]:
    """读取官方 infer_video JSONL，并保留官方 SegmentPrediction 的时间语义。

    官方 ``parse_model_output`` 只会修正 ``end < start``，不会丢弃 ``end == start``。
    零长度 segment 对 hard cut 很重要：模型可能把单帧切点表达为同一个 start/end 时间。
    """

    if not path.is_file():
        raise v2.MediaPipelineError("TransVLM 推理完成但没有生成 output JSONL")

    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise v2.MediaPipelineError("TransVLM output JSONL 损坏") from exc
        if isinstance(value, dict):
            records.append(value)
    if not records:
        raise v2.MediaPipelineError("TransVLM 没有返回任何视频结果")

    raw_segments = records[-1].get("segments")
    if raw_segments is None:
        raise v2.MediaPipelineError("TransVLM output 缺少 segments")
    if not isinstance(raw_segments, list):
        raise v2.MediaPipelineError("TransVLM segments 格式无效")

    segments: list[TransVLMTransition] = []
    for item in raw_segments:
        if not isinstance(item, dict):
            continue
        try:
            start_us = int(round(float(item["start_time"]) * 1_000_000))
            end_us = int(round(float(item["end_time"]) * 1_000_000))
        except (KeyError, TypeError, ValueError):
            continue

        # 与 TransVLM 官方 parser.py 保持一致：反向区间交换，零长度 hard cut 保留。
        if end_us < start_us:
            start_us, end_us = end_us, start_us
        start_us = max(0, start_us)
        end_us = max(0, end_us)
        segments.append(TransVLMTransition(start_us=start_us, end_us=end_us))

    segments.sort(key=lambda item: (item.start_us, item.end_us))
    deduped: list[TransVLMTransition] = []
    for item in segments:
        if deduped and item.start_us == deduped[-1].start_us and item.end_us == deduped[-1].end_us:
            continue
        deduped.append(item)
    return deduped


def detect_transition_segments(
    video_path: Path,
    work_dir: Path,
    progress: RuntimeProgress | None = None,
) -> list[TransVLMTransition]:
    """调用官方 TransVLM whole-video inference，并返回 Source timeline transition spans。"""

    status = runtime_status()
    if not status["ready"]:
        missing = "、".join(status["missing"])
        raise v2.MediaPipelineError(
            "TransVLM Runtime 尚未准备完成："
            f"{missing}。请先运行 scripts/setup_transvlm_runtime.ps1"
        )

    config = runtime_config()
    work_dir.mkdir(parents=True, exist_ok=True)
    output_jsonl = work_dir / "transvlm.jsonl"
    runtime_log = work_dir / "transvlm-runtime.log"
    temp_dir = work_dir / "tmp"
    output_jsonl.unlink(missing_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    command = [
        str(config.python_executable),
        str(config.infer_script),
        "--video", str(video_path),
        "--ckpt-dir", str(config.checkpoint_dir),
        "--output-jsonl", str(output_jsonl),
        "--backend", "hf",
        "--device", config.device,
        "--temp-dir", str(temp_dir),
    ]
    env = _transvlm_subprocess_env(config)

    if progress is not None:
        progress(1.0, "transvlm", f"正在启动 TransVLM · {config.device}", None, None)

    def on_line(line: str) -> None:
        if progress is None:
            return
        event = _progress_from_log_line(line)
        if event is not None:
            progress(*event)

    try:
        return_code, output_tail = _run_streaming_process(
            command,
            cwd=config.inference_root,
            env=env,
            log_path=runtime_log,
            on_line=on_line,
        )
    except FileNotFoundError as exc:
        raise v2.MediaPipelineError("TransVLM Python Runtime 不存在") from exc
    except subprocess.TimeoutExpired as exc:
        detail = _error_tail(exc.stdout if isinstance(exc.stdout, str) else None, None)
        raise v2.MediaPipelineError(
            "TransVLM 推理超时" + (f"：{detail}" if detail else "")
        ) from exc
    except OSError as exc:
        raise v2.MediaPipelineError(f"TransVLM Runtime 启动失败：{exc}") from exc

    if return_code != 0:
        detail = _error_tail(output_tail, None)
        raise v2.MediaPipelineError(
            "TransVLM 推理失败" + (f"：{detail}" if detail else f"，exit={return_code}")
        )

    if progress is not None:
        progress(99.0, "transvlm", "TransVLM 推理完成，正在解析转场区间", None, None)
    segments = _parse_output(output_jsonl)
    if progress is not None:
        progress(100.0, "transvlm", f"TransVLM 返回 {len(segments)} 个转场区间", len(segments), len(segments))
    return segments
