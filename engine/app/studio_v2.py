"""AI Drama Studio V2 的核心数据模型与业务服务。

V2 以“参考视频驱动重制”为主线：
Project -> Episode -> Preprocess -> Shot/Reference Clip -> downstream assets.
旧版 F01-F06 表和单视频限制不再参与新业务。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from fastapi import UploadFile
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

APP_FORMAT_VERSION = "2.0"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def data_root() -> Path:
    configured = os.getenv("AI_DRAMA_STUDIO_HOME")
    root = Path(configured).expanduser().resolve() if configured else (Path.cwd() / "data_v2").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def workspace_root() -> Path:
    root = data_root() / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    return root


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "v2_projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_language: Mapped[str] = mapped_column(String(32), nullable=False)
    target_language: Mapped[str] = mapped_column(String(32), nullable=False)
    target_region: Mapped[str] = mapped_column(String(64), nullable=False)
    project_format_version: Mapped[str] = mapped_column(String(16), nullable=False, default=APP_FORMAT_VERSION)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    episodes: Mapped[list["Episode"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Episode(Base):
    __tablename__ = "v2_episodes"
    __table_args__ = (UniqueConstraint("project_id", "sort_order", name="uq_v2_episode_project_sort"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="IMPORTED")
    duration_us: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    project: Mapped[Project] = relationship(back_populates="episodes")
    preprocess: Mapped["Preprocess | None"] = relationship(back_populates="episode", uselist=False, cascade="all, delete-orphan")
    shots: Mapped[list["Shot"]] = relationship(back_populates="episode", cascade="all, delete-orphan")


class Preprocess(Base):
    __tablename__ = "v2_preprocess"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("v2_episodes.id", ondelete="CASCADE"), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    proxy_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_info_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    episode: Mapped[Episode] = relationship(back_populates="preprocess")


class Shot(Base):
    __tablename__ = "v2_shots"
    __table_args__ = (UniqueConstraint("episode_id", "ordinal", name="uq_v2_shot_episode_ordinal"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("v2_episodes.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    start_us: Mapped[int] = mapped_column(Integer, nullable=False)
    end_us: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_us: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_clip_path: Mapped[str] = mapped_column(Text, nullable=False)
    thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    keyframes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    short_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    shot_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    camera_motion: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="READY")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    episode: Mapped[Episode] = relationship(back_populates="shots")


class Character(Base):
    __tablename__ = "v2_characters"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class Scene(Base):
    __tablename__ = "v2_scenes"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class Prop(Base):
    __tablename__ = "v2_props"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_key_prop: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class Dialogue(Base):
    __tablename__ = "v2_dialogues"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    shot_id: Mapped[str] = mapped_column(ForeignKey("v2_shots.id", ondelete="CASCADE"), index=True)
    speaker_character_id: Mapped[str | None] = mapped_column(ForeignKey("v2_characters.id", ondelete="SET NULL"), nullable=True)
    dialogue_type: Mapped[str] = mapped_column(String(32), nullable=False, default="dialogue")
    start_us: Mapped[int] = mapped_column(Integer, nullable=False)
    end_us: Mapped[int] = mapped_column(Integer, nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    translated_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    localized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    emotion: Mapped[str | None] = mapped_column(String(64), nullable=True)
    speaking_style: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Asset(Base):
    __tablename__ = "v2_assets"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    asset_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class Voice(Base):
    __tablename__ = "v2_voices"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("v2_projects.id", ondelete="CASCADE"), index=True)
    character_id: Mapped[str | None] = mapped_column(ForeignKey("v2_characters.id", ondelete="SET NULL"), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    voice_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class Generation(Base):
    __tablename__ = "v2_generations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    shot_id: Mapped[str] = mapped_column(ForeignKey("v2_shots.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    strategy: Mapped[str] = mapped_column(String(64), nullable=False, default="REUSE_REFERENCE")
    target_duration_us: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PLANNED")
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


DB_PATH = data_root() / "studio_v2.sqlite3"
ENGINE = create_engine(f"sqlite:///{DB_PATH.as_posix()}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, expire_on_commit=False)


def init_database() -> None:
    """初始化正式 V2 schema；仅创建缺失表，不删除或重写历史表/字段。"""

    # P1.1 的 Breakdown Draft 与 ShotRevision 共用 studio_v2.Base。
    # 延迟 import 既避免模块加载期的循环依赖，也保证直接调用 init_database()
    # 时不会因为 main.py 的 import 顺序不同而漏建 Breakdown / ShotRevision 表。
    from engine.app import breakdown_models_v1 as _breakdown_models_v1  # noqa: F401

    Base.metadata.create_all(ENGINE)


def get_session() -> Session:
    return SessionLocal()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_dir(project_id: str) -> Path:
    path = workspace_root() / project_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def episode_dir(project_id: str, episode_id: str) -> Path:
    path = project_dir(project_id) / "episodes" / episode_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def serialize_project(project: Project, episodes: Iterable[Episode] | None = None) -> dict[str, Any]:
    payload = {
        "id": project.id,
        "name": project.name,
        "source_language": project.source_language,
        "target_language": project.target_language,
        "target_region": project.target_region,
        "project_format_version": project.project_format_version,
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
    }
    if episodes is not None:
        payload["episodes"] = [serialize_episode(item) for item in episodes]
    return payload


def serialize_episode(episode: Episode) -> dict[str, Any]:
    preprocess = episode.preprocess
    return {
        "id": episode.id,
        "project_id": episode.project_id,
        "title": episode.title,
        "original_filename": episode.original_filename,
        "sort_order": episode.sort_order,
        "status": episode.status,
        "duration_us": episode.duration_us,
        "width": episode.width,
        "height": episode.height,
        "fps": episode.fps,
        "preprocess_status": preprocess.status if preprocess else None,
        "shot_count": len(episode.shots),
        "created_at": episode.created_at.isoformat(),
    }


def serialize_shot(shot: Shot) -> dict[str, Any]:
    return {
        "id": shot.id,
        "episode_id": shot.episode_id,
        "ordinal": shot.ordinal,
        "start_us": shot.start_us,
        "end_us": shot.end_us,
        "duration_us": shot.duration_us,
        "reference_url": f"/api/shots/{shot.id}/reference",
        "thumbnail_url": f"/api/shots/{shot.id}/thumbnail" if shot.thumbnail_path else None,
        "keyframes": json.loads(shot.keyframes_json) if shot.keyframes_json else [],
        "short_description": shot.short_description,
        "shot_type": shot.shot_type,
        "camera_motion": shot.camera_motion,
        "status": shot.status,
    }


def create_project(*, name: str, source_language: str, target_language: str, target_region: str) -> dict[str, Any]:
    name = name.strip()
    if not name:
        raise ValueError("项目名称不能为空")
    project = Project(id=new_id("PROJECT"), name=name, source_language=source_language.strip(), target_language=target_language.strip(), target_region=target_region.strip())
    with get_session() as session:
        session.add(project)
        session.commit()
        session.refresh(project)
        project_dir(project.id)
        return serialize_project(project, [])


def list_projects() -> list[dict[str, Any]]:
    with get_session() as session:
        projects = session.scalars(select(Project).order_by(Project.created_at.desc())).all()
        result: list[dict[str, Any]] = []
        for project in projects:
            episodes = session.scalars(select(Episode).where(Episode.project_id == project.id).order_by(Episode.sort_order)).all()
            for episode in episodes:
                _ = episode.preprocess
                _ = episode.shots
            result.append(serialize_project(project, episodes))
        return result


def get_project(project_id: str) -> dict[str, Any] | None:
    with get_session() as session:
        project = session.get(Project, project_id)
        if project is None:
            return None
        episodes = session.scalars(select(Episode).where(Episode.project_id == project.id).order_by(Episode.sort_order)).all()
        for episode in episodes:
            _ = episode.preprocess
            _ = episode.shots
        return serialize_project(project, episodes)


def _safe_filename(filename: str) -> str:
    name = Path(filename).name.strip().replace("\x00", "")
    return name or "video.mp4"


def _copy_upload(upload: UploadFile, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as target:
        shutil.copyfileobj(upload.file, target, length=1024 * 1024)


def import_episode(*, project_id: str, upload: UploadFile, title: str | None = None) -> dict[str, Any]:
    filename = _safe_filename(upload.filename or "video.mp4")
    episode_id = new_id("EPISODE")
    with get_session() as session:
        project = session.get(Project, project_id)
        if project is None:
            raise LookupError("项目不存在")
        current_max = session.scalars(select(Episode.sort_order).where(Episode.project_id == project_id).order_by(Episode.sort_order.desc())).first()
        sort_order = (current_max or 0) + 1
        ext = Path(filename).suffix.lower() or ".mp4"
        source_path = episode_dir(project_id, episode_id) / "source" / f"original{ext}"
        _copy_upload(upload, source_path)
        episode = Episode(id=episode_id, project_id=project_id, title=(title or Path(filename).stem).strip() or f"第{sort_order}集", original_filename=filename, source_path=str(source_path), source_sha256=file_sha256(source_path), sort_order=sort_order, status="IMPORTED")
        session.add(episode)
        project.updated_at = utcnow()
        session.commit()
        session.refresh(episode)
        return serialize_episode(episode)


def reorder_episodes(*, project_id: str, episode_ids: list[str]) -> list[dict[str, Any]]:
    with get_session() as session:
        episodes = session.scalars(select(Episode).where(Episode.project_id == project_id).order_by(Episode.sort_order)).all()
        existing_ids = [item.id for item in episodes]
        if sorted(existing_ids) != sorted(episode_ids):
            raise ValueError("排序列表必须包含项目当前全部剧集且不能重复")
        by_id = {item.id: item for item in episodes}
        for index, episode_id in enumerate(episode_ids, start=1):
            by_id[episode_id].sort_order = -index
        session.flush()
        for index, episode_id in enumerate(episode_ids, start=1):
            by_id[episode_id].sort_order = index
        project = session.get(Project, project_id)
        if project:
            project.updated_at = utcnow()
        session.commit()
        ordered = [by_id[item_id] for item_id in episode_ids]
        for episode in ordered:
            _ = episode.preprocess
            _ = episode.shots
        return [serialize_episode(item) for item in ordered]


def delete_episode(episode_id: str) -> None:
    with get_session() as session:
        episode = session.get(Episode, episode_id)
        if episode is None:
            raise LookupError("剧集不存在")
        project_id = episode.project_id
        path = episode_dir(project_id, episode.id)
        session.delete(episode)
        session.commit()
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
        remaining = session.scalars(select(Episode).where(Episode.project_id == project_id).order_by(Episode.sort_order)).all()
        for index, item in enumerate(remaining, start=1):
            item.sort_order = index
        session.commit()


def get_episode_record(episode_id: str) -> Episode | None:
    with get_session() as session:
        episode = session.get(Episode, episode_id)
        if episode is None:
            return None
        _ = episode.preprocess
        _ = episode.shots
        session.expunge(episode)
        return episode


def get_episode(episode_id: str) -> dict[str, Any] | None:
    with get_session() as session:
        episode = session.get(Episode, episode_id)
        if episode is None:
            return None
        _ = episode.preprocess
        _ = episode.shots
        return serialize_episode(episode)


def list_episode_records(project_id: str) -> list[Episode]:
    with get_session() as session:
        episodes = session.scalars(select(Episode).where(Episode.project_id == project_id).order_by(Episode.sort_order)).all()
        for item in episodes:
            _ = item.preprocess
            _ = item.shots
            session.expunge(item)
        return list(episodes)


def upsert_preprocess(*, episode_id: str, status: str, proxy_path: str | None = None, audio_path: str | None = None, media_info: dict[str, Any] | None = None, error_message: str | None = None) -> None:
    with get_session() as session:
        episode = session.get(Episode, episode_id)
        if episode is None:
            raise LookupError("剧集不存在")
        record = session.scalar(select(Preprocess).where(Preprocess.episode_id == episode_id))
        if record is None:
            record = Preprocess(id=new_id("PREPROCESS"), episode_id=episode_id)
            session.add(record)
        record.status = status
        record.proxy_path = proxy_path if proxy_path is not None else record.proxy_path
        record.audio_path = audio_path if audio_path is not None else record.audio_path
        record.media_info_json = json.dumps(media_info, ensure_ascii=False) if media_info is not None else record.media_info_json
        record.error_message = error_message
        record.completed_at = utcnow() if status == "READY" else None
        episode.status = "PREPROCESSED" if status == "READY" else ("PREPROCESSING" if status == "PROCESSING" else episode.status)
        if media_info:
            episode.duration_us = int(media_info.get("duration_us") or 0) or episode.duration_us
            episode.width = media_info.get("width")
            episode.height = media_info.get("height")
            episode.fps = media_info.get("fps")
        episode.updated_at = utcnow()
        session.commit()


def replace_shots(episode_id: str, shot_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    with get_session() as session:
        episode = session.get(Episode, episode_id)
        if episode is None:
            raise LookupError("剧集不存在")
        existing = session.scalars(select(Shot).where(Shot.episode_id == episode_id)).all()
        for item in existing:
            session.delete(item)
        session.flush()
        shots: list[Shot] = []
        for payload in shot_payloads:
            shot = Shot(id=new_id("SHOT"), episode_id=episode_id, **payload)
            session.add(shot)
            shots.append(shot)
        episode.status = "SHOTS_READY"
        episode.updated_at = utcnow()
        session.commit()
        for shot in shots:
            session.refresh(shot)
        return [serialize_shot(item) for item in shots]


def list_shots(episode_id: str) -> list[dict[str, Any]]:
    with get_session() as session:
        shots = session.scalars(select(Shot).where(Shot.episode_id == episode_id).order_by(Shot.ordinal)).all()
        return [serialize_shot(item) for item in shots]


def get_shot_path(shot_id: str, kind: str) -> Path | None:
    with get_session() as session:
        shot = session.get(Shot, shot_id)
        if shot is None:
            return None
        raw = shot.reference_clip_path if kind == "reference" else shot.thumbnail_path
        return Path(raw) if raw else None