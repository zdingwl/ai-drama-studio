"""F04「重新自动拉片」安全重跑业务。

旧 READY 结果会一直保留到新结果完整成功，再用单事务原子替换。
F05 一旦建立 Final Shot Edit Set，本接口立即禁止重跑，避免替换 F05 正在追溯的 Auto Evidence。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError

from engine.app.core.database import init_database
from engine.app.core.media_time import derived_to_source_microseconds
from engine.app.preprocess import get_source_preprocess
from engine.app.shot_detection import (
    DETECTOR_NAME,
    DETECTOR_PROFILE_VERSION,
    DETECTOR_THRESHOLD,
    MIN_BOUNDARY_GAP_US,
    PROXY_DURATION_TOLERANCE_US,
    TRANSNET_PACKAGE_VERSION,
    ShotDetectionError,
    ShotDetectionRecord,
    _database_engine,
    _hash_file,
    _load_workspace,
    _require_proxy_integrity,
    _resolve_workspace_path,
    _table,
    build_shot_candidates,
    detect_proxy_cut_events,
    generate_shot_detection_id,
    get_shot_detection,
    inspect_proxy_timeline,
)


def rerun_shot_detection(*, project_id: str, app_data_path: Path | None = None) -> ShotDetectionRecord:
    """显式重新执行 F04，并在成功后原子替换旧 Auto Evidence。

    关键约束：
    - 必须已有 READY F04；
    - F05 尚未开始；一旦存在 `shot_edit_sets`，禁止替换其上游 Detection；
    - 旧结果在新模型推理期间不删除；
    - 新结果通过 PTS / Proxy 完整性校验后才在一个事务中替换。
    """

    old_detection = get_shot_detection(project_id=project_id, app_data_path=app_data_path)
    if old_detection is None:
        raise ShotDetectionError(
            "SHOT_DETECTION_RERUN_NOT_READY",
            "当前项目还没有可重新运行的自动拉片结果，请先执行一次自动拉片",
        )
    if old_detection.status != "ready":
        raise ShotDetectionError("SHOT_DETECTION_IN_PROGRESS", "当前自动拉片尚未完成，不能重新运行")

    database_path = init_database(app_data_path)
    engine = _database_engine(database_path)
    projects = _table(engine, "projects")
    runs = _table(engine, "shot_detection_runs")
    candidate_table = _table(engine, "shot_candidates")

    try:
        # F05 Edit Set 保存 source_detection_id。进入 F05 后再替换 F04 会让 Final Shot 失去
        # 可追溯的自动来源，因此在任何 GPU 推理之前直接拒绝，避免浪费计算资源。
        if sa.inspect(engine).has_table("shot_edit_sets"):
            edit_sets = _table(engine, "shot_edit_sets")
            with engine.connect() as connection:
                existing_edit = connection.execute(
                    edit_sets.select().where(edit_sets.c.project_id == project_id)
                ).mappings().first()
            if existing_edit is not None:
                raise ShotDetectionError(
                    "SHOT_DETECTION_RERUN_BLOCKED_BY_F05",
                    "当前项目已经进入 F05 镜头修正，不能再替换 F04 自动证据",
                )

        workspace = _load_workspace(engine, projects, project_id)
        preprocess = get_source_preprocess(project_id=project_id, app_data_path=app_data_path)
        if preprocess is None:
            raise ShotDetectionError("SHOT_DETECTION_PREPROCESS_REQUIRED", "请先完成 F03 视频预处理")

        proxy_path = _resolve_workspace_path(workspace, preprocess.proxy_relative_path)
        initial_integrity = _hash_file(proxy_path)
        _require_proxy_integrity(initial_integrity, preprocess)

        timeline = inspect_proxy_timeline(proxy_path=proxy_path)
        if abs(timeline.duration_us - preprocess.proxy_duration_us) > PROXY_DURATION_TOLERANCE_US:
            raise ShotDetectionError(
                "SHOT_DETECTION_INVALID_RESULT",
                "F04 重新读取的 Proxy 时长与 F03 记录不一致，旧结果已保留",
            )

        evidence = detect_proxy_cut_events(
            proxy_path=proxy_path,
            frame_pts_us=timeline.frame_pts_us,
            threshold=DETECTOR_THRESHOLD,
        )

        new_detection_id = generate_shot_detection_id()
        candidates = build_shot_candidates(
            detection_id=new_detection_id,
            project_id=project_id,
            cut_events=evidence.events,
            proxy_start_us=timeline.start_us,
            proxy_end_us=timeline.end_us,
            proxy_to_source_offset_us=preprocess.proxy_to_source_offset_us,
            min_boundary_gap_us=MIN_BOUNDARY_GAP_US,
        )

        final_integrity = _hash_file(proxy_path)
        _require_proxy_integrity(final_integrity, preprocess)
        if final_integrity != initial_integrity:
            raise ShotDetectionError(
                "SHOT_DETECTION_PROXY_INTEGRITY_MISMATCH",
                "Proxy 在重新自动拉片过程中发生变化，旧结果已保留",
            )

        source_start_us = derived_to_source_microseconds(timeline.start_us, preprocess.proxy_to_source_offset_us)
        source_end_us = derived_to_source_microseconds(timeline.end_us, preprocess.proxy_to_source_offset_us)
        created_at = datetime.now(timezone.utc)
        completed_at = datetime.now(timezone.utc)

        try:
            with engine.begin() as connection:
                current = connection.execute(
                    runs.select().where(runs.c.project_id == project_id)
                ).mappings().first()
                if current is None or current["id"] != old_detection.id or current["status"] != "ready":
                    raise ShotDetectionError(
                        "SHOT_DETECTION_RERUN_CONFLICT",
                        "自动拉片结果在重新计算期间已发生变化，请刷新页面后再试",
                    )

                connection.execute(candidate_table.delete().where(candidate_table.c.detection_id == old_detection.id))
                deleted = connection.execute(
                    runs.delete().where(
                        runs.c.id == old_detection.id,
                        runs.c.project_id == project_id,
                        runs.c.status == "ready",
                    )
                )
                if deleted.rowcount != 1:
                    raise ShotDetectionError(
                        "SHOT_DETECTION_RERUN_CONFLICT",
                        "旧自动拉片结果无法安全替换，请刷新页面后再试",
                    )

                connection.execute(
                    runs.insert().values(
                        id=new_detection_id,
                        project_id=project_id,
                        source_video_id=preprocess.source_video_id,
                        status="ready",
                        detector_name=DETECTOR_NAME,
                        detector_profile_version=DETECTOR_PROFILE_VERSION,
                        detector_threshold=DETECTOR_THRESHOLD,
                        min_boundary_gap_us=MIN_BOUNDARY_GAP_US,
                        detector_package_version=TRANSNET_PACKAGE_VERSION,
                        torch_version=evidence.torch_version,
                        detector_device=evidence.detector_device,
                        ffprobe_version=timeline.ffprobe_version,
                        preprocess_profile_version=preprocess.profile_version,
                        proxy_sha256_snapshot=preprocess.proxy_sha256,
                        proxy_to_source_offset_us=preprocess.proxy_to_source_offset_us,
                        proxy_start_us=timeline.start_us,
                        proxy_end_us=timeline.end_us,
                        source_start_us=source_start_us,
                        source_end_us=source_end_us,
                        analyzed_frame_count=evidence.analyzed_frame_count,
                        detected_cut_count=len(candidates) - 1,
                        shot_count=len(candidates),
                        created_at=created_at,
                        completed_at=completed_at,
                    )
                )
                connection.execute(candidate_table.insert(), [candidate.to_dict() for candidate in candidates])
        except ShotDetectionError:
            raise
        except SQLAlchemyError as exc:
            raise ShotDetectionError(
                "SHOT_DETECTION_FAILED",
                "重新自动拉片结果替换失败，旧结果已保留",
            ) from exc

        ready = get_shot_detection(project_id=project_id, app_data_path=app_data_path)
        if ready is None or ready.id != new_detection_id:
            raise ShotDetectionError("SHOT_DETECTION_FAILED", "重新自动拉片完成后无法读取新结果")
        return ready
    finally:
        engine.dispose()
