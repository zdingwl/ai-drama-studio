"""F01「创建项目」的核心业务函数。

本文件只处理项目级基础能力：Workspace、创建、列表、打开和 creating 状态恢复。
不处理视频、Shot、人物、AI 等任何 F02 以后业务。
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError

from engine.app.core.database import init_database
from engine.app.core.ids import generate_project_id

PROJECT_FORMAT_VERSION = 1
PROJECT_MANIFEST_FILENAME = "project.json"
PROJECT_MANIFEST_TEMP_FILENAME = "project.json.tmp"
DEFAULT_WORKSPACE_FOLDER_NAME = "AI Drama Studio Projects"


class ProjectError(RuntimeError):
    """F01 可以安全返回给 Controller 的项目业务错误。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ProjectRecord:
    """前后端都需要的项目基础信息，不包含任何媒体或 AI 数据。"""

    id: str
    name: str
    source_language: str | None
    target_language: str
    target_region: str
    workspace_path: str
    project_format_version: int
    status: str
    created_at: datetime
    last_opened_at: datetime | None

    def to_dict(self) -> dict[str, Any]:
        """转换为 FastAPI/Pydantic 可直接消费的字典。"""
        return asdict(self)


def _database_engine(database_path: Path) -> sa.Engine:
    """创建访问指定 app.db 的轻量 SQLAlchemy Engine。"""
    return sa.create_engine(f"sqlite:///{database_path.as_posix()}", future=True)


def _projects_table(engine: sa.Engine) -> sa.Table:
    """从 Alembic 已创建的数据库反射 projects 表，避免维护第二套建表定义。"""
    metadata = sa.MetaData()
    return sa.Table("projects", metadata, autoload_with=engine)


def _default_workspace_root() -> Path:
    """返回 F01 默认项目根目录；Windows 优先使用 USERPROFILE。"""
    user_profile = os.getenv("USERPROFILE")
    home = Path(user_profile).expanduser() if user_profile and user_profile.strip() else Path.home()
    return (home / DEFAULT_WORKSPACE_FOLDER_NAME).resolve(strict=False)


def _normalize_project_input(name: str, source_language: str | None, target_language: str, target_region: str) -> tuple[str, str | None, str, str]:
    """集中做 F01 创建项目最小输入校验。"""
    normalized_name = name.strip()
    if not normalized_name:
        raise ProjectError("PROJECT_NAME_REQUIRED", "项目名称不能为空")
    if len(normalized_name) > 100:
        raise ProjectError("PROJECT_NAME_TOO_LONG", "项目名称不能超过 100 个字符")

    normalized_target_language = target_language.strip().lower()
    if not normalized_target_language:
        raise ProjectError("PROJECT_TARGET_LANGUAGE_REQUIRED", "目标语言不能为空")

    normalized_target_region = target_region.strip().upper()
    if not normalized_target_region:
        raise ProjectError("PROJECT_TARGET_REGION_REQUIRED", "目标地区不能为空")

    normalized_source = source_language.strip().lower() if source_language and source_language.strip() else None
    return normalized_name, normalized_source, normalized_target_language, normalized_target_region


def _read_valid_manifest(workspace_path: Path, expected_project_id: str) -> dict[str, Any]:
    """读取并验证 F01 project.json；只校验打开项目真正依赖的基础字段。"""
    manifest_path = workspace_path / PROJECT_MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise ProjectError("PROJECT_MANIFEST_INVALID", "项目文件 project.json 不存在")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectError("PROJECT_MANIFEST_INVALID", "项目文件 project.json 无法读取或格式损坏") from exc

    if manifest.get("project_id") != expected_project_id:
        raise ProjectError("PROJECT_MANIFEST_INVALID", "project.json 中的项目 ID 与数据库不一致")
    if manifest.get("project_format_version") != PROJECT_FORMAT_VERSION:
        raise ProjectError("PROJECT_MANIFEST_INVALID", "project.json 的项目格式版本当前无法打开")
    return manifest


def _row_to_record(row: sa.RowMapping) -> ProjectRecord:
    """把 SQLAlchemy 查询结果转换成 F01 ProjectRecord。"""
    return ProjectRecord(
        id=row["id"], name=row["name"], source_language=row["source_language"],
        target_language=row["target_language"], target_region=row["target_region"],
        workspace_path=row["workspace_path"], project_format_version=row["project_format_version"],
        status=row["status"], created_at=row["created_at"], last_opened_at=row["last_opened_at"],
    )


def create_project_workspace(*, workspace_root: str | Path, project_id: str, name: str, source_language: str | None, target_language: str, target_region: str) -> Path:
    """创建一个 F01 Project Workspace 并原子写入 ``project.json``。

    业务作用：把 Project ID 和基础资料真正落到本地项目目录中，使项目不仅存在于数据库，
    还拥有可以重新打开、校验和未来继续扩展的文件系统容器。

    安全边界：目标 Project 目录已存在时绝不覆盖；写入失败只清理本函数明确创建的
    ``project.json(.tmp)`` 和空项目目录；绝不递归删除 Workspace Root、其它项目或未知用户文件。
    """
    root = Path(workspace_root).expanduser().resolve(strict=False)
    project_path = root / project_id
    manifest_path = project_path / PROJECT_MANIFEST_FILENAME
    temp_path = project_path / PROJECT_MANIFEST_TEMP_FILENAME
    manifest = {
        "project_id": project_id,
        "project_format_version": PROJECT_FORMAT_VERSION,
        "name": name,
        "source_language": source_language,
        "target_language": target_language,
        "target_region": target_region,
    }

    try:
        root.mkdir(parents=True, exist_ok=True)
        project_path.mkdir(exist_ok=False)
        with temp_path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, manifest_path)
        _read_valid_manifest(project_path, project_id)
        return project_path
    except FileExistsError as exc:
        if project_path.exists():
            raise ProjectError("PROJECT_CREATE_FAILED", "项目目录已经存在，系统不会覆盖已有文件") from exc
        raise ProjectError("PROJECT_WORKSPACE_INVALID", "项目保存位置不是可用目录") from exc
    except ProjectError:
        _cleanup_failed_workspace(project_path, manifest_path, temp_path)
        raise
    except OSError as exc:
        _cleanup_failed_workspace(project_path, manifest_path, temp_path)
        raise ProjectError("PROJECT_WORKSPACE_INVALID", "项目保存位置不可创建或不可写") from exc


def _cleanup_failed_workspace(project_path: Path, manifest_path: Path, temp_path: Path) -> None:
    """只清理 create_project_workspace() 自己明确创建的已知文件，不递归删除。"""
    for known_file in (temp_path, manifest_path):
        try:
            known_file.unlink(missing_ok=True)
        except OSError:
            pass
    try:
        project_path.rmdir()
    except OSError:
        # 目录非空或无法删除时保留现场，宁可留下痕迹也不误删未知用户文件。
        pass


def create_project(*, name: str, target_language: str, target_region: str, source_language: str | None = None, workspace_root: str | Path | None = None, app_data_path: Path | None = None) -> ProjectRecord:
    """创建一个新的、可以在重启后重新打开的 F01 项目。

    流程：校验输入 → 生成稳定 ID → DB 写 creating 并提交 → 创建 Workspace/project.json →
    DB 改 ready 并记录首次打开时间。

    失败边界：Workspace 尚未成功创建时删除本次 creating 记录；Workspace 已完整创建但最终
    DB 更新失败时保留 creating 记录和文件，交给启动恢复，绝不删除已经完成的用户项目文件。
    """
    normalized_name, normalized_source, normalized_target_language, normalized_target_region = _normalize_project_input(
        name, source_language, target_language, target_region
    )
    database_path = init_database(app_data_path)
    engine = _database_engine(database_path)
    projects = _projects_table(engine)

    project_id = generate_project_id()
    root = Path(workspace_root).expanduser().resolve(strict=False) if workspace_root else _default_workspace_root()
    project_path = root / project_id
    created_at = datetime.now(timezone.utc)

    try:
        with engine.begin() as connection:
            connection.execute(projects.insert().values(
                id=project_id, name=normalized_name, source_language=normalized_source,
                target_language=normalized_target_language, target_region=normalized_target_region,
                workspace_path=str(project_path), project_format_version=PROJECT_FORMAT_VERSION,
                status="creating", created_at=created_at, last_opened_at=None,
            ))
    except SQLAlchemyError as exc:
        engine.dispose()
        raise ProjectError("PROJECT_CREATE_FAILED", "项目数据库记录创建失败") from exc

    try:
        create_project_workspace(
            workspace_root=root, project_id=project_id, name=normalized_name,
            source_language=normalized_source, target_language=normalized_target_language,
            target_region=normalized_target_region,
        )
    except Exception:
        try:
            with engine.begin() as connection:
                connection.execute(projects.delete().where(projects.c.id == project_id, projects.c.status == "creating"))
        finally:
            engine.dispose()
        raise

    opened_at = datetime.now(timezone.utc)
    try:
        with engine.begin() as connection:
            connection.execute(
                projects.update().where(projects.c.id == project_id, projects.c.status == "creating")
                .values(status="ready", last_opened_at=opened_at)
            )
            row = connection.execute(projects.select().where(projects.c.id == project_id)).mappings().one()
    except SQLAlchemyError as exc:
        raise ProjectError("PROJECT_CREATE_FAILED", "项目文件已经创建，但数据库最终状态未完成；重新启动应用后系统会自动恢复") from exc
    finally:
        engine.dispose()
    return _row_to_record(row)


