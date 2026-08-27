"""Character Evidence 原子持久化（历史文件名 V6）。

职责：
- 在一次数据库事务里保存 Character / Track / Scene / Shot Evidence；
- CharacterCandidate 明确保存 RESOLVED / UNRESOLVED 身份状态；
- RESOLVED 与 UNRESOLVED 分别编号；
- ContentAnalysisRun counts 同时记录 Final-ready 与待解析数量；
- 只有全部 Evidence 保存成功后才切换 Current Run。

V10 兼容：如果 Observation 带 Person Evidence 元数据，Track 代表帧按人物图质量 / 可靠度优先，
不再按 face_visible 优先。这样侧身、背影、多角色同框拆出的单人图不会被正脸帧天然压制。

V10.1 兼容：已通过 known-identity recovery 挂回确认人物的 Track 会把 recovery source / score /
policy 一起写入 CharacterTrack.evidence_json，供 Final Shot Binding 使用 Shot 级存在置信度。
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
FORMAL_PROFILE_PREFIXES = ("f05-assets-v9", "f05-assets-v10")


def _representative_rank(item: Any) -> tuple[float, ...]:
    """Rank a Track representative without introducing a V10 frontal-face bias."""

    if hasattr(item, "person_evidence_eligible"):
        eligible = 1.0 if bool(getattr(item, "person_evidence_eligible", False)) else 0.0
        quality = max(0.0, min(1.0, float(getattr(item, "person_feature_quality", 0.0) or 0.0)))
        reliability = max(0.0, min(1.0, float(getattr(item, "person_evidence_reliability", 0.0) or 0.0)))
        body = max(0.0, min(1.0, float(getattr(item, "body_completeness", 0.0) or 0.0)))
        clarity = max(0.0, min(1.0, float(getattr(item, "clarity_score", 0.0) or 0.0)))
        detection = max(0.0, min(1.0, float(getattr(item, "detection_score", 0.0) or 0.0)))
        face = max(0.0, min(1.0, float(getattr(item, "face_score", 0.0) or 0.0)))
        return (
            eligible,
            quality * (0.72 + 0.28 * reliability),
            body,
            clarity,
            detection,
            face,
        )

    # Historical pre-V10 behavior stays unchanged for old runs/tests.
    return (
        1.0 if bool(getattr(item, "face_visible", False)) else 0.0,
        float(getattr(item, "face_score", getattr(item, "detection_score", 0.0))),
        float(getattr(item, "detection_score", 0.0)),
    )


def _persistence_profile(run: ContentAnalysisRun) -> str:
    """Preserve a formal V9/V10 profile instead of temporarily downgrading it to V6."""

    value = str(run.profile_version or "")
    return value if value.startswith(FORMAL_PROFILE_PREFIXES) else PROFILE_VERSION


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
    """把人物 / Scene 全部 Evidence 原子写入数据库并安全切换 Current。"""

    scene_by_shot: dict[str, str] = {}
    resolved_ordinal = 0
    unresolved_ordinal = 0

    with get_session() as session:
        run = session.get(ContentAnalysisRun, run_id)
        if run is None or run.project_id != project_id:
            raise ContentAnalysisError("Asset Run 记录丢失")
        run_profile = _persistence_profile(run)

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
                "profile": run_profile,
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
                representative = max(track.observations, key=_representative_rank)
                face_scores = [
                    float(getattr(item, "face_score", item.detection_score))
                    for item in track.observations if item.face_visible
                ]
                body_scores = [
                    cosine(track.body_hist, item.body_hist)
                    for item in track.observations if item.body_hist is not None
                ]
                valid_body_scores = [value for value in body_scores if value is not None]
                identity_recovery = dict(getattr(track, "identity_recovery", {}) or {})
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
                        "identity_recovery": identity_recovery or None,
                        "representative_policy": (
                            "V10 person-image-quality-first" if hasattr(representative, "person_evidence_eligible")
                            else "historical-face-first"
                        ),
                        "samples": [
                            {
                                "source_time_us": item.source_time_us,
                                "bbox": list(item.bbox),
                                "face_bbox": list(item.face_bbox) if item.face_bbox else None,
                                "score": item.detection_score,
                                "face_score": float(getattr(item, "face_score", 0.0)),
                                "face_visible": item.face_visible,
                                "detection_source": item.detection_source,
                                "instance_id": getattr(item, "instance_id", None),
                                "instance_class": getattr(item, "instance_class", None),
                                "person_evidence_eligible": getattr(item, "person_evidence_eligible", None),
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
                    "profile": run_profile,
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
        component_status.setdefault("characters_profile", "V6_GLOBAL_IDENTITY")
        component_status["resolved_characters"] = str(resolved_ordinal)
        component_status["unresolved_character_evidence"] = str(unresolved_ordinal)

        run.status = "READY_WITH_WARNINGS" if warnings else "READY"
        run.is_current = True
        run.profile_version = run_profile
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
