"""R10 episode assembly from successful PostProductionSegment outputs.

Only current SUCCEEDED PostProductionSegment files may enter an EpisodeOutput. The assembler
normalizes every segment to one stable episode stream, concatenates them in target timeline order,
writes a UTF-8 SRT sidecar, and embeds the same subtitles as a selectable MP4 text track.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from engine.app.episode_output_contract_v1 import EpisodeOutputPlanV1, EpisodeOutputV1
from engine.app.generation_segment_v1 import get_generation_segments_v1
from engine.app.postproduction_v1 import compile_postproduction_plan_v1
from engine.app.studio_v2 import Base, Episode, Project, get_session, project_dir, utcnow


class EpisodeAssemblyError(RuntimeError):
    pass


class EpisodeOutput(Base):
    __tablename__ = "v2_episode_outputs"
    __table_args__ = (UniqueConstraint("episode_id", name="uq_v2_episode_output_episode"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("v2_episodes.id", ondelete="CASCADE"), index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    segment_count: Mapped[int] = mapped_column(Integer, nullable=False)
    target_duration_us: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    subtitle_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


def _digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _json(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _file_identity(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    stat = path.stat()
    return {"path": str(path.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _episode_output_id(episode_id: str) -> str:
    return f"EPOUT_{hashlib.sha1(episode_id.encode('utf-8')).hexdigest()}"


def _run(command: list[str], *, timeout_seconds: int = 3600) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout_seconds)
    except FileNotFoundError as exc:
        raise EpisodeAssemblyError(f"找不到命令：{command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise EpisodeAssemblyError(f"整集媒体处理超时：{command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()[-5000:]
        raise EpisodeAssemblyError(f"整集媒体处理失败：{detail}") from exc


def _probe_json(path: Path, entries: str, selector: str | None = None) -> dict[str, Any]:
    command = ["ffprobe", "-v", "error"]
    if selector:
        command += ["-select_streams", selector]
    command += ["-show_entries", entries, "-of", "json", str(path)]
    result = _run(command, timeout_seconds=60)
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise EpisodeAssemblyError("无法解析 ffprobe 输出") from exc
    if not isinstance(payload, dict):
        raise EpisodeAssemblyError("ffprobe 输出格式非法")
    return payload


def _video_size(path: Path) -> tuple[int, int]:
    payload = _probe_json(path, "stream=width,height", "v:0")
    streams = payload.get("streams") or []
    if not streams:
        raise EpisodeAssemblyError("分段视频缺少视频流")
    width = int(streams[0].get("width") or 0)
    height = int(streams[0].get("height") or 0)
    if width <= 0 or height <= 0:
        raise EpisodeAssemblyError("分段视频尺寸非法")
    return width - width % 2, height - height % 2


def _has_audio(path: Path) -> bool:
    payload = _probe_json(path, "stream=index", "a:0")
    return bool(payload.get("streams"))


def _duration_us(path: Path) -> int:
    payload = _probe_json(path, "format=duration")
    try:
        seconds = float((payload.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError) as exc:
        raise EpisodeAssemblyError("无法读取整集输出时长") from exc
    if seconds <= 0:
        raise EpisodeAssemblyError("整集输出时长非法")
    return int(round(seconds * 1_000_000))


def _subtitle_events(segments: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for segment in segments:
        for dialogue in segment.get("dialogues") or []:
            if not isinstance(dialogue, Mapping):
                continue
            dialogue_id = str(dialogue.get("target_dialogue_id") or "").strip()
            text = " ".join(str(dialogue.get("final_text") or "").strip().split())
            if not dialogue_id or not text:
                continue
            start_us = int(dialogue.get("global_start_us") or 0)
            end_us = int(dialogue.get("global_end_us") or 0)
            if end_us <= start_us:
                continue
            existing = by_id.get(dialogue_id)
            if existing is None:
                by_id[dialogue_id] = {
                    "target_dialogue_id": dialogue_id,
                    "start_us": start_us,
                    "end_us": end_us,
                    "text": text,
                    "target_character_id": str(dialogue.get("target_character_id") or "") or None,
                    "target_character_name": dialogue.get("target_character_name"),
                }
            else:
                existing["start_us"] = min(int(existing["start_us"]), start_us)
                existing["end_us"] = max(int(existing["end_us"]), end_us)
                if not existing.get("text"):
                    existing["text"] = text
    return sorted(by_id.values(), key=lambda item: (int(item["start_us"]), int(item["end_us"]), item["target_dialogue_id"]))


def _build_episode_payload(
    *,
    project_id: str,
    episode: Episode,
    generation_segments: list[Mapping[str, Any]],
    post_by_segment: Mapping[str, Mapping[str, Any]],
    existing: EpisodeOutput | None,
) -> dict[str, Any]:
    ordered = sorted(
        [dict(item) for item in generation_segments],
        key=lambda item: (int(item.get("target_start_us") or 0), int(item.get("target_end_us") or 0), str(item.get("id") or "")),
    )
    segment_rows: list[dict[str, Any]] = []
    all_succeeded = bool(ordered)
    for segment in ordered:
        segment_id = str(segment["id"])
        post = post_by_segment.get(segment_id)
        post_status = str(post.get("status") or "MISSING") if post else "MISSING"
        output_path = str(post.get("output_path") or "") if post else ""
        output = Path(output_path) if output_path else None
        output_ready = bool(
            post_status == "SUCCEEDED"
            and output is not None
            and output.is_file()
            and output.stat().st_size > 0
        )
        all_succeeded = all_succeeded and output_ready
        segment_rows.append({
            "generation_segment_id": segment_id,
            "postproduction_status": post_status,
            "postproduction_fingerprint": str(post.get("postproduction_fingerprint") or segment.get("input_fingerprint") or ""),
            "target_start_us": int(segment["target_start_us"]),
            "target_end_us": int(segment["target_end_us"]),
            "target_duration_us": int(segment["target_duration_us"]),
            "output_path": str(output.resolve()) if output_ready and output is not None else None,
            "output_identity": _file_identity(output) if output_ready else None,
        })

    subtitles = _subtitle_events(ordered)
    fingerprint = _digest({
        "episode_id": episode.id,
        "segments": [
            {
                "generation_segment_id": item["generation_segment_id"],
                "postproduction_fingerprint": item["postproduction_fingerprint"],
                "postproduction_status": item["postproduction_status"],
                "target_start_us": item["target_start_us"],
                "target_end_us": item["target_end_us"],
                "output_identity": item["output_identity"],
            }
            for item in segment_rows
        ],
        "subtitles": subtitles,
    })
    target_duration_us = sum(int(item["target_duration_us"]) for item in segment_rows)

    output_path = None
    subtitle_path = None
    error_message = None
    if not all_succeeded:
        status = "WAITING_POSTPRODUCTION"
        missing = sum(item["postproduction_status"] != "SUCCEEDED" or not item["output_path"] for item in segment_rows)
        reason = f"仍有 {missing} 个分段没有当前成功的 R10 PostProduction 输出"
    elif existing is not None and existing.input_fingerprint == fingerprint:
        current_output = Path(existing.output_path) if existing.output_path else None
        current_subtitle = Path(existing.subtitle_path) if existing.subtitle_path else None
        if existing.status == "SUCCEEDED" and current_output is not None and current_output.is_file() and current_output.stat().st_size > 0:
            status = "SUCCEEDED"
            reason = existing.reason
            output_path = existing.output_path
            subtitle_path = existing.subtitle_path if current_subtitle is not None and current_subtitle.is_file() else None
        elif existing.status == "PROCESSING":
            status = "PROCESSING"
            reason = existing.reason
        else:
            status = "READY"
            reason = "全部 R10 PostProduction 分段已完成，可自动拼接整集"
            error_message = existing.error_message if existing.status == "FAILED" else None
    else:
        status = "READY"
        reason = "全部 R10 PostProduction 分段已完成，可自动拼接整集"

    clean_segments = [{key: value for key, value in item.items() if key != "output_identity"} for item in segment_rows]
    return EpisodeOutputV1.model_validate({
        "id": existing.id if existing is not None else _episode_output_id(episode.id),
        "project_id": project_id,
        "episode_id": episode.id,
        "episode_title": episode.title,
        "input_fingerprint": fingerprint,
        "status": status,
        "reason": reason,
        "segment_count": len(clean_segments),
        "target_duration_us": target_duration_us,
        "segments": clean_segments,
        "subtitles": subtitles,
        "subtitle_path": subtitle_path,
        "output_path": output_path,
        "error_message": error_message,
        "created_at": (existing.created_at if existing is not None else utcnow()).isoformat(),
        "updated_at": utcnow().isoformat(),
    }).model_dump(mode="json")


def _aggregate(episodes: list[dict[str, Any]]) -> tuple[str, int, int, int]:
    ready = sum(item["status"] == "READY" for item in episodes)
    succeeded = sum(item["status"] == "SUCCEEDED" for item in episodes)
    waiting = sum(item["status"] == "WAITING_POSTPRODUCTION" for item in episodes)
    if waiting:
        status = "WAITING_POSTPRODUCTION"
    elif episodes and succeeded == len(episodes):
        status = "SUCCEEDED"
    elif any(item["status"] == "FAILED" for item in episodes):
        status = "FAILED"
    else:
        status = "READY"
    return status, ready, succeeded, waiting


def _serialize_plan(project_id: str, payloads: list[dict[str, Any]]) -> dict[str, Any]:
    status, ready, succeeded, waiting = _aggregate(payloads)
    return EpisodeOutputPlanV1.model_validate({
        "schema_version": "episode-output-plan-v1",
        "project_id": project_id,
        "status": status,
        "episode_count": len(payloads),
        "ready_count": ready,
        "succeeded_count": succeeded,
        "waiting_count": waiting,
        "episodes": payloads,
    }).model_dump(mode="json")


def compile_episode_outputs_v1(project_id: str, *, persist: bool = True) -> dict[str, Any]:
    generation_plan = get_generation_segments_v1(project_id)
    post_plan = compile_postproduction_plan_v1(project_id, persist=persist)
    post_by_segment = {
        str(segment["generation_segment_id"]): segment
        for episode in post_plan.get("episodes") or []
        for segment in episode.get("segments") or []
        if isinstance(segment, Mapping) and segment.get("generation_segment_id")
    }
    generation_by_episode = {
        str(episode.get("episode_id") or ""): [
            dict(segment) for segment in episode.get("segments") or [] if isinstance(segment, Mapping)
        ]
        for episode in generation_plan.get("episodes") or []
        if isinstance(episode, Mapping)
    }
    with get_session() as session:
        if session.get(Project, project_id) is None:
            raise LookupError("项目不存在")
        episodes = list(session.scalars(
            select(Episode).where(Episode.project_id == project_id).order_by(Episode.sort_order, Episode.created_at)
        ).all())
        existing = {
            row.episode_id: row
            for row in session.scalars(select(EpisodeOutput).where(EpisodeOutput.project_id == project_id)).all()
        }

    payloads = [
        _build_episode_payload(
            project_id=project_id,
            episode=episode,
            generation_segments=generation_by_episode.get(episode.id, []),
            post_by_segment=post_by_segment,
            existing=existing.get(episode.id),
        )
        for episode in episodes
    ]
    if not persist:
        return _serialize_plan(project_id, payloads)

    active_ids = {item["episode_id"] for item in payloads}
    now = utcnow()
    with get_session() as session:
        rows = {
            row.episode_id: row
            for row in session.scalars(select(EpisodeOutput).where(EpisodeOutput.project_id == project_id)).all()
        }
        for episode_id, row in rows.items():
            if episode_id not in active_ids:
                session.delete(row)
        for payload in payloads:
            row = rows.get(payload["episode_id"])
            if row is None:
                row = EpisodeOutput(
                    id=payload["id"],
                    project_id=project_id,
                    episode_id=payload["episode_id"],
                    input_fingerprint=payload["input_fingerprint"],
                    status=payload["status"],
                    segment_count=payload["segment_count"],
                    target_duration_us=payload["target_duration_us"],
                    reason=payload["reason"],
                    payload_json="{}",
                    created_at=datetime.fromisoformat(payload["created_at"]),
                    updated_at=now,
                )
                session.add(row)
            row.input_fingerprint = payload["input_fingerprint"]
            row.status = payload["status"]
            row.segment_count = payload["segment_count"]
            row.target_duration_us = payload["target_duration_us"]
            row.reason = payload["reason"]
            row.payload_json = json.dumps(payload, ensure_ascii=False)
            row.subtitle_path = payload.get("subtitle_path")
            row.output_path = payload.get("output_path")
            row.error_message = payload.get("error_message")
            row.updated_at = now
        session.commit()

    return _serialize_plan(project_id, payloads)


def get_episode_output_v1(project_id: str, episode_id: str) -> dict[str, Any] | None:
    plan = compile_episode_outputs_v1(project_id, persist=False)
    current = next(
        (item for item in plan.get("episodes") or [] if item.get("episode_id") == episode_id),
        None,
    )
    if current is None:
        return None
    return EpisodeOutputV1.model_validate(current).model_dump(mode="json")


def _srt_timestamp(value_us: int) -> str:
    total_ms = max(0, int(round(value_us / 1000)))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def _write_srt(events: list[Mapping[str, Any]], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    blocks: list[str] = []
    for index, event in enumerate(events, start=1):
        text = str(event.get("text") or "").strip()
        if not text:
            continue
        blocks.append(
            f"{index}\n{_srt_timestamp(int(event['start_us']))} --> {_srt_timestamp(int(event['end_us']))}\n{text}\n"
        )
    output.write_text("\n".join(blocks), encoding="utf-8")
    return output


def _validate_timeline(segments: list[Mapping[str, Any]]) -> None:
    if not segments:
        raise EpisodeAssemblyError("剧集没有可拼接的 GenerationSegment")
    ordered = sorted(segments, key=lambda item: int(item["target_start_us"]))
    if int(ordered[0]["target_start_us"]) > 100_000:
        raise EpisodeAssemblyError("目标时间轴开头存在未解释空洞，拒绝静默压缩整集")
    for previous, current in zip(ordered, ordered[1:]):
        delta = int(current["target_start_us"]) - int(previous["target_end_us"])
        if abs(delta) > 100_000:
            relation = "空洞" if delta > 0 else "重叠"
            raise EpisodeAssemblyError(f"目标时间轴分段存在 {abs(delta) / 1_000_000:.3f}s {relation}，拒绝静默改变成片时长")


def _normalize_segment(source: Path, output: Path, *, width: int, height: int, duration_us: int) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    duration = duration_us / 1_000_000
    video_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p"
    )
    if _has_audio(source):
        command = [
            "ffmpeg", "-y", "-i", str(source), "-t", f"{duration:.6f}",
            "-map", "0:v:0", "-map", "0:a:0", "-vf", video_filter,
            "-af", "aresample=48000,aformat=channel_layouts=stereo,apad",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-g", "60",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart", str(output),
        ]
    else:
        command = [
            "ffmpeg", "-y", "-i", str(source), "-f", "lavfi", "-t", f"{duration:.6f}",
            "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{duration:.6f}",
            "-map", "0:v:0", "-map", "1:a:0", "-vf", video_filter,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-g", "60",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart", str(output),
        ]
    _run(command)
    if not output.is_file() or output.stat().st_size <= 0:
        raise EpisodeAssemblyError("整集标准化分段输出为空")
    return output


def _concat_normalized(paths: list[Path], output: Path) -> Path:
    if not paths:
        raise EpisodeAssemblyError("没有标准化分段可拼接")
    output.parent.mkdir(parents=True, exist_ok=True)
    list_file = output.with_suffix(".concat.txt")
    lines: list[str] = []
    for path in paths:
        escaped = str(path.resolve()).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c", "copy", "-movflags", "+faststart", str(output),
    ])
    if not output.is_file() or output.stat().st_size <= 0:
        raise EpisodeAssemblyError("整集拼接输出为空")
    return output


def _mux_subtitles(video: Path, subtitle: Path, output: Path, *, language: str) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    if subtitle.is_file() and subtitle.stat().st_size > 0:
        _run([
            "ffmpeg", "-y", "-i", str(video), "-i", str(subtitle),
            "-map", "0:v:0", "-map", "0:a:0", "-map", "1:0",
            "-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text",
            "-metadata:s:s:0", f"language={language.split('-', 1)[0].lower()}",
            "-metadata:s:s:0", "title=Localized Dialogue",
            "-movflags", "+faststart", str(output),
        ])
    else:
        video.replace(output)
    if not output.is_file() or output.stat().st_size <= 0:
        raise EpisodeAssemblyError("整集最终输出为空")
    return output


def execute_episode_output_v1(project_id: str, episode_id: str) -> dict[str, Any]:
    plan = compile_episode_outputs_v1(project_id)
    current = next((item for item in plan.get("episodes") or [] if item.get("episode_id") == episode_id), None)
    if current is None:
        raise LookupError("EpisodeOutput 不存在")
    if current["status"] == "SUCCEEDED":
        return current
    if current["status"] != "READY":
        raise EpisodeAssemblyError(f"EpisodeOutput 当前不可执行：{current['reason']}")

    _validate_timeline(current["segments"])
    fingerprint = str(current["input_fingerprint"])
    root = project_dir(project_id) / "target" / "output" / episode_id / fingerprint[:16]
    root.mkdir(parents=True, exist_ok=True)
    now = utcnow()
    with get_session() as session:
        row = session.scalar(select(EpisodeOutput).where(EpisodeOutput.project_id == project_id, EpisodeOutput.episode_id == episode_id))
        if row is None:
            raise EpisodeAssemblyError("EpisodeOutput 记录不存在")
        row.status = "PROCESSING"
        row.reason = "正在标准化分段、拼接整集并写入字幕"
        row.error_message = None
        row.updated_at = now
        payload = _json(row.payload_json, {})
        payload.update({"status": row.status, "reason": row.reason, "error_message": None, "updated_at": now.isoformat()})
        row.payload_json = json.dumps(payload, ensure_ascii=False)
        session.commit()

    try:
        sources = [Path(str(item["output_path"])) for item in current["segments"]]
        for source in sources:
            if not source.is_file() or source.stat().st_size <= 0:
                raise EpisodeAssemblyError("拼接期间某个 PostProductionSegment 输出已失效")
        width, height = _video_size(sources[0])
        normalized: list[Path] = []
        for index, (source, segment) in enumerate(zip(sources, current["segments"]), start=1):
            normalized.append(_normalize_segment(
                source,
                root / "normalized" / f"segment-{index:04d}.mp4",
                width=width,
                height=height,
                duration_us=int(segment["target_duration_us"]),
            ))
        assembled = _concat_normalized(normalized, root / "episode-assembled.mp4")
        subtitle = _write_srt(current.get("subtitles") or [], root / "subtitles.srt")
        with get_session() as session:
            project = session.get(Project, project_id)
            target_language = project.target_language if project is not None else "und"
        output = _mux_subtitles(assembled, subtitle, root / "episode.mp4", language=target_language)
        actual_duration = _duration_us(output)
        expected_duration = int(current["target_duration_us"])
        tolerance = max(120_000, int(expected_duration * 0.012))
        if abs(actual_duration - expected_duration) > tolerance:
            raise EpisodeAssemblyError(
                f"整集成片时长不一致：目标 {expected_duration / 1_000_000:.3f}s，实际 {actual_duration / 1_000_000:.3f}s"
            )

        fresh = compile_episode_outputs_v1(project_id)
        fresh_episode = next((item for item in fresh.get("episodes") or [] if item.get("episode_id") == episode_id), None)
        still_current = bool(fresh_episode and fresh_episode.get("input_fingerprint") == fingerprint)
        now = utcnow()
        with get_session() as session:
            row = session.scalar(select(EpisodeOutput).where(EpisodeOutput.project_id == project_id, EpisodeOutput.episode_id == episode_id))
            if row is None:
                raise EpisodeAssemblyError("整集完成后 EpisodeOutput 记录丢失")
            row.subtitle_path = str(subtitle)
            row.output_path = str(output)
            row.status = "SUCCEEDED" if still_current else "STALE"
            row.reason = "R10 当前整集成片已完成" if still_current else "整集拼接期间上游 PostProduction 输出发生变化"
            row.error_message = None if still_current else row.reason
            row.updated_at = now
            payload = _json(row.payload_json, {})
            payload.update({
                "status": row.status,
                "reason": row.reason,
                "subtitle_path": row.subtitle_path,
                "output_path": row.output_path,
                "error_message": row.error_message,
                "updated_at": now.isoformat(),
            })
            row.payload_json = json.dumps(payload, ensure_ascii=False)
            session.commit()
        result = get_episode_output_v1(project_id, episode_id)
        if result is None:
            raise EpisodeAssemblyError("EpisodeOutput 无法重新读取")
        return result
    except Exception as exc:
        now = utcnow()
        with get_session() as session:
            row = session.scalar(select(EpisodeOutput).where(EpisodeOutput.project_id == project_id, EpisodeOutput.episode_id == episode_id))
            if row is not None:
                row.status = "FAILED"
                row.reason = "整集拼接失败，可在媒体环境恢复后重试"
                row.error_message = str(exc)[:5000]
                row.updated_at = now
                payload = _json(row.payload_json, {})
                payload.update({
                    "status": row.status,
                    "reason": row.reason,
                    "error_message": row.error_message,
                    "updated_at": now.isoformat(),
                })
                row.payload_json = json.dumps(payload, ensure_ascii=False)
                session.commit()
        if isinstance(exc, EpisodeAssemblyError):
            raise
        raise EpisodeAssemblyError(str(exc)) from exc


ProgressCallback = Callable[[int, int, str], None]


def assemble_ready_episodes_v1(project_id: str, *, progress: ProgressCallback | None = None) -> dict[str, Any]:
    plan = compile_episode_outputs_v1(project_id)
    ready = [item for item in plan.get("episodes") or [] if item.get("status") == "READY"]
    succeeded = 0
    failed: list[dict[str, str]] = []
    for index, episode in enumerate(ready, start=1):
        if progress:
            progress(index, len(ready), f"整集拼接 {index}/{len(ready)} · {episode['episode_title']}")
        try:
            result = execute_episode_output_v1(project_id, str(episode["episode_id"]))
            if result.get("status") == "SUCCEEDED":
                succeeded += 1
        except Exception as exc:
            failed.append({"episode_id": str(episode["episode_id"]), "error": str(exc)})
    return {
        "project_id": project_id,
        "succeeded_now": succeeded,
        "failed": failed,
        "plan": compile_episode_outputs_v1(project_id),
    }


def episode_output_video_v1(project_id: str, episode_id: str) -> Path | None:
    row = get_episode_output_v1(project_id, episode_id)
    path = Path(str(row.get("output_path"))) if row and row.get("status") == "SUCCEEDED" and row.get("output_path") else None
    return path if path is not None and path.is_file() and path.stat().st_size > 0 else None


def episode_output_subtitle_v1(project_id: str, episode_id: str) -> Path | None:
    row = get_episode_output_v1(project_id, episode_id)
    path = Path(str(row.get("subtitle_path"))) if row and row.get("status") == "SUCCEEDED" and row.get("subtitle_path") else None
    return path if path is not None and path.is_file() else None


__all__ = [
    "EpisodeAssemblyError",
    "EpisodeOutput",
    "assemble_ready_episodes_v1",
    "compile_episode_outputs_v1",
    "episode_output_subtitle_v1",
    "episode_output_video_v1",
    "execute_episode_output_v1",
    "get_episode_output_v1",
]
