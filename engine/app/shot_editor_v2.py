"""V2 Shot 人工修正。

职责：
- 修改两个相邻 Shot 的公共边界；
- 在当前 Shot 内拆分；
- 合并当前 Shot 与下一 Shot；
- 重新生成受影响 Shot 的 Reference Clip / Thumbnail；
- Shot 结构变化后把当前资产分析标记为 STALE。

为什么存在：拉片页面只有在用户能够真正修正错误 Cut 时才有意义。
自动 TransNet 结果仍保留在执行历史里；本模块只维护当前可生产 Shot 集合。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select

from engine.app.content_analysis_v2 import ContentAnalysisRun
from engine.app.media_v2 import MIN_SHOT_DURATION_US, _render_reference, _render_thumbnail
from engine.app.studio_v2 import Episode, Shot, episode_dir, get_session, new_id, serialize_shot, utcnow


class ShotEditError(RuntimeError):
    """V2 Shot 编辑业务错误。"""


class _PendingMedia:
    def __init__(self, reference: Path, thumbnail: Path, tmp_reference: Path, tmp_thumbnail: Path) -> None:
        self.reference = reference
        self.thumbnail = thumbnail
        self.tmp_reference = tmp_reference
        self.tmp_thumbnail = tmp_thumbnail

    def commit(self) -> None:
        self.tmp_reference.replace(self.reference)
        self.tmp_thumbnail.replace(self.thumbnail)

    def cleanup(self) -> None:
        for path in (self.tmp_reference, self.tmp_thumbnail):
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass


def _ordered_shots(session: Any, episode_id: str) -> list[Shot]:
    return list(session.scalars(select(Shot).where(Shot.episode_id == episode_id).order_by(Shot.ordinal)).all())


def _shot_index(shots: list[Shot], shot_id: str) -> int:
    for index, shot in enumerate(shots):
        if shot.id == shot_id:
            return index
    raise ShotEditError("Shot 不存在")


def _paths_for_new_shot(episode: Episode, shot_id: str) -> tuple[Path, Path]:
    root = episode_dir(episode.project_id, episode.id) / "shots"
    return root / "reference" / f"manual_{shot_id}.mp4", root / "thumbnails" / f"manual_{shot_id}.jpg"


def _render_pending(source: Path, reference: Path, thumbnail: Path, start_us: int, end_us: int) -> _PendingMedia:
    """先生成临时文件，全部成功后再替换正式媒体，避免 FFmpeg 失败留下半成品。"""

    duration_us = end_us - start_us
    reference.parent.mkdir(parents=True, exist_ok=True)
    thumbnail.parent.mkdir(parents=True, exist_ok=True)
    tmp_reference = reference.with_name(f"{reference.stem}.pending{reference.suffix}")
    tmp_thumbnail = thumbnail.with_name(f"{thumbnail.stem}.pending{thumbnail.suffix}")
    for path in (tmp_reference, tmp_thumbnail):
        if path.exists():
            path.unlink()
    try:
        _render_reference(source, tmp_reference, start_us, duration_us)
        _render_thumbnail(tmp_reference, tmp_thumbnail, duration_us)
        return _PendingMedia(reference, thumbnail, tmp_reference, tmp_thumbnail)
    except Exception:
        for path in (tmp_reference, tmp_thumbnail):
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass
        raise


def _update_shot_media_fields(shot: Shot, reference: Path, thumbnail: Path) -> None:
    shot.reference_clip_path = str(reference)
    shot.thumbnail_path = str(thumbnail)
    shot.keyframes_json = json.dumps([{"kind": "middle", "path": str(thumbnail)}], ensure_ascii=False)
    shot.status = "MANUAL"


def _mark_assets_stale(session: Any, project_id: str) -> None:
    """镜头时间轴改变后旧资产 Evidence 仍可查看，但不能继续当作最新结果。"""

    runs = session.scalars(
        select(ContentAnalysisRun).where(
            ContentAnalysisRun.project_id == project_id,
            ContentAnalysisRun.is_current.is_(True),
        )
    ).all()
    for run in runs:
        if run.status not in {"PROCESSING", "FAILED", "STALE"}:
            run.status = "STALE"


def _validate_duration(start_us: int, end_us: int, *, label: str) -> None:
    if end_us - start_us < MIN_SHOT_DURATION_US:
        raise ShotEditError(f"{label}不能短于 {MIN_SHOT_DURATION_US / 1000:.0f} ms")


def adjust_boundary(*, shot_id: str, side: str, source_time_us: int) -> list[dict[str, Any]]:
    """移动公共边界。

    输入：当前 Shot、start/end 侧、新 Source Domain 微秒时间。
    输出：该 Episode 完整 Shot 列表。
    为什么：公共边界必须同时更新左右两 Shot，禁止产生 gap / overlap。
    """

    if side not in {"start", "end"}:
        raise ShotEditError("side 只能是 start 或 end")

    pending: list[_PendingMedia] = []
    try:
        with get_session() as session:
            shot = session.get(Shot, shot_id)
            if shot is None:
                raise ShotEditError("Shot 不存在")
            episode = session.get(Episode, shot.episode_id)
            if episode is None:
                raise ShotEditError("剧集不存在")
            shots = _ordered_shots(session, episode.id)
            index = _shot_index(shots, shot_id)

            if side == "start":
                if index == 0:
                    raise ShotEditError("第一个 Shot 的起点固定为视频起点")
                left, right = shots[index - 1], shots[index]
            else:
                if index >= len(shots) - 1:
                    raise ShotEditError("最后一个 Shot 的终点固定为视频终点")
                left, right = shots[index], shots[index + 1]

            boundary_us = int(source_time_us)
            _validate_duration(left.start_us, boundary_us, label="左侧 Shot")
            _validate_duration(boundary_us, right.end_us, label="右侧 Shot")
            if not left.start_us < boundary_us < right.end_us:
                raise ShotEditError("新边界必须位于两个相邻 Shot 的总区间内部")

            source = Path(episode.source_path)
            if not source.is_file():
                raise ShotEditError("原视频文件不存在")

            left_ref = Path(left.reference_clip_path)
            left_thumb = Path(left.thumbnail_path) if left.thumbnail_path else _paths_for_new_shot(episode, left.id)[1]
            right_ref = Path(right.reference_clip_path)
            right_thumb = Path(right.thumbnail_path) if right.thumbnail_path else _paths_for_new_shot(episode, right.id)[1]
            pending = [
                _render_pending(source, left_ref, left_thumb, left.start_us, boundary_us),
                _render_pending(source, right_ref, right_thumb, boundary_us, right.end_us),
            ]

            left.end_us = boundary_us
            left.duration_us = left.end_us - left.start_us
            right.start_us = boundary_us
            right.duration_us = right.end_us - right.start_us
            _update_shot_media_fields(left, left_ref, left_thumb)
            _update_shot_media_fields(right, right_ref, right_thumb)
            episode.status = "SHOTS_EDITED"
            episode.updated_at = utcnow()
            _mark_assets_stale(session, episode.project_id)
            session.commit()

            for item in pending:
                item.commit()
            return [serialize_shot(item) for item in _ordered_shots(session, episode.id)]
    except Exception:
        for item in pending:
            item.cleanup()
        raise


def split_shot(*, shot_id: str, source_time_us: int) -> list[dict[str, Any]]:
    """在当前 Shot 内拆分。左段保留原 Shot ID，右段生成新 ID。"""

    pending: list[_PendingMedia] = []
    try:
        with get_session() as session:
            shot = session.get(Shot, shot_id)
            if shot is None:
                raise ShotEditError("Shot 不存在")
            episode = session.get(Episode, shot.episode_id)
            if episode is None:
                raise ShotEditError("剧集不存在")
            shots = _ordered_shots(session, episode.id)
            index = _shot_index(shots, shot_id)
            split_us = int(source_time_us)
            _validate_duration(shot.start_us, split_us, label="拆分后的左 Shot")
            _validate_duration(split_us, shot.end_us, label="拆分后的右 Shot")
            if not shot.start_us < split_us < shot.end_us:
                raise ShotEditError("拆分点必须位于当前 Shot 内部")

            source = Path(episode.source_path)
            if not source.is_file():
                raise ShotEditError("原视频文件不存在")

            # 从末尾向后移动 ordinal，避免唯一约束冲突。
            for following in reversed(shots[index + 1 :]):
                following.ordinal += 1
            session.flush()

            old_end = shot.end_us
            left_ref = Path(shot.reference_clip_path)
            left_thumb = Path(shot.thumbnail_path) if shot.thumbnail_path else _paths_for_new_shot(episode, shot.id)[1]

            right_id = new_id("SHOT")
            right_ref, right_thumb = _paths_for_new_shot(episode, right_id)
            pending = [
                _render_pending(source, left_ref, left_thumb, shot.start_us, split_us),
                _render_pending(source, right_ref, right_thumb, split_us, old_end),
            ]

            shot.end_us = split_us
            shot.duration_us = split_us - shot.start_us
            _update_shot_media_fields(shot, left_ref, left_thumb)

            right = Shot(
                id=right_id,
                episode_id=episode.id,
                ordinal=shot.ordinal + 1,
                start_us=split_us,
                end_us=old_end,
                duration_us=old_end - split_us,
                reference_clip_path=str(right_ref),
                thumbnail_path=str(right_thumb),
                keyframes_json=json.dumps([{"kind": "middle", "path": str(right_thumb)}], ensure_ascii=False),
                short_description=None,
                shot_type=None,
                camera_motion=None,
                status="MANUAL",
            )
            session.add(right)
            episode.status = "SHOTS_EDITED"
            episode.updated_at = utcnow()
            _mark_assets_stale(session, episode.project_id)
            session.commit()

            for item in pending:
                item.commit()
            return [serialize_shot(item) for item in _ordered_shots(session, episode.id)]
    except Exception:
        for item in pending:
            item.cleanup()
        raise


def merge_with_next(*, shot_id: str) -> list[dict[str, Any]]:
    """合并当前 Shot 与下一 Shot；保留左 Shot ID。"""

    pending: list[_PendingMedia] = []
    remove_after_commit: list[Path] = []
    try:
        with get_session() as session:
            left = session.get(Shot, shot_id)
            if left is None:
                raise ShotEditError("Shot 不存在")
            episode = session.get(Episode, left.episode_id)
            if episode is None:
                raise ShotEditError("剧集不存在")
            shots = _ordered_shots(session, episode.id)
            index = _shot_index(shots, shot_id)
            if index >= len(shots) - 1:
                raise ShotEditError("最后一个 Shot 无法与下一镜合并")
            right = shots[index + 1]

            source = Path(episode.source_path)
            if not source.is_file():
                raise ShotEditError("原视频文件不存在")
            left_ref = Path(left.reference_clip_path)
            left_thumb = Path(left.thumbnail_path) if left.thumbnail_path else _paths_for_new_shot(episode, left.id)[1]
            pending = [_render_pending(source, left_ref, left_thumb, left.start_us, right.end_us)]

            if right.reference_clip_path:
                remove_after_commit.append(Path(right.reference_clip_path))
            if right.thumbnail_path:
                remove_after_commit.append(Path(right.thumbnail_path))

            left.end_us = right.end_us
            left.duration_us = left.end_us - left.start_us
            _update_shot_media_fields(left, left_ref, left_thumb)
            session.delete(right)
            session.flush()
            for following in shots[index + 2 :]:
                following.ordinal -= 1
            episode.status = "SHOTS_EDITED"
            episode.updated_at = utcnow()
            _mark_assets_stale(session, episode.project_id)
            session.commit()

            for item in pending:
                item.commit()
            for path in remove_after_commit:
                try:
                    if path.exists() and path not in {left_ref, left_thumb}:
                        path.unlink()
                except OSError:
                    pass
            return [serialize_shot(item) for item in _ordered_shots(session, episode.id)]
    except Exception:
        for item in pending:
            item.cleanup()
        raise
