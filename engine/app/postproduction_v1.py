"""R10 postproduction planning and execution.

Authority flow:

GenerationSelection + current GenerationSegment dialogue/timing
    -> PostProductionSegment
    -> optional local LatentSync
    -> authoritative target-dialogue audio mux

R10 never changes H3 GenerationAttempt/GenerationSelection or TargetDialogue. A successful
postproduction row is only a derivative of those current facts.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from engine.app.generation_segment_v1 import get_generation_segments_v1
from engine.app.generation_selection_v1 import list_generation_selections_v1, selected_generation_output_v1
from engine.app.latentsync_provider_v1 import LatentSyncProviderError, get_lip_sync_provider_v1
from engine.app.lip_sync_provider_v1 import LipSyncProvider, LipSyncRequestV1
from engine.app.postproduction_contract_v1 import PostProductionPlanV1, PostProductionSegmentV1
from engine.app.postproduction_lipsync_v1 import (
    PostProductionLipSyncError,
    plan_lip_sync_v1,
    render_target_face_windows_v1,
)
from engine.app.review_issue_v1 import ReviewIssue, upsert_review_issue
from engine.app.studio_v2 import Base, Project, get_session, project_dir, utcnow


class PostProductionError(RuntimeError):
    pass


class PostProductionSegment(Base):
    __tablename__ = "v2_postproduction_segments"
    __table_args__ = (
        UniqueConstraint("generation_segment_id", name="uq_v2_postproduction_generation_segment"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("v2_episodes.id", ondelete="CASCADE"), index=True)
    generation_segment_id: Mapped[str] = mapped_column(ForeignKey("v2_generation_segments.id", ondelete="CASCADE"), index=True)
    segment_input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    selection_id: Mapped[str | None] = mapped_column(ForeignKey("v2_generation_selections.id", ondelete="SET NULL"), nullable=True, index=True)
    selected_attempt_id: Mapped[str | None] = mapped_column(ForeignKey("v2_generation_attempts.id", ondelete="SET NULL"), nullable=True, index=True)
    postproduction_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_start_us: Mapped[int] = mapped_column(Integer, nullable=False)
    target_end_us: Mapped[int] = mapped_column(Integer, nullable=False)
    target_duration_us: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    lip_sync_mode: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    audio_path: Mapped[str | None] = mapped_column(Text, nullable=True)
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


def _resolve_project_path(project_id: str, raw: str | None) -> Path | None:
    value = str(raw or "").strip()
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = project_dir(project_id) / path
    return path.resolve()


def _run(command: list[str], *, timeout_seconds: int = 1800) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout_seconds)
    except FileNotFoundError as exc:
        raise PostProductionError(f"找不到命令：{command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise PostProductionError(f"媒体处理超时：{command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()[-4000:]
        raise PostProductionError(f"媒体处理失败：{detail}") from exc


def _probe_duration_us(path: Path) -> int:
    result = _run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ], timeout_seconds=60)
    try:
        seconds = float((result.stdout or "").strip())
    except ValueError as exc:
        raise PostProductionError("无法读取后期视频时长") from exc
    if seconds <= 0:
        raise PostProductionError("后期视频时长非法")
    return int(round(seconds * 1_000_000))


def _validate_video(path: Path, target_duration_us: int) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise PostProductionError("后期视频文件不存在或为空")
    actual = _probe_duration_us(path)
    tolerance = max(80_000, int(target_duration_us * 0.015))
    if abs(actual - target_duration_us) > tolerance:
        raise PostProductionError(
            f"后期视频时长不一致：目标 {target_duration_us / 1_000_000:.3f}s，实际 {actual / 1_000_000:.3f}s"
        )
    _run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0", "-f", "null", "-"], timeout_seconds=600)


def _selection_map(project_id: str) -> dict[str, dict[str, Any]]:
    return {str(item["generation_segment_id"]): item for item in list_generation_selections_v1(project_id)}


def _segment_map(project_id: str) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    plan = get_generation_segments_v1(project_id)
    return plan, {
        str(segment["id"]): dict(segment)
        for episode in plan.get("episodes") or []
        for segment in episode.get("segments") or []
        if isinstance(segment, Mapping) and segment.get("id")
    }


def _postproduction_id(segment_id: str) -> str:
    return f"POSTSEG_{hashlib.sha1(segment_id.encode('utf-8')).hexdigest()}"


def _lip_sync_issue_key(segment_id: str) -> str:
    return f"auto:lip-sync-qc:{segment_id}"


def _resolve_lip_sync_issue(project_id: str, segment_id: str, reason: str) -> None:
    with get_session() as session:
        row = session.scalar(select(ReviewIssue).where(
            ReviewIssue.project_id == project_id,
            ReviewIssue.source_key == _lip_sync_issue_key(segment_id),
            ReviewIssue.status == "OPEN",
        ))
        if row is None:
            return
        now = utcnow()
        row.status = "RESOLVED"
        row.resolution_json = json.dumps({"automatic": True, "reason": reason}, ensure_ascii=False)
        row.resolved_at = now
        row.updated_at = now
        session.commit()


def _dialogue_payload(project_id: str, segment: Mapping[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    rows: list[dict[str, Any]] = []
    waiting_audio = False
    segment_start = int(segment.get("target_start_us") or 0)
    for item in segment.get("dialogues") or []:
        if not isinstance(item, Mapping):
            continue
        path = _resolve_project_path(project_id, str(item.get("audio_path") or ""))
        ready = item.get("audio_status") == "READY" and path is not None and path.is_file() and path.stat().st_size > 0
        if not ready:
            waiting_audio = True
            continue
        global_start = int(item.get("global_start_us") or segment_start)
        rows.append({
            "target_dialogue_id": str(item.get("target_dialogue_id") or ""),
            "target_character_id": str(item.get("target_character_id") or "") or None,
            "target_character_name": item.get("target_character_name"),
            "final_text": item.get("final_text"),
            "audio_path": str(path),
            "audio_trim_start_us": max(0, segment_start - global_start),
            "start_offset_us": int(item.get("segment_start_offset_us") or 0),
            "end_offset_us": int(item.get("segment_end_offset_us") or 0),
            "speaker_visible": bool(item.get("speaker_visible")),
            "audio_identity": _file_identity(path),
        })
    return rows, waiting_audio


def _plan_segment(
    project_id: str,
    segment: Mapping[str, Any],
    selection: Mapping[str, Any] | None,
    existing: PostProductionSegment | None,
) -> dict[str, Any]:
    segment_id = str(segment["id"])
    dialogues, waiting_audio = _dialogue_payload(project_id, segment)
    visible_speaker_ids = sorted({
        str(item.get("target_character_id"))
        for item in dialogues
        if item.get("speaker_visible") and item.get("target_character_id")
    })
    visible_dialogues = [item for item in dialogues if item.get("speaker_visible")]
    visible_character_ids = {
        str(item.get("target_character_id") or "")
        for item in segment.get("target_characters") or []
        if isinstance(item, Mapping) and item.get("target_character_id")
    }
    visible_character_count = len(visible_character_ids)

    if not visible_dialogues:
        lip_sync_mode = "SKIP_NO_VISIBLE_DIALOGUE"
    elif visible_character_count == 1 and len(visible_speaker_ids) == 1 and visible_speaker_ids[0] in visible_character_ids:
        lip_sync_mode = "LATENTSYNC_FULL_SEGMENT"
    else:
        # The actual SFace locator runs only in the R10 background task. Merely opening the
        # Output/read-model endpoint must never synchronously execute face models.
        lip_sync_mode = "LATENTSYNC_TARGET_FACE_ROI"

    selection_id = str(selection.get("id")) if selection else None
    selected_attempt_id = str(selection.get("selected_attempt_id")) if selection else None
    fingerprint = _digest({
        "segment_input_fingerprint": segment.get("input_fingerprint"),
        "selection_id": selection_id,
        "selected_attempt_id": selected_attempt_id,
        "lip_sync_mode": lip_sync_mode,
        "dialogues": [
            {
                "target_dialogue_id": item["target_dialogue_id"],
                "audio_identity": item["audio_identity"],
                "audio_trim_start_us": item["audio_trim_start_us"],
                "start_offset_us": item["start_offset_us"],
                "end_offset_us": item["end_offset_us"],
                "speaker_visible": item["speaker_visible"],
                "target_character_id": item["target_character_id"],
            }
            for item in dialogues
        ],
    })

    output_path = None
    audio_path = None
    error_message = None
    locator_input_fingerprint = None
    lip_sync_windows: list[dict[str, Any]] = []
    existing_payload = _json(existing.payload_json, {}) if existing is not None else {}
    same_fingerprint = bool(existing is not None and existing.postproduction_fingerprint == fingerprint)
    if same_fingerprint:
        locator_input_fingerprint = existing_payload.get("locator_input_fingerprint")
        cached_windows = existing_payload.get("lip_sync_windows")
        lip_sync_windows = list(cached_windows) if isinstance(cached_windows, list) else []

    if selection is None:
        status, reason = "WAITING_SELECTION", "当前 GenerationSegment 尚无 R9 Selected Output"
    elif selected_generation_output_v1(project_id, segment_id) is None:
        status, reason = "WAITING_SELECTION", "当前 GenerationSelection 输出文件不可用"
    elif waiting_audio:
        status, reason = "WAITING_AUDIO", "目标对白音频尚未全部 READY"
    elif same_fingerprint:
        existing_output = Path(existing.output_path) if existing and existing.output_path else None
        if existing and existing.status == "SUCCEEDED" and existing_output is not None and existing_output.is_file() and existing_output.stat().st_size > 0:
            status, reason = "SUCCEEDED", existing.reason
            output_path = existing.output_path
            audio_path = existing.audio_path
        elif existing and existing.status == "PROCESSING":
            status, reason = "PROCESSING", existing.reason
            audio_path = existing.audio_path
        elif existing and existing.status == "REVIEW":
            status, reason = "REVIEW", existing.reason
            lip_sync_mode = "REVIEW_MULTI_FACE"
            error_message = existing.error_message
        else:
            # WAITING_MODEL / FAILED are retriable infrastructure states. Recompile exposes them as
            # READY so a later background run can retry after the local runtime/models recover.
            status, reason = "READY", "当前 Selected Output 与最终目标音频完整，可进入 R10 后期"
            error_message = existing.error_message if existing and existing.status == "FAILED" else None
    else:
        status, reason = "READY", "当前 Selected Output 与最终目标音频完整，可进入 R10 后期"

    clean_dialogues = [{key: value for key, value in item.items() if key != "audio_identity"} for item in dialogues]
    payload = {
        "id": existing.id if existing is not None else _postproduction_id(segment_id),
        "project_id": project_id,
        "episode_id": str(segment["episode_id"]),
        "generation_segment_id": segment_id,
        "segment_input_fingerprint": str(segment["input_fingerprint"]),
        "selection_id": selection_id,
        "selected_attempt_id": selected_attempt_id,
        "postproduction_fingerprint": fingerprint,
        "target_start_us": int(segment["target_start_us"]),
        "target_end_us": int(segment["target_end_us"]),
        "target_duration_us": int(segment["target_duration_us"]),
        "status": status,
        "reason": reason,
        "lip_sync_mode": lip_sync_mode,
        "visible_character_count": visible_character_count,
        "visible_speaker_ids": visible_speaker_ids,
        "locator_input_fingerprint": locator_input_fingerprint,
        "lip_sync_windows": lip_sync_windows,
        "dialogues": clean_dialogues,
        "audio_path": audio_path,
        "output_path": output_path,
        "error_message": error_message,
        "created_at": (existing.created_at if existing is not None else utcnow()).isoformat(),
        "updated_at": utcnow().isoformat(),
    }
    return PostProductionSegmentV1.model_validate(payload).model_dump(mode="json")


def _aggregate_status(segments: list[dict[str, Any]]) -> tuple[str, int, int, int]:
    succeeded = sum(item["status"] == "SUCCEEDED" for item in segments)
    review = sum(item["status"] == "REVIEW" for item in segments)
    waiting = sum(item["status"] in {"WAITING_SELECTION", "WAITING_AUDIO", "WAITING_MODEL"} for item in segments)
    if review:
        status = "REVIEW"
    elif waiting:
        if any(item["status"] == "WAITING_SELECTION" for item in segments):
            status = "WAITING_SELECTION"
        elif any(item["status"] == "WAITING_AUDIO" for item in segments):
            status = "WAITING_AUDIO"
        else:
            status = "WAITING_MODEL"
    elif segments and succeeded == len(segments):
        status = "SUCCEEDED"
    else:
        status = "READY"
    return status, succeeded, review, waiting


def compile_postproduction_plan_v1(project_id: str) -> dict[str, Any]:
    generation_plan, _segments = _segment_map(project_id)
    selections = _selection_map(project_id)
    with get_session() as session:
        if session.get(Project, project_id) is None:
            raise LookupError("项目不存在")
        existing = {
            row.generation_segment_id: row
            for row in session.scalars(select(PostProductionSegment).where(PostProductionSegment.project_id == project_id)).all()
        }

    episode_payloads: list[dict[str, Any]] = []
    active_ids: set[str] = set()
    for episode in generation_plan.get("episodes") or []:
        episode_segments: list[dict[str, Any]] = []
        for segment in episode.get("segments") or []:
            if not isinstance(segment, Mapping):
                continue
            segment_id = str(segment["id"])
            planned = _plan_segment(project_id, segment, selections.get(segment_id), existing.get(segment_id))
            episode_segments.append(planned)
            active_ids.add(segment_id)
        status, succeeded, review, waiting = _aggregate_status(episode_segments)
        episode_payloads.append({
            "episode_id": str(episode.get("episode_id") or ""),
            "status": status,
            "segment_count": len(episode_segments),
            "succeeded_count": succeeded,
            "review_count": review,
            "waiting_count": waiting,
            "segments": episode_segments,
        })

    now = utcnow()
    with get_session() as session:
        rows = {
            row.generation_segment_id: row
            for row in session.scalars(select(PostProductionSegment).where(PostProductionSegment.project_id == project_id)).all()
        }
        for segment_id, row in rows.items():
            if segment_id not in active_ids:
                session.delete(row)
        for episode in episode_payloads:
            for payload in episode["segments"]:
                row = rows.get(payload["generation_segment_id"])
                if row is None:
                    row = PostProductionSegment(
                        id=payload["id"], project_id=project_id, episode_id=payload["episode_id"],
                        generation_segment_id=payload["generation_segment_id"],
                        segment_input_fingerprint=payload["segment_input_fingerprint"],
                        postproduction_fingerprint=payload["postproduction_fingerprint"],
                        target_start_us=payload["target_start_us"], target_end_us=payload["target_end_us"],
                        target_duration_us=payload["target_duration_us"], status=payload["status"],
                        lip_sync_mode=payload["lip_sync_mode"], reason=payload["reason"], payload_json="{}",
                        created_at=datetime.fromisoformat(payload["created_at"]), updated_at=now,
                    )
                    session.add(row)
                row.episode_id = payload["episode_id"]
                row.segment_input_fingerprint = payload["segment_input_fingerprint"]
                row.selection_id = payload["selection_id"]
                row.selected_attempt_id = payload["selected_attempt_id"]
                row.postproduction_fingerprint = payload["postproduction_fingerprint"]
                row.target_start_us = payload["target_start_us"]
                row.target_end_us = payload["target_end_us"]
                row.target_duration_us = payload["target_duration_us"]
                row.status = payload["status"]
                row.lip_sync_mode = payload["lip_sync_mode"]
                row.reason = payload["reason"]
                row.payload_json = json.dumps(payload, ensure_ascii=False)
                row.audio_path = payload.get("audio_path")
                row.output_path = payload.get("output_path")
                row.error_message = payload.get("error_message")
                row.updated_at = now
        session.commit()

    flat = [segment for episode in episode_payloads for segment in episode["segments"]]
    status, succeeded, review, waiting = _aggregate_status(flat)
    return PostProductionPlanV1.model_validate({
        "schema_version": "postproduction-plan-v1",
        "project_id": project_id,
        "status": status,
        "episode_count": len(episode_payloads),
        "segment_count": len(flat),
        "succeeded_count": succeeded,
        "review_count": review,
        "waiting_count": waiting,
        "episodes": episode_payloads,
    }).model_dump(mode="json")


def get_postproduction_plan_v1(project_id: str) -> dict[str, Any]:
    return compile_postproduction_plan_v1(project_id)


def get_postproduction_segment_v1(segment_id: str) -> dict[str, Any] | None:
    with get_session() as session:
        row = session.scalar(select(PostProductionSegment).where(PostProductionSegment.generation_segment_id == segment_id))
        if row is None:
            return None
        payload = _json(row.payload_json, {})
        payload.update({
            "status": row.status,
            "reason": row.reason,
            "audio_path": row.audio_path,
            "output_path": row.output_path,
            "error_message": row.error_message,
            "updated_at": row.updated_at.isoformat(),
        })
        return PostProductionSegmentV1.model_validate(payload).model_dump(mode="json")


def _set_runtime_state(
    segment_id: str,
    *,
    status: str,
    reason: str,
    lip_sync_mode: str | None = None,
    locator_input_fingerprint: str | None = None,
    lip_sync_windows: list[Mapping[str, Any]] | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    now = utcnow()
    with get_session() as session:
        row = session.scalar(select(PostProductionSegment).where(PostProductionSegment.generation_segment_id == segment_id))
        if row is None:
            raise PostProductionError("PostProductionSegment 记录不存在")
        row.status = status
        row.reason = reason
        if lip_sync_mode is not None:
            row.lip_sync_mode = lip_sync_mode
        row.error_message = error_message
        row.updated_at = now
        payload = _json(row.payload_json, {})
        payload.update({
            "status": status,
            "reason": reason,
            "lip_sync_mode": row.lip_sync_mode,
            "locator_input_fingerprint": locator_input_fingerprint,
            "lip_sync_windows": [dict(item) for item in (lip_sync_windows or [])],
            "error_message": error_message,
            "updated_at": now.isoformat(),
        })
        row.payload_json = json.dumps(payload, ensure_ascii=False)
        session.commit()
    result = get_postproduction_segment_v1(segment_id)
    if result is None:
        raise PostProductionError("PostProductionSegment 状态更新后无法读取")
    return result


def _materialize_dialogue_audio(
    dialogues: list[Mapping[str, Any]],
    duration_us: int,
    output: Path,
    *,
    sample_rate: int,
    stereo: bool,
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    duration = duration_us / 1_000_000
    channel_layout = "stereo" if stereo else "mono"
    command: list[str] = [
        "ffmpeg", "-y", "-f", "lavfi", "-t", f"{duration:.6f}",
        "-i", f"anullsrc=r={sample_rate}:cl={channel_layout}",
    ]
    for dialogue in dialogues:
        command += ["-i", str(dialogue["audio_path"])]

    filters: list[str] = []
    mix_inputs = ["[0:a]"]
    for index, dialogue in enumerate(dialogues, start=1):
        start_us = int(dialogue["start_offset_us"])
        end_us = int(dialogue["end_offset_us"])
        trim_start = int(dialogue.get("audio_trim_start_us") or 0) / 1_000_000
        slice_duration = max(1, end_us - start_us) / 1_000_000
        delay_ms = max(0, round(start_us / 1000))
        channel_filter = f"aformat=sample_fmts=s16:channel_layouts={channel_layout}"
        delay = f"adelay={delay_ms}|{delay_ms}" if stereo else f"adelay={delay_ms}"
        filters.append(
            f"[{index}:a]atrim=start={trim_start:.6f}:duration={slice_duration:.6f},"
            f"asetpts=PTS-STARTPTS,aresample={sample_rate},{channel_filter},{delay}[d{index}]"
        )
        mix_inputs.append(f"[d{index}]")
    filters.append(
        "".join(mix_inputs)
        + f"amix=inputs={len(mix_inputs)}:duration=first:dropout_transition=0:normalize=0,"
        + f"atrim=duration={duration:.6f},asetpts=N/SR/TB[out]"
    )
    command += ["-filter_complex", ";".join(filters), "-map", "[out]", "-c:a", "pcm_s16le", str(output)]
    _run(command)
    if not output.is_file() or output.stat().st_size <= 0:
        raise PostProductionError("目标对白音轨物化失败")
    return output


def _mux_final_video(visual: Path, audio: Path | None, output: Path, duration_us: int) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(f".{output.stem}.muxing{output.suffix}")
    duration = duration_us / 1_000_000
    try:
        if audio is None:
            _run([
                "ffmpeg", "-y", "-i", str(visual), "-t", f"{duration:.6f}",
                "-map", "0:v:0", "-map", "0:a?", "-c", "copy", "-movflags", "+faststart", str(temp),
            ])
        else:
            _run([
                "ffmpeg", "-y", "-i", str(visual), "-i", str(audio), "-t", f"{duration:.6f}",
                "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                "-movflags", "+faststart", str(temp),
            ])
        if not temp.is_file() or temp.stat().st_size <= 0:
            raise PostProductionError("后期音视频封装输出为空")
        temp.replace(output)
        return output
    finally:
        if temp.exists() and temp != output:
            temp.unlink(missing_ok=True)


def execute_postproduction_segment_v1(
    project_id: str,
    segment_id: str,
    *,
    provider: LipSyncProvider | None = None,
) -> dict[str, Any]:
    plan = compile_postproduction_plan_v1(project_id)
    current = next(
        (
            segment
            for episode in plan.get("episodes") or []
            for segment in episode.get("segments") or []
            if segment.get("generation_segment_id") == segment_id
        ),
        None,
    )
    if current is None:
        raise LookupError("PostProductionSegment 不存在")
    if current["status"] == "SUCCEEDED":
        return current
    if current["status"] != "READY":
        raise PostProductionError(f"PostProductionSegment 当前不可执行：{current['reason']}")

    _generation_plan, generation_segments = _segment_map(project_id)
    generation_segment = generation_segments.get(segment_id)
    if generation_segment is None:
        raise PostProductionError("当前 GenerationSegment 已不存在")
    selected = selected_generation_output_v1(project_id, segment_id)
    if selected is None:
        raise PostProductionError("当前 Selected Output 不存在")
    fingerprint = str(current["postproduction_fingerprint"])
    workspace = (
        project_dir(project_id) / "target" / "postproduction" / str(current["episode_id"])
        / segment_id / fingerprint[:16]
    )
    workspace.mkdir(parents=True, exist_ok=True)
    dialogues = [item for item in current.get("dialogues") or [] if isinstance(item, Mapping)]
    final_audio: Path | None = None
    driving_audio: Path | None = None

    _set_runtime_state(
        segment_id,
        status="PROCESSING",
        reason="正在生成最终目标音轨与口型后期",
        lip_sync_mode=str(current["lip_sync_mode"]),
        locator_input_fingerprint=current.get("locator_input_fingerprint"),
        lip_sync_windows=current.get("lip_sync_windows") or [],
    )

    try:
        if dialogues:
            final_audio = _materialize_dialogue_audio(
                dialogues,
                int(current["target_duration_us"]),
                workspace / "final-dialogue.wav",
                sample_rate=48_000,
                stereo=True,
            )

        visual = selected
        lip_sync_mode = str(current["lip_sync_mode"])
        if lip_sync_mode != "SKIP_NO_VISIBLE_DIALOGUE":
            driving_audio = _materialize_dialogue_audio(
                dialogues,
                int(current["target_duration_us"]),
                workspace / "lipsync-driving.wav",
                sample_rate=16_000,
                stereo=False,
            )
            lip_provider = provider or get_lip_sync_provider_v1()
            runtime = lip_provider.status()
            if not runtime.get("ready"):
                raise PostProductionError(f"LatentSync Runtime 尚未 READY：{runtime.get('error') or runtime.get('worker')}")
            seed = int(fingerprint[:8], 16) & 0x7FFFFFFF
            inference_steps = max(20, min(50, int(os.getenv("AI_DRAMA_LATENTSYNC_STEPS", "20"))))
            guidance_scale = max(1.0, min(3.0, float(os.getenv("AI_DRAMA_LATENTSYNC_GUIDANCE", "1.5"))))

            if lip_sync_mode == "LATENTSYNC_FULL_SEGMENT":
                visual = lip_provider.render(LipSyncRequestV1(
                    video_path=selected,
                    audio_path=driving_audio,
                    output_path=workspace / "latentsync-visual.mp4",
                    seed=seed,
                    inference_steps=inference_steps,
                    guidance_scale=guidance_scale,
                ))
            elif lip_sync_mode == "LATENTSYNC_TARGET_FACE_ROI":
                locator_plan = plan_lip_sync_v1(
                    project_id=project_id,
                    segment=generation_segment,
                    selected_video=selected,
                    dialogues=dialogues,
                    existing_payload=current,
                )
                locator_status = str(locator_plan.get("status") or "REVIEW")
                locator_mode = str(locator_plan.get("mode") or "REVIEW_MULTI_FACE")
                locator_fp = locator_plan.get("locator_input_fingerprint")
                locator_windows = list(locator_plan.get("windows") or [])
                locator_reason = str(locator_plan.get("reason") or "目标说话人定位结果不完整")
                if locator_status == "WAITING_MODEL":
                    return _set_runtime_state(
                        segment_id,
                        status="WAITING_MODEL",
                        reason=locator_reason,
                        lip_sync_mode="LATENTSYNC_TARGET_FACE_ROI",
                        locator_input_fingerprint=locator_fp,
                        lip_sync_windows=locator_windows,
                        error_message=None,
                    )
                if locator_status != "READY" or locator_mode != "LATENTSYNC_TARGET_FACE_ROI":
                    issue = upsert_review_issue(
                        project_id=project_id,
                        episode_id=str(current["episode_id"]),
                        source_key=_lip_sync_issue_key(segment_id),
                        issue_type="LIP_SYNC_QC",
                        severity="REVIEW",
                        reason=locator_reason,
                        ai_suggestion={
                            "generation_segment_id": segment_id,
                            "visible_speaker_ids": current.get("visible_speaker_ids") or [],
                            "lip_sync_windows": locator_windows,
                        },
                        editable_payload={
                            "generation_segment_id": segment_id,
                            "selected_attempt_id": current.get("selected_attempt_id"),
                            "lip_sync_windows": locator_windows,
                        },
                    )
                    return _set_runtime_state(
                        segment_id,
                        status="REVIEW",
                        reason=locator_reason,
                        lip_sync_mode="REVIEW_MULTI_FACE",
                        locator_input_fingerprint=locator_fp,
                        lip_sync_windows=locator_windows,
                        error_message=f"ReviewIssue {issue['id']}",
                    )
                visual = render_target_face_windows_v1(
                    selected_video=selected,
                    driving_audio=driving_audio,
                    windows=locator_windows,
                    workspace=workspace,
                    provider=lip_provider,
                    seed=seed,
                    inference_steps=inference_steps,
                    guidance_scale=guidance_scale,
                )
                _set_runtime_state(
                    segment_id,
                    status="PROCESSING",
                    reason="目标说话人 ROI 已安全定位，正在完成最终封装",
                    lip_sync_mode="LATENTSYNC_TARGET_FACE_ROI",
                    locator_input_fingerprint=locator_fp,
                    lip_sync_windows=locator_windows,
                )
            else:
                raise PostProductionError(f"未知口型模式：{lip_sync_mode}")

        output = _mux_final_video(
            visual,
            final_audio,
            workspace / "final-segment.mp4",
            int(current["target_duration_us"]),
        )
        _validate_video(output, int(current["target_duration_us"]))

        fresh_segment = next(
            (
                segment
                for episode in compile_postproduction_plan_v1(project_id).get("episodes") or []
                for segment in episode.get("segments") or []
                if segment.get("generation_segment_id") == segment_id
            ),
            None,
        )
        still_current = bool(fresh_segment and fresh_segment.get("postproduction_fingerprint") == fingerprint)
        now = utcnow()
        with get_session() as session:
            row = session.scalar(select(PostProductionSegment).where(PostProductionSegment.generation_segment_id == segment_id))
            if row is None:
                raise PostProductionError("PostProductionSegment 完成后记录丢失")
            row.audio_path = str(final_audio) if final_audio else None
            row.output_path = str(output)
            row.status = "SUCCEEDED" if still_current else "STALE"
            row.reason = "R10 当前后期分段已完成" if still_current else "后期执行期间上游 Selected Output / TargetDialogue 已变化"
            row.error_message = None if still_current else row.reason
            row.updated_at = now
            payload = _json(row.payload_json, {})
            payload.update({
                "status": row.status,
                "reason": row.reason,
                "audio_path": row.audio_path,
                "output_path": row.output_path,
                "error_message": row.error_message,
                "updated_at": now.isoformat(),
            })
            row.payload_json = json.dumps(payload, ensure_ascii=False)
            session.commit()
        if still_current:
            _resolve_lip_sync_issue(project_id, segment_id, "当前目标说话人口型后期已成功完成")
        result = get_postproduction_segment_v1(segment_id)
        if result is None:
            raise PostProductionError("PostProductionSegment 无法重新读取")
        return result
    except Exception as exc:
        now = utcnow()
        with get_session() as session:
            row = session.scalar(select(PostProductionSegment).where(PostProductionSegment.generation_segment_id == segment_id))
            if row is not None:
                row.status = "FAILED"
                row.reason = "R10 后期执行失败，可在运行环境恢复后重试"
                row.error_message = str(exc)[:4000]
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
        if isinstance(exc, (PostProductionError, PostProductionLipSyncError, LatentSyncProviderError)):
            raise
        raise PostProductionError(str(exc)) from exc


ProgressCallback = Callable[[int, int, str], None]


def run_ready_postproduction_v1(project_id: str, *, progress: ProgressCallback | None = None) -> dict[str, Any]:
    plan = compile_postproduction_plan_v1(project_id)
    ready = [
        segment
        for episode in plan.get("episodes") or []
        for segment in episode.get("segments") or []
        if segment.get("status") == "READY"
    ]
    succeeded = 0
    failed: list[dict[str, str]] = []
    for index, segment in enumerate(ready, start=1):
        if progress:
            progress(index, len(ready), f"R10 后期 {index}/{len(ready)} · {segment['generation_segment_id']}")
        try:
            result = execute_postproduction_segment_v1(project_id, str(segment["generation_segment_id"]))
            if result.get("status") == "SUCCEEDED":
                succeeded += 1
        except Exception as exc:
            failed.append({"generation_segment_id": str(segment["generation_segment_id"]), "error": str(exc)})
    return {
        "project_id": project_id,
        "succeeded_now": succeeded,
        "failed": failed,
        "plan": compile_postproduction_plan_v1(project_id),
    }


def postproduction_output_v1(project_id: str, segment_id: str) -> Path | None:
    compile_postproduction_plan_v1(project_id)
    with get_session() as session:
        row = session.scalar(select(PostProductionSegment).where(
            PostProductionSegment.project_id == project_id,
            PostProductionSegment.generation_segment_id == segment_id,
            PostProductionSegment.status == "SUCCEEDED",
        ))
        path = Path(row.output_path) if row is not None and row.output_path else None
    return path if path is not None and path.is_file() and path.stat().st_size > 0 else None


__all__ = [
    "PostProductionError",
    "PostProductionSegment",
    "compile_postproduction_plan_v1",
    "execute_postproduction_segment_v1",
    "get_postproduction_plan_v1",
    "get_postproduction_segment_v1",
    "postproduction_output_v1",
    "run_ready_postproduction_v1",
]
