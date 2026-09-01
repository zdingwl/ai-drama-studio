"""R8 H3 Context Compiler.

GenerationSegment contains product facts and internal Studio URLs. This compiler resolves
those facts into concrete local files plus the official H3 prompt structure. It never
passes an internal `/api/...` URL blindly to SGLang and never lets source-language audio
leak through the source directing/reference video.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

from engine.app.generation_segment_v1 import GenerationSegmentError, get_generation_segments_v1
from engine.app.h3_context_contract_v1 import H3CompiledContextV1, H3MaterializedConditionV1
from engine.app.h3_reference_assets_v1 import (
    current_target_character_reference_assets_v1,
    current_target_scene_reference_asset_v1,
)
from engine.app.shot_revision_v2 import get_revision_item_path
from engine.app.studio_v2 import Episode, get_session, get_shot_path, project_dir, utcnow
from engine.app.target_localization_v1 import get_target_localization_v1
from engine.app.video_generation_provider_v1 import VideoGenerationRequestV1


class H3ContextCompilerError(RuntimeError):
    pass


_REVISION_REFERENCE_RE = re.compile(r"^/api/shot-revision-items/([^/]+)/reference$")
_SHOT_REFERENCE_RE = re.compile(r"^/api/shots/([^/]+)/reference$")


def _digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_ffmpeg(command: list[str], *, timeout_seconds: int = 1200) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout_seconds)
    except FileNotFoundError as exc:
        raise H3ContextCompilerError("找不到 ffmpeg，请先把 FFmpeg 加入 PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise H3ContextCompilerError("H3 条件素材处理超时") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()[-3500:]
        raise H3ContextCompilerError(f"H3 条件素材处理失败：{detail}") from exc


def _resolve_local_path(project_id: str, value: str) -> Path | None:
    clean = value.strip()
    if not clean:
        return None
    match = _REVISION_REFERENCE_RE.match(clean)
    if match:
        return get_revision_item_path(match.group(1), "reference")
    match = _SHOT_REFERENCE_RE.match(clean)
    if match:
        return get_shot_path(match.group(1), "reference")
    if clean.startswith("file://"):
        from urllib.parse import unquote, urlparse

        parsed = urlparse(clean)
        path = Path(unquote(parsed.path))
        if parsed.netloc and not path.drive:
            path = Path(f"//{parsed.netloc}{path}")
        return path
    path = Path(clean).expanduser()
    if not path.is_absolute():
        path = project_dir(project_id) / path
    return path


def _materialized_condition(
    *,
    path: Path,
    condition_type: str,
    role: str,
    label: str,
    source: str,
    frame_index: int | None = None,
    start_time_seconds: float | None = None,
) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    if not resolved.is_file() or resolved.stat().st_size <= 0:
        raise H3ContextCompilerError(f"H3 条件文件不存在：{resolved}")
    return H3MaterializedConditionV1.model_validate({
        "type": condition_type,
        "role": role,
        "label": label,
        "uri": resolved.as_uri(),
        "local_path": str(resolved),
        "sha256": _file_sha256(resolved),
        "source": source,
        "frame_index": frame_index,
        "start_time_seconds": start_time_seconds,
    }).model_dump(mode="json")


def _materialize_reference_video(segment: Mapping[str, Any], workspace: Path) -> Path:
    """Create a silent 24fps visual-only Ref2VA clip.

    Existing Shot Reference Clips intentionally retain source audio for source analysis and
    review. H3 must not receive that source-language soundtrack because Ref2VA can treat an
    embedded soundtrack as reference audio. Therefore R8 makes an explicit `-an` derivative.
    """

    raw = str(segment.get("reference_url") or "")
    source = _resolve_local_path(str(segment.get("project_id") or ""), raw)
    if source is None or not source.is_file():
        raise H3ContextCompilerError("Source Reference Video 无法解析为当前本地文件")
    start_us = int(segment.get("reference_clip_start_offset_us") or 0)
    duration_us = int(segment.get("reference_clip_duration_us") or 0)
    if duration_us < 2_000_000 or duration_us > 15_000_000:
        raise H3ContextCompilerError("Ref2VA Reference Video 必须物化为 2-15 秒")
    output = workspace / "source-reference.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg([
        "ffmpeg", "-y",
        "-ss", f"{start_us / 1_000_000:.6f}",
        "-i", str(source),
        "-map", "0:v:0", "-an",
        "-vf", "fps=24",
        "-t", f"{duration_us / 1_000_000:.6f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(output),
    ])
    if not output.is_file() or output.stat().st_size <= 0:
        raise H3ContextCompilerError("Reference Video 物化失败")
    return output


def _extract_last_frame(video: Path, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg([
        "ffmpeg", "-y", "-sseof", "-0.080", "-i", str(video),
        "-frames:v", "1", "-q:v", "2", str(output),
    ])
    if not output.is_file() or output.stat().st_size <= 0:
        raise H3ContextCompilerError("上一生成段无法抽取连续首帧")
    return output


def _materialize_target_audio(segment: Mapping[str, Any], workspace: Path) -> Path | None:
    """Mix target TTS slices onto one exact segment-local stereo timeline."""

    dialogues = [item for item in segment.get("dialogues") or [] if isinstance(item, Mapping)]
    if not dialogues:
        return None
    source_paths: list[Path] = []
    for item in dialogues:
        raw = str(item.get("audio_path") or "")
        path = _resolve_local_path(str(segment.get("project_id") or ""), raw) if raw else None
        if item.get("audio_status") != "READY" or path is None or not path.is_file():
            raise H3ContextCompilerError("目标对白音频尚未 READY，不能物化 H3 Audio condition")
        source_paths.append(path)

    duration_seconds = int(segment.get("h3_duration_us") or 0) / 1_000_000
    if not 4 <= duration_seconds <= 15:
        raise H3ContextCompilerError("H3 Audio condition 时长必须跟随 4-15 秒输出窗口")
    output = workspace / "target-dialogue.wav"
    command: list[str] = [
        "ffmpeg", "-y", "-f", "lavfi", "-t", f"{duration_seconds:.6f}",
        "-i", "anullsrc=r=32000:cl=stereo",
    ]
    for path in source_paths:
        command += ["-i", str(path)]

    filters: list[str] = []
    mix_inputs = ["[0:a]"]
    segment_start_us = int(segment.get("target_start_us") or 0)
    for index, (dialogue, _path) in enumerate(zip(dialogues, source_paths), start=1):
        global_start = int(dialogue.get("global_start_us") or 0)
        global_end = int(dialogue.get("global_end_us") or global_start)
        if global_end <= global_start:
            raise H3ContextCompilerError("目标对白全局时长非法")
        overlap_start = max(segment_start_us, global_start)
        audio_trim_start = max(0, overlap_start - global_start) / 1_000_000
        slice_duration = max(
            1,
            int(dialogue.get("segment_end_offset_us") or 0)
            - int(dialogue.get("segment_start_offset_us") or 0),
        ) / 1_000_000
        delay_ms = max(0, round(int(dialogue.get("segment_start_offset_us") or 0) / 1000))
        filters.append(
            f"[{index}:a]atrim=start={audio_trim_start:.6f}:duration={slice_duration:.6f},"
            f"asetpts=PTS-STARTPTS,aresample=32000,aformat=sample_fmts=s16:channel_layouts=stereo,"
            f"adelay={delay_ms}|{delay_ms}[d{index}]"
        )
        mix_inputs.append(f"[d{index}]")
    filters.append(
        "".join(mix_inputs)
        + f"amix=inputs={len(mix_inputs)}:duration=first:dropout_transition=0,"
        + f"atrim=duration={duration_seconds:.6f},asetpts=N/SR/TB[out]"
    )
    command += [
        "-filter_complex", ";".join(filters), "-map", "[out]", "-c:a", "pcm_s16le", str(output)
    ]
    _run_ffmpeg(command)
    if not output.is_file() or output.stat().st_size <= 0:
        raise H3ContextCompilerError("目标对白 Audio condition 物化失败")
    return output


def _language_name(value: str | None) -> str:
    prefix = str(value or "").strip().lower().replace("_", "-").split("-", 1)[0]
    return {
        "ar": "Arabic", "zh": "Chinese", "en": "English", "fr": "French", "de": "German",
        "it": "Italian", "ja": "Japanese", "ko": "Korean", "pt": "Portuguese", "ru": "Russian",
        "es": "Spanish",
    }.get(prefix, "Target language")


def _scene_description(segment: Mapping[str, Any]) -> str:
    scene = segment.get("target_scene") if isinstance(segment.get("target_scene"), Mapping) else None
    if not scene:
        return "Preserve the source location function and spatial layout."
    if scene.get("decision") == "LOCALIZE":
        return str(scene.get("target_description") or scene.get("target_label") or "localized target-region environment")
    return "Keep the source environment, spatial layout, entrances, furniture relationships and practical lighting unless needed to remove source-cast identity."


def _camera_description(segment: Mapping[str, Any]) -> str:
    camera = segment.get("cinematography") if isinstance(segment.get("cinematography"), Mapping) else {}
    values = [
        str(camera.get("shot_type") or "").strip(),
        str(camera.get("composition") or "").strip(),
        str(camera.get("camera_motion") or "").strip(),
    ]
    values = [item for item in values if item]
    return "; ".join(values) if values else "Preserve the source framing and camera behavior."


def _performance_description(segment: Mapping[str, Any]) -> str:
    rows = []
    for item in segment.get("performance") or []:
        if isinstance(item, Mapping) and str(item.get("text") or "").strip():
            rows.append(str(item["text"]).strip())
    return " ".join(rows) if rows else "Preserve the source blocking, action order and performance rhythm."


def _target_character_text(character: Mapping[str, Any]) -> str:
    return (
        f"{character.get('target_name')}: {character.get('appearance_profile')}. "
        f"{character.get('generation_prompt')}"
    ).strip()


def _dialogue_body(
    segment: Mapping[str, Any],
    subject_labels: Mapping[str, str],
    *,
    target_language: str,
) -> str:
    language = _language_name(target_language)
    speaker_ids: dict[str, str] = {}
    lines: list[str] = []
    for item in segment.get("dialogues") or []:
        if not isinstance(item, Mapping) or not item.get("final_text"):
            continue
        character_id = str(item.get("target_character_id") or "")
        if character_id and character_id not in speaker_ids:
            speaker_ids[character_id] = f"S{len(speaker_ids) + 1}"
        speaker_id = speaker_ids.get(character_id, f"S{len(speaker_ids) + 1}")
        subject = subject_labels.get(character_id, str(item.get("target_character_name") or "The target speaker"))
        seconds = int(item.get("segment_start_offset_us") or 0) / 1_000_000
        visible = bool(item.get("speaker_visible"))
        carry = bool(item.get("carried_from_previous_shot"))
        qualifier = "off-screen " if not visible else ""
        continuation = " The line carries over from the previous source shot without an audio break." if carry else ""
        lines.append(
            f"At {seconds:.3f} seconds, {subject} ({speaker_id}) {qualifier}says: "
            f"<d>[{language}] {item.get('final_text')}</d>.{continuation}"
        )
    return " ".join(lines)


def _build_ref_prompt(
    segment: Mapping[str, Any],
    *,
    image_subjects: list[tuple[Mapping[str, Any], str]],
    scene_picture: str | None,
    has_audio: bool,
    target_language: str,
) -> str:
    definitions: list[str] = []
    retention: list[str] = []
    subject_labels: dict[str, str] = {}
    for index, (character, picture_label) in enumerate(image_subjects, start=1):
        subject_label = f"<Subject {index}>"
        subject_labels[str(character.get("target_character_id") or "")] = subject_label
        definitions.append(
            f"{subject_label} is the fictional target character {character.get('target_name')} whose identity comes from {picture_label}: "
            f"{character.get('appearance_profile')}"
        )
        retention.append(
            f"{subject_label} (throughout the target shot): fully_preserved - preserve this target identity and never preserve the source actor identity from <Video 1>."
        )
    next_subject = len(image_subjects) + 1
    scene = segment.get("target_scene") if isinstance(segment.get("target_scene"), Mapping) else None
    scene_subject_label: str | None = None
    if scene and scene.get("decision") == "LOCALIZE":
        scene_subject_label = f"<Subject {next_subject}>"
        source = f" from {scene_picture}" if scene_picture else ""
        definitions.append(
            f"{scene_subject_label} is the localized target environment{source}: {_scene_description(segment)}"
        )
        retention.append(
            f"{scene_subject_label} (whole shot): fully_preserved - use the localized environment instead of source-region visual identity."
        )
    definitions.append("<Video 1> is the source directing/reference video for action order, blocking, framing, camera motion and performance rhythm.")
    retention.append(
        "<Video 1> (action/blocking/camera structure): partially_preserved - preserve motion, timing relationships, composition and camera behavior; replace source people with target characters, replace source dialogue/voice, and replace the environment when the target scene is localized."
    )
    if has_audio:
        definitions.append("<Audio 1> is the exact target-language dialogue timeline for this generation segment.")
        retention.append("<Audio 1>: fully_copy - keep the supplied target dialogue signal synchronized without changing its wording or speaker timing.")

    task_types = ["video editing", "reference generation"]
    if has_audio:
        task_types.append("audio reuse")
    summary = (
        f"[{' + '.join(task_types)}] The target video is an edited version of <Video 1>. "
        "Use the source only as a directing/performance template while replacing every visible source person with the defined target character subjects. "
        + (f"Use {scene_subject_label} as the target environment. " if scene_subject_label else "Keep the source environment. ")
        + ("Reuse <Audio 1> as the synchronized target dialogue. " if has_audio else "")
        + f"The final target segment lasts {int(segment.get('h3_duration_us') or 0) / 1_000_000:.2f} seconds."
    )

    visual = str(segment.get("visual_description") or "").strip()
    performance = _performance_description(segment)
    camera = _camera_description(segment)
    characters = " ".join(
        f"{subject_labels.get(str(item.get('target_character_id') or ''), str(item.get('target_name') or 'Target character'))}: {_target_character_text(item)}."
        for item in segment.get("target_characters") or [] if isinstance(item, Mapping)
    )
    dialogue = _dialogue_body(segment, subject_labels, target_language=target_language)
    detailed = (
        "Live-action localized short-drama remake. [Shot 1] "
        f"{characters} Environment: {_scene_description(segment)}. "
        f"Source visible event: {visual or 'follow the visible source event from <Video 1>'}. "
        f"Performance path: {performance}. Camera: {camera}. "
        "Transfer only action, blocking, composition, camera movement and performance rhythm from <Video 1>; do not preserve any source actor face, ethnicity, distinctive body identity, costume identity, source-language lip motion or source voice. "
        + (dialogue if dialogue else "No spoken line occurs in this segment. ")
        + f"Reach a natural end state at {int(segment.get('h3_duration_us') or 0) / 1_000_000:.2f} seconds without adding a new plot event."
    )
    soundscape = (
        "<Audio 1> is reused as the exact synchronized dialogue track. Add only restrained environment and physical foley that does not mask or replace it."
        if has_audio
        else "Use natural location ambience and restrained physical foley matching the visible actions. No source-language dialogue is retained."
    )
    return (
        "subject_definitions:\n" + "\n".join(definitions)
        + "\n\nsummary:\n" + summary
        + "\n\nretention_analysis:\n" + "\n".join(retention)
        + "\n\ndetailed_description:\n" + detailed
        + "\n\noverall_soundscape:\n" + soundscape
        + "\n\nnon_diegetic_music:\nN/A"
    )


def _build_fl_prompt(
    segment: Mapping[str, Any],
    *,
    keyframe_count: int,
    target_language: str,
) -> str:
    duration = int(segment.get("h3_duration_us") or 0) / 1_000_000
    instruction = ""
    if keyframe_count == 1:
        instruction = "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n\n"
    elif keyframe_count == 2:
        instruction = (
            "How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; "
            f"Picture 2 (from Shot 1) aligns with the {duration:.2f}-second mark of the target video.\n\n"
        )
    characters = " ".join(
        f"{_target_character_text(item)}."
        for item in segment.get("target_characters") or [] if isinstance(item, Mapping)
    )
    dialogue = _dialogue_body(segment, {}, target_language=target_language)
    integrated = (
        "[Shot 1] Live-action localized short-drama remake. "
        + ("Begin exactly from <Picture 1> and preserve its already-localized character identity, clothing, scene state and composition. " if keyframe_count else "")
        + f"Target characters: {characters or 'no visible person'}. Environment: {_scene_description(segment)}. "
        + f"Visible event: {segment.get('visual_description') or 'continue the planned shot action'}. "
        + f"Performance path: {_performance_description(segment)}. Camera: {_camera_description(segment)}. "
        + (dialogue if dialogue else "No spoken line occurs in this segment. ")
        + f"Continue naturally for {duration:.2f} seconds without introducing a new story event."
    )
    return (
        instruction
        + "integrated_multimodal_description: " + integrated
        + "\n\noverall_soundscape: Use natural location ambience and restrained physical foley. Final target dialogue audio will be enforced by the downstream lip-sync/audio stage."
        + "\n\nnon_diegetic_music: N/A"
    )


def _nearest_aspect_ratio(episode_id: str) -> str:
    with get_session() as session:
        episode = session.get(Episode, episode_id)
        width = int(episode.width or 0) if episode else 0
        height = int(episode.height or 0) if episode else 0
    if width <= 0 or height <= 0:
        return "9:16"
    value = width / height
    choices = {
        "21:9": 21 / 9,
        "16:9": 16 / 9,
        "4:3": 4 / 3,
        "1:1": 1.0,
        "3:4": 3 / 4,
        "9:16": 9 / 16,
    }
    return min(choices, key=lambda key: abs(math.log(value / choices[key])))


def _current_segment(project_id: str, segment_id: str) -> dict[str, Any]:
    plan = get_generation_segments_v1(project_id)
    for episode in plan.get("episodes") or []:
        for segment in episode.get("segments") or []:
            if isinstance(segment, Mapping) and segment.get("id") == segment_id:
                return dict(segment)
    raise LookupError("GenerationSegment 不存在或已经失效")


def _request_condition(item: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": item["type"],
        "uri": item["uri"],
        "role": item["role"],
    }
    if item.get("frame_index") is not None:
        payload["frame_index"] = int(item["frame_index"])
    if item.get("start_time_seconds") is not None:
        payload["start_time_seconds"] = float(item["start_time_seconds"])
    return payload


def compile_h3_context_v1(project_id: str, segment_id: str) -> dict[str, Any]:
    segment = _current_segment(project_id, segment_id)
    if segment.get("status") != "READY":
        raise GenerationSegmentError(f"GenerationSegment 尚不可提交 H3：{segment.get('reason')}")

    localization = get_target_localization_v1(project_id)
    target_language = str(localization.get("target_language") or "")
    target_region = str(localization.get("target_region") or "")
    workspace = project_dir(project_id) / "target" / "h3" / "contexts" / segment_id / str(segment["input_fingerprint"])[:16]
    workspace.mkdir(parents=True, exist_ok=True)
    conditions: list[dict[str, Any]] = []
    reason = "H3 条件已物化，可执行"
    status = "READY"

    mode = str(segment.get("generation_mode") or "")
    picture_subjects: list[tuple[Mapping[str, Any], str]] = []
    scene_picture_label: str | None = None

    if mode == "REF2VA":
        image_number = 0
        target_characters = [item for item in segment.get("target_characters") or [] if isinstance(item, Mapping)]
        if len(target_characters) > 9:
            status, reason = "REVIEW", "单个镜头可见目标人物超过 H3 的 9 张图片参考上限"
        else:
            for character in target_characters:
                refs = current_target_character_reference_assets_v1(character)
                if not refs:
                    status, reason = "WAITING_REFERENCE", f"目标人物 {character.get('target_name')} 尚未生成当前版本参考资产"
                    break
                image_number += 1
                label = f"<Picture {image_number}>"
                conditions.append(_materialized_condition(
                    path=refs[0],
                    condition_type="image",
                    role=f"target_character:{character.get('target_character_id')}",
                    label=label,
                    source="target-character-reference",
                ))
                picture_subjects.append((character, label))

        scene = segment.get("target_scene") if isinstance(segment.get("target_scene"), Mapping) else None
        if status == "READY" and scene and scene.get("decision") == "LOCALIZE" and image_number < 9:
            full_scene = next(
                (
                    item
                    for item in localization.get("scene_mappings") or []
                    if isinstance(item, Mapping) and item.get("id") == scene.get("mapping_id")
                ),
                None,
            )
            if full_scene is not None:
                scene_ref = current_target_scene_reference_asset_v1(full_scene, target_region=target_region)
                if scene_ref is None:
                    status, reason = "WAITING_REFERENCE", "目标本土化场景尚未生成当前版本参考资产"
                else:
                    image_number += 1
                    scene_picture_label = f"<Picture {image_number}>"
                    conditions.append(_materialized_condition(
                        path=scene_ref,
                        condition_type="image",
                        role="target_scene",
                        label=scene_picture_label,
                        source="target-scene-reference",
                    ))

        if status == "READY":
            ref = _materialize_reference_video(segment, workspace)
            conditions.append(_materialized_condition(
                path=ref,
                condition_type="video",
                role="source_directing_reference",
                label="<Video 1>",
                source="source-reference-video",
            ))
            audio = _materialize_target_audio(segment, workspace)
            if audio is not None:
                conditions.append(_materialized_condition(
                    path=audio,
                    condition_type="audio",
                    role="target_dialogue_timeline",
                    label="<Audio 1>",
                    source="target-dialogue-audio",
                ))
        prompt = _build_ref_prompt(
            segment,
            image_subjects=picture_subjects,
            scene_picture=scene_picture_label,
            has_audio=any(item["type"] == "audio" for item in conditions),
            target_language=target_language,
        )
    elif mode == "FL2VA":
        keyframe_count = 0
        previous_segment_id = str(segment.get("continuity_from_segment_id") or "")
        if previous_segment_id:
            try:
                from engine.app.generation_attempt_v1 import latest_successful_generation_output_v1

                previous_output = latest_successful_generation_output_v1(project_id, previous_segment_id)
            except ImportError:
                previous_output = None
            if previous_output is None:
                status, reason = "WAITING_PREVIOUS_OUTPUT", "FL2VA 连续段需要上一 GenerationSegment 的当前成功输出作为首帧"
            else:
                first_frame = _extract_last_frame(previous_output, workspace / "continuity-first-frame.jpg")
                conditions.append(_materialized_condition(
                    path=first_frame,
                    condition_type="image",
                    role="first_frame",
                    label="<Picture 1>",
                    source="previous-generation-output",
                    frame_index=0,
                ))
                keyframe_count = 1
        prompt = _build_fl_prompt(
            segment,
            keyframe_count=keyframe_count,
            target_language=target_language,
        )
    else:
        raise H3ContextCompilerError(f"未知 GenerationSegment mode：{mode}")

    seed = int(str(segment["input_fingerprint"])[:8], 16) & 0x7FFFFFFF
    request_payload = {
        "provider": "MINIMAX_H3_LOCAL",
        "mode": mode,
        "prompt": prompt,
        "conditions": [_request_condition(item) for item in conditions],
        "duration_seconds": int(segment["h3_duration_us"]) // 1_000_000,
        "short_edge": 768,
        "aspect_ratio": _nearest_aspect_ratio(str(segment["episode_id"])),
        "seed": seed,
    }
    request = VideoGenerationRequestV1.model_validate(request_payload) if status == "READY" else None
    context_fingerprint = _digest({
        "segment_input_fingerprint": segment["input_fingerprint"],
        "mode": mode,
        "target_language": target_language,
        "target_region": target_region,
        "prompt": prompt,
        "conditions": [
            {
                "type": item["type"],
                "role": item["role"],
                "sha256": item["sha256"],
                "frame_index": item.get("frame_index"),
                "start_time_seconds": item.get("start_time_seconds"),
            }
            for item in conditions
        ],
        "request": request.model_dump(mode="json", exclude_none=True) if request else None,
        "status": status,
    })
    return H3CompiledContextV1.model_validate({
        "schema_version": "h3-context-v1",
        "project_id": project_id,
        "episode_id": str(segment["episode_id"]),
        "segment_id": segment_id,
        "segment_input_fingerprint": str(segment["input_fingerprint"]),
        "context_fingerprint": context_fingerprint,
        "status": status,
        "reason": reason,
        "provider": "MINIMAX_H3_LOCAL",
        "mode": mode,
        "prompt": prompt,
        "conditions": conditions,
        "request": request.model_dump(mode="json", exclude_none=True) if request else None,
        "workspace_dir": str(workspace),
        "created_at": utcnow().isoformat(),
    }).model_dump(mode="json")


__all__ = ["H3ContextCompilerError", "compile_h3_context_v1"]
