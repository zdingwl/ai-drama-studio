"""模块 3/4：精确采样帧中的单人人物图、数据库证据与安全自动归并。

读取已发布拉片的 VLM 定位和原片，检测框一对一复核后提取人物。
所有图片、mask、特征存数据库；普通读取只返回每个观察/人物的一张代表图。
只由显式拉片 Worker 调用，不在 GET 内运行模型或更新身份。
"""
from __future__ import annotations

from dataclasses import asdict, fields
import hashlib
import json
from pathlib import Path

from sqlalchemy import LargeBinary, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from engine.app import studio_v2 as studio

PROFILE = "source-person-isolation-v2"


class SourcePersonImage(studio.Base):
    __tablename__ = "v2_source_person_images"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(80), index=True)
    episode_id: Mapped[str] = mapped_column(String(80), index=True)
    shot_id: Mapped[str] = mapped_column(String(80), index=True)
    observation_key: Mapped[str] = mapped_column(String(255), index=True)
    anchor: Mapped[str] = mapped_column(String(64))
    image: Mapped[bytes] = mapped_column(LargeBinary)
    mask: Mapped[bytes] = mapped_column(LargeBinary)
    evidence_json: Mapped[str] = mapped_column(Text)


class SourcePersonCaptureState(studio.Base):
    __tablename__ = "v2_source_person_capture_states"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    observation_key: Mapped[str] = mapped_column(String(255), index=True)
    shot_id: Mapped[str] = mapped_column(String(80))
    anchor: Mapped[str] = mapped_column(String(64))
    image_ids_json: Mapped[str] = mapped_column(Text)


def _states(session, keys):
    return {(r.observation_key, r.shot_id): (r.anchor, set(json.loads(r.image_ids_json)))
            for r in session.scalars(select(SourcePersonCaptureState).where(SourcePersonCaptureState.observation_key.in_(keys)))}


def _active(states, image_id, key, shot_id, anchor):
    state = states.get((key, shot_id))
    return state is None or (state[0] == anchor and image_id in state[1])


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      default=lambda item: item.tolist() if hasattr(item, "tolist") else str(item))


def isolate(frame, box, *, segmenter, other_boxes=()):
    """人体语义分割限制到当前检测框，排除其他人物区域；不以矩形裁图冒充抠图。"""
    import cv2
    import numpy as np
    h, w = frame.shape[:2]
    x, y, bw, bh = map(int, box)
    x, y = max(0, x), max(0, y)
    bw, bh = min(bw, w-x), min(bh, h-y)
    if min(bw, bh) < 16:
        raise ValueError("人物区域太小，无法可靠提取")
    margin = max(4, round(max(bw, bh) * .08))
    left, top, right, bottom = max(0, x-margin), max(0, y-margin), min(w, x+bw+margin), min(h, y+bh+margin)
    crop = frame[top:bottom, left:right].copy()
    blob = cv2.dnn.blobFromImage(crop, 1/127.5, (192, 192), (127.5,127.5,127.5), swapRB=True)
    segmenter.setInput(blob)
    logits = segmenter.forward()[0]
    foreground = cv2.resize(logits[1] - logits[0], (right-left, bottom-top)) > 0
    allowed = np.zeros(foreground.shape, np.uint8)
    allowed[y-top:y-top+bh, x-left:x-left+bw] = 1
    for ox, oy, ow, oh in other_boxes:
        a, b, c, d = max(left, ox), max(top, oy), min(right, ox+ow), min(bottom, oy+oh)
        if c > a and d > b:
            allowed[b-top:d-top, a-left:c-left] = 0
    alpha = (foreground & allowed.astype(bool)).astype(np.uint8) * 255
    if np.count_nonzero(alpha) < bw * bh * .08 or np.count_nonzero(alpha) > bw * bh * .98:
        raise ValueError("人物前景分割失败，请人工核对")
    rgba = cv2.cvtColor(crop, cv2.COLOR_BGR2BGRA)
    rgba[:, :, 3] = alpha
    ok, png = cv2.imencode(".png", rgba)
    mask_ok, mask_png = cv2.imencode(".png", alpha)
    if not ok or not mask_ok:
        raise ValueError("人物图编码失败")
    return png.tobytes(), mask_png.tobytes()


def image_url(image_id):
    return f"/api/source-person-images/{image_id}"


def valid_mark(row, mark):
    if not isinstance(mark, dict) or mark.get("source") != PROFILE:
        return False
    with studio.get_session() as session:
        image = session.get(SourcePersonImage, str(mark.get("evidence_id") or ""))
        return bool(image and image.observation_key == row["key"] and image.anchor == row["anchor"]
                    and _active(_states(session, [row["key"]]), image.id, row["key"], image.shot_id, row["anchor"])
                    and image.shot_id == mark.get("shot_id") and mark.get("image_url") == image_url(image.id)
                    and mark.get("box") == [0, 0, 1, 1]
                    and image.shot_id in {s["id"] for s in row["shots"]})


def decorate(rows, characters):
    """只读，每个观察和正式人物至多一个代表图，无 gallery 输出。"""
    if not rows:
        return
    current = {r["key"]: r for r in rows}
    best, by_character = {}, {}
    with studio.get_session() as session:
        states = _states(session, current)
        records = session.execute(select(SourcePersonImage.id, SourcePersonImage.observation_key,
                                        SourcePersonImage.anchor, SourcePersonImage.shot_id, SourcePersonImage.evidence_json)
                                  .where(SourcePersonImage.observation_key.in_(current))).all()
        for image_id, key, anchor, shot_id, raw in records:
            row = current[key]
            if anchor != row["anchor"] or shot_id not in {s["id"] for s in row["shots"]} or not _active(states, image_id, key, shot_id, anchor):
                continue
            quality = float(json.loads(raw).get("display_quality") or 0)
            item = (quality, image_id, shot_id)
            if key not in best or item > best[key]:
                best[key] = item
            if row.get("character_id"):
                cid = row["character_id"]
                if cid not in by_character or item > by_character[cid]:
                    by_character[cid] = item
    for key, (_, image_id, shot_id) in best.items():
        row = current[key]
        row["extracted_image_url"] = image_url(image_id)
        row["extracted_localization"] = dict(source=PROFILE, evidence_id=image_id, shot_id=shot_id,
                                              image_url=image_url(image_id), box=[0, 0, 1, 1])
    for character in characters:
        best_image = by_character.get(character["id"])
        if best_image:
            character["cover_url"] = image_url(best_image[1])
            character["cover_box"] = None


def _sources(draft):
    """冻结 LocalSubject -> Scene/P ref -> 每 Shot 原 VLM label，不能按外观文字猜 ID。"""
    result = {}
    for scene in draft.get("scene_segments", []):
        subjects = sorted(scene.get("subjects", []), key=lambda s: s["ordinal"])
        refs = {s["id"]: f"P{i}" for i, s in enumerate(subjects, 1)}
        for shot in scene.get("shots", []):
            for presence in shot.get("subjects", []):
                ref = refs.get(presence.get("local_subject_id"))
                label = (presence.get("search_hint") or {}).get("source_vlm_label")
                if ref and label:
                    result[(shot["shot_ordinal_snapshot"], label)] = f'{draft["run"]["episode_id"]}:{scene["ordinal"]}:{ref}'
    return result


