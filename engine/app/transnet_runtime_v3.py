"""TransNetV2 稳定视频解码入口。

职责：
- 不调用 transnetv2-pytorch 自带的 ``predict_video`` ffmpeg-python 黑盒；
- 使用项目统一的系统 FFmpeg 把 Proxy 解码为 TransNetV2 要求的 48x27 RGB24；
- 将帧直接交给官方 ``model.predict_frames``，不改变模型推理和 Shot 阈值；
- FFmpeg 失败时把真正 stderr 转换成中文业务错误，任务栏能直接看到原因。

为什么：transnetv2-pytorch 1.0.5 的 predict_video 会捕获 stderr，但 ffmpeg-python
异常字符串只显示 ``ffmpeg error (see stderr output for detail)``，Windows 上排错完全不可见。
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

TRANSNET_WIDTH = 48
TRANSNET_HEIGHT = 27
TRANSNET_CHANNELS = 3
TRANSNET_FRAME_BYTES = TRANSNET_WIDTH * TRANSNET_HEIGHT * TRANSNET_CHANNELS
TRANSNET_DECODE_TIMEOUT_SECONDS = 60 * 60


class TransNetRuntimeError(RuntimeError):
    """TransNetV2 输入解码 / 推理准备错误。"""


def _decode_text(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _stderr_tail(value: bytes | str | None, limit: int = 4000) -> str:
    text = _decode_text(value).strip()
    return text[-limit:] if text else ""


def decode_transnet_frames(video_path: Path) -> bytes:
    """把 Proxy 解码成连续 RGB24 原始帧。

    输入：已经完成预处理的 Proxy。
    输出：48x27 RGB24 rawvideo bytes。
    为什么：使用参数列表直接启动系统 FFmpeg，避免 ffmpeg-python 在 Windows 路径/
    子进程失败时吞掉真正 stderr。
    """

    command = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel", "error",
        "-i", str(video_path),
        "-map", "0:v:0",
        "-vf", f"scale={TRANSNET_WIDTH}:{TRANSNET_HEIGHT}",
        "-pix_fmt", "rgb24",
        "-f", "rawvideo",
        "pipe:1",
    ]
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=TRANSNET_DECODE_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise TransNetRuntimeError("TransNetV2 解码失败：找不到 FFmpeg，请确认 ffmpeg 已加入 PATH") from exc
    except subprocess.TimeoutExpired as exc:
        detail = _stderr_tail(exc.stderr)
        raise TransNetRuntimeError(
            f"TransNetV2 解码超时{f'：{detail}' if detail else ''}"
        ) from exc

    if result.returncode != 0:
        detail = _stderr_tail(result.stderr)
        raise TransNetRuntimeError(
            "TransNetV2 输入视频 FFmpeg 解码失败："
            + (detail or f"FFmpeg exit code {result.returncode}")
        )
    if not result.stdout:
        raise TransNetRuntimeError("TransNetV2 输入视频 FFmpeg 解码失败：没有输出任何视频帧")
    if len(result.stdout) % TRANSNET_FRAME_BYTES != 0:
        raise TransNetRuntimeError(
            "TransNetV2 输入帧数据不完整："
            f"raw bytes={len(result.stdout)}，frame bytes={TRANSNET_FRAME_BYTES}"
        )
    return result.stdout


def predict_single_frame_scores(model: Any, video_path: Path) -> Any:
    """系统 FFmpeg 解码 + 官方 TransNetV2 predict_frames。

    输出保持官方 single-frame prediction Tensor；调用方继续使用原有阈值、PTS 映射和
    Revision 安全切换逻辑。
    """

    try:
        import numpy as np
        import torch
    except ImportError as exc:
        raise TransNetRuntimeError("TransNetV2 本地依赖不完整，请重新安装 engine/requirements.txt") from exc

    raw = decode_transnet_frames(video_path)
    array = np.frombuffer(raw, dtype=np.uint8).reshape(
        (-1, TRANSNET_HEIGHT, TRANSNET_WIDTH, TRANSNET_CHANNELS)
    )
    # frombuffer 的数组只读；官方实现同样会复制一份再送入 torch。
    video = torch.from_numpy(np.array(array, copy=True)).to(getattr(model, "device", "cpu"))
    try:
        with torch.no_grad():
            try:
                single_frame, _all_frames = model.predict_frames(video, quiet=True)
            except TypeError:
                # 保留对旧 TransNetV2 wrapper 的兼容。
                single_frame, _all_frames = model.predict_frames(video)
    except Exception as exc:
        raise TransNetRuntimeError(f"TransNetV2 模型推理失败：{exc}") from exc
    return single_frame
