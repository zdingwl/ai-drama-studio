#!/usr/bin/env python3
"""Reconstruction-safe compact Exact-Shot grounding contract v3.

Compact v2 substantially reduced generation cost, but real selected-batch acceptance exposed a
quality regression on Shot 1: the visible description correctly mentioned blue roses and a glass
vase while ``props`` remained empty. v3 keeps the same compact/local-index architecture, preserves
salient reconstruction objects, and now also extracts the Shot-level directing facts needed by H3:
angle, lighting and structured performance (expression/posture/gaze/interaction).

The model still never emits frozen revision_item_id values or internal anonymous subject labels.
Those remain deterministic host-side compatibility fields. Camera motion is intentionally not
inferred from static frames; the Episode-window temporal pass owns that fact.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import sys
from typing import Any, Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR.parent))

import run_breakdown_vlm_fast_grounded_qwen3 as fast

EXACT_SHOT_PROMPT_PROFILE = "breakdown-p2-vlm-exact-shot-detector-recheck-zh-v5"
PRESENCE_RECHECK_PROFILE = "breakdown-p2-vlm-detector-local-recheck-zh-v1"
_ALLOWED_IE = {"INT", "EXT", "MIXED", "UNKNOWN"}
_ALLOWED_VISIBILITY = {"FULL", "PARTIAL", "OCCLUDED", "BACK_VIEW", "UNKNOWN"}
_ALLOWED_IMPORTANCE = {"LOW", "MEDIUM", "HIGH"}


def _clean(value: Any, limit: int) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def _subject_label(index: int) -> str:
    if 1 <= index <= 26:
        return f"subject_{chr(ord('A') + index - 1)}"
    return f"subject_{index}"


def _compact_scene_contexts(
    batch: Sequence[Mapping[str, Any]],
    windows: Sequence[Mapping[str, Any]],
    window_results: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    canonical = fast._grounding_scene_contexts(batch, windows, window_results)
    rows: list[dict[str, Any]] = []
    for local_index, shot in enumerate(batch, start=1):
        item_id = str(shot.get("revision_item_id") or "").strip()
        contexts: list[dict[str, Any]] = []
        for raw in canonical.get(item_id, []):
            if not isinstance(raw, Mapping):
                continue
            hint = raw.get("shot_scene_hint")
            if not isinstance(hint, Mapping):
                continue
            scene = hint.get("scene") if isinstance(hint.get("scene"), Mapping) else {}
            compact = {
                "loc": _clean(scene.get("location_hint"), 40),
                "ie": str(scene.get("interior_exterior") or "UNKNOWN").strip().upper(),
                "tod": _clean(scene.get("time_of_day"), 16),
                "sc": str(hint.get("scene_continuity") or "UNCERTAIN").strip().upper(),
            }
            if compact not in contexts:
                contexts.append(compact)
        rows.append({"i": local_index, "scene_ctx": contexts[:2]})
    return rows


def _prompt(
    source_language: str,
    batch: Sequence[Mapping[str, Any]],
    scene_contexts: Sequence[Mapping[str, Any]],
) -> str:
    import json

    language = (source_language or "und").strip() or "und"
    targets = ", ".join(
        f"{index}=EpisodeShot{fast._safe_int(shot.get('ordinal'))}"
        for index, shot in enumerate(batch, start=1)
    )
    context_json = json.dumps(scene_contexts, ensure_ascii=False, separators=(",", ":"))
    return f"""你是短剧 Exact-Shot 视觉事实提取器。原始语言：{language}。
只输出一个合法 JSON object，不要 Markdown、解释、额外字段。

本批 ShotIndex：{targets}
Scene上下文（只可补地点/INT-EXT/时间/同场景连续关系，不能搬入邻镜人物动作道具）：{context_json}

随后图片按 ShotIndex 分组；每组图片只属于该 Shot。

硬规则：
1. visible / people / props / shot_type / angle / composition / lighting 只能来自当前 Shot 图片。
2. 当前 Shot 看不到的人、动作、表情、姿态、视线、交互、道具绝不能从上下文补入。
3. props 不只记录“人物正在使用的剧情道具”；凡是对镜头重建重要、画面中显著且可独立识别的可见物体都必须列出，例如花束、花瓶、手机、袋子、书籍等。
4. 如果 visible 明确写到了这类具体物体，props 不能漏掉；人物没有接触该物体时 people=[]、interaction="" 即可。
5. 桌面/沙发/门等大环境结构只在它本身是镜头核心或后续重建必须保留时列 props，避免把整个背景家具清单化。
6. people 的 expression/posture/gaze/interaction 只写当前 Shot 图片直接支持的事实；看不清就写空字符串，不要从人物身份或剧情猜。
7. angle 写镜头视角/机位关系，例如平视、俯拍、仰拍、过肩、侧面、背面、顶视；无法确认写空字符串。
8. lighting 只写当前 Shot 直接可见的主光方向/软硬/明暗/色温等简短事实；无法确认写空字符串。
9. continuity 只允许根据给定 scene_ctx.sc 写“同场景延续/新场景起点”这类保守提示；不能发明服装、人物、道具连续性。UNCERTAIN 时写空字符串。
10. 不猜姓名、Character/Scene/Prop ID；people 按当前 Shot 稳定视觉顺序输出。
11. 不转录对白/OCR；说话真相由 ASR 负责。
12. 静态采样图不能可靠判断推/拉/摇/移，因此不要输出 camera motion；程序统一记 UNKNOWN，运镜由视频窗口阶段补充。
13. visible<=80字；appearance<=32字；activity<=24字；expression/posture/gaze/interaction<=20字；composition<=24字；angle<=12字；lighting<=28字；continuity<=24字。
14. 每个 ShotIndex 必须且只能输出一次。不要输出 revision_item_id、人物身份标签、跨镜人物标签、events、长解释。
15. 逐帧枚举所有可见的人，包括前景背身、侧身、遮挡、贴边、只露头肩或躯干的人。不能只列正脸、正在说话或能认出身份的人；背身人物的表情可空，但 people 不能漏掉。不能把两个人合成一个外观描述。
16. 同一人在不同采样帧只列一个 people 条目；无法确认是同一人时不要强行合并。只在实际出现的帧列 frame_boxes，frame 是本 Shot 从 1 开始的图片序号，box 是该帧整个可见人体的 [x,y,width,height]，坐标除以原图宽高归一化到 0..1。不能把脸框当全身框，也不能搬用别帧的位置。不能定位时 frame_boxes=[]，不要编造框。

