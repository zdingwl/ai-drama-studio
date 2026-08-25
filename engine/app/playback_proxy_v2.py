"""拉片工作台专用播放代理。

职责：把分析 Proxy 的视频流与原片/独立 WAV 的声音快速封装成浏览器播放用 MP4。
说明：分析 Proxy 继续服务 TransNetV2 / PTS，不被播放器逻辑改写。
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path

from engine.app.studio_v2 import get_episode_record

_FFMPEG_TIMEOUT_SECONDS = 60 * 60
_PLAYBACK_PROXY_LOCK = threading.RLock()


class PlaybackProxyError(RuntimeError):
    """播放代理生成失败。"""


def _run(command: list[str], *, timeout: int = _FFMPEG_TIMEOUT_SECONDS) -> subprocess.CompletedProcess[str]:
    """执行 FFmpeg/FFprobe，并把底层错误转换成中文业务错误。"""

    try:
        return subprocess.run(command, capture_output=True, text=True, check=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise PlaybackProxyError(f"找不到媒体工具：{command[0]}，请确认 FFmpeg/FFprobe 已加入 PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise PlaybackProxyError(f"媒体处理超时：{command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()[-2000:]
        raise PlaybackProxyError(f"播放代理生成失败：{detail or command[0]}") from exc


def _has_audio(path: Path) -> bool:
    """检查一个媒体文件是否真的包含音频流。"""

    result = _run([
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=index,codec_name", "-of", "json", str(path),
    ], timeout=10 * 60)
    payload = json.loads(result.stdout or "{}")
    return bool(payload.get("streams"))


def ensure_playback_proxy(episode_id: str) -> Path:
    """返回带声音的拉片播放器 MP4。

    输入：Episode ID。
    输出：``preprocess/playback-v2.mp4``（原片无音轨时退回分析 Proxy）。
    为什么：历史分析 Proxy 曾经是 video-only；浏览器又会缓存旧 MP4 的 stream layout。
    因此播放文件与分析文件彻底分离，并使用新的文件名生成，避免旧缓存和分析链路互相影响。
    """

    with _PLAYBACK_PROXY_LOCK:
        episode = get_episode_record(episode_id)
        if episode is None:
            raise LookupError("剧集不存在")

        preprocess = episode.preprocess
        if preprocess is None or preprocess.status != "READY" or not preprocess.proxy_path:
            raise PlaybackProxyError("当前剧集的分析视频尚未准备完成")

        analysis_proxy = Path(preprocess.proxy_path)
        if not analysis_proxy.is_file():
            raise PlaybackProxyError("分析 Proxy 不存在")

        source = Path(episode.source_path)
        if not source.is_file():
            raise PlaybackProxyError("原视频文件不存在")

        # 原片本身没有声音时，不伪造音轨，直接返回可播放的视频 Proxy。
        if not _has_audio(source):
            return analysis_proxy

        playback = analysis_proxy.with_name("playback-v2.mp4")
        if playback.is_file():
            try:
                if _has_audio(playback):
                    return playback
            except PlaybackProxyError:
                pass

        audio = Path(preprocess.audio_path) if preprocess.audio_path else None
        audio_input = audio if audio is not None and audio.is_file() else source
        temp = playback.with_name(".playback-v2.tmp.mp4")
        if temp.exists():
            temp.unlink(missing_ok=True)

        try:
            # 视频流直接 copy；只把声音编码成浏览器普遍支持的 AAC，所以生成很快。
            _run([
                "ffmpeg", "-y",
                "-i", str(analysis_proxy),
                "-i", str(audio_input),
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "160k",
                "-ac", "2",
                "-shortest",
                "-movflags", "+faststart",
                str(temp),
            ])
            if not temp.is_file() or temp.stat().st_size <= 0:
                raise PlaybackProxyError("播放代理文件没有成功生成")
            if not _has_audio(temp):
                raise PlaybackProxyError("播放代理生成完成但仍未检测到音轨")
            os.replace(temp, playback)
            return playback
        finally:
            if temp.exists():
                temp.unlink(missing_ok=True)
