"""V2 本地媒体流水线：视频预处理 + 自动切镜和 Reference Clip 生成。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable

from engine.app.shot_revision_v2 import commit_auto_shot_revision
from engine.app.studio_v2 import episode_dir, get_episode_record, new_id, upsert_preprocess

FFMPEG_TIMEOUT_SECONDS = 60 * 60
SHOT_THRESHOLD = 0.5
MIN_SHOT_DURATION_US = 120_000

# percent, stage_key, message, current, total
ProgressReporter = Callable[[float, str, str, int | None, int | None], None]
_PLAYABLE_PROXY_LOCK = threading.RLock()


class MediaPipelineError(RuntimeError):
    pass


def _report(
    reporter: ProgressReporter | None,
    percent: float,
    stage_key: str,
    message: str,
    current: int | None = None,
    total: int | None = None,
) -> None:
    if reporter is not None:
        reporter(max(0.0, min(100.0, float(percent))), stage_key, message, current, total)


def _run(command: list[str], *, timeout: int = FFMPEG_TIMEOUT_SECONDS) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, capture_output=True, text=True, check=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise MediaPipelineError(f"找不到媒体工具：{command[0]}，请确认 FFmpeg/FFprobe 已加入 PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaPipelineError(f"媒体处理超时：{command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()[-2000:]
        raise MediaPipelineError(f"媒体处理失败：{detail or command[0]}") from exc


def _ratio(value: str | None) -> float | None:
    if not value or value in {"0/0", "N/A"}:
        return None
    try:
        if "/" in value:
            numerator, denominator = value.split("/", 1)
            den = float(denominator)
            return float(numerator) / den if den else None
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def probe_media(path: Path) -> dict[str, Any]:
    result = _run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], timeout=10 * 60)
    payload = json.loads(result.stdout)
    streams = payload.get("streams") or []
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    if not video:
        raise MediaPipelineError("导入文件没有可用视频流")
    raw_duration = video.get("duration") or (payload.get("format") or {}).get("duration")
    try:
        duration_us = int(round(float(raw_duration) * 1_000_000))
    except (TypeError, ValueError) as exc:
        raise MediaPipelineError("无法读取视频时长") from exc
    if duration_us <= 0:
        raise MediaPipelineError("视频时长无效")
    return {
        "duration_us": duration_us,
        "width": int(video.get("width") or 0) or None,
        "height": int(video.get("height") or 0) or None,
        "fps": _ratio(video.get("avg_frame_rate") or video.get("r_frame_rate")),
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name") if audio else None,
        "has_audio": audio is not None,
    }


def ensure_playable_proxy(episode_id: str) -> Path:
    """确保整集拉片播放器拿到带原声的 Proxy。

    输入：Episode ID；输出：可直接给浏览器播放的 Proxy 路径。
    为什么：历史 V2 Proxy 曾使用 ``-an`` 生成无声视频。旧项目已有独立 audio.wav，
    因此这里只需把现有 H.264 视频流原样复制并重新封装 AAC 音频，不必重跑镜头检测或重编码视频。
    修复通过临时文件 + os.replace 原子替换；之后该 Episode 永久复用修复后的 Proxy。
    """

    with _PLAYABLE_PROXY_LOCK:
        episode = get_episode_record(episode_id)
        if episode is None:
            raise LookupError("剧集不存在")
        preprocess = episode.preprocess
        if preprocess is None or preprocess.status != "READY" or not preprocess.proxy_path:
            raise MediaPipelineError("当前剧集的分析视频尚未准备完成")

        proxy = Path(preprocess.proxy_path)
        if not proxy.is_file():
            raise MediaPipelineError("分析视频不存在")
        proxy_info = probe_media(proxy)
        if proxy_info["has_audio"]:
            return proxy

        source = Path(episode.source_path)
        if not source.is_file():
            raise MediaPipelineError("原视频文件不存在")
        source_info = probe_media(source)
        if not source_info["has_audio"]:
            return proxy

        audio = Path(preprocess.audio_path) if preprocess.audio_path else None
        audio_input = audio if audio is not None and audio.is_file() else source
        temp = proxy.with_name(f".{proxy.stem}.audio-repair.tmp.mp4")
        if temp.exists():
            temp.unlink()
        try:
            _run([
                "ffmpeg", "-y",
                "-i", str(proxy),
                "-i", str(audio_input),
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "160k", "-ac", "2",
                "-movflags", "+faststart",
                str(temp),
            ])
            repaired = probe_media(temp)
            if not repaired["has_audio"]:
                raise MediaPipelineError("修复后的 Proxy 仍未检测到音轨")
            os.replace(temp, proxy)
            return proxy
        finally:
            if temp.exists():
                temp.unlink(missing_ok=True)


def preprocess_episode(episode_id: str, progress: ProgressReporter | None = None) -> dict[str, Any]:
    """生成播放/分析共用 Proxy 与独立 Audio，并向调用方报告真实阶段进度。"""

    episode = get_episode_record(episode_id)
    if episode is None:
        raise LookupError("剧集不存在")
    source = Path(episode.source_path)
    if not source.is_file():
        raise MediaPipelineError("原视频文件不存在")

    root = episode_dir(episode.project_id, episode.id) / "preprocess"
    root.mkdir(parents=True, exist_ok=True)
    proxy = root / "proxy.mp4"
    audio = root / "audio.wav"

    upsert_preprocess(episode_id=episode_id, status="PROCESSING")
    try:
        _report(progress, 5, "probe", "正在读取媒体信息")
        info = probe_media(source)

        _report(progress, 15, "proxy", "正在生成带原声的分析 Proxy")
        _run([
            "ffmpeg", "-y", "-i", str(source),
            "-map", "0:v:0", "-map", "0:a:0?",
            "-vf", "scale='min(1280,iw)':-2,fps=25",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-ac", "2",
            "-movflags", "+faststart",
            "-avoid_negative_ts", "make_zero", str(proxy),
        ])
        _report(progress, 70, "proxy", "带原声 Proxy 已生成")

        if info["has_audio"]:
            _report(progress, 75, "audio", "正在提取独立音轨")
            _run([
                "ffmpeg", "-y", "-i", str(source), "-map", "0:a:0",
                "-vn", "-ac", "2", "-ar", "48000", "-c:a", "pcm_s16le", str(audio),
            ])
        elif audio.exists():
            audio.unlink()
        _report(progress, 92, "persist", "正在保存预处理结果")

        upsert_preprocess(
            episode_id=episode_id,
            status="READY",
            proxy_path=str(proxy),
            audio_path=str(audio) if audio.exists() else None,
            media_info=info,
        )
        _report(progress, 100, "ready", "视频初始化完成")
        return info | {"proxy_path": str(proxy), "audio_path": str(audio) if audio.exists() else None}
    except Exception as exc:
        upsert_preprocess(episode_id=episode_id, status="FAILED", error_message=str(exc))
        raise


def _frame_pts_us(proxy_path: Path) -> tuple[int, ...]:
    result = _run([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_frames",
        "-show_entries", "frame=best_effort_timestamp_time,pts_time", "-of", "json", str(proxy_path),
    ], timeout=30 * 60)
    payload = json.loads(result.stdout)
    pts: list[int] = []
    for frame in payload.get("frames") or []:
        raw = frame.get("best_effort_timestamp_time") or frame.get("pts_time")
        if raw not in (None, "N/A", ""):
            pts.append(int(round(float(raw) * 1_000_000)))
    if not pts:
        raise MediaPipelineError("FFprobe 没有返回代理视频帧时间")
    return tuple(pts)


def _transnet_cut_points(proxy_path: Path, frame_pts: tuple[int, ...]) -> list[int]:
    try:
        import numpy as np
        import torch
        import transnetv2_pytorch
        from transnetv2_pytorch import TransNetV2
    except ImportError as exc:
        raise MediaPipelineError("未安装 TransNetV2 本地依赖，请执行 pip install -r engine/requirements.txt") from exc

    package_root = Path(transnetv2_pytorch.__file__).resolve().parent
    candidates = [
        package_root / "transnetv2-pytorch-weights.pth",
        package_root / "weights" / "transnetv2-pytorch-weights.pth",
    ]
    weights_path = next((path for path in candidates if path.is_file()), None)
    if weights_path is None:
        raise MediaPipelineError("TransNetV2 权重文件缺失")

    model = TransNetV2(device="auto")
    try:
        state_dict = torch.load(weights_path, map_location=getattr(model, "device", "cpu"), weights_only=True)
    except TypeError:
        state_dict = torch.load(weights_path, map_location=getattr(model, "device", "cpu"))
    model.load_state_dict(state_dict)
    model.eval()
    with torch.no_grad():
        _, raw_scores, _ = model.predict_video(str(proxy_path))
    if hasattr(raw_scores, "detach"):
        raw_scores = raw_scores.detach().cpu().numpy()
    scores = np.asarray(raw_scores, dtype=np.float64).reshape(-1)
    if len(scores) != len(frame_pts):
        raise MediaPipelineError(f"TransNetV2 帧数 {len(scores)} 与 FFprobe 帧数 {len(frame_pts)} 不一致")

    cuts: list[int] = []
    index = 0
    while index < len(scores):
        if float(scores[index]) <= SHOT_THRESHOLD:
            index += 1
            continue
        while index + 1 < len(scores) and float(scores[index + 1]) > SHOT_THRESHOLD:
            index += 1
        next_index = index + 1
        if next_index < len(frame_pts):
            cuts.append(frame_pts[next_index])
        index += 1
    return cuts


def _normalize_boundaries(duration_us: int, cuts: list[int]) -> list[int]:
    clean: list[int] = [0]
    for value in sorted(set(cuts)):
        if value <= 0 or value >= duration_us:
            continue
        if value - clean[-1] < MIN_SHOT_DURATION_US:
            continue
        clean.append(value)
    if duration_us - clean[-1] < MIN_SHOT_DURATION_US and len(clean) > 1:
        clean.pop()
    clean.append(duration_us)
    return clean


def _render_reference(source: Path, output: Path, start_us: int, duration_us: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-ss", f"{start_us / 1_000_000:.6f}", "-i", str(source),
        "-t", f"{duration_us / 1_000_000:.6f}", "-map", "0:v:0", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output),
    ])


def _render_thumbnail(reference: Path, output: Path, duration_us: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    midpoint_s = max(0.0, duration_us / 2_000_000)
    _run([
        "ffmpeg", "-y", "-ss", f"{midpoint_s:.6f}", "-i", str(reference),
        "-frames:v", "1", "-vf", "scale='min(640,iw)':-2", "-q:v", "2", str(output),
    ], timeout=10 * 60)


def detect_episode_shots(episode_id: str, progress: ProgressReporter | None = None) -> list[dict[str, Any]]:
    """安全自动拉片：先完整生成新 Run，成功后才原子切换 Current Revision。

    重新拉片期间旧 Shot / Reference Clip 始终保持可读。TransNetV2、FFmpeg 或数据库任一步失败，
    旧 Current 不变；只清理本次尚未提交的临时 Run 目录。
    """

    episode = get_episode_record(episode_id)
    if episode is None:
        raise LookupError("剧集不存在")
    if episode.preprocess is None or episode.preprocess.status != "READY" or not episode.preprocess.proxy_path:
        raise MediaPipelineError("请先完成该剧集的视频预处理")
    source = Path(episode.source_path)
    proxy = Path(episode.preprocess.proxy_path)
    if not source.is_file() or not proxy.is_file():
        raise MediaPipelineError("原视频或代理视频文件缺失")

    _report(progress, 3, "probe", "正在读取原片时长")
    info = probe_media(source)
    duration_us = int(info["duration_us"])

    _report(progress, 8, "frame_pts", "正在读取 FFprobe 真实逐帧 PTS")
    frame_pts = _frame_pts_us(proxy)

    _report(progress, 15, "transnet", "TransNetV2 正在检测镜头边界")
    cuts = _transnet_cut_points(proxy, frame_pts)

    _report(progress, 24, "boundaries", "正在整理 Cut 与 Shot 边界")
    boundaries = _normalize_boundaries(duration_us, cuts)

    run_id = new_id("SHOTRUN")
    run_root = episode_dir(episode.project_id, episode.id) / "shots" / "runs" / run_id
    refs = run_root / "reference"
    thumbs = run_root / "thumbnails"
    refs.mkdir(parents=True, exist_ok=True)
    thumbs.mkdir(parents=True, exist_ok=True)

    payloads: list[dict[str, Any]] = []
    total_shots = max(1, len(boundaries) - 1)
    try:
        for index, (start_us, end_us) in enumerate(zip(boundaries, boundaries[1:]), start=1):
            duration = end_us - start_us
            reference = refs / f"shot_{index:04d}.mp4"
            thumbnail = thumbs / f"shot_{index:04d}.jpg"
            progress_percent = 25 + ((index - 1) / total_shots) * 70
            _report(progress, progress_percent, "reference_clips", f"正在生成 Reference Clip {index} / {total_shots}", index, total_shots)
            _render_reference(source, reference, start_us, duration)
            _render_thumbnail(reference, thumbnail, duration)
            payloads.append({
                "ordinal": index,
                "start_us": start_us,
                "end_us": end_us,
                "duration_us": duration,
                "reference_clip_path": str(reference),
                "thumbnail_path": str(thumbnail) if thumbnail.exists() else None,
                "keyframes_json": json.dumps([{"kind": "middle", "path": str(thumbnail)}], ensure_ascii=False),
                "short_description": None,
                "shot_type": None,
                "camera_motion": None,
                "status": "READY",
            })
            _report(progress, 25 + (index / total_shots) * 70, "reference_clips", f"已生成 {index} / {total_shots} 个 Reference Clip", index, total_shots)

        _report(progress, 97, "persist", "新拉片结果已完整生成，正在安全切换 Current Revision", total_shots, total_shots)
        result = commit_auto_shot_revision(episode_id, payloads, note=f"自动拉片 {run_id}")
        _report(progress, 100, "ready", f"拉片完成：{len(result)} Shots", len(result), len(result))
        return result
    except Exception:
        # 只有尚未进入 Current 的本次 Run 才允许清理；历史 Revision 的媒体目录永不在这里删除。
        if run_root.exists():
            shutil.rmtree(run_root, ignore_errors=True)
        raise