JSON schema：
{{
  "shots":[{{
    "i":1,
    "scene":{{"loc":"地点或空","ie":"INT|EXT|MIXED|UNKNOWN","tod":"白天|夜晚|未知"}},
    "visible":"当前Shot核心可见事实",
    "shot_type":"特写|近景|中景|全景|远景|空",
    "angle":"平视|俯拍|仰拍|过肩|侧面|背面|顶视|空",
    "composition":"简短构图或空",
    "lighting":"当前Shot可见光线事实或空",
    "continuity":"同场景延续|新场景起点|空",
    "people":[{{
      "appearance":"稳定可见外观",
      "activity":"当前可见动作",
      "expression":"当前可见表情或空",
      "posture":"当前可见姿态或空",
      "gaze":"当前可见视线或空",
      "interaction":"当前可见人物/道具交互或空",
      "position":"左侧|中央|右侧|前景|背景|UNKNOWN",
      "visibility":"FULL|PARTIAL|OCCLUDED|BACK_VIEW|UNKNOWN",
      "frame_boxes":[{{"frame":1,"box":[0.1,0.2,0.3,0.6]}}]
    }}],
    "props":[{{
      "label":"对镜头重建重要的显著可见物体",
      "importance":"LOW|MEDIUM|HIGH",
      "people":[1],
      "interaction":"与人物的可见关系或空"
    }}]
  }}]
}}
"""


def _messages(
    *,
    source_language: str,
    batch: Sequence[Mapping[str, Any]],
    scene_contexts: Sequence[Mapping[str, Any]],
    max_pixels: int,
) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [{
        "type": "text",
        "text": _prompt(source_language, batch, scene_contexts),
    }]
    for local_index, shot in enumerate(batch, start=1):
        ordinal = fast._safe_int(shot.get("ordinal"))
        content.append({"type": "text", "text": f"ShotIndex {local_index} / EpisodeShot {ordinal}"})
        frames = shot.get("frames")
        if not isinstance(frames, list) or not frames:
            raise ValueError(f"Shot {ordinal} has no grounding frames")
        for frame_index, raw in enumerate(frames, start=1):
            if not isinstance(raw, Mapping):
                continue
            path = Path(str(raw.get("path") or ""))
            if not path.is_file():
                raise FileNotFoundError(f"Shot {ordinal} frame missing")
            content.append({"type": "text", "text": f"ShotIndex {local_index} frame {frame_index}"})
            content.append({
                "type": "image",
                "image": fast._media_ref(path),
                "max_pixels": int(max_pixels),
            })
    return [{"role": "user", "content": content}]


def _canonical_subjects(raw: Any) -> list[dict[str, Any]]:
    from engine.person_presence_geometry_v1 import frame_boxes
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for index, item in enumerate(raw[:12], start=1):
        if not isinstance(item, Mapping):
            continue
        visibility = str(item.get("visibility") or "UNKNOWN").strip().upper()
        if visibility not in _ALLOWED_VISIBILITY:
            visibility = "UNKNOWN"
        result.append({
            "label": _subject_label(index),
            "appearance_summary": _clean(item.get("appearance"), 160),
            "activity_summary": _clean(item.get("activity"), 160),
            "expression_summary": _clean(item.get("expression"), 160),
            "posture_summary": _clean(item.get("posture"), 160),
            "gaze_summary": _clean(item.get("gaze"), 160),
            "interaction_summary": _clean(item.get("interaction"), 160),
            "screen_position": _clean(item.get("position"), 48) or "UNKNOWN",
            "visibility": visibility,
            "speaking_state": "UNKNOWN",
            "frame_boxes": frame_boxes(item.get("frame_boxes")),
        })
    return result


def _canonical_props(raw: Any, subject_count: int) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw[:12]:
        if not isinstance(item, Mapping):
            continue
        label = _clean(item.get("label"), 160)
        marker = label.casefold()
        if not label or marker in seen:
            continue
        seen.add(marker)
        importance = str(item.get("importance") or "LOW").strip().upper()
        if importance not in _ALLOWED_IMPORTANCE:
            importance = "LOW"
        labels: list[str] = []
        indexes = item.get("people")
        if isinstance(indexes, list):
            for raw_index in indexes:
                try:
                    index = int(raw_index)
                except (TypeError, ValueError):
                    continue
                if 1 <= index <= subject_count:
                    label_key = _subject_label(index)
                    if label_key not in labels:
                        labels.append(label_key)
        result.append({
            "label": label,
            "importance": importance,
            "narrative_reason": _clean(item.get("interaction"), 160),
            "subject_labels": labels,
        })
    return result


def expand_compact(value: Mapping[str, Any], batch: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    raw_shots = value.get("shots")
    if not isinstance(raw_shots, list):
        raise ValueError("compact exact-shot output.shots must be a list")
    by_index: dict[int, Mapping[str, Any]] = {}
    for raw in raw_shots:
        if not isinstance(raw, Mapping):
            continue
        index = fast._safe_int(raw.get("i"))
        if index < 1 or index > len(batch) or index in by_index:
            raise ValueError("compact exact-shot output has invalid/duplicate ShotIndex")
        by_index[index] = raw
    if set(by_index) != set(range(1, len(batch) + 1)):
        raise ValueError("compact exact-shot output must cover every target ShotIndex exactly once")

    result: list[dict[str, Any]] = []
    for index, target in enumerate(batch, start=1):
        raw = by_index[index]
        item_id = str(target.get("revision_item_id") or "").strip()
        if not item_id:
            raise ValueError("compact exact-shot target missing revision_item_id")
        scene_raw = raw.get("scene") if isinstance(raw.get("scene"), Mapping) else {}
        ie = str(scene_raw.get("ie") or "UNKNOWN").strip().upper()
        if ie not in _ALLOWED_IE:
            ie = "UNKNOWN"
        visible = _clean(raw.get("visible"), 1200)
        if not visible:
            raise ValueError("compact exact-shot visible description is required")
        subjects = _canonical_subjects(raw.get("people"))
        props = _canonical_props(raw.get("props"), len(subjects))
        semantic = {
            "scene": {
                "location_hint": _clean(scene_raw.get("loc"), 255),
                "interior_exterior": ie,
                "time_of_day": _clean(scene_raw.get("tod"), 64) or "未知",
                "environment_description": "",
            },
            "shot": {
                "summary": visible,
                "visual_description": visible,
                "shot_type_hint": _clean(raw.get("shot_type"), 64),
                "camera_angle_hint": _clean(raw.get("angle"), 160),
                "camera_motion_hint": "UNKNOWN",
                "lighting_hint": _clean(raw.get("lighting"), 500),
                "continuity_hint": _clean(raw.get("continuity"), 500),
                "narrative_function_hint": "",
                "composition_hint": _clean(raw.get("composition"), 160),
            },
            "subjects": subjects,
            "events": [],
            "props": props,
        }
        result.append({"revision_item_id": item_id, "semantic": semantic})
    return result


def _presence_candidates(
    shot: Mapping[str, Any],
    semantic: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """找出检测器有证据、但首轮人物结构没有可靠覆盖的局部区域。"""
    from engine.person_presence_geometry_v1 import box_iou, valid_box

    raw_subjects = semantic.get("subjects")
    subjects = raw_subjects if isinstance(raw_subjects, list) else []
    raw_frames = shot.get("frames")
    if not isinstance(raw_frames, list):
        return []
    detections_by_frame: dict[int, list[Mapping[str, Any]]] = {}
    for frame_index, raw_frame in enumerate(raw_frames, start=1):
        if not isinstance(raw_frame, Mapping):
            continue
        raw_detections = raw_frame.get("person_detections")
        detections_by_frame[frame_index] = [
            item for item in (raw_detections if isinstance(raw_detections, list) else [])
            if isinstance(item, Mapping) and valid_box(item.get("box"))
        ]

    # 先以首轮逐帧框为种子，再沿相邻采样帧传播已知人物的检测轨迹。
    # 这只用于排除重复补人，不建立跨镜身份。
    existing: set[tuple[int, int]] = set()
    for frame_index, detections in detections_by_frame.items():
        locations = [
            item["box"] for subject in subjects if isinstance(subject, Mapping)
            for item in (subject.get("frame_boxes") or [])
            if isinstance(item, Mapping) and item.get("frame") == frame_index
            and valid_box(item.get("box"))
        ]
        pairs = sorted(
            ((box_iou(detection["box"], location), detection_index, location_index)
             for detection_index, detection in enumerate(detections)
             for location_index, location in enumerate(locations)),
            reverse=True,
        )
        used_detections, used_locations = set(), set()
        for score, detection_index, location_index in pairs:
            if (score >= .35 and detection_index not in used_detections
                    and location_index not in used_locations):
                existing.add((frame_index, detection_index))
                used_detections.add(detection_index)
                used_locations.add(location_index)
    changed = True
    while changed:
        changed = False
        for frame_index, detection_index in tuple(existing):
            source = detections_by_frame[frame_index][detection_index]["box"]
            for neighbor in (frame_index - 1, frame_index + 1):
                choices = [
                    (box_iou(source, detection["box"]), index)
                    for index, detection in enumerate(detections_by_frame.get(neighbor, []))
                    if (neighbor, index) not in existing
                ]
                if choices:
                    score, index = max(choices)
                    if score >= .25:
                        existing.add((neighbor, index))
                        changed = True

    result: list[dict[str, Any]] = []
    for frame_index, raw_frame in enumerate(raw_frames, start=1):
        if not isinstance(raw_frame, Mapping):
            continue
        detections = detections_by_frame.get(frame_index, [])
        # 人数没有超过首轮结构时，位置不完整交给原覆盖审核，不自动造新人。
        if len(detections) <= len(subjects):
            continue
        for detection_index, detection in enumerate(detections):
            if (frame_index, detection_index) in existing:
                continue
            detection = detections[detection_index]
            box = detection.get("box")
            if not valid_box(box):
                continue
            result.append({
                "ref": f"F{frame_index}-C{detection_index + 1}",
                "frame": frame_index,
                "box": [round(float(value), 6) for value in box],
                "score": round(float(detection.get("score") or 0.0), 6),
                "path": str(raw_frame.get("path") or ""),
            })
    return result[:24]


def _presence_recheck_prompt(
    shot: Mapping[str, Any],
    semantic: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
) -> str:
    import json

    existing = []
    for subject in semantic.get("subjects") or []:
        if not isinstance(subject, Mapping):
            continue
        existing.append({
            "appearance": _clean(subject.get("appearance_summary"), 80),
            "activity": _clean(subject.get("activity_summary"), 60),
            "position": _clean(subject.get("screen_position"), 24),
            "visibility": str(subject.get("visibility") or "UNKNOWN"),
        })
    regions = [
        {"ref": item["ref"], "frame": item["frame"], "box": item["box"]}
        for item in candidates
    ]
    return f"""你是 Exact-Shot 漏人局部复核器。只输出合法 JSON object，不要解释。
EpisodeShot={fast._safe_int(shot.get('ordinal'))}
首轮已列人物：{json.dumps(existing, ensure_ascii=False, separators=(',', ':'))}
人体检测候选：{json.dumps(regions, ensure_ascii=False, separators=(',', ':'))}

随后先给当前 Shot 的整帧标框图，再给每个 ref 的局部裁剪图；彩色框和标签对应候选 ref。
只报告画面中确实是“人”、并且不属于首轮已列人物的候选。人体检测框本身不能直接算人物。
同一个人在多帧出现时必须合并成一个 missing_people 条目，并在 refs 中列全其候选；不能按帧重复造人。
背身、贴边、遮挡、只露头肩或躯干的人也算人。不要猜姓名、身份、Character ID、性别或跨镜关系。
如果候选只是首轮人物在另一帧的位置，或是背景误检，不要输出。
appearance<=32字，activity<=24字，其余看不清写空字符串。

JSON schema：
{{"missing_people":[{{"refs":["F1-C1"],"appearance":"稳定可见外观","activity":"当前动作","position":"左侧|中央|右侧|前景|背景|UNKNOWN","visibility":"FULL|PARTIAL|OCCLUDED|BACK_VIEW|UNKNOWN"}}]}}
"""


def _annotated_candidate_images(
    candidates: Sequence[Mapping[str, Any]], output_dir: Path
) -> list[tuple[int, Path]]:
    from PIL import Image, ImageDraw

    by_frame: dict[int, list[Mapping[str, Any]]] = {}
    for item in candidates:
        by_frame.setdefault(int(item["frame"]), []).append(item)
    result: list[tuple[int, Path]] = []
    for frame_index, items in sorted(by_frame.items()):
        source = Path(str(items[0].get("path") or ""))
        if not source.is_file():
            raise FileNotFoundError(f"presence recheck frame missing: {source.name}")
        with Image.open(source) as opened:
            image = opened.convert("RGB")
        draw = ImageDraw.Draw(image)
        width, height = image.size
        stroke = max(3, round(min(width, height) * .008))
        for item in items:
            x, y, box_width, box_height = item["box"]
            left, top = round(x * width), round(y * height)
            right, bottom = round((x + box_width) * width), round((y + box_height) * height)
            draw.rectangle((left, top, right, bottom), outline=(255, 32, 32), width=stroke)
            draw.text((left + stroke, max(0, top + stroke)), str(item["ref"]), fill=(255, 32, 32),
                      stroke_width=max(1, stroke // 2), stroke_fill=(255, 255, 255))
        target = output_dir / f"presence-recheck-frame-{frame_index}.jpg"
        image.save(target, quality=94)
        result.append((frame_index, target))
    return result


def _candidate_crop_images(
    candidates: Sequence[Mapping[str, Any]], output_dir: Path
) -> list[tuple[str, Path]]:
    from PIL import Image

    result: list[tuple[str, Path]] = []
    for item in candidates:
        source = Path(str(item.get("path") or ""))
        if not source.is_file():
            raise FileNotFoundError(f"presence recheck frame missing: {source.name}")
        with Image.open(source) as opened:
            image = opened.convert("RGB")
        width, height = image.size
        x, y, box_width, box_height = item["box"]
        pad_x, pad_y = box_width * .06, box_height * .04
        left = max(0, round((x - pad_x) * width))
        top = max(0, round((y - pad_y) * height))
        right = min(width, round((x + box_width + pad_x) * width))
        bottom = min(height, round((y + box_height + pad_y) * height))
        crop = image.crop((left, top, max(left + 2, right), max(top + 2, bottom)))
        target = output_dir / f"presence-recheck-{item['ref']}.jpg"
        crop.save(target, quality=95)
        result.append((str(item["ref"]), target))
    return result


def _merge_presence_recheck(
    semantic: Mapping[str, Any],
    raw: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], int]:
    """只补 Shot 内匿名人物；候选 ref 决定框，不接收模型自造坐标或身份。"""
    by_ref = {str(item["ref"]): item for item in candidates}
    merged = dict(semantic)
    subjects = [dict(item) for item in semantic.get("subjects") or [] if isinstance(item, Mapping)]
    raw_people = raw.get("missing_people")
    if not isinstance(raw_people, list):
        raise ValueError("presence recheck missing_people must be a list")
    additions: list[dict[str, Any]] = []
    used_refs: set[str] = set()
    for item in raw_people[:8]:
        if not isinstance(item, Mapping) or not isinstance(item.get("refs"), list):
            continue
        refs = [str(value) for value in item["refs"] if str(value) in by_ref]
        refs = list(dict.fromkeys(refs))
        if not refs or any(ref in used_refs for ref in refs):
            continue
        visibility = str(item.get("visibility") or "UNKNOWN").strip().upper()
        if visibility not in _ALLOWED_VISIBILITY:
            visibility = "UNKNOWN"
        boxes = [
            {"frame": int(by_ref[ref]["frame"]), "box": list(by_ref[ref]["box"])}
            for ref in refs
        ]
        boxes.sort(key=lambda row: row["frame"])
        addition = {
            "label": _subject_label(len(subjects) + len(additions) + 1),
            "appearance_summary": _clean(item.get("appearance"), 160),
            "activity_summary": _clean(item.get("activity"), 160),
            "expression_summary": "",
            "posture_summary": "",
            "gaze_summary": "",
            "interaction_summary": "",
            "screen_position": _clean(item.get("position"), 48) or "UNKNOWN",
            "visibility": visibility,
            "speaking_state": "UNKNOWN",
            "frame_boxes": boxes,
        }
        additions.append(addition)
        used_refs.update(refs)
    if additions:
        subjects.extend(additions)
        merged["subjects"] = subjects
        shot = dict(merged.get("shot") or {})
        summary = _clean(shot.get("summary"), 1200)
        descriptions = "、".join(
            item["appearance_summary"] or "未识别身份的可见人物" for item in additions
        )
        supplemented = _clean(f"{summary}；另有{descriptions}" if summary else f"另有{descriptions}", 1200)
        shot["summary"] = supplemented
        shot["visual_description"] = supplemented
        merged["shot"] = shot
    return merged, len(additions)


def _focused_semantic_if_safe(
    first: Mapping[str, Any], focused: Mapping[str, Any], shot: Mapping[str, Any]
) -> tuple[dict[str, Any], int] | None:
    previous_count = len(first.get("subjects") or [])
    focused_count = len(focused.get("subjects") or [])
    detector_ceiling = max(
        (len(frame.get("person_detections") or [])
         for frame in shot.get("frames") or [] if isinstance(frame, Mapping)),
        default=0,
    )
    if previous_count < focused_count <= detector_ceiling:
        return dict(focused), focused_count - previous_count
    return None


def _run_presence_recheck(
    *, model: Any, processor: Any, shot: Mapping[str, Any], semantic: Mapping[str, Any],
    source_language: str, windows: Sequence[Mapping[str, Any]],
    window_results: Mapping[str, Mapping[str, Any]], max_pixels: int, max_new_tokens: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidates = _presence_candidates(shot, semantic)
    if not candidates:
        return dict(semantic), {"profile": PRESENCE_RECHECK_PROFILE, "status": "NOT_NEEDED",
                                "candidate_count": 0, "added_subject_count": 0}
    # 首轮按 5 个 Shot 批处理时，小模型容易只关注中心/说话人物。
    # 有检测差异才以同一正式 Exact-Shot 契约单独重看该 Shot。
    try:
        focused_value = fast._generate_json(
            model=model,
            processor=processor,
            messages=_messages(
                source_language=source_language,
                batch=[shot],
                scene_contexts=_compact_scene_contexts([shot], windows, window_results),
                max_pixels=max_pixels,
            ),
            max_new_tokens=max_new_tokens,
        )
        focused = expand_compact(focused_value, [shot])[0]["semantic"]
        accepted = _focused_semantic_if_safe(semantic, focused, shot)
        if accepted is not None:
            accepted_semantic, added_count = accepted
            return accepted_semantic, {
                "profile": PRESENCE_RECHECK_PROFILE,
                "status": "APPLIED",
                "strategy": "detector-triggered-single-shot-exact",
                "candidate_count": len(candidates),
                "added_subject_count": added_count,
            }
    except Exception:
        # 继续尝试更小的标框/裁剪复核；两种复核都失败时保留首轮结果并进入人工审核。
        pass
    try:
        with tempfile.TemporaryDirectory(prefix="exact-shot-presence-recheck-") as temp_name:
            content: list[dict[str, Any]] = [{
                "type": "text", "text": _presence_recheck_prompt(shot, semantic, candidates)
            }]
            for frame_index, path in _annotated_candidate_images(candidates, Path(temp_name)):
                content.append({"type": "text", "text": f"frame {frame_index}"})
                content.append({"type": "image", "image": fast._media_ref(path),
                                "max_pixels": int(max_pixels)})
            for candidate_ref, path in _candidate_crop_images(candidates, Path(temp_name)):
                content.append({"type": "text", "text": f"candidate crop {candidate_ref}"})
                content.append({"type": "image", "image": fast._media_ref(path),
                                "max_pixels": min(int(max_pixels), 262144)})
            raw = fast._generate_json(
                model=model, processor=processor, messages=[{"role": "user", "content": content}],
                max_new_tokens=min(1024, int(max_new_tokens)),
            )
        merged, added = _merge_presence_recheck(semantic, raw, candidates)
        return merged, {"profile": PRESENCE_RECHECK_PROFILE,
                        "status": "APPLIED" if added else "NO_GAIN",
                        "strategy": "annotated-region-fallback",
                        "candidate_count": len(candidates), "added_subject_count": added}
    except Exception as exc:
        return dict(semantic), {"profile": PRESENCE_RECHECK_PROFILE, "status": "FAILED",
                                "candidate_count": len(candidates), "added_subject_count": 0,
                                "error_type": type(exc).__name__,
                                "error_detail": fast._safe_error(exc)}


def analyze_grounding_batch(
    *,
    model: Any,
    processor: Any,
    batch: Sequence[Mapping[str, Any]],
    source_language: str,
    windows: Sequence[Mapping[str, Any]],
    window_results: Mapping[str, Mapping[str, Any]],
    max_pixels: int,
    max_new_tokens: int,
) -> list[dict[str, Any]]:
    contexts = _compact_scene_contexts(batch, windows, window_results)
    value = fast._generate_json(
        model=model,
        processor=processor,
        messages=_messages(
            source_language=source_language,
            batch=batch,
            scene_contexts=contexts,
            max_pixels=max_pixels,
        ),
        max_new_tokens=max_new_tokens,
    )
    results = expand_compact(value, batch)
    targets = {str(item.get("revision_item_id") or ""): item for item in batch}
    for result in results:
        item_id = str(result.get("revision_item_id") or "")
        target = targets.get(item_id)
        if target is None:
            continue
        semantic, recheck = _run_presence_recheck(
            model=model,
            processor=processor,
            shot=target,
            semantic=result["semantic"],
            source_language=source_language,
            windows=windows,
            window_results=window_results,
            max_pixels=max_pixels,
            max_new_tokens=max_new_tokens,
        )
        result["semantic"] = semantic
        result["presence_recheck"] = recheck
    return results


def grounding_adaptive(
    *,
    model: Any,
    processor: Any,
    batch: Sequence[Mapping[str, Any]],
    source_language: str,
    windows: Sequence[Mapping[str, Any]],
    window_results: Mapping[str, Mapping[str, Any]],
    max_pixels: int,
    max_new_tokens: int,
) -> list[dict[str, Any]]:
    targets = tuple(batch)
    try:
        return analyze_grounding_batch(
            model=model,
            processor=processor,
            batch=targets,
            source_language=source_language,
            windows=windows,
            window_results=window_results,
            max_pixels=max_pixels,
            max_new_tokens=max_new_tokens,
        )
    except Exception:
        if len(targets) <= 1:
            raise
        midpoint = max(1, len(targets) // 2)
        left = grounding_adaptive(
            model=model,
            processor=processor,
            batch=targets[:midpoint],
            source_language=source_language,
            windows=windows,
            window_results=window_results,
            max_pixels=max_pixels,
            max_new_tokens=max_new_tokens,
        )
        fast._cleanup_cuda()
        right = grounding_adaptive(
            model=model,
            processor=processor,
            batch=targets[midpoint:],
            source_language=source_language,
            windows=windows,
            window_results=window_results,
            max_pixels=max_pixels,
            max_new_tokens=max_new_tokens,
        )
        return [*left, *right]


__all__ = [
    "EXACT_SHOT_PROMPT_PROFILE",
    "PRESENCE_RECHECK_PROFILE",
    "_merge_presence_recheck",
    "_presence_candidates",
    "_focused_semantic_if_safe",
    "_prompt",
    "analyze_grounding_batch",
    "expand_compact",
    "grounding_adaptive",
]
