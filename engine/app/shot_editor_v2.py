"""V2 Shot 人工修正。

职责：
- 修改两个相邻 Shot 的公共边界；
- 在当前 Shot 内拆分；
- 合并当前 Shot 与下一 Shot；
- 为每次人工修正生成独立媒体，不覆盖历史 Revision；
- Shot 修改与 MANUAL Revision 在同一数据库事务提交；
- Shot 结构变化后把当前资产分析标记为 STALE。
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select

from engine.app.content_analysis_v2 import ContentAnalysisRun
from engine.app.media_v2 import MIN_SHOT_DURATION_US, _render_reference, _render_thumbnail
from engine.app.shot_revision_v2 import _create_revision_from_current, ensure_current_revision
from engine.app.studio_v2 import Episode, Shot, episode_dir, get_session, new_id, serialize_shot, utcnow


class ShotEditError(RuntimeError):
    """V2 Shot 编辑业务错误。"""


class _PendingMedia:
    """人工编辑媒体的两阶段文件。

    final 路径使用本次 edit token 的独立目录，因此可以先落盘再提交数据库；
    数据库失败时删除新文件，不会碰历史版本媒体。
    """

    def __init__(self, reference: Path, thumbnail: Path, tmp_reference: Path, tmp_thumbnail: Path) -> None:
        self.reference = reference
        self.thumbnail = thumbnail
        self.tmp_reference = tmp_reference
        self.tmp_thumbnail = tmp_thumbnail
        self.committed = False

    def commit_files(self) -> None:
        self.tmp_reference.replace(self.reference)
        self.tmp_thumbnail.replace(self.thumbnail)
        self.committed = True

    def cleanup(self) -> None:
        for path in (self.tmp_reference, self.tmp_thumbnail):
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass
        if self.committed:
            for path in (self.reference, self.thumbnail):
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


def _edit_paths(episode: Episode, shot_id: str, edit_token: str) -> tuple[Path, Path]:
    root = episode_dir(episode.project_id, episode.id) / "shots" / "manual" / edit_token
    return root / "reference" / f"{shot_id}.mp4", root / "thumbnails" / f"{shot_id}.jpg"


def _render_pending(source: Path, reference: Path, thumbnail: Path, start_us: int, end_us: int) -> _PendingMedia:
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


def _renumber_after_split(session: Any, shots: list[Shot], split_index: int) -> None:
    following = shots[split_index + 1 :]
    for item in following:
        item.ordinal = -item.ordinal
    session.flush()
    for item in following:
        item.ordinal = (-item.ordinal) + 1
    session.flush()


def _renumber_after_merge(session: Any, shots: list[Shot], merged_right_index: int) -> None:
    following = shots[merged_right_index + 1 :]
    for item in following:
        item.ordinal = -item.ordinal
    session.flush()
    for item in following:
        item.ordinal = (-item.ordinal) - 1
    session.flush()


def adjust_boundary(*, shot_id: str, side: str, source_time_us: int) -> list[dict[str, Any]]:
    """移动公共边界；同时更新左右 Shot，禁止 gap / overlap。"""

    if side not in {"start", "end"}:
        raise ShotEditError("side 只能是 start 或 end")

    pending: list[_PendingMedia] = []
    try:
        with get_session() as lookup:
            current = lookup.get(Shot, shot_id)
            if current is None:
                raise ShotEditError("Shot 不存在")
            episode_id = current.episode_id
        ensure_current_revision(episode_id)

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
            if not left.start_us < boundary_us < right.end_us:
                raise ShotEditError("新边界必须位于两个相邻 Shot 的总区间内部")
            _validate_duration(left.start_us, boundary_us, label="左侧 Shot")
            _validate_duration(boundary_us, right.end_us, label="右侧 Shot")

            source = Path(episode.source_path)
            if not source.is_file():
                raise ShotEditError("原视频文件不存在")
            token = f"EDIT_{uuid.uuid4().hex}"
            left_ref, left_thumb = _edit_paths(episode, left.id, token)
            right_ref, right_thumb = _edit_paths(episode, right.id, token)
            pending = [
                _render_pending(source, left_ref, left_thumb, left.start_us, boundary_us),
                _render_pending(source, right_ref, right_thumb, boundary_us, right.end_us),
            ]
            for item in pending:
                item.commit_files()

            left.end_us = boundary_us
            left.duration_us = left.end_us - left.start_us
            right.start_us = boundary_us
            right.duration_us = right.end_us - right.start_us
            _update_shot_media_fields(left, left_ref, left_thumb)
            _update_shot_media_fields(right, right_ref, right_thumb)
            episode.status = "SHOTS_EDITED"
            episode.updated_at = utcnow()
            _mark_assets_stale(session, episode.project_id)
            _create_revision_from_current(
                session,
                episode_id=episode.id,
                kind="MANUAL",
                note=f"修改 Shot 公共{'开始' if side == 'start' else '结束'}边界",
            )
            session.commit()
            return [serialize_shot(item) for item in _ordered_shots(session, episode.id)]
    except Exception:
        for item in pending:
            item.cleanup()
        raise


def split_shot(*, shot_id: str, source_time_us: int) -> list[dict[str, Any]]:
    """在当前 Shot 内拆分。左段保留原 Shot ID，右段生成新 ID。"""

    pending: list[_PendingMedia] = []
    try:
        with get_session() as lookup:
            current = lookup.get(Shot, shot_id)
            if current is None:
                raise ShotEditError("Shot 不存在")
            episode_id = current.episode_id
        ensure_current_revision(episode_id)

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
            if not shot.start_us < split_us < shot.end_us:
                raise ShotEditError("拆分点必须位于当前 Shot 内部")
            _validate_duration(shot.start_us, split_us, label="拆分后的左 Shot")
            _validate_duration(split_us, shot.end_us, label="拆分后的右 Shot")

            source = Path(episode.source_path)
            if not source.is_file():
                raise ShotEditError("原视频文件不存在")
            token = f"EDIT_{uuid.uuid4().hex}"
            right_id = new_id("SHOT")
            left_ref, left_thumb = _edit_paths(episode, shot.id, token)
            right_ref, right_thumb = _edit_paths(episode, right_id, token)
            old_end = shot.end_us
            pending = [
                _render_pending(source, left_ref, left_thumb, shot.start_us, split_us),
                _render_pending(source, right_ref, right_thumb, split_us, old_end),
            ]
            for item in pending:
                item.commit_files()

            _renumber_after_split(session, shots, index)
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
            session.flush()
            episode.status = "SHOTS_EDITED"
            episode.updated_at = utcnow()
            _mark_assets_stale(session, episode.project_id)
            _create_revision_from_current(session, episode_id=episode.id, kind="MANUAL", note="在播放头拆分 Shot")
            session.commit()
            return [serialize_shot(item) for item in _ordered_shots(session, episode.id)]
    except Exception:
        for item in pending:
            item.cleanup()
        raise


def merge_with_next(*, shot_id: str) -> list[dict[str, Any]]:
    """合并当前 Shot 与下一 Shot；保留左 Shot ID。"""

    pending: list[_PendingMedia] = []
    try:
        with get_session() as lookup:
            current = lookup.get(Shot, shot_id)
            if current is None:
                raise ShotEditError("Shot 不存在")
            episode_id = current.episode_id
        ensure_current_revision(episode_id)

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
            token = f"EDIT_{uuid.uuid4().hex}"
            left_ref, left_thumb = _edit_paths(episode, left.id, token)
            pending = [_render_pending(source, left_ref, left_thumb, left.start_us, right.end_us)]
            for item in pending:
                item.commit_files()

            left.end_us = right.end_us
            left.duration_us = left.end_us - left.start_us
            _update_shot_media_fields(left, left_ref, left_thumb)
            session.delete(right)
            session.flush()
            _renumber_after_merge(session, shots, index + 1)
            episode.status = "SHOTS_EDITED"
            episode.updated_at = utcnow()
            _mark_assets_stale(session, episode.project_id)
            _create_revision_from_current(session, episode_id=episode.id, kind="MANUAL", note="合并相邻 Shot")
            session.commit()
            return [serialize_shot(item) for item in _ordered_shots(session, episode.id)]
    except Exception:
        for item in pending:
            item.cleanup()
        raise