def capture(episode_id, *, shot_ordinal=None, progress=None, rerun_artifact=None):
    """仅提取所请求 Shot；跨镜归并复用数据库现有特征，不重跑其他镜头模型。"""
    import cv2
    from engine.app.breakdown_serializer_v1 import get_current_breakdown
    from engine.app.breakdown_shot_rerun_v1 import _load_full_context
    from engine.app.breakdown_p2_fusion_v1 import _load_one_component
    from engine.app.breakdown_models_v1 import BreakdownRun
    from engine.app.source_person_assets_v1 import LOCK, inventory
    from engine.app.source_presence_audit_v1 import detector, iou
    from engine.app.character_visual_v5 import Observation, _YoutuReIDOrt, _read_frame, _clarity_score, _representative_quality, _body_completeness
    from engine.app.content_models_v2 import require_models
    from engine.app.character_observation_v9 import annotate_person_instances
    from engine.app.character_person_features_v9 import extract_person_features, attach_person_features
    from engine.app.character_person_evidence_v10 import attach_v10_policy
    from engine.person_presence_geometry_v1 import frame_boxes
    from engine.app.breakdown_p2_vlm_fast_grounded_v1 import frame_sample_ratios

    draft = get_current_breakdown(episode_id)
    if not draft:
        raise ValueError("请先完成原片内容分析")
    context = _load_full_context(draft, rerun_id=draft["run"]["id"])
    workspace = inventory(context.project_id)
    expected = workspace["revision"]
    rows = {r["key"]: r for r in workspace["observations"]}
    source_keys = _sources(draft)
    with studio.get_session() as session:
        statuses = json.loads(session.get(BreakdownRun, context.run_id).component_status_json)
    vlm = _load_one_component(context, statuses["VLM"], "VLM")
    payloads = {r.shot_revision_item_id: r.payload for r in vlm.result.evidence if r.source_type == "VLM_OUTPUT"}
    if rerun_artifact:
        rerun = json.loads(Path(rerun_artifact).read_text(encoding="utf-8"))
        if rerun.get("source_breakdown_run_id") != context.run_id or rerun.get("source_shot_revision_id") != context.source_shot_revision_id:
            raise ValueError("单镜人物提取输入已经过期")
        for evidence in rerun["providers"]["VLM"]["evidence"]:
            if evidence.get("source_type") != "VLM_OUTPUT":
                continue
            revision_item = evidence.get("shot_revision_item_id")
            old = payloads.get(revision_item, {})
            new = evidence.get("payload") or {}
            old_subjects = (old.get("exact_shot_semantic") or old.get("semantic") or {}).get("subjects", [])
            new_subjects = (new.get("exact_shot_semantic") or new.get("semantic") or {}).get("subjects", [])
            # 单镜重拉的 label 不是稳定身份。未能逐项保持外观与 label 时交原片结构核对。
            signature = lambda subjects: sorted((str(s.get("label")), str(s.get("appearance_summary"))) for s in subjects)
            if signature(old_subjects) != signature(new_subjects):
                affected = next((s for s in context.shots if s.revision_item_id == revision_item), None)
                if affected:
                    with LOCK, studio.get_session() as session:
                        for row in rows.values():
                            if row["episode_id"] != episode_id or affected.original_shot_id not in {s["id"] for s in row["shots"]}:
                                continue
                            state_id = hashlib.sha256(f'{row["key"]}:{affected.original_shot_id}'.encode()).hexdigest()
                            session.merge(SourcePersonCaptureState(id=state_id, observation_key=row["key"],
                                          shot_id=affected.original_shot_id, anchor=row["anchor"], image_ids_json="[]"))
                        session.commit()
                return {"auto_merged_observations": 0, "image_count": 0,
                        "warnings": ["单镜人物观察发生变化，需核对人物结构后再归并；未沿用旧 label 自动绑定"]}
            payloads[revision_item] = new
    targets = [s for s in context.shots if shot_ordinal is None or s.ordinal == shot_ordinal]
    if not targets:
        raise ValueError("请求的分镜不存在")
    models = require_models(include_segmentation=True)
    segmenter = cv2.dnn.readNet(str(models["person_segmentation.pphumanseg.2023mar"]))
    reid = _YoutuReIDOrt(models["person_reid.youtu.2021nov"])
    detect = detector().detect
    face_detector = cv2.FaceDetectorYN.create(str(models["face_detection.yunet.2023mar"]), "", (320, 320), score_threshold=.8)
    face_recognizer = cv2.FaceRecognizerSF.create(str(models["face_recognition.sface.2021dec"]), "")
    pending, warnings = [], []
    episode = studio.get_episode(episode_id)
    for index, shot in enumerate(targets, 1):
        if progress:
            progress(index, len(targets), f"提取单人人物图 · 分镜 {shot.ordinal:02d}")
        payload = payloads.get(shot.revision_item_id, {})
        semantic = payload.get("exact_shot_semantic") or payload.get("semantic") or {}
        ratios = (payload.get("exact_shot_grounding") or {}).get("frame_sample_ratios") or list(frame_sample_ratios(shot.duration_us))
        subjects = semantic.get("subjects") or []
        for frame_index, ratio in enumerate(ratios, 1):
            local_us = min(shot.duration_us-1, round(shot.duration_us * ratio))
            frame = _read_frame(shot.reference_clip_path, local_us)
            if frame is None:
                warnings.append(f"分镜 {shot.ordinal} 人物采样帧读取失败")
                continue
            h, w = frame.shape[:2]
            detections = detect(frame)
            face_detector.setInputSize((w, h))
            _, face_rows = face_detector.detect(frame)
            frame_observations = []
            used = set()
            for subject in subjects:
                key = source_keys.get((shot.ordinal, subject.get("label")))
                row = rows.get(key)
                if not row or row.get("identity_issue"):
                    continue
                boxes = [b["box"] for b in frame_boxes(subject.get("frame_boxes")) if b["frame"] == frame_index]
                single = len(subjects) == 1 and len(detections) == 1 and not boxes
                matches = [(i, b, score) for i, (b, score) in enumerate(detections)
                           if single or (len(boxes) == 1 and iou([b[0]/w,b[1]/h,b[2]/w,b[3]/h], boxes[0]) >= .60)]
                if len(matches) != 1 or matches[0][0] in used:
                    continue
                i, box, score = matches[0]
                # 检查一个检测框是否同时被多个 VLM 主体引用，阻止多人观察误映射。
                owners = sum(any(b["frame"] == frame_index and iou([box[0]/w,box[1]/h,box[2]/w,box[3]/h], b["box"]) >= .60
                                 for b in frame_boxes(s.get("frame_boxes"))) for s in subjects)
                if not single and owners != 1:
                    continue
                used.add(i)
                obs = Observation(shot.original_shot_id, episode_id, int(episode["sort_order"]), shot.ordinal,
                                  shot.start_us+local_us, local_us, tuple(box), None, shot.reference_clip_path,
                                  float(score), None, reid.infer(frame, box), None, False, "yolox-exact-vlm",
                                  frame_width=w, frame_height=h, clarity_score=_clarity_score(frame, box),
                                  body_completeness=_body_completeness(box, w, h),
                                  other_person_boxes=[b for j,(b,_) in enumerate(detections) if j != i])
                obs.source_observation_key = key
                matching_faces = [f for f in ([] if face_rows is None else face_rows)
                                  if box[0] <= f[0]+f[2]/2 <= box[0]+box[2] and box[1] <= f[1]+f[3]/2 <= box[1]+box[3]]
                if len(matching_faces) == 1:
                    face = matching_faces[0]
                    obs.face_bbox = tuple(int(v) for v in face[:4])
                    obs.face_visible, obs.face_score = True, float(face[-1])
                    obs.face_embedding = face_recognizer.feature(face_recognizer.alignCrop(frame, face)).flatten()
                frame_observations.append(obs)
            annotate_person_instances(frame_observations)
            for obs in frame_observations:
                # 匿名语义可能漏人；污染判断仍必须看到全部检测区域。
                from engine.app.character_person_instance_v9 import classify_person_instance
                others = [tuple(b) for b,_ in detections if tuple(b) != tuple(obs.bbox)]
                safety = classify_person_instance(person_bbox=obs.bbox, other_person_boxes=others,
                                                  frame_width=w, frame_height=h, proposal_source=obs.detection_source)
                obs.other_person_boxes = others
                obs.person_bbox, obs.person_crop_bbox = safety.person_bbox, safety.crop_bbox
                obs.instance_class, obs.gallery_eligible = safety.instance_class, safety.gallery_eligible
                obs.interference_ratio = safety.contamination_ratio
                attach_person_features(obs, extract_person_features(frame, obs))
                attach_v10_policy(obs)
                row = rows[obs.source_observation_key]
                try:
                    image, mask = isolate(frame, obs.person_bbox, segmenter=segmenter, other_boxes=others)
                except (ValueError, cv2.error):
                    warnings.append(f"分镜 {shot.ordinal} 人物前景提取失败，保留人工核对")
                    continue
                data = dict(observation={k:v for k,v in vars(obs).items() if k != "person_feature_bundle"},
                            bundle=asdict(obs.person_feature_bundle), display_quality=_representative_quality(obs),
                            source_time_us=obs.source_time_us, profile=PROFILE)
                identity = hashlib.sha256((row["anchor"] + obs.instance_id + hashlib.sha256(image).hexdigest()).encode()).hexdigest()
                pending.append(dict(id=identity, project_id=context.project_id, episode_id=episode_id,
                                    shot_id=obs.shot_id, observation_key=row["key"], anchor=row["anchor"],
                                    image=image, mask=mask, evidence_json=_json(data)))
    with LOCK:
        if inventory(context.project_id)["revision"] != expected:
            raise ValueError("提取期间人物或原片版本发生变化，请重新拉片")
        with studio.get_session() as session:
            for item in pending:
                if session.get(SourcePersonImage, item["id"]) is None:
                    session.add(SourcePersonImage(**item))
            for row in rows.values():
                for shot in targets:
                    if row["episode_id"] != episode_id or shot.original_shot_id not in {s["id"] for s in row["shots"]}:
                        continue
                    state_id = hashlib.sha256(f'{row["key"]}:{shot.original_shot_id}'.encode()).hexdigest()
                    state = session.get(SourcePersonCaptureState, state_id)
                    if state is None:
                        state = SourcePersonCaptureState(id=state_id, observation_key=row["key"], shot_id=shot.original_shot_id)
                        session.add(state)
                    state.anchor = row["anchor"]
                    ids = [p["id"] for p in pending if p["observation_key"] == row["key"] and p["shot_id"] == shot.original_shot_id]
                    state.image_ids_json = json.dumps(ids)
                    if not ids:
                        warnings.append(f'分镜 {shot.ordinal} 有人物尚未获得可靠独立图，需要核对位置')
            session.commit()
    result = auto_merge(context.project_id)
    return {**result, "image_count": len(pending), "warnings": sorted(set(warnings))}


def _restore(raw):
    import numpy as np
    from engine.app.character_visual_v5 import Observation
    from engine.app.character_person_features_v9 import PersonFeatureBundle
    data = json.loads(raw)
    values = data["observation"]
    obs = Observation(**{f.name: values[f.name] for f in fields(Observation) if f.name in values})
    for key, value in values.items():
        setattr(obs, key, value)
    channels = {"person_reid", "clothing_upper", "clothing_lower", "body_hist", "body_structure", "face"}
    obs.person_feature_bundle = PersonFeatureBundle(**{k: np.asarray(v, dtype=np.float32) if k in channels and v is not None else v
                                                      for k,v in data["bundle"].items()})
    return obs


def auto_merge(project_id):
    from engine.app.source_person_assets_v1 import LOCK, inventory, assign
    from engine.app.character_visual_v5 import TrackDraft
    from engine.app.character_identity_v101 import resolve_global_identities
    with LOCK:
        workspace = inventory(project_id)
        rows = {r["key"]: r for r in workspace["observations"] if not r.get("identity_issue")}
        tracks, observations = {}, {}
        with studio.get_session() as session:
            states = _states(session, rows)
            for image_id, key, anchor, shot_id, raw in session.execute(select(SourcePersonImage.id, SourcePersonImage.observation_key, SourcePersonImage.anchor, SourcePersonImage.shot_id,
                                                           SourcePersonImage.evidence_json).where(SourcePersonImage.project_id == project_id)):
                if key not in rows or anchor != rows[key]["anchor"] or not _active(states, image_id, key, shot_id, anchor):
                    continue
                obs = _restore(raw)
                bucket = (key, obs.shot_id)
                if bucket not in tracks:
                    tracks[bucket] = TrackDraft(obs.shot_id, obs.episode_id, obs.episode_order, obs.shot_ordinal)
                tracks[bucket].observations.append(obs)
                observations.setdefault(key, set()).add(obs.instance_id)
        candidates = resolve_global_identities(list(tracks.values()))
        assigned, count = {}, 0
        for candidate in candidates:
            for track in candidate.tracks:
                for obs in track.observations:
                    assigned[obs.instance_id] = candidate.id
        for candidate in candidates:
            metadata = getattr(candidate, "v10_metadata", {})
            if candidate.identity_status != "RESOLVED" or int(metadata.get("confirmed_gallery_shots", 0)) < 3 or int(metadata.get("confirmed_gallery_images", 0)) < 3:
                continue
            keys = [key for key, ids in observations.items() if {assigned.get(i) for i in ids} == {candidate.id}
                    and {s["id"] for s in rows[key]["shots"]} <= {shot for k,shot in tracks if k == key}]
            if not keys:
                continue
            existing = {rows[k]["character_id"] for k in keys if rows[k].get("character_id")}
            if len(existing) > 1:
                continue
            target_id = next(iter(existing), None)
            keys = [k for k in keys if not rows[k].get("character_id")]
            if not keys:
                continue
            current = inventory(project_id)
            current_rows = {r["key"]: r for r in current["observations"]}
            marks = {k: current_rows[k].get("extracted_localization") for k in keys}
            if any(not mark for mark in marks.values()):
                continue
            try:
                assign(project_id, keys, f'人物 {len(current["characters"])+1:03d}', target_id, current["revision"], marks,
                       decision_source="AUTO")
            except ValueError:
                continue  # 同镜冲突或并发修订保持待核对。
            count += len(keys)
        return {"auto_merged_observations": count}
