"""R10.1 best-effort safe background-audio enhancement.

R10 first produces a valid target-dialogue/lip-sync PostProductionSegment. R10.1 then optionally
adds a source-derived non-dialogue bed. Failure or an unavailable separator never downgrades the
already-valid R10 output and never causes a human ReviewIssue.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping

from sqlalchemy import select

from engine.app.background_audio_provider_v1 import BackgroundAudioProvider
from engine.app.background_audio_v1 import mix_postproduction_audio_v1, prepare_safe_background_v1
from engine.app.generation_segment_v1 import get_generation_segments_v1
from engine.app.postproduction_v1 import (
    PostProductionSegment,
    get_postproduction_segment_v1,
    run_ready_postproduction_v1,
)
from engine.app.studio_v2 import get_session, utcnow


class PostProductionAudioMixError(RuntimeError):
    pass


def _run(command: list[str], *, timeout_seconds: int = 1800) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout_seconds)
    except FileNotFoundError as exc:
        raise PostProductionAudioMixError(f"找不到命令：{command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise PostProductionAudioMixError(f"R10.1 音视频处理超时：{command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()[-4000:]
        raise PostProductionAudioMixError(f"R10.1 音视频处理失败：{detail}") from exc


def _replace_audio(video: Path, audio: Path, output: Path, duration_us: int) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(f".{output.stem}.mixing{output.suffix}")
    duration = duration_us / 1_000_000
    try:
        _run([
            "ffmpeg", "-y", "-i", str(video), "-i", str(audio), "-t", f"{duration:.6f}",
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart", str(temp),
        ])
        if not temp.is_file() or temp.stat().st_size <= 0:
            raise PostProductionAudioMixError("R10.1 混音视频输出为空")
        temp.replace(output)
        return output
    finally:
        if temp.exists() and temp != output:
            temp.unlink(missing_ok=True)


def _generation_context(project_id: str, segment_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    plan = get_generation_segments_v1(project_id)
    flat = [
        dict(segment)
        for episode in plan.get("episodes") or []
        for segment in episode.get("segments") or []
        if isinstance(segment, Mapping)
    ]
    current = next((item for item in flat if item.get("id") == segment_id), None)
    if current is None:
        raise PostProductionAudioMixError("当前 GenerationSegment 已不存在")
    return current, flat


def _update_mix_state(
    segment_id: str,
    *,
    mode: str,
    reason: str,
    audio_path: Path | None = None,
    background_audio_path: Path | None = None,
    output_path: Path | None = None,
) -> None:
    now = utcnow()
    with get_session() as session:
        row = session.scalar(select(PostProductionSegment).where(PostProductionSegment.generation_segment_id == segment_id))
        if row is None:
            raise PostProductionAudioMixError("PostProductionSegment 记录不存在")
        try:
            payload = json.loads(row.payload_json) if row.payload_json else {}
        except json.JSONDecodeError:
            payload = {}
        payload.update({
            "audio_mix_mode": mode,
            "background_audio_path": str(background_audio_path) if background_audio_path else None,
            "background_audio_reason": reason,
            "updated_at": now.isoformat(),
        })
        if audio_path is not None:
            row.audio_path = str(audio_path)
            payload["audio_path"] = row.audio_path
        if output_path is not None:
            row.output_path = str(output_path)
            payload["output_path"] = row.output_path
        if mode == "SOURCE_BACKGROUND_SAFE":
            row.reason = "R10.1 安全背景音混音已完成"
            payload["reason"] = row.reason
        row.payload_json = json.dumps(payload, ensure_ascii=False)
        row.updated_at = now
        session.commit()


def enhance_postproduction_segment_audio_v1(
    project_id: str,
    segment_id: str,
    *,
    provider: BackgroundAudioProvider | None = None,
) -> dict[str, Any]:
    current = get_postproduction_segment_v1(segment_id)
    if current is None or current.get("project_id") != project_id:
        raise LookupError("PostProductionSegment 不存在")
    if current.get("status") != "SUCCEEDED":
        return {"status": "SKIPPED", "segment_id": segment_id, "reason": "后期分段尚未成功"}
    base_video = Path(str(current.get("output_path") or "")).expanduser().resolve()
    if not base_video.is_file() or base_video.stat().st_size <= 0:
        raise PostProductionAudioMixError("R10 成功输出文件不存在")
    if base_video.name == "final-segment-mixed.mp4":
        return {"status": "ALREADY_MIXED", "segment_id": segment_id, "output_path": str(base_video)}

    generation_segment, siblings = _generation_context(project_id, segment_id)
    workspace = base_video.parent
    try:
        background = prepare_safe_background_v1(
            project_id,
            generation_segment,
            siblings,
            workspace,
            provider=provider,
        )
    except Exception as exc:
        # Background enhancement is quality-only. Never discard a valid R10 target-dialogue result.
        _update_mix_state(
            segment_id,
            mode="TARGET_DIALOGUE_ONLY_FALLBACK",
            reason=f"背景音增强失败，保留安全目标对白版：{str(exc)[:500]}",
        )
        return {"status": "FALLBACK", "segment_id": segment_id, "reason": str(exc)}

    background_path_raw = background.get("path")
    if background.get("status") != "READY" or not background_path_raw:
        _update_mix_state(
            segment_id,
            mode="TARGET_DIALOGUE_ONLY_FALLBACK",
            reason=str(background.get("reason") or "背景音增强未执行"),
        )
        return {
            "status": "FALLBACK",
            "segment_id": segment_id,
            "reason": str(background.get("reason") or "背景音增强未执行"),
        }

    background_path = Path(str(background_path_raw)).expanduser().resolve()
    dialogue_audio_raw = current.get("audio_path")
    dialogue_audio = Path(str(dialogue_audio_raw)).expanduser().resolve() if dialogue_audio_raw else None
    mixed_audio = mix_postproduction_audio_v1(
        dialogue_audio=dialogue_audio,
        background_audio=background_path,
        dialogues=[item for item in current.get("dialogues") or [] if isinstance(item, Mapping)],
        duration_us=int(current["target_duration_us"]),
        output=workspace / "final-mix.wav",
    )
    if mixed_audio is None:
        raise PostProductionAudioMixError("R10.1 没有产生可用最终音轨")
    mixed_video = _replace_audio(
        base_video,
        mixed_audio,
        workspace / "final-segment-mixed.mp4",
        int(current["target_duration_us"]),
    )
    _update_mix_state(
        segment_id,
        mode="SOURCE_BACKGROUND_SAFE",
        reason=str(background.get("reason") or "安全背景音已完成"),
        audio_path=mixed_audio,
        background_audio_path=background_path,
        output_path=mixed_video,
    )
    return {
        "status": "SUCCEEDED",
        "segment_id": segment_id,
        "audio_mix_mode": "SOURCE_BACKGROUND_SAFE",
        "background_audio_path": str(background_path),
        "audio_path": str(mixed_audio),
        "output_path": str(mixed_video),
    }


ProgressCallback = Callable[[int, int, str], None]


def run_ready_postproduction_with_audio_mix_v1(
    project_id: str,
    *,
    progress: ProgressCallback | None = None,
    provider: BackgroundAudioProvider | None = None,
) -> dict[str, Any]:
    result = run_ready_postproduction_v1(project_id, progress=progress)
    plan = result.get("plan") or {}
    succeeded_segments = [
        segment
        for episode in plan.get("episodes") or []
        for segment in episode.get("segments") or []
        if segment.get("status") == "SUCCEEDED"
    ]
    enhanced = 0
    fallbacks: list[dict[str, str]] = []
    for index, segment in enumerate(succeeded_segments, start=1):
        segment_id = str(segment.get("generation_segment_id") or "")
        if progress:
            progress(index, len(succeeded_segments), f"R10.1 背景音 {index}/{len(succeeded_segments)} · {segment_id}")
        try:
            mixed = enhance_postproduction_segment_audio_v1(project_id, segment_id, provider=provider)
            if mixed.get("status") == "SUCCEEDED":
                enhanced += 1
            elif mixed.get("status") == "FALLBACK":
                fallbacks.append({"generation_segment_id": segment_id, "reason": str(mixed.get("reason") or "fallback")})
        except Exception as exc:
            # Same fail-open-to-target-dialogue rule as above; this should never block Episode assembly.
            fallbacks.append({"generation_segment_id": segment_id, "reason": str(exc)})
    result["background_audio"] = {
        "enhanced_now": enhanced,
        "fallback_count": len(fallbacks),
        "fallbacks": fallbacks,
    }
    return result


__all__ = [
    "PostProductionAudioMixError",
    "enhance_postproduction_segment_audio_v1",
    "run_ready_postproduction_with_audio_mix_v1",
]
