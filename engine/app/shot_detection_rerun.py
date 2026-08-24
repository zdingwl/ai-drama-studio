"""F04「重新自动拉片」安全重跑业务。

为什么单独存在：
- F04 首次检测已经把当时的 PyTorch / device / Shot Candidate 保存成 Auto Evidence；
- 用户升级 CUDA、修复模型环境或需要重新验证时，应当允许显式重跑；
- 但不能为了重跑先删除旧 READY 结果，否则新推理失败会把已有证据一起丢失。

因此本模块采用“先计算、后原子替换”：
1. 旧 READY 结果在整个模型推理期间保持可用；
2. 新 TransNetV2 结果全部完成、PTS 对齐、Proxy 双重完整性校验通过后；
3. 在一个 SQLite transaction 中删除旧 Run/Candidates，并写入新的 READY Run/Candidates；
4. 任意失败都会回滚事务，旧结果仍然存在。

本模块不修改 F03 媒体，不产生新视频文件，也不创建 F05 Final Shot。
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

    输入：
        project_id: 当前项目稳定业务 ID。
        app_data_path: 测试时可覆盖 App Data；正常 UI 不传。

    返回：
        新一次 READY Detection Run，包含新的 runtime 快照和 Shot Candidates。

    关键安全规则：
    - 必须已经存在 READY F04；没有旧结果时应走普通“开始自动拉片”；
    - 旧结果在新模型推理阶段不删除；
    - 重新读取并校验 F03 Proxy，禁止对被替换的 Proxy 重跑；
    - commit 前再次校验 Proxy，防止推理过程中媒体变化；
    - 最终替换必须是单事务，失败即保留旧 READY 结果；
    - 不允许传入 threshold/device/model path，仍使用冻结 Profile V1。
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

        # 这里不先删除旧 READY。只有新结果已经完整计算后，才在同一事务里替换。
        # 如果任意 INSERT/DELETE/约束失败，SQLite 会回滚，旧 Auto Evidence 继续可用。
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

                connection.execute(
                    candidate_table.delete().where(candidate_table.c.detection_id == old_detection.id)
                )
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
