"""Read-only resolver for the shot-workbench playback proxy.

GET requests must never remux media or create files.  Playback generation remains in
``playback_proxy_v2.ensure_playback_proxy`` and is exposed only through an explicit
write command.
"""
from __future__ import annotations

from pathlib import Path

from engine.app.playback_proxy_v2 import PlaybackProxyError, _has_audio, _is_fresh
from engine.app.studio_v2 import get_episode_record


def get_playback_proxy_read_only_v2(episode_id: str) -> Path:
    """Resolve an already usable playback file without creating or changing artifacts."""

    episode = get_episode_record(episode_id)
    if episode is None:
        raise LookupError("剧集不存在")

    preprocess = episode.preprocess
    if preprocess is None or preprocess.status != "READY" or not preprocess.proxy_path:
        raise PlaybackProxyError("当前剧集的分析视频尚未准备完成")

    analysis_proxy = Path(preprocess.proxy_path)
    if not analysis_proxy.is_file() or analysis_proxy.stat().st_size <= 0:
        raise PlaybackProxyError("分析 Proxy 不存在")

    source = Path(episode.source_path)
    if not source.is_file() or source.stat().st_size <= 0:
        raise PlaybackProxyError("原视频文件不存在")

    # A source without audio needs no remux; the analysis proxy is already the complete
    # playable representation for this episode.
    if not _has_audio(source):
        return analysis_proxy

    audio = Path(preprocess.audio_path) if preprocess.audio_path else None
    audio_input = audio if audio is not None and audio.is_file() and audio.stat().st_size > 0 else source
    playback = analysis_proxy.with_name("playback-v2.mp4")
    if not _is_fresh(playback, analysis_proxy, audio_input):
        raise PlaybackProxyError("播放代理尚未准备或已经过期，请显式重新准备播放代理")
    if not _has_audio(playback):
        raise PlaybackProxyError("现有播放代理缺少音轨，请显式重新准备播放代理")
    return playback


__all__ = ["get_playback_proxy_read_only_v2"]
