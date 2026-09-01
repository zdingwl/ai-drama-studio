"""R10 safe lip-sync window planning and rendering.

Single-person segments may still use full-segment LatentSync. Multi-person segments are split into
visible-dialogue windows, each target speaker is identified from current TargetCharacter reference
images with YuNet/SFace, then LatentSync runs on a fixed ROI containing only that target face.
The processed ROI is composited back onto the untouched Selected Output.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

from engine.app.h3_reference_assets_v1 import current_target_character_reference_assets_v1
from engine.app.lip_sync_provider_v1 import LipSyncProvider, LipSyncRequestV1
from engine.app.speaker_face_locator_v1 import locate_target_speaker_face_v1


class PostProductionLipSyncError(RuntimeError):
    pass


def _digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _file_identity(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {"path": str(path.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _run(command: list[str], *, timeout_seconds: int = 1800) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout_seconds)
    except FileNotFoundError as exc:
        raise PostProductionLipSyncError(f"找不到命令：{command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise PostProductionLipSyncError(f"口型窗口媒体处理超时：{command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()[-4000:]
        raise PostProductionLipSyncError(f"口型窗口媒体处理失败：{detail}") from exc


def _merge_speaker_windows(dialogues: list[Mapping[str, Any]], duration_us: int) -> tuple[list[dict[str, Any]], str | None]:
    visible = [
        item for item in dialogues
        if item.get("speaker_visible") and item.get("target_character_id")
    ]
    if not visible:
        return [], None
    rows = sorted(
        [
            {
                "target_character_id": str(item["target_character_id"]),
                "target_character_name": item.get("target_character_name"),
                "start_offset_us": max(0, int(item["start_offset_us"])),
                "end_offset_us": min(duration_us, int(item["end_offset_us"])),
            }
            for item in visible
        ],
        key=lambda item: (item["start_offset_us"], item["end_offset_us"]),
    )
    # Overlapping visible speech by different target speakers cannot be assigned to one ROI safely.
    for left, right in zip(rows, rows[1:]):
        if (
            right["start_offset_us"] < left["end_offset_us"]
            and right["target_character_id"] != left["target_character_id"]
        ):
            return [], "不同可见说话人的对白窗口发生重叠，无法安全自动分配口型目标"

    merged: list[dict[str, Any]] = []
    for row in rows:
        if row["end_offset_us"] <= row["start_offset_us"]:
            continue
        if (
            merged
            and merged[-1]["target_character_id"] == row["target_character_id"]
            and row["start_offset_us"] - merged[-1]["end_offset_us"] <= 160_000
        ):
            merged[-1]["end_offset_us"] = max(merged[-1]["end_offset_us"], row["end_offset_us"])
            continue
        merged.append(dict(row))

    # A small boundary pad gives LatentSync coarticulation context but never lets windows overlap.
    for index, row in enumerate(merged):
        left_limit = merged[index - 1]["end_offset_us"] if index else 0
        right_limit = merged[index + 1]["start_offset_us"] if index + 1 < len(merged) else duration_us
        row["start_offset_us"] = max(left_limit, row["start_offset_us"] - 100_000)
        row["end_offset_us"] = min(right_limit, row["end_offset_us"] + 120_000)
    return merged, None


def _target_character_map(segment: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(item["target_character_id"]): item
        for item in segment.get("target_characters") or []
        if isinstance(item, Mapping) and item.get("target_character_id")
    }


def _reference_identities(characters: Mapping[str, Mapping[str, Any]], speaker_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for speaker_id in speaker_ids:
        character = characters.get(speaker_id)
        if character is None:
            result[speaker_id] = []
            continue
        result[speaker_id] = [
            _file_identity(path)
            for path in current_target_character_reference_assets_v1(character)
            if path.is_file() and path.stat().st_size > 0
        ]
    return result


def plan_lip_sync_v1(
    *,
    project_id: str,
    segment: Mapping[str, Any],
    selected_video: Path,
    dialogues: list[Mapping[str, Any]],
    existing_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    visible_character_ids = {
        str(item.get("target_character_id") or "")
        for item in segment.get("target_characters") or []
        if isinstance(item, Mapping) and item.get("target_character_id")
    }
    visible_speaker_ids = sorted({
        str(item.get("target_character_id"))
        for item in dialogues
        if item.get("speaker_visible") and item.get("target_character_id")
    })
    if not visible_speaker_ids:
        return {
            "status": "READY",
            "reason": "当前分段没有可见说话人，不需要口型模型",
            "mode": "SKIP_NO_VISIBLE_DIALOGUE",
            "visible_character_count": len(visible_character_ids),
            "visible_speaker_ids": [],
            "locator_input_fingerprint": None,
            "windows": [],
        }
    if len(visible_character_ids) == 1 and len(visible_speaker_ids) == 1 and visible_speaker_ids[0] in visible_character_ids:
        return {
            "status": "READY",
            "reason": "当前分段只有一个可见目标人物，可安全自动执行整段口型",
            "mode": "LATENTSYNC_FULL_SEGMENT",
            "visible_character_count": 1,
            "visible_speaker_ids": visible_speaker_ids,
            "locator_input_fingerprint": None,
            "windows": [],
        }

    windows, overlap_error = _merge_speaker_windows(dialogues, int(segment["target_duration_us"]))
    if overlap_error:
        return {
            "status": "REVIEW",
            "reason": overlap_error,
            "mode": "REVIEW_MULTI_FACE",
            "visible_character_count": len(visible_character_ids),
            "visible_speaker_ids": visible_speaker_ids,
            "locator_input_fingerprint": None,
            "windows": [],
        }
    characters = _target_character_map(segment)
    reference_identities = _reference_identities(characters, visible_speaker_ids)
    locator_input_fingerprint = _digest({
        "selected_video": _file_identity(selected_video),
        "segment_input_fingerprint": segment.get("input_fingerprint"),
        "windows": windows,
        "references": reference_identities,
    })
    if existing_payload and existing_payload.get("locator_input_fingerprint") == locator_input_fingerprint:
        cached = existing_payload.get("lip_sync_windows")
        cached_mode = existing_payload.get("lip_sync_mode")
        if isinstance(cached, list) and cached_mode in {"LATENTSYNC_TARGET_FACE_ROI", "REVIEW_MULTI_FACE"}:
            statuses = {str(item.get("locator_status") or "") for item in cached if isinstance(item, Mapping)}
            if statuses <= {"READY"} and cached:
                return {
                    "status": "READY",
                    "reason": "已复用当前 Selected Output 的目标说话人安全 ROI",
                    "mode": "LATENTSYNC_TARGET_FACE_ROI",
                    "visible_character_count": len(visible_character_ids),
                    "visible_speaker_ids": visible_speaker_ids,
                    "locator_input_fingerprint": locator_input_fingerprint,
                    "windows": cached,
                }
            if "REVIEW" in statuses:
                return {
                    "status": "REVIEW",
                    "reason": "目标说话人自动定位仍存在歧义，需要人工确认",
                    "mode": "REVIEW_MULTI_FACE",
                    "visible_character_count": len(visible_character_ids),
                    "visible_speaker_ids": visible_speaker_ids,
                    "locator_input_fingerprint": locator_input_fingerprint,
                    "windows": cached,
                }

    planned: list[dict[str, Any]] = []
    wait_reason: str | None = None
    review_reason: str | None = None
    for window in windows:
        speaker_id = str(window["target_character_id"])
        character = characters.get(speaker_id)
        if character is None:
            locator = {"status": "REVIEW", "reason": f"目标说话人 {speaker_id} 不在当前 GenerationSegment 可见人物中"}
        else:
            locator = locate_target_speaker_face_v1(
                video_path=selected_video,
                target_character=character,
                windows=[(int(window["start_offset_us"]), int(window["end_offset_us"]))],
                duration_us=int(segment["target_duration_us"]),
            )
        locator_status = str(locator.get("status") or "REVIEW")
        if locator_status in {"WAITING_MODEL", "WAITING_REFERENCE"} and wait_reason is None:
            wait_reason = str(locator.get("reason") or "目标说话人定位所需模型/参考尚未准备")
        if locator_status == "REVIEW" and review_reason is None:
            review_reason = str(locator.get("reason") or "目标说话人定位不唯一")
        planned.append({
            "target_character_id": speaker_id,
            "target_character_name": window.get("target_character_name"),
            "start_offset_us": int(window["start_offset_us"]),
            "end_offset_us": int(window["end_offset_us"]),
            "crop_box": locator.get("crop_box"),
            "locator_status": locator_status,
            "locator_reason": str(locator.get("reason") or "目标说话人定位完成"),
            "locator_confidence": locator.get("median_similarity"),
        })
    if wait_reason:
        return {
            "status": "WAITING_MODEL",
            "reason": wait_reason,
            "mode": "REVIEW_MULTI_FACE",
            "visible_character_count": len(visible_character_ids),
            "visible_speaker_ids": visible_speaker_ids,
            "locator_input_fingerprint": locator_input_fingerprint,
            "windows": planned,
        }
    if review_reason:
        return {
            "status": "REVIEW",
            "reason": review_reason,
            "mode": "REVIEW_MULTI_FACE",
            "visible_character_count": len(visible_character_ids),
            "visible_speaker_ids": visible_speaker_ids,
            "locator_input_fingerprint": locator_input_fingerprint,
            "windows": planned,
        }
    return {
        "status": "READY",
        "reason": "多人镜头的每个可见对白窗口都已定位唯一目标说话人 ROI",
        "mode": "LATENTSYNC_TARGET_FACE_ROI",
        "visible_character_count": len(visible_character_ids),
        "visible_speaker_ids": visible_speaker_ids,
        "locator_input_fingerprint": locator_input_fingerprint,
        "windows": planned,
    }


def _extract_crop_window(video: Path, window: Mapping[str, Any], output: Path) -> Path:
    x, y, w, h = [int(value) for value in window["crop_box"]]
    start = int(window["start_offset_us"]) / 1_000_000
    duration = (int(window["end_offset_us"]) - int(window["start_offset_us"])) / 1_000_000
    output.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-ss", f"{start:.6f}", "-i", str(video), "-t", f"{duration:.6f}",
        "-vf", f"crop={w}:{h}:{x}:{y},setpts=PTS-STARTPTS", "-an",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
        str(output),
    ])
    if not output.is_file() or output.stat().st_size <= 0:
        raise PostProductionLipSyncError("目标说话人 ROI 视频抽取失败")
    return output


def _extract_audio_window(audio: Path, window: Mapping[str, Any], output: Path) -> Path:
    start = int(window["start_offset_us"]) / 1_000_000
    duration = (int(window["end_offset_us"]) - int(window["start_offset_us"])) / 1_000_000
    output.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-ss", f"{start:.6f}", "-i", str(audio), "-t", f"{duration:.6f}",
        "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(output),
    ])
    if not output.is_file() or output.stat().st_size <= 0:
        raise PostProductionLipSyncError("目标说话人窗口音频抽取失败")
    return output


def render_target_face_windows_v1(
    *,
    selected_video: Path,
    driving_audio: Path,
    windows: list[Mapping[str, Any]],
    workspace: Path,
    provider: LipSyncProvider,
    seed: int,
    inference_steps: int,
    guidance_scale: float,
) -> Path:
    if not windows:
        raise PostProductionLipSyncError("目标脸 ROI 模式缺少可执行窗口")
    processed: list[tuple[Mapping[str, Any], Path]] = []
    for index, window in enumerate(windows, start=1):
        if window.get("locator_status") != "READY" or not window.get("crop_box"):
            raise PostProductionLipSyncError("目标脸 ROI 窗口尚未通过唯一身份定位")
        root = workspace / f"speaker-window-{index:02d}"
        crop = _extract_crop_window(selected_video, window, root / "input-crop.mp4")
        audio = _extract_audio_window(driving_audio, window, root / "driving.wav")
        rendered = provider.render(LipSyncRequestV1(
            video_path=crop,
            audio_path=audio,
            output_path=root / "latentsync-crop.mp4",
            seed=(seed + index * 7919) & 0x7FFFFFFF,
            inference_steps=inference_steps,
            guidance_scale=guidance_scale,
        ))
        processed.append((window, rendered))

    output = workspace / "latentsync-target-face-visual.mp4"
    command: list[str] = ["ffmpeg", "-y", "-i", str(selected_video)]
    for _window, path in processed:
        command += ["-i", str(path)]
    filters: list[str] = ["[0:v]setpts=PTS-STARTPTS[base0]"]
    previous = "base0"
    for index, (window, _path) in enumerate(processed, start=1):
        x, y, w, h = [int(value) for value in window["crop_box"]]
        start = int(window["start_offset_us"]) / 1_000_000
        end = int(window["end_offset_us"]) / 1_000_000
        filters.append(
            f"[{index}:v]setpts=PTS-STARTPTS+{start:.6f}/TB,scale={w}:{h}[roi{index}]"
        )
        current = f"base{index}"
        filters.append(
            f"[{previous}][roi{index}]overlay={x}:{y}:eof_action=pass:shortest=0:"
            f"enable='between(t,{start:.6f},{end:.6f})'[{current}]"
        )
        previous = current
    command += [
        "-filter_complex", ";".join(filters), "-map", f"[{previous}]", "-an",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(output),
    ]
    _run(command)
    if not output.is_file() or output.stat().st_size <= 0:
        raise PostProductionLipSyncError("目标说话人 ROI 回贴失败")
    return output


__all__ = [
    "PostProductionLipSyncError",
    "plan_lip_sync_v1",
    "render_target_face_windows_v1",
]
