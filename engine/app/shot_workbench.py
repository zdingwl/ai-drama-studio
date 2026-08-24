"""F05「镜头人工修正 / 拉片工作台」核心业务。

职责：
- 从 F04 ready Shot Candidate 初始化独立 Final Shot Draft；
- 保持 Final Shot 在 Source Domain integer microseconds 上连续、无 gap、无 overlap；
- 支持人工调整相邻边界、拆分镜头、合并镜头和最终确认；
- 为三栏工作台提供 F03 Proxy 播放路径和按 Source 时间抽取的预览帧。

不负责：
- 不修改 F04 `shot_candidates.detected_*` 自动证据；
- 不做人物识别、ASR、Scene、Qwen3-VL 或生成；
- 不把浏览器 player.currentTime 当成 Source absolute timestamp。
"""

from __future__ import annotations

import json
import subprocess
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from engine.app.core.database import init_database
from engine.app.preprocess import get_source_preprocess
from engine.app.projects import ProjectError, _read_valid_manifest
from engine.app.shot_detection import get_shot_detection

FFMPEG_FRAME_TIMEOUT_SECONDS = 60


class ShotWorkbenchError(RuntimeError):
    """F05 可以稳定映射到 HTTP error envelope 的业务错误。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class FinalShotRecord:
    """人工工作区中的生产级 Final Shot；后续 Feature 应通过该 ID 关联。"""

    id: str
    edit_set_id: str
    project_id: str
    ordinal: int
    final_start_us: int
    final_end_us: int
    duration_us: int
    origin_kind: str
    origin_candidate_ids: tuple[str, ...]
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["origin_candidate_ids"] = list(self.origin_candidate_ids)
        return payload


@dataclass(frozen=True)
class ShotWorkbenchRecord:
    """F05 页面一次读取所需的 Edit Set 与完整 Final Shot Timeline。"""

    id: str
    project_id: str
    source_detection_id: str
    status: str
    revision: int
    source_start_us: int
    source_end_us: int
    created_at: datetime
    updated_at: datetime
    confirmed_at: datetime | None
    shots: tuple[FinalShotRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["shots"] = [shot.to_dict() for shot in self.shots]
        return payload


def generate_shot_edit_set_id() -> str:
    """生成一套 F05 人工修正工作的稳定 UUID4 业务 ID。"""

    return f"SHOT_EDIT_{uuid.uuid4().hex}"


def generate_final_shot_id() -> str:
    """生成生产级 Final Shot UUID4 ID；边界调整后 ID 保持不变。"""

    return f"SHOT_{uuid.uuid4().hex}"


def initialize_shot_workbench(*, project_id: str, app_data_path: Path | None = None) -> ShotWorkbenchRecord:
    """从当前 F04 ready Candidate 一次性初始化独立 Final Shot Draft。

    已存在 F05 时保持幂等，直接返回当前工作区。初始化只复制时间和来源 Candidate ID，
    不 UPDATE F04 自动证据。
    """

    existing = get_shot_workbench(project_id=project_id, app_data_path=app_data_path)
    if existing is not None:
        return existing

    detection = get_shot_detection(project_id=project_id, app_data_path=app_data_path)
    if detection is None or detection.status != "ready":
        raise ShotWorkbenchError("SHOT_WORKBENCH_DETECTION_REQUIRED", "请先完成 F04 自动拉片")
    if detection.source_start_us is None or detection.source_end_us is None or not detection.candidates:
        raise ShotWorkbenchError("SHOT_WORKBENCH_INVALID_UPSTREAM", "F04 ready 结果缺少完整 Source Timeline")

    database_path = init_database(app_data_path)
    engine = _database_engine(database_path)
    edit_sets = _table(engine, "shot_edit_sets")
    final_shots = _table(engine, "final_shots")
    edit_set_id = generate_shot_edit_set_id()
    now = datetime.now(timezone.utc)

    rows = []
    for candidate in detection.candidates:
        rows.append(
            {
                "id": generate_final_shot_id(),
                "edit_set_id": edit_set_id,
                "project_id": project_id,
                "ordinal": candidate.ordinal,
                "final_start_us": candidate.detected_start_us,
                "final_end_us": candidate.detected_end_us,
                "duration_us": candidate.duration_us,
                "origin_kind": "auto",
                "origin_candidate_ids_json": _encode_origin_ids((candidate.id,)),
                "created_at": now,
                "updated_at": now,
            }
        )

    try:
        with engine.begin() as connection:
            connection.execute(
                edit_sets.insert().values(
                    id=edit_set_id,
                    project_id=project_id,
                    source_detection_id=detection.id,
                    status="editing",
                    revision=1,
                    source_start_us=detection.source_start_us,
                    source_end_us=detection.source_end_us,
                    created_at=now,
                    updated_at=now,
                    confirmed_at=None,
                )
            )
            connection.execute(final_shots.insert(), rows)
    except IntegrityError:
        # 两个页面几乎同时初始化时，唯一约束只允许一套；重新读取即可。
        ready = get_shot_workbench(project_id=project_id, app_data_path=app_data_path)
        if ready is not None:
            return ready
        raise ShotWorkbenchError("SHOT_WORKBENCH_INITIALIZE_FAILED", "镜头工作台初始化冲突")
    except SQLAlchemyError as exc:
        raise ShotWorkbenchError("SHOT_WORKBENCH_INITIALIZE_FAILED", "镜头工作台初始化失败") from exc
    finally:
        engine.dispose()

    result = get_shot_workbench(project_id=project_id, app_data_path=app_data_path)
    if result is None:
        raise ShotWorkbenchError("SHOT_WORKBENCH_INITIALIZE_FAILED", "镜头工作台创建后无法重新读取")
    return result


def get_shot_workbench(*, project_id: str, app_data_path: Path | None = None) -> ShotWorkbenchRecord | None:
    """读取当前项目 F05 Final Shot 工作区，并验证完整连续性与 F04 来源身份。"""

    database_path = init_database(app_data_path)
    engine = _database_engine(database_path)
    edit_sets = _table(engine, "shot_edit_sets")
    final_shots = _table(engine, "final_shots")
    try:
        with engine.connect() as connection:
            edit_row = connection.execute(
                edit_sets.select().where(edit_sets.c.project_id == project_id)
            ).mappings().first()
            if edit_row is None:
                return None
            shot_rows = list(
                connection.execute(
                    final_shots.select()
                    .where(final_shots.c.edit_set_id == edit_row["id"])
                    .order_by(final_shots.c.ordinal.asc())
                ).mappings().all()
            )

        detection = get_shot_detection(project_id=project_id, app_data_path=app_data_path)
        if detection is None or detection.id != edit_row["source_detection_id"]:
            raise ShotWorkbenchError(
                "SHOT_WORKBENCH_UPSTREAM_CHANGED",
                "F04 自动拉片结果与当前 Final Shot 来源不一致，请先处理上游变更",
            )
        shots = tuple(_row_to_final_shot(row) for row in shot_rows)
        _validate_final_timeline(
            shots=shots,
            source_start_us=edit_row["source_start_us"],
            source_end_us=edit_row["source_end_us"],
        )
        return _row_to_workbench(edit_row, shots)
    finally:
        engine.dispose()


def adjust_shot_boundary(
    *,
    project_id: str,
    left_shot_id: str,
    boundary_us: int,
    app_data_path: Path | None = None,
) -> ShotWorkbenchRecord:
    """移动两个相邻 Final Shot 的公共边界，始终同时更新左右两侧。

    参数中的 `left_shot_id` 表示边界左侧 Shot。首尾外边界不通过本接口编辑，因此不会
    改变整集覆盖范围，也不会产生 gap / overlap。
    """

    database_path = init_database(app_data_path)
    engine = _database_engine(database_path)
    edit_sets = _table(engine, "shot_edit_sets")
    final_shots = _table(engine, "final_shots")
    now = datetime.now(timezone.utc)
    try:
        with engine.begin() as connection:
            edit_row, rows = _load_edit_rows(connection, edit_sets, final_shots, project_id)
            _require_editing(edit_row)
            index = _find_shot_index(rows, left_shot_id)
            if index >= len(rows) - 1:
                raise ShotWorkbenchError("SHOT_WORKBENCH_BOUNDARY_INVALID", "最后一个镜头没有可向后的公共边界")
            left = rows[index]
            right = rows[index + 1]
            if not left["final_start_us"] < boundary_us < right["final_end_us"]:
                raise ShotWorkbenchError("SHOT_WORKBENCH_BOUNDARY_INVALID", "新边界必须位于两个相邻镜头的总区间内部")

            connection.execute(
                final_shots.update().where(final_shots.c.id == left["id"]).values(
                    final_end_us=boundary_us,
                    duration_us=boundary_us - left["final_start_us"],
                    origin_kind="manual",
                    updated_at=now,
                )
            )
            connection.execute(
                final_shots.update().where(final_shots.c.id == right["id"]).values(
                    final_start_us=boundary_us,
                    duration_us=right["final_end_us"] - boundary_us,
                    origin_kind="manual",
                    updated_at=now,
                )
            )
            _bump_revision(connection, edit_sets, edit_row, now)
    finally:
        engine.dispose()
    return _require_workbench(project_id, app_data_path)


def split_final_shot(
    *,
    project_id: str,
    shot_id: str,
    split_us: int,
    app_data_path: Path | None = None,
) -> ShotWorkbenchRecord:
    """在指定 Final Shot 内拆分（新增镜头）。原 Shot ID 保留给左段，新建右段 ID。"""

    database_path = init_database(app_data_path)
    engine = _database_engine(database_path)
    edit_sets = _table(engine, "shot_edit_sets")
    final_shots = _table(engine, "final_shots")
    now = datetime.now(timezone.utc)
    try:
        with engine.begin() as connection:
            edit_row, rows = _load_edit_rows(connection, edit_sets, final_shots, project_id)
            _require_editing(edit_row)
            index = _find_shot_index(rows, shot_id)
            shot = rows[index]
            if not shot["final_start_us"] < split_us < shot["final_end_us"]:
                raise ShotWorkbenchError("SHOT_WORKBENCH_SPLIT_INVALID", "拆分点必须严格位于当前镜头内部")

            # 唯一 ordinal 约束要求从末尾向后移动，先腾出 current.ordinal + 1。
            for following in reversed(rows[index + 1 :]):
                connection.execute(
                    final_shots.update().where(final_shots.c.id == following["id"]).values(
                        ordinal=following["ordinal"] + 1,
                        updated_at=now,
                    )
                )

            origin_json = shot["origin_candidate_ids_json"]
            connection.execute(
                final_shots.update().where(final_shots.c.id == shot["id"]).values(
                    final_end_us=split_us,
                    duration_us=split_us - shot["final_start_us"],
                    origin_kind="manual",
                    updated_at=now,
                )
            )
            connection.execute(
                final_shots.insert().values(
                    id=generate_final_shot_id(),
                    edit_set_id=edit_row["id"],
                    project_id=project_id,
                    ordinal=shot["ordinal"] + 1,
                    final_start_us=split_us,
                    final_end_us=shot["final_end_us"],
                    duration_us=shot["final_end_us"] - split_us,
                    origin_kind="manual",
                    origin_candidate_ids_json=origin_json,
                    created_at=now,
                    updated_at=now,
                )
            )
            _bump_revision(connection, edit_sets, edit_row, now)
    finally:
        engine.dispose()
    return _require_workbench(project_id, app_data_path)


def merge_final_shots(
    *,
    project_id: str,
    left_shot_id: str,
    app_data_path: Path | None = None,
) -> ShotWorkbenchRecord:
    """删除指定左 Shot 与下一 Shot 的公共边界并合并；保留左 Shot ID。"""

    database_path = init_database(app_data_path)
    engine = _database_engine(database_path)
    edit_sets = _table(engine, "shot_edit_sets")
    final_shots = _table(engine, "final_shots")
    now = datetime.now(timezone.utc)
    try:
        with engine.begin() as connection:
            edit_row, rows = _load_edit_rows(connection, edit_sets, final_shots, project_id)
            _require_editing(edit_row)
            index = _find_shot_index(rows, left_shot_id)
            if index >= len(rows) - 1:
                raise ShotWorkbenchError("SHOT_WORKBENCH_MERGE_INVALID", "最后一个镜头无法与下一镜合并")
            left = rows[index]
            right = rows[index + 1]
            merged_origins = _merge_origin_ids(
                _decode_origin_ids(left["origin_candidate_ids_json"]),
                _decode_origin_ids(right["origin_candidate_ids_json"]),
            )

            connection.execute(
                final_shots.update().where(final_shots.c.id == left["id"]).values(
                    final_end_us=right["final_end_us"],
                    duration_us=right["final_end_us"] - left["final_start_us"],
                    origin_kind="manual",
                    origin_candidate_ids_json=_encode_origin_ids(merged_origins),
                    updated_at=now,
                )
            )
            connection.execute(final_shots.delete().where(final_shots.c.id == right["id"]))
            # right 已删除形成 ordinal 空位，从前向后回填不会触发唯一约束冲突。
            for following in rows[index + 2 :]:
                connection.execute(
                    final_shots.update().where(final_shots.c.id == following["id"]).values(
                        ordinal=following["ordinal"] - 1,
                        updated_at=now,
                    )
                )
            _bump_revision(connection, edit_sets, edit_row, now)
    finally:
        engine.dispose()
    return _require_workbench(project_id, app_data_path)


def confirm_final_shots(*, project_id: str, app_data_path: Path | None = None) -> ShotWorkbenchRecord:
    """人工确认当前连续 Final Shot Timeline；确认后所有 F05 编辑接口只读锁定。"""

    database_path = init_database(app_data_path)
    engine = _database_engine(database_path)
    edit_sets = _table(engine, "shot_edit_sets")
    final_shots = _table(engine, "final_shots")
    now = datetime.now(timezone.utc)
    try:
        with engine.begin() as connection:
            edit_row, rows = _load_edit_rows(connection, edit_sets, final_shots, project_id)
            if edit_row["status"] == "confirmed":
                return _require_workbench(project_id, app_data_path)
            shots = tuple(_row_to_final_shot(row) for row in rows)
            _validate_final_timeline(
                shots=shots,
                source_start_us=edit_row["source_start_us"],
                source_end_us=edit_row["source_end_us"],
            )
            connection.execute(
                edit_sets.update().where(edit_sets.c.id == edit_row["id"]).values(
                    status="confirmed",
                    revision=edit_row["revision"] + 1,
                    updated_at=now,
                    confirmed_at=now,
                )
            )
    finally:
        engine.dispose()
    return _require_workbench(project_id, app_data_path)


def get_workbench_proxy_path(*, project_id: str, app_data_path: Path | None = None) -> Path:
    """返回 F05 播放器应读取的 F03 Proxy 绝对路径；不复制媒体。"""

    _require_workbench(project_id, app_data_path)
    preprocess = get_source_preprocess(project_id=project_id, app_data_path=app_data_path)
    if preprocess is None:
        raise ShotWorkbenchError("SHOT_WORKBENCH_MEDIA_MISSING", "F03 Proxy 已不存在")
    database_path = init_database(app_data_path)
    engine = _database_engine(database_path)
    projects = _table(engine, "projects")
    try:
        workspace = _load_workspace(engine, projects, project_id)
    finally:
        engine.dispose()
    path = _resolve_workspace_path(workspace, preprocess.proxy_relative_path)
    if not path.is_file():
        raise ShotWorkbenchError("SHOT_WORKBENCH_MEDIA_MISSING", "F03 proxy.mp4 文件不存在")
    return path


def render_workbench_frame(
    *,
    project_id: str,
    source_time_us: int,
    app_data_path: Path | None = None,
) -> Path:
    """按 Source 时间抽取单帧 JPEG，并缓存为可删除的 F05 UI 预览缓存。

    FFmpeg `-ss` 使用的是媒体相对时间，因此必须减去 Edit Set 的 Source 起点，不能把
    Source absolute timestamp 直接传给 FFmpeg。
    """

    workbench = _require_workbench(project_id, app_data_path)
    if not workbench.source_start_us <= source_time_us < workbench.source_end_us:
        raise ShotWorkbenchError("SHOT_WORKBENCH_FRAME_TIME_INVALID", "预览帧时间超出 Final Shot 时间轴")

    proxy_path = get_workbench_proxy_path(project_id=project_id, app_data_path=app_data_path)
    workspace = _project_workspace(project_id=project_id, app_data_path=app_data_path)
    cache_dir = workspace / ".cache" / "f05" / "frames"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{source_time_us}.jpg"
    if cache_path.is_file() and cache_path.stat().st_size > 0:
        return cache_path

    relative_seconds = (source_time_us - workbench.source_start_us) / 1_000_000
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{relative_seconds:.6f}",
        "-i",
        str(proxy_path),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        "-y",
        str(cache_path),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=FFMPEG_FRAME_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ShotWorkbenchError("SHOT_WORKBENCH_FFMPEG_UNAVAILABLE", "未找到 FFmpeg，无法生成镜头预览帧") from exc
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise ShotWorkbenchError("SHOT_WORKBENCH_FRAME_FAILED", "FFmpeg 生成镜头预览帧失败") from exc
    if completed.returncode != 0 or not cache_path.is_file() or cache_path.stat().st_size <= 0:
        cache_path.unlink(missing_ok=True)
        raise ShotWorkbenchError("SHOT_WORKBENCH_FRAME_FAILED", "镜头预览帧生成失败")
    return cache_path


def _require_workbench(project_id: str, app_data_path: Path | None) -> ShotWorkbenchRecord:
    record = get_shot_workbench(project_id=project_id, app_data_path=app_data_path)
    if record is None:
        raise ShotWorkbenchError("SHOT_WORKBENCH_NOT_INITIALIZED", "镜头工作台尚未初始化")
    return record


def _load_edit_rows(
    connection: sa.Connection,
    edit_sets: sa.Table,
    final_shots: sa.Table,
    project_id: str,
) -> tuple[sa.RowMapping, list[sa.RowMapping]]:
    edit_row = connection.execute(edit_sets.select().where(edit_sets.c.project_id == project_id)).mappings().first()
    if edit_row is None:
        raise ShotWorkbenchError("SHOT_WORKBENCH_NOT_INITIALIZED", "镜头工作台尚未初始化")
    rows = list(
        connection.execute(
            final_shots.select()
            .where(final_shots.c.edit_set_id == edit_row["id"])
            .order_by(final_shots.c.ordinal.asc())
        ).mappings().all()
    )
    if not rows:
        raise ShotWorkbenchError("SHOT_WORKBENCH_INVALID_RESULT", "Final Shot 数据为空")
    return edit_row, rows


def _require_editing(edit_row: sa.RowMapping) -> None:
    if edit_row["status"] != "editing":
        raise ShotWorkbenchError("SHOT_WORKBENCH_CONFIRMED", "Final Shots 已确认，不能继续修改")


def _find_shot_index(rows: list[sa.RowMapping], shot_id: str) -> int:
    for index, row in enumerate(rows):
        if row["id"] == shot_id:
            return index
    raise ShotWorkbenchError("SHOT_WORKBENCH_SHOT_NOT_FOUND", "没有找到当前 Final Shot")


def _bump_revision(connection: sa.Connection, edit_sets: sa.Table, edit_row: sa.RowMapping, now: datetime) -> None:
    connection.execute(
        edit_sets.update().where(edit_sets.c.id == edit_row["id"]).values(
            revision=edit_row["revision"] + 1,
            updated_at=now,
        )
    )


def _validate_final_timeline(*, shots: tuple[FinalShotRecord, ...], source_start_us: int, source_end_us: int) -> None:
    """统一验证跨行 Final Shot 连续性；数据库单行 CHECK 无法表达这些规则。"""

    if not shots:
        raise ShotWorkbenchError("SHOT_WORKBENCH_INVALID_RESULT", "Final Shot 至少需要一个镜头")
    if shots[0].final_start_us != source_start_us or shots[-1].final_end_us != source_end_us:
        raise ShotWorkbenchError("SHOT_WORKBENCH_INVALID_RESULT", "Final Shot 没有完整覆盖 Source 时间范围")
    for index, shot in enumerate(shots):
        if shot.ordinal != index + 1:
            raise ShotWorkbenchError("SHOT_WORKBENCH_INVALID_RESULT", "Final Shot ordinal 不连续")
        if shot.final_end_us <= shot.final_start_us or shot.duration_us != shot.final_end_us - shot.final_start_us:
            raise ShotWorkbenchError("SHOT_WORKBENCH_INVALID_RESULT", "Final Shot 时间或 duration 无效")
        if index + 1 < len(shots) and shot.final_end_us != shots[index + 1].final_start_us:
            raise ShotWorkbenchError("SHOT_WORKBENCH_INVALID_RESULT", "Final Shot 存在 gap 或 overlap")


def _row_to_workbench(row: sa.RowMapping, shots: tuple[FinalShotRecord, ...]) -> ShotWorkbenchRecord:
    return ShotWorkbenchRecord(
        id=row["id"],
        project_id=row["project_id"],
        source_detection_id=row["source_detection_id"],
        status=row["status"],
        revision=row["revision"],
        source_start_us=row["source_start_us"],
        source_end_us=row["source_end_us"],
        created_at=_as_datetime(row["created_at"]),
        updated_at=_as_datetime(row["updated_at"]),
        confirmed_at=_as_datetime(row["confirmed_at"]) if row["confirmed_at"] is not None else None,
        shots=shots,
    )


def _row_to_final_shot(row: sa.RowMapping) -> FinalShotRecord:
    return FinalShotRecord(
        id=row["id"],
        edit_set_id=row["edit_set_id"],
        project_id=row["project_id"],
        ordinal=row["ordinal"],
        final_start_us=row["final_start_us"],
        final_end_us=row["final_end_us"],
        duration_us=row["duration_us"],
        origin_kind=row["origin_kind"],
        origin_candidate_ids=_decode_origin_ids(row["origin_candidate_ids_json"]),
        created_at=_as_datetime(row["created_at"]),
        updated_at=_as_datetime(row["updated_at"]),
    )


def _encode_origin_ids(values: tuple[str, ...]) -> str:
    return json.dumps(list(values), ensure_ascii=True, separators=(",", ":"))


def _decode_origin_ids(value: str) -> tuple[str, ...]:
    try:
        decoded = json.loads(value)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ShotWorkbenchError("SHOT_WORKBENCH_INVALID_RESULT", "Final Shot 来源 Candidate 数据损坏") from exc
    if not isinstance(decoded, list) or not decoded or not all(isinstance(item, str) and item for item in decoded):
        raise ShotWorkbenchError("SHOT_WORKBENCH_INVALID_RESULT", "Final Shot 来源 Candidate 数据无效")
    return tuple(decoded)


def _merge_origin_ids(left: tuple[str, ...], right: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys((*left, *right)))


def _database_engine(database_path: Path) -> sa.Engine:
    return sa.create_engine(f"sqlite:///{database_path.as_posix()}", future=True)


def _table(engine: sa.Engine, table_name: str) -> sa.Table:
    metadata = sa.MetaData()
    return sa.Table(table_name, metadata, autoload_with=engine)


def _project_workspace(*, project_id: str, app_data_path: Path | None) -> Path:
    database_path = init_database(app_data_path)
    engine = _database_engine(database_path)
    projects = _table(engine, "projects")
    try:
        return _load_workspace(engine, projects, project_id)
    finally:
        engine.dispose()


def _load_workspace(engine: sa.Engine, projects: sa.Table, project_id: str) -> Path:
    with engine.connect() as connection:
        row = connection.execute(projects.select().where(projects.c.id == project_id)).mappings().first()
    if row is None or row["status"] != "ready":
        raise ProjectError("PROJECT_NOT_FOUND", "没有找到可使用的项目")
    workspace = Path(row["workspace_path"])
    if not workspace.is_dir():
        raise ProjectError("PROJECT_WORKSPACE_MISSING", "项目文件夹不存在或已被移动")
    _read_valid_manifest(workspace, project_id)
    return workspace


def _resolve_workspace_path(workspace: Path, relative_path: str) -> Path:
    root = workspace.resolve(strict=False)
    candidate = (root / Path(relative_path)).resolve(strict=False)
    if candidate != root and root not in candidate.parents:
        raise ShotWorkbenchError("SHOT_WORKBENCH_MEDIA_MISSING", "F05 Proxy 路径超出 Project Workspace")
    return candidate


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
