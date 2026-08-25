"""Character V6 Evidence 原子持久化。

职责：
- 在一次数据库事务里保存 Character / Track / Scene / Shot Evidence；
- CharacterCandidate 明确保存 RESOLVED / UNRESOLVED 身份状态；
- RESOLVED 与 UNRESOLVED 分别编号，Unresolved 仍完整保留真实 Face/Track Evidence；
- ContentAnalysisRun counts 同时记录 Final-ready 与待解析数量；
- 只有全部 Evidence 保存成功后才切换 Current Run。

为什么：V6 的核心产品约束是“视觉碎片 != Final Character”。身份状态必须和 Evidence 一起原子落库，
不能先提交旧 Candidate 再事后补 identity_status，否则补写失败时会发布一个语义不完整的新 Current。
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from engine.app.character_visual_v2 import cosine, save_candidate_cover
from engine.app.content_analysis_v2 import (
    AnalysisDialogue,
    CharacterCandidate,
    CharacterTrack,
    ContentAnalysisError,
    ContentAnalysisRun,
    SceneCandidate,
    ShotSceneEvidence,
    SpeakerSegment,
)
from engine.app.studio_v2 import Shot, get_session, new_id, utcnow

PROFILE_VERSION = "f05-assets-v6-global-identity"


def persist_results_v6(
    *,
    run_id: str,
    project_id: str,
    shots: list[dict[str, Any]],
    candidates: list[Any],
    scenes: list[Any],
    dialogues: list[dict[str, Any]],
    speaker_segments: list[dict[str, Any]],
    component_status: dict[str, str],
) -> None:
    """把 V6 全部 Evidence 原子写入数据库并安全切换 Current。

    输入：当前 Run、Global Identity Candidates、Scene Segments、Current Shots。
    输出：无；成功后 Run 成为 Current。
    为什么：任何一个 Candidate/Track/Scene 保存失败都必须整体回滚，旧 Current 继续可用。
    """

    scene_by_shot: dict[str, str] = {}
    resolved_ordinal = 0
    unresolved_ordinal = 0

    with get_session() as session:
        run = session.get(ContentAnalysisRun, run_id)
        if run is None or run.project_id != project_id:
            raise ContentAnalysisError("V6 Asset Run 记录丢失")

        for candidate in candidates:
            identity_status = str(getattr(candidate, "identity_status", "UNRESOLVED"))
            if identity_status == "RESOLVED":
                resolved_ordinal += 1
                auto_label = f"人物 {resolved_ordinal:03d}"
            else:
                unresolved_ordinal += 1
                auto_label = f"待解析人物 {unresolved_ordinal:03d}"

            ordinal = resolved_ordinal if identity_status == "RESOLVED" else resolved_ordinal + unresolved_ordinal
            cover_path = save_candidate_cover(run_id, candidate, ordinal)
            confidence = sum(candidate.scores) / len(candidate.scores) if candidate.scores else None
            face_track_count = sum(
                1 for track in candidate.tracks
                if any(obs.face_visible for obs in track.observations)
            )
            v6_metadata = dict(getattr(candidate, "v6_metadata", {}) or {})
            evidence = {
                "identity_status": identity_status,
                "final_asset_eligible": identity_status == "RESOLVED",
                "identity": "Global Identity Graph; Face primary; CLEAN ReID temporal support",
                "face_track_count": face_track_count,
                "body_only_extension_track_count": len(candidate.tracks) - face_track_count,
                "profile": PROFILE_VERSION,
                **v6_metadata,
            }
            session.add(CharacterCandidate(
                id=candidate.id,
                run_id=run_id,
                project_id=project_id,
                ordinal=ordinal,
                auto_label=auto_label,
                track_count=len(candidate.tracks),
                shot_count=len({item.shot_id for item in candidate.tracks}),
                confidence=confidence,
                cover_path=cover_path,
                evidence_json=json.dumps(evidence, ensure_ascii=False),
            ))

            for track in candidate.tracks:
                if not track.observations:
                    continue
                representative = max(
                    track.observations,
                    key=lambda item: (
                        1 if item.face_visible else 0,
                        float(getattr(item, "face_score", item.detection_score)),
                        item.detection_score,
                    ),
                )
                face_scores = [
                    float(getattr(item, "face_score", item.detection_score))
                    for item in track.observations if item.face_visible
                ]
                body_scores = [
                    cosine(track.body_hist, item.body_hist)
                    for item in track.observations if item.body_hist is not None
                ]
                valid_body_scores = [value for value in body_scores if value is not None]
                session.add(CharacterTrack(
                    id=new_id("CHAR_TRACK"),
                    run_id=run_id,
                    candidate_id=candidate.id,
                    shot_id=track.shot_id,
                    start_us=min(item.source_time_us for item in track.observations),
                    end_us=max(item.source_time_us for item in track.observations) + 1,
                    representative_source_us=representative.source_time_us,
                    bbox_json=json.dumps(list(representative.bbox)),
                    sample_count=len(track.observations),
                    face_visible=any(item.face_visible for item in track.observations),
                    mean_face_score=sum(face_scores) / len(face_scores) if face_scores else None,
                    body_evidence_score=sum(valid_body_scores) / len(valid_body_scores) if valid_body_scores else None,
                    evidence_json=json.dumps({
                        "identity_status": identity_status,
                        "final_asset_eligible": identity_status == "RESOLVED",
                        "samples": [
                            {
                                "source_time_us": item.source_time_us,
                                "bbox": list(item.bbox),
                                "face_bbox": list(item.face_bbox) if item.face_bbox else None,
                                "score": item.detection_score,
                                "face_score": float(getattr(item, "face_score", 0.0)),
                                "face_visible": item.face_visible,
                                "detection_source": item.detection_source,
                            }
                            for item in track.observations
                        ],
                    }, ensure_ascii=False),
                ))

        for ordinal, scene in enumerate(scenes, start=1):
            session.add(SceneCandidate(
                id=scene.id,
                run_id=run_id,
                project_id=project_id,
                ordinal=ordinal,
                auto_label=f"场景 {ordinal:03d}",
                shot_count=len(scene.shot_ids),
                cover_path=scene.cover_path,
                evidence_json=json.dumps({
                    "method": "episode-contiguous HSV scene candidate segmentation",
                    "profile": PROFILE_VERSION,
                }, ensure_ascii=False),
            ))
            scene_confidence = sum(scene.scores) / len(scene.scores) if scene.scores else 1.0
            for shot_id in scene.shot_ids:
                scene_by_shot[shot_id] = scene.id
                session.add(ShotSceneEvidence(
                    id=new_id("SHOT_SCENE"),
                    run_id=run_id,
                    shot_id=shot_id,
                    scene_candidate_id=scene.id,
                    confidence=scene_confidence,
                ))

        # 历史兼容；03 新 Run 正常传空数组，后续内容剧本模块可继续复用这些表。
        for item in speaker_segments:
            session.add(SpeakerSegment(
                id=item["id"],
                run_id=run_id,
                episode_id=item["episode_id"],
                start_us=item["start_us"],
                end_us=item["end_us"],
                speaker_label=item["speaker_label"],
                confidence=item.get("confidence"),
            ))
        for item in dialogues:
            session.add(AnalysisDialogue(
                id=item["id"],
                run_id=run_id,
                episode_id=item["episode_id"],
                shot_id=item["shot_id"],
                source_start_us=item["source_start_us"],
                source_end_us=item["source_end_us"],
                shot_start_us=item["shot_start_us"],
                shot_end_us=item["shot_end_us"],
                ai_text=item["ai_text"],
                language=item.get("language"),
                speaker_label=item.get("speaker_label"),
                speaker_candidate_id=item.get("speaker_candidate_id"),
                speaker_mapping_confidence=item.get("speaker_mapping_confidence"),
                dialogue_type=item.get("dialogue_type") or "unknown",
                emotion=item.get("emotion"),
                speaking_style=item.get("speaking_style"),
                confidence=item.get("confidence"),
                evidence_json=json.dumps(item.get("evidence") or {}, ensure_ascii=False),
            ))

        resolved_character_count_by_shot: dict[str, int] = {}
        unresolved_character_count_by_shot: dict[str, int] = {}
        for candidate in candidates:
            bucket = (
                resolved_character_count_by_shot
                if getattr(candidate, "identity_status", "UNRESOLVED") == "RESOLVED"
                else unresolved_character_count_by_shot
            )
            for shot_id in {track.shot_id for track in candidate.tracks}:
                bucket[shot_id] = bucket.get(shot_id, 0) + 1

        for shot_payload in shots:
            shot = session.get(Shot, shot_payload["id"])
            if shot is None:
                continue
            parts: list[str] = []
            resolved = resolved_character_count_by_shot.get(shot.id, 0)
            unresolved = unresolved_character_count_by_shot.get(shot.id, 0)
            if resolved:
                parts.append(f"{resolved} 个已解析人物")
            if unresolved:
                parts.append(f"{unresolved} 个待解析人物 Evidence")
            if scene_by_shot.get(shot.id):
                parts.append("已归入场景候选")
            shot.short_description = "；".join(parts) if parts else "暂无人物 / 场景 / 道具自动 Evidence"

        # 直到这里所有 ORM 对象都准备完成，先 flush；任何约束错误都会在 Current 切换前暴露。
        session.flush()

        for previous in session.scalars(select(ContentAnalysisRun).where(
            ContentAnalysisRun.project_id == project_id,
            ContentAnalysisRun.is_current.is_(True),
        )).all():
            previous.is_current = False

        normal_statuses = {"READY", "NO_CHARACTER", "NO_SCENE"}
        core_values = [component_status.get(key, "") for key in ("characters", "scenes")]
        warnings = any(value not in normal_statuses for value in core_values) or component_status.get("props") != "READY"
        if unresolved_ordinal:
            warnings = True

        component_status = dict(component_status)
        component_status["characters_profile"] = "V6_GLOBAL_IDENTITY"
        component_status["resolved_characters"] = str(resolved_ordinal)
        component_status["unresolved_character_evidence"] = str(unresolved_ordinal)

        run.status = "READY_WITH_WARNINGS" if warnings else "READY"
        run.is_current = True
        run.profile_version = PROFILE_VERSION
        run.component_status_json = json.dumps(component_status, ensure_ascii=False)
        run.counts_json = json.dumps({
            "character_candidates": len(candidates),
            "resolved_character_candidates": resolved_ordinal,
            "unresolved_character_candidates": unresolved_ordinal,
            "character_tracks": sum(len(item.tracks) for item in candidates),
            "scene_candidates": len(scenes),
            "prop_candidates": 0,
            "dialogues": len(dialogues),
            "speaker_segments": len(speaker_segments),
        }, ensure_ascii=False)
        run.completed_at = utcnow()
        session.commit()
