import hashlib
import json
import mimetypes
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.artifacts.enums import ArtifactNamespace
from app.artifacts.service import create_artifact, get_current_artifacts
from app.core.errors import AppError
from app.projects.enums import VIDEO_PROJECT_TYPES, ProjectType
from app.projects.service import get_project
from app.skills.models import ArtifactType
from app.sources.enums import SourceAssetKind, SourceDocumentFormat
from app.sources.media import decode_preflight, probe_video
from app.sources.models import Episode, SourceAsset, SourceDocument
from app.sources.schemas import EpisodeRead, SourceAssetRead, SourceDocumentRead
from app.sources.storage import cleanup_asset_file, move_temp_to_immutable_source, stream_upload_to_temp

_VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
_TEXT_SUFFIXES = {".txt": SourceDocumentFormat.TXT, ".md": SourceDocumentFormat.MARKDOWN, ".markdown": SourceDocumentFormat.MARKDOWN}
_TEXT_PROJECT_TYPES = frozenset(set(ProjectType) - set(VIDEO_PROJECT_TYPES))


def _asset_mime_type(upload_content_type: str | None, filename: str, *, fallback: str) -> str:
    if upload_content_type and upload_content_type != "application/octet-stream":
        return upload_content_type
    return mimetypes.guess_type(filename)[0] or fallback


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _ensure_video_project(project_type: ProjectType) -> None:
    if project_type not in VIDEO_PROJECT_TYPES:
        raise AppError("VIDEO_SOURCE_NOT_ALLOWED", "当前项目类型不接收原片视频", status_code=422)


def _ensure_text_project(project_type: ProjectType) -> None:
    if project_type not in _TEXT_PROJECT_TYPES:
        raise AppError("TEXT_SOURCE_NOT_ALLOWED", "当前项目类型不接收小说/剧本文本", status_code=422)


def _asset_read(asset: SourceAsset) -> SourceAssetRead:
    return SourceAssetRead.model_validate(asset)


def _episode_read(episode: Episode, asset: SourceAsset) -> EpisodeRead:
    return EpisodeRead(
        id=episode.id,
        project_id=episode.project_id,
        source_asset=_asset_read(asset),
        episode_order=episode.episode_order,
        duration_us=episode.duration_us,
        width=episode.width,
        height=episode.height,
        codec_name=episode.codec_name,
        avg_frame_rate=episode.avg_frame_rate,
        has_audio=episode.has_audio,
        created_at=episode.created_at,
    )


def _document_read(document: SourceDocument, asset: SourceAsset) -> SourceDocumentRead:
    return SourceDocumentRead(
        id=document.id,
        project_id=document.project_id,
        source_asset=_asset_read(asset),
        revision=document.revision,
        document_format=document.document_format,
        encoding=document.encoding,
        char_count=document.char_count,
        is_current=document.is_current,
        created_at=document.created_at,
    )


def list_source_assets(db: Session, project_id: str) -> list[SourceAssetRead]:
    get_project(db, project_id)
    rows = db.scalars(
        select(SourceAsset).where(SourceAsset.project_id == project_id).order_by(SourceAsset.created_at.asc())
    ).all()
    return [_asset_read(row) for row in rows]


def _episode_rows(db: Session, project_id: str) -> list[tuple[Episode, SourceAsset]]:
    statement = (
        select(Episode, SourceAsset)
        .join(SourceAsset, Episode.source_asset_id == SourceAsset.id)
        .where(Episode.project_id == project_id)
        .order_by(Episode.episode_order.asc(), Episode.created_at.asc())
    )
    return list(db.execute(statement).all())


def list_episodes(db: Session, project_id: str) -> list[EpisodeRead]:
    project = get_project(db, project_id)
    _ensure_video_project(project.project_type)
    return [_episode_read(episode, asset) for episode, asset in _episode_rows(db, project_id)]


def _current_source_artifact(db: Session, project_id: str, artifact_type: ArtifactType):
    return next((row for row in get_current_artifacts(db, project_id) if row.type_enum == artifact_type), None)


def _refresh_video_artifact(db: Session, project_id: str) -> None:
    project = get_project(db, project_id)
    rows = _episode_rows(db, project_id)
    payload = [
        {
            "episode_id": episode.id,
            "source_asset_id": asset.id,
            "episode_order": episode.episode_order,
            "sha256": asset.sha256,
        }
        for episode, asset in rows
    ]
    fingerprint = _canonical_sha256(payload)
    current = _current_source_artifact(db, project_id, ArtifactType.SOURCE_VIDEO)
    if current is not None and current.input_fingerprint == fingerprint:
        db.commit()
        return
    create_artifact(
        db,
        project_id=project_id,
        artifact_type=ArtifactType.SOURCE_VIDEO,
        namespace=ArtifactNamespace.SOURCE,
        label=f"原片素材（{len(rows)} 集）",
        input_fingerprint=fingerprint,
        skill_id=project.root_skill_id,
        skill_version=project.root_skill_version,
        metadata_json={"episode_ids": [item["episode_id"] for item in payload], "episodes": payload},
    )


def _refresh_text_artifact(db: Session, project_id: str, document: SourceDocument, asset: SourceAsset) -> None:
    project = get_project(db, project_id)
    payload = {"document_id": document.id, "revision": document.revision, "source_asset_id": asset.id, "sha256": asset.sha256}
    fingerprint = _canonical_sha256(payload)
    current = _current_source_artifact(db, project_id, ArtifactType.SOURCE_TEXT)
    if current is not None and current.input_fingerprint == fingerprint:
        db.commit()
        return
    create_artifact(
        db,
        project_id=project_id,
        artifact_type=ArtifactType.SOURCE_TEXT,
        namespace=ArtifactNamespace.SOURCE,
        label=f"原始文本 r{document.revision}",
        input_fingerprint=fingerprint,
        skill_id=project.root_skill_id,
        skill_version=project.root_skill_version,
        metadata_json={"document_id": document.id, "source_asset_id": asset.id, "document_revision": document.revision},
    )


async def ingest_video_uploads(db: Session, project_id: str, uploads: list[UploadFile]) -> list[EpisodeRead]:
    project = get_project(db, project_id)
    _ensure_video_project(project.project_type)
    if not uploads:
        raise AppError("VIDEO_UPLOAD_REQUIRED", "请选择至少一个视频文件", status_code=422)

    next_order = int(db.scalar(select(func.max(Episode.episode_order)).where(Episode.project_id == project_id)) or 0) + 1
    created_paths: list[str] = []
    touched = False
    requested_episode_ids: list[str] = []

    try:
        for upload in uploads:
            upload_content_type = upload.content_type
            temp_path, sha256, size_bytes, filename = await stream_upload_to_temp(
                upload,
                project_id=project_id,
                asset_kind=SourceAssetKind.VIDEO,
            )
            if Path(filename).suffix.lower() not in _VIDEO_SUFFIXES:
                temp_path.unlink(missing_ok=True)
                raise AppError("VIDEO_EXTENSION_UNSUPPORTED", "暂不支持该视频文件格式", status_code=422)

            existing_asset = db.scalar(
                select(SourceAsset).where(
                    SourceAsset.project_id == project_id,
                    SourceAsset.asset_kind == SourceAssetKind.VIDEO,
                    SourceAsset.sha256 == sha256,
                )
            )
            if existing_asset is not None:
                temp_path.unlink(missing_ok=True)
                existing_episode = db.scalar(select(Episode).where(Episode.source_asset_id == existing_asset.id))
                if existing_episode is None:
                    raise AppError("SOURCE_ASSET_INCONSISTENT", "已存在视频素材缺少 Episode 记录", status_code=500)
                requested_episode_ids.append(existing_episode.id)
                continue

            probe = probe_video(temp_path)
            decode_preflight(temp_path)
            asset_id = str(uuid4())
            _, relative_path = move_temp_to_immutable_source(
                temp_path,
                project_id=project_id,
                asset_id=asset_id,
                original_filename=filename,
            )
            created_paths.append(relative_path)
            asset = SourceAsset(
                id=asset_id,
                project_id=project_id,
                asset_kind=SourceAssetKind.VIDEO,
                original_filename=filename,
                mime_type=_asset_mime_type(upload_content_type, filename, fallback="video/unknown"),
                size_bytes=size_bytes,
                sha256=sha256,
                relative_path=relative_path,
                immutable=True,
            )
            episode = Episode(
                project_id=project_id,
                source_asset_id=asset.id,
                episode_order=next_order,
                duration_us=probe.duration_us,
                width=probe.width,
                height=probe.height,
                codec_name=probe.codec_name,
                avg_frame_rate=probe.avg_frame_rate,
                has_audio=probe.has_audio,
                probe_json=probe.raw,
            )
            next_order += 1
            db.add_all([asset, episode])
            db.flush()
            requested_episode_ids.append(episode.id)
            touched = True

        if touched:
            _refresh_video_artifact(db, project_id)
        else:
            db.commit()
    except Exception:
        db.rollback()
        for relative_path in created_paths:
            cleanup_asset_file(relative_path)
        raise

    result_by_id = {item.id: item for item in list_episodes(db, project_id)}
    seen: set[str] = set()
    return [result_by_id[item] for item in requested_episode_ids if item in result_by_id and not (item in seen or seen.add(item))]


def reorder_episodes(db: Session, project_id: str, episode_ids: list[str]) -> list[EpisodeRead]:
    project = get_project(db, project_id)
    _ensure_video_project(project.project_type)
    rows = list(db.scalars(select(Episode).where(Episode.project_id == project_id)).all())
    current_ids = {row.id for row in rows}
    if set(episode_ids) != current_ids or len(episode_ids) != len(rows):
        raise AppError(
            "EPISODE_REORDER_MISMATCH",
            "排序列表必须完整包含当前项目的全部集数",
            status_code=422,
        )
    current_order = [item.id for item in sorted(rows, key=lambda row: row.episode_order)]
    if current_order == episode_ids:
        return list_episodes(db, project_id)

    by_id = {row.id: row for row in rows}
    for position, episode_id in enumerate(episode_ids, start=1):
        by_id[episode_id].episode_order = position
        db.add(by_id[episode_id])
    db.flush()
    _refresh_video_artifact(db, project_id)
    return list_episodes(db, project_id)


async def ingest_text_upload(db: Session, project_id: str, upload: UploadFile) -> SourceDocumentRead:
    project = get_project(db, project_id)
    _ensure_text_project(project.project_type)
    upload_content_type = upload.content_type
    temp_path, sha256, size_bytes, filename = await stream_upload_to_temp(
        upload,
        project_id=project_id,
        asset_kind=SourceAssetKind.TEXT,
    )
    document_format = _TEXT_SUFFIXES.get(Path(filename).suffix.lower())
    if document_format is None:
        temp_path.unlink(missing_ok=True)
        raise AppError("TEXT_FORMAT_UNSUPPORTED", "当前仅支持 TXT、MD、Markdown 文本", status_code=422)

    try:
        raw_bytes = temp_path.read_bytes()
        try:
            text = raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise AppError("TEXT_ENCODING_UNSUPPORTED", "文本必须使用 UTF-8 编码", status_code=422) from exc
        if not text.strip():
            raise AppError("TEXT_CONTENT_EMPTY", "文本内容为空", status_code=422)

        existing_asset = db.scalar(
            select(SourceAsset).where(
                SourceAsset.project_id == project_id,
                SourceAsset.asset_kind == SourceAssetKind.TEXT,
                SourceAsset.sha256 == sha256,
            )
        )
        current_document = db.scalar(
            select(SourceDocument).where(
                SourceDocument.project_id == project_id,
                SourceDocument.is_current.is_(True),
            )
        )
        if existing_asset is not None and current_document is not None and current_document.source_asset_id == existing_asset.id:
            temp_path.unlink(missing_ok=True)
            return _document_read(current_document, existing_asset)

        created_path: str | None = None
        if existing_asset is None:
            asset_id = str(uuid4())
            _, relative_path = move_temp_to_immutable_source(
                temp_path,
                project_id=project_id,
                asset_id=asset_id,
                original_filename=filename,
            )
            created_path = relative_path
            asset = SourceAsset(
                id=asset_id,
                project_id=project_id,
                asset_kind=SourceAssetKind.TEXT,
                original_filename=filename,
                mime_type=_asset_mime_type(upload_content_type, filename, fallback="text/plain"),
                size_bytes=size_bytes,
                sha256=sha256,
                relative_path=relative_path,
                immutable=True,
            )
            db.add(asset)
            db.flush()
        else:
            temp_path.unlink(missing_ok=True)
            asset = existing_asset

        if current_document is not None:
            current_document.is_current = False
            db.add(current_document)

        latest_revision = int(
            db.scalar(select(func.max(SourceDocument.revision)).where(SourceDocument.project_id == project_id)) or 0
        )
        document = SourceDocument(
            project_id=project_id,
            source_asset_id=asset.id,
            revision=latest_revision + 1,
            document_format=document_format,
            encoding="utf-8",
            char_count=len(text),
            is_current=True,
        )
        db.add(document)
        db.flush()
        _refresh_text_artifact(db, project_id, document, asset)
        return _document_read(document, asset)
    except Exception:
        db.rollback()
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        if "created_path" in locals() and created_path:
            cleanup_asset_file(created_path)
        raise


def get_current_document(db: Session, project_id: str) -> SourceDocumentRead:
    project = get_project(db, project_id)
    _ensure_text_project(project.project_type)
    document = db.scalar(
        select(SourceDocument).where(
            SourceDocument.project_id == project_id,
            SourceDocument.is_current.is_(True),
        )
    )
    if document is None:
        raise AppError("SOURCE_DOCUMENT_NOT_FOUND", "当前项目还没有原始文本", status_code=404)
    asset = db.get(SourceAsset, document.source_asset_id)
    if asset is None:
        raise AppError("SOURCE_ASSET_INCONSISTENT", "SourceDocument 缺少原始文件", status_code=500)
    return _document_read(document, asset)