def list_projects(*, app_data_path: Path | None = None) -> list[ProjectRecord]:
    """返回首页需要的所有 ``ready`` 项目，最近打开的项目排在前面；本函数只读。"""
    database_path = init_database(app_data_path)
    engine = _database_engine(database_path)
    projects = _projects_table(engine)
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                projects.select().where(projects.c.status == "ready")
                .order_by(projects.c.last_opened_at.desc(), projects.c.created_at.desc())
            ).mappings().all()
        return [_row_to_record(row) for row in rows]
    finally:
        engine.dispose()


def open_project(*, project_id: str, app_data_path: Path | None = None) -> ProjectRecord:
    """验证历史项目仍完整，并记录本次成功进入 Workspace 的时间。

    必须同时满足：DB 有 ready 记录、Workspace 存在、project.json 可读取且 Project ID/格式一致。
    发现损坏时只报错，不自动修改或删除用户 Workspace。
    """
    database_path = init_database(app_data_path)
    engine = _database_engine(database_path)
    projects = _projects_table(engine)
    try:
        with engine.begin() as connection:
            row = connection.execute(projects.select().where(projects.c.id == project_id)).mappings().first()
            if row is None or row["status"] != "ready":
                raise ProjectError("PROJECT_NOT_FOUND", "没有找到可打开的项目")
            workspace_path = Path(row["workspace_path"])
            if not workspace_path.is_dir():
                raise ProjectError("PROJECT_WORKSPACE_MISSING", "项目文件夹不存在或已被移动")
            _read_valid_manifest(workspace_path, project_id)
            opened_at = datetime.now(timezone.utc)
            connection.execute(projects.update().where(projects.c.id == project_id).values(last_opened_at=opened_at))
            updated = connection.execute(projects.select().where(projects.c.id == project_id)).mappings().one()
        return _row_to_record(updated)
    finally:
        engine.dispose()


def recover_creating_projects(*, app_data_path: Path | None = None) -> dict[str, int]:
    """应用启动时恢复上次异常退出留下的 ``creating`` 项目。

    完整 Workspace + 合法 project.json 转 ready；Workspace 不存在则删除无意义记录；
    仅含 F01 已知半成品文件时可安全清理；出现未知文件或无法确认归属时保留现场。
    """
    database_path = init_database(app_data_path)
    engine = _database_engine(database_path)
    projects = _projects_table(engine)
    stats = {"recovered": 0, "removed": 0, "preserved": 0}
    try:
        with engine.begin() as connection:
            rows = connection.execute(projects.select().where(projects.c.status == "creating")).mappings().all()
            for row in rows:
                project_id = row["id"]
                workspace_path = Path(row["workspace_path"])
                if workspace_path.is_dir():
                    try:
                        _read_valid_manifest(workspace_path, project_id)
                    except ProjectError:
                        known_names = {PROJECT_MANIFEST_FILENAME, PROJECT_MANIFEST_TEMP_FILENAME}
                        try:
                            existing_names = {item.name for item in workspace_path.iterdir()}
                        except OSError:
                            stats["preserved"] += 1
                            continue
                        if existing_names.issubset(known_names) and workspace_path.name == project_id:
                            _cleanup_failed_workspace(
                                workspace_path,
                                workspace_path / PROJECT_MANIFEST_FILENAME,
                                workspace_path / PROJECT_MANIFEST_TEMP_FILENAME,
                            )
                            if not workspace_path.exists():
                                connection.execute(projects.delete().where(projects.c.id == project_id))
                                stats["removed"] += 1
                            else:
                                stats["preserved"] += 1
                        else:
                            stats["preserved"] += 1
                        continue
                    connection.execute(projects.update().where(projects.c.id == project_id).values(status="ready"))
                    stats["recovered"] += 1
                elif not workspace_path.exists():
                    connection.execute(projects.delete().where(projects.c.id == project_id))
                    stats["removed"] += 1
                else:
                    stats["preserved"] += 1
        return stats
    finally:
        engine.dispose()
