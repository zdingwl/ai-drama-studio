"""R10.1 safe background-audio preparation and target mix.

Safety invariant: raw source audio is never mixed into a target output. A source Shot must first be
separated to an Instrumental/background stem, then every known source-dialogue interval is muted
again with padding. If the separator runtime is unavailable or processing fails, callers may safely
fall back to the existing target-dialogue-only mix.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
from typing import Any, Mapping, Sequence

from sqlalchemy import select

from engine.app.audio_separator_provider_v1 import RUNTIME_PROFILE, get_background_audio_provider_v1, model_filename
from engine.app.background_audio_provider_v1 import BackgroundAudioProvider, BackgroundSeparationRequestV1
from engine.app.source_drama_snapshot_v1 import load_project_source_drama_snapshot_v1
from engine.app.studio_v2 import Episode, Preprocess, Shot, get_session, project_dir


class BackgroundAudioError(RuntimeError):
    pass


def _truthy(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _float_env(name: str, default: float, low: float, high: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(low, min(high, value))


def background_audio_profile_v1() -> dict[str, Any]:
    return {
        "enabled": _truthy("AI_DRAMA_BACKGROUND_AUDIO_ENABLED", True),
        "runtime_profile": RUNTIME_PROFILE,
        "model_filename": model_filename(),
        "source_dialogue_pad_before_us": int(_float_env("AI_DRAMA_BACKGROUND_DIALOGUE_PAD_BEFORE_MS", 150, 0, 1000) * 1000),
        "source_dialogue_pad_after_us": int(_float_env("AI_DRAMA_BACKGROUND_DIALOGUE_PAD_AFTER_MS", 250, 0, 1500) * 1000),
        "background_gain_db": _float_env("AI_DRAMA_BACKGROUND_AUDIO_GAIN_DB", -12.0, -36.0, 0.0),
        "dialogue_duck_db": _float_env("AI_DRAMA_BACKGROUND_AUDIO_DUCK_DB", -8.0, -30.0, 0.0),
        "no_dialogue_gain_db": _float_env("AI_DRAMA_BACKGROUND_AUDIO_NO_DIALOGUE_GAIN_DB", -3.0, -24.0, 0.0),
        "mix_profile": "SOURCE_INSTRUMENTAL_DIALOGUE_MASK_V1",
    }


def _digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _file_identity(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {"path": str(path.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _run(command: list[str], *, timeout_seconds: int = 1800) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout_seconds)
    except FileNotFoundError as exc:
        raise BackgroundAudioError(f"找不到命令：{command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise BackgroundAudioError(f"背景音处理超时：{command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()[-4000:]
        raise BackgroundAudioError(f"背景音处理失败：{detail}") from exc


def _source_context(segment: Mapping[str, Any]) -> tuple[Episode, Shot, Path]:
    episode_id = str(segment.get("episode_id") or "")
    shot_id = str(segment.get("source_shot_id") or "")
    with get_session() as session:
        episode = session.get(Episode, episode_id)
        if episode is None:
            raise BackgroundAudioError("源 Episode 不存在")
        shot = session.get(Shot, shot_id) if shot_id else None
        if shot is None:
            shot = session.scalar(select(Shot).where(
                Shot.episode_id == episode_id,
                Shot.ordinal == int(segment.get("shot_ordinal") or 0),
            ))
        if shot is None:
            raise BackgroundAudioError("源 Shot 不存在，无法提取背景音")
        preprocess = session.scalar(select(Preprocess).where(Preprocess.episode_id == episode_id))
        candidate = Path(preprocess.audio_path).expanduser() if preprocess and preprocess.audio_path else Path(episode.source_path).expanduser()
        source_audio = candidate.resolve()
        if not source_audio.is_file() or source_audio.stat().st_size <= 0:
            source_audio = Path(episode.source_path).expanduser().resolve()
        if not source_audio.is_file() or source_audio.stat().st_size <= 0:
            raise BackgroundAudioError("源 Episode 音频不可用")
        # Detach SQLAlchemy objects before the Session closes.
        episode_copy = Episode(
            id=episode.id,
            project_id=episode.project_id,
            title=episode.title,
            original_filename=episode.original_filename,
            source_path=episode.source_path,
            source_sha256=episode.source_sha256,
            sort_order=episode.sort_order,
            status=episode.status,
            duration_us=episode.duration_us,
            width=episode.width,
            height=episode.height,
            fps=episode.fps,
            created_at=episode.created_at,
            updated_at=episode.updated_at,
        )
        shot_copy = Shot(
            id=shot.id,
            episode_id=shot.episode_id,
            ordinal=shot.ordinal,
            start_us=shot.start_us,
            end_us=shot.end_us,
            duration_us=shot.duration_us,
            reference_clip_path=shot.reference_clip_path,
            thumbnail_path=shot.thumbnail_path,
            keyframes_json=shot.keyframes_json,
            short_description=shot.short_description,
            shot_type=shot.shot_type,
            camera_motion=shot.camera_motion,
            status=shot.status,
            created_at=shot.created_at,
        )
    return episode_copy, shot_copy, source_audio


def _snapshot_shot(project_id: str, segment: Mapping[str, Any]) -> Mapping[str, Any] | None:
    snapshot = load_project_source_drama_snapshot_v1(project_id)
    shot_id = str(segment.get("source_shot_id") or "")
    shot_key = str(segment.get("shot_key") or "")
    for episode in snapshot.get("episodes") or []:
        if not isinstance(episode, Mapping) or str(episode.get("episode_id") or "") != str(segment.get("episode_id") or ""):
            continue
        for scene in episode.get("scenes") or []:
            if not isinstance(scene, Mapping):
                continue
            for shot in scene.get("shots") or []:
                if not isinstance(shot, Mapping):
                    continue
                if shot_id and str(shot.get("source_shot_id") or "") == shot_id:
                    return shot
                if shot_key and str(shot.get("shot_key") or "") == shot_key:
                    return shot
    return None


def _dialogue_suppression_windows(
    snapshot_shot: Mapping[str, Any] | None,
    *,
    shot_start_us: int,
    shot_duration_us: int,
    profile: Mapping[str, Any],
) -> list[tuple[int, int]]:
    if snapshot_shot is None:
        return []
    before = int(profile["source_dialogue_pad_before_us"])
    after = int(profile["source_dialogue_pad_after_us"])
    windows: list[tuple[int, int]] = []
    for dialogue in snapshot_shot.get("source_dialogue") or []:
        if not isinstance(dialogue, Mapping):
            continue
        start = int(dialogue.get("start_us") or 0)
        end = int(dialogue.get("end_us") or start)
        if start >= shot_start_us and end <= shot_start_us + shot_duration_us + 1_000_000:
            start -= shot_start_us
            end -= shot_start_us
        start = max(0, start - before)
        end = min(shot_duration_us, max(start, end + after))
        if end > start:
            windows.append((start, end))
    windows.sort()
    merged: list[tuple[int, int]] = []
    for start, end in windows:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _materialize_source_shot(source_audio: Path, shot: Shot, output: Path) -> Path:
    if output.is_file() and output.stat().st_size > 0:
        return output
    output.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-ss", f"{shot.start_us / 1_000_000:.6f}", "-i", str(source_audio),
        "-t", f"{shot.duration_us / 1_000_000:.6f}", "-vn", "-ar", "48000", "-ac", "2",
        "-c:a", "pcm_s16le", str(output),
    ])
    if not output.is_file() or output.stat().st_size <= 0:
        raise BackgroundAudioError("源 Shot 音轨提取失败")
    return output


def _suppress_source_dialogue(source: Path, windows: Sequence[tuple[int, int]], output: Path) -> Path:
    if output.is_file() and output.stat().st_size > 0:
        return output
    output.parent.mkdir(parents=True, exist_ok=True)
    filters = ["aresample=48000", "aformat=sample_fmts=s16:channel_layouts=stereo"]
    for start_us, end_us in windows:
        start = start_us / 1_000_000
        end = end_us / 1_000_000
        filters.append(f"volume=0:enable='between(t,{start:.6f},{end:.6f})'")
    _run([
        "ffmpeg", "-y", "-i", str(source), "-af", ",".join(filters),
        "-c:a", "pcm_s16le", str(output),
    ])
    if not output.is_file() or output.stat().st_size <= 0:
        raise BackgroundAudioError("原对白二次抑制失败")
    return output


def _atempo_chain(factor: float) -> list[float]:
    if not math.isfinite(factor) or factor <= 0:
        raise BackgroundAudioError("背景音时间缩放比例非法")
    values: list[float] = []
    remaining = factor
    while remaining < 0.5 - 1e-9:
        values.append(0.5)
        remaining /= 0.5
    while remaining > 2.0 + 1e-9:
        values.append(2.0)
        remaining /= 2.0
    if abs(remaining - 1.0) > 1e-6:
        values.append(remaining)
    return values


def _conform_background_segment(
    safe_background: Path,
    *,
    segment: Mapping[str, Any],
    siblings: Sequence[Mapping[str, Any]],
    source_duration_us: int,
    output: Path,
) -> Path:
    target_duration_us = int(segment.get("target_duration_us") or 0)
    if target_duration_us <= 0 or source_duration_us <= 0:
        raise BackgroundAudioError("背景音重定时时长非法")
    shot_segments = [item for item in siblings if str(item.get("shot_plan_id") or "") == str(segment.get("shot_plan_id") or "")]
    if not shot_segments:
        shot_segments = [segment]
    target_shot_start = min(int(item.get("target_start_us") or 0) for item in shot_segments)
    target_shot_end = max(int(item.get("target_end_us") or 0) for item in shot_segments)
    target_shot_duration = max(1, target_shot_end - target_shot_start)
    relative_start = max(0, int(segment.get("target_start_us") or 0) - target_shot_start)
    relative_end = min(target_shot_duration, int(segment.get("target_end_us") or 0) - target_shot_start)
    source_start_us = int(source_duration_us * relative_start / target_shot_duration)
    source_end_us = int(source_duration_us * relative_end / target_shot_duration)
    source_end_us = min(source_duration_us, max(source_start_us + 20_000, source_end_us))
    source_slice_us = max(20_000, source_end_us - source_start_us)
    speed_factor = source_slice_us / target_duration_us
    filters = [
        f"atrim=start={source_start_us / 1_000_000:.6f}:end={source_end_us / 1_000_000:.6f}",
        "asetpts=PTS-STARTPTS",
    ]
    filters += [f"atempo={value:.8f}" for value in _atempo_chain(speed_factor)]
    filters += [
        "aresample=48000",
        "aformat=sample_fmts=s16:channel_layouts=stereo",
        "apad",
        f"atrim=duration={target_duration_us / 1_000_000:.6f}",
        "asetpts=N/SR/TB",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-i", str(safe_background), "-af", ",".join(filters),
        "-c:a", "pcm_s16le", str(output),
    ])
    if not output.is_file() or output.stat().st_size <= 0:
        raise BackgroundAudioError("目标背景音重定时失败")
    return output


def prepare_safe_background_v1(
    project_id: str,
    segment: Mapping[str, Any],
    siblings: Sequence[Mapping[str, Any]],
    workspace: Path,
    *,
    provider: BackgroundAudioProvider | None = None,
) -> dict[str, Any]:
    profile = background_audio_profile_v1()
    if not profile["enabled"]:
        return {"status": "SKIPPED", "mode": "TARGET_DIALOGUE_ONLY", "reason": "背景音增强已关闭", "path": None}

    separator = provider or get_background_audio_provider_v1()
    runtime = separator.status()
    if not runtime.get("ready"):
        return {
            "status": "SKIPPED",
            "mode": "TARGET_DIALOGUE_ONLY_FALLBACK",
            "reason": "背景音分离 Runtime 未就绪，安全回退到目标对白音轨",
            "path": None,
            "runtime": runtime,
        }

    episode, shot, source_audio = _source_context(segment)
    snapshot_shot = _snapshot_shot(project_id, segment)
    windows = _dialogue_suppression_windows(
        snapshot_shot,
        shot_start_us=shot.start_us,
        shot_duration_us=shot.duration_us,
        profile=profile,
    )
    cache_fingerprint = _digest({
        "source_sha256": episode.source_sha256,
        "source_audio": _file_identity(source_audio),
        "source_fingerprint": segment.get("source_fingerprint"),
        "shot_id": shot.id,
        "shot_start_us": shot.start_us,
        "shot_end_us": shot.end_us,
        "profile": profile,
        "dialogue_windows": windows,
    })
    cache = project_dir(project_id) / "target" / "background-audio-cache" / episode.id / shot.id / cache_fingerprint[:16]
    source_shot = _materialize_source_shot(source_audio, shot, cache / "source-shot.wav")
    separated = cache / "instrumental-raw.wav"
    if not separated.is_file() or separated.stat().st_size <= 0:
        separator.separate_background(BackgroundSeparationRequestV1(
            input_path=source_shot,
            output_path=separated,
            model_filename=str(profile["model_filename"]),
        ))
    safe_background = _suppress_source_dialogue(separated, windows, cache / "instrumental-safe.wav")
    conformed = _conform_background_segment(
        safe_background,
        segment=segment,
        siblings=siblings,
        source_duration_us=shot.duration_us,
        output=workspace / "safe-background.wav",
    )
    return {
        "status": "READY",
        "mode": "SOURCE_BACKGROUND_SAFE",
        "reason": "源非对白背景音已分离并按原对白时间窗二次抑制",
        "path": str(conformed),
        "cache_fingerprint": cache_fingerprint,
        "runtime_profile": profile["runtime_profile"],
        "model_filename": profile["model_filename"],
        "dialogue_suppression_windows": [[start, end] for start, end in windows],
    }


def mix_postproduction_audio_v1(
    *,
    dialogue_audio: Path | None,
    background_audio: Path | None,
    dialogues: Sequence[Mapping[str, Any]],
    duration_us: int,
    output: Path,
) -> Path | None:
    if background_audio is None:
        return dialogue_audio
    if not background_audio.is_file() or background_audio.stat().st_size <= 0:
        raise BackgroundAudioError("安全背景音文件不存在")

    profile = background_audio_profile_v1()
    duration = duration_us / 1_000_000
    output.parent.mkdir(parents=True, exist_ok=True)
    if dialogue_audio is None:
        _run([
            "ffmpeg", "-y", "-i", str(background_audio), "-af",
            f"aresample=48000,aformat=sample_fmts=s16:channel_layouts=stereo,volume={profile['no_dialogue_gain_db']:.2f}dB,"
            f"alimiter=limit=0.95,atrim=duration={duration:.6f},asetpts=N/SR/TB",
            "-c:a", "pcm_s16le", str(output),
        ])
    else:
        if not dialogue_audio.is_file() or dialogue_audio.stat().st_size <= 0:
            raise BackgroundAudioError("目标对白音轨不存在")
        background_filters = [
            "aresample=48000",
            "aformat=sample_fmts=s16:channel_layouts=stereo",
            f"volume={profile['background_gain_db']:.2f}dB",
        ]
        for item in dialogues:
            start = max(0, int(item.get("start_offset_us") or 0)) / 1_000_000
            end = max(int(item.get("end_offset_us") or 0), int(item.get("start_offset_us") or 0) + 1) / 1_000_000
            background_filters.append(
                f"volume={profile['dialogue_duck_db']:.2f}dB:enable='between(t,{start:.6f},{end:.6f})'"
            )
        filter_complex = ";".join([
            "[0:a]aresample=48000,aformat=sample_fmts=s16:channel_layouts=stereo[d]",
            f"[1:a]{','.join(background_filters)}[b]",
            f"[d][b]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.95,"
            f"atrim=duration={duration:.6f},asetpts=N/SR/TB[out]",
        ])
        _run([
            "ffmpeg", "-y", "-i", str(dialogue_audio), "-i", str(background_audio),
            "-filter_complex", filter_complex, "-map", "[out]", "-c:a", "pcm_s16le", str(output),
        ])
    if not output.is_file() or output.stat().st_size <= 0:
        raise BackgroundAudioError("最终背景音混音物化失败")
    return output


__all__ = [
    "BackgroundAudioError",
    "background_audio_profile_v1",
    "mix_postproduction_audio_v1",
    "prepare_safe_background_v1",
]
