"""02 拉片 V5：TransVLM 独立 Runtime 适配器。

职责：
- 不把 TransVLM 的 Python 3.12 / torch 2.9.1 / cuDNN 9.16+ 依赖塞进主工程 .venv；
- 默认从 ``.runtime/TransVLM/inference`` 调官方 ``infer_video.py``；
- 使用官方 HuggingFace backend，读取 transition segments；
- 与官方 parser 语义保持一致：允许 ``start_time == end_time`` 的零长度 hard cut，
  ``end_time < start_time`` 时交换两端而不是丢弃；
- 运行失败时把 stderr/stdout 尾部转换为稳定的 MediaPipelineError；
- 只接受本地已准备好的 Runtime / checkpoint，不在正式拉片过程中静默安装依赖。

可覆盖环境变量：
- AI_DRAMA_TRANSVLM_INFERENCE
- AI_DRAMA_TRANSVLM_PYTHON
- AI_DRAMA_TRANSVLM_CKPT
- AI_DRAMA_TRANSVLM_DEVICE
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import subprocess
from typing import Any

from engine.app import media_v2 as v2

TRANSVLM_TIMEOUT_SECONDS = 4 * 60 * 60


@dataclass(frozen=True)
class TransVLMRuntimeConfig:
    inference_root: Path
    python_executable: Path
    checkpoint_dir: Path
    infer_script: Path
    device: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("inference_root", "python_executable", "checkpoint_dir", "infer_script"):
            payload[key] = str(payload[key])
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

    return {
        "ready": not missing,
        "profile": "TransVLM-Qwen3-VL-4B-Instruct",
        "backend": "hf",
        "device": config.device,
        "missing": missing,
        "config": config.to_dict(),
    }


def _error_tail(stdout: str | None, stderr: str | None, limit: int = 5000) -> str:
    text = "\n".join(part.strip() for part in (stdout or "", stderr or "") if part and part.strip())
    return text[-limit:] if text else ""


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


def detect_transition_segments(video_path: Path, work_dir: Path) -> list[TransVLMTransition]:
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
    env = os.environ.copy()
    # 模型与 NeuFlow 权重必须在 setup 阶段准备；正式业务 Run 禁止静默联网改变运行状态。
    env.setdefault("HF_HUB_OFFLINE", "1")
    env.setdefault("TRANSFORMERS_OFFLINE", "1")

    try:
        completed = subprocess.run(
            command,
            cwd=str(config.inference_root),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TRANSVLM_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        raise v2.MediaPipelineError("TransVLM Python Runtime 不存在") from exc
    except subprocess.TimeoutExpired as exc:
        detail = _error_tail(exc.stdout, exc.stderr)
        raise v2.MediaPipelineError(
            "TransVLM 推理超时" + (f"：{detail}" if detail else "")
        ) from exc
    except OSError as exc:
        raise v2.MediaPipelineError(f"TransVLM Runtime 启动失败：{exc}") from exc

    if completed.returncode != 0:
        detail = _error_tail(completed.stdout, completed.stderr)
        raise v2.MediaPipelineError(
            "TransVLM 推理失败" + (f"：{detail}" if detail else f"，exit={completed.returncode}")
        )
    return _parse_output(output_jsonl)
