"""AI Drama Studio 本地 FastAPI 应用与 F01–F05 HTTP Controller。

Controller 只负责 HTTP 边界：接收请求、调用业务函数、返回响应。
不在本文件直接执行 SQL、媒体处理、模型推理、Hash 或业务状态转换。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal

from fastapi import FastAPI, File, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from engine.app.core.database import init_database
from engine.app.preprocess import (
    PreprocessError,
    get_source_preprocess,
    preprocess_source_video,
    recover_source_preprocesses,
)
from engine.app.projects import (
    ProjectError,
    create_project,
    list_projects,
    open_project,
    recover_creating_projects,
)
from engine.app.shot_detection import (
    ShotDetectionError,
    get_shot_detection,
    recover_shot_detections,
    run_shot_detection,
)
from engine.app.shot_detection_rerun import rerun_shot_detection
from engine.app.shot_workbench import (
    ShotWorkbenchError,
    adjust_shot_boundary,
    confirm_final_shots,
    get_shot_workbench,
    get_workbench_proxy_path,
    initialize_shot_workbench,
    merge_final_shots,
    render_workbench_frame,
    split_final_shot,
)
from engine.app.source_videos import (
    SourceVideoError,
    get_source_video,
    import_source_video,
    recover_source_video_imports,
)

# F01 创建项目只允许保存下面这些稳定代码。
# 前端使用下拉框限制普通用户，API Schema 再限制直接请求，形成双层保护。
LanguageCode = Literal["zh", "en", "ja", "ko", "es", "pt", "fr", "de", "id", "th", "vi"]
RegionCode = Literal["US", "GB", "JP", "KR", "ES", "BR", "FR", "DE", "ID", "TH", "VN", "TW", "SG"]


class CreateProjectRequest(BaseModel):
    """前端创建项目时允许提交的 F01 基础字段。"""

    name: str = Field(description="用户看到的项目名称")
    source_language: LanguageCode | None = Field(default=None, description="原片标准语言代码；可为空表示暂不指定")
    target_language: LanguageCode = Field(description="重制目标标准语言代码，例如 en")
    target_region: RegionCode = Field(description="本土化目标标准地区代码，例如 US")
    workspace_root: str | None = Field(default=None, description="项目保存根目录；为空使用默认路径")


class ProjectResponse(BaseModel):
    """F01 返回给前端的项目基础信息。"""

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


class SourceVideoResponse(BaseModel):
    """F02 返回给前端的 ready Source Video 基础信息。"""

    id: str
    project_id: str
    original_filename: str
    relative_path: str
    file_size_bytes: int
    sha256: str
    status: str
    container_format: str
    duration_us: int
    source_start_time_us: int | None
    video_stream_index: int
    video_codec: str
    width: int
    height: int
    fps_num: int | None
    fps_den: int | None
    audio_stream_index: int | None
    audio_codec: str | None
    audio_sample_rate: int | None
    audio_channels: int | None
    created_at: datetime


class SourcePreprocessResponse(BaseModel):
    """F03 返回给前端的 ready 预处理派生资产集。"""

    source_video_id: str
    project_id: str
    status: str
    profile_version: int
    source_sha256_snapshot: str
    proxy_relative_path: str
    proxy_file_size_bytes: int
    proxy_sha256: str
    proxy_duration_us: int
    proxy_video_time_base_num: int
    proxy_video_time_base_den: int
    proxy_fps_num: int | None
    proxy_fps_den: int | None
    proxy_to_source_offset_us: int
    audio_relative_path: str | None
    audio_file_size_bytes: int | None
    audio_sha256: str | None
    audio_duration_us: int | None
    audio_sample_rate: int | None
    audio_channels: int | None
    audio_to_source_offset_us: int | None
    thumbnail_relative_path: str
    thumbnail_file_size_bytes: int
    thumbnail_sha256: str
    thumbnail_source_time_us: int
    source_video_time_base_num: int
    source_video_time_base_den: int
    created_at: datetime
    completed_at: datetime


class ShotCandidateResponse(BaseModel):
    """F04 返回的单个自动 Shot Candidate；detected_* 永远表示自动证据。"""

    id: str
    detection_id: str
    project_id: str
    ordinal: int
    detected_proxy_start_us: int
    detected_proxy_end_us: int
    detected_start_us: int
    detected_end_us: int
    duration_us: int
    end_boundary_kind: str
    end_boundary_score: float | None


class ShotDetectionResponse(BaseModel):
    """F04 一次 Detection Run 与全部自动候选镜头。"""

    id: str
    project_id: str
    source_video_id: str
    status: str
    detector_name: str
    detector_profile_version: int
    detector_threshold: float
    min_boundary_gap_us: int
    detector_package_version: str
    torch_version: str | None
    detector_device: str | None
    ffprobe_version: str | None
    preprocess_profile_version: int
    proxy_sha256_snapshot: str
    proxy_to_source_offset_us: int
    proxy_start_us: int | None
    proxy_end_us: int | None
    source_start_us: int | None
    source_end_us: int | None
    analyzed_frame_count: int | None
    detected_cut_count: int | None
    shot_count: int | None
    created_at: datetime
    completed_at: datetime | None
    candidates: list[ShotCandidateResponse]


class FinalShotResponse(BaseModel):
    """F05 人工工作区中的生产级 Final Shot。"""

    id: str = Field(description="稳定 Final Shot ID；边界微调不会改变该 ID")
    edit_set_id: str
    project_id: str
    ordinal: int
    final_start_us: int = Field(description="人工最终 Source 起点，integer microseconds")
    final_end_us: int = Field(description="人工最终 Source 终点，integer microseconds")
    duration_us: int
    origin_kind: str
    origin_candidate_ids: list[str]
    created_at: datetime
    updated_at: datetime


class ShotWorkbenchResponse(BaseModel):
    """F05 三栏拉片工作台完整状态。"""

    id: str
    project_id: str
    source_detection_id: str
    status: str = Field(description="editing 可修改；confirmed 已人工确认锁定")
    revision: int
    source_start_us: int
    source_end_us: int
    created_at: datetime
    updated_at: datetime
    confirmed_at: datetime | None
    shots: list[FinalShotResponse]


class AdjustBoundaryRequest(BaseModel):
    """移动两个相邻 Final Shot 的公共边界。"""

    left_shot_id: str = Field(description="公共边界左侧 Final Shot ID")
    boundary_us: int = Field(description="新的 Source Domain 公共边界，integer microseconds")


class SplitShotRequest(BaseModel):
    """在一个 Final Shot 内拆分新增镜头。"""

    shot_id: str
    split_us: int = Field(description="严格位于当前 Shot 内部的 Source Domain 拆分点")


class MergeShotsRequest(BaseModel):
    """删除左 Shot 与其下一 Shot 的公共边界。"""

    left_shot_id: str


@asynccontextmanager
async def _lifespan(_: FastAPI):
    """启动时升级数据库，并按依赖顺序恢复 F01–F04 可恢复状态。"""

    init_database()
    recover_creating_projects()
    recover_source_video_imports()
    recover_source_preprocesses()
    recover_shot_detections()
    yield


def create_app() -> FastAPI:
    """创建 AI Drama Studio 本地 FastAPI Application。"""

    app = FastAPI(title="AI Drama Studio", version="0.5.0", lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        """把 FastAPI/Pydantic 请求格式错误转换成当前 Feature 的统一错误码。"""

        if request.url.path.endswith("/source-video"):
            return JSONResponse(
                status_code=422,
                content={"error": {"code": "SOURCE_VIDEO_REQUEST_INVALID", "message": "原视频上传请求格式不正确"}},
            )
        if "/shot-workbench/" in request.url.path:
            return JSONResponse(
                status_code=422,
                content={"error": {"code": "SHOT_WORKBENCH_REQUEST_INVALID", "message": "镜头修正请求格式不正确"}},
            )

        invalid_fields = {str(error["loc"][-1]) for error in exc.errors() if error.get("loc")}
        if "source_language" in invalid_fields:
            code, message = "PROJECT_SOURCE_LANGUAGE_UNSUPPORTED", "原片语言不是系统支持的标准语言"
        elif "target_language" in invalid_fields:
            code, message = "PROJECT_TARGET_LANGUAGE_UNSUPPORTED", "目标语言不是系统支持的标准语言"
        elif "target_region" in invalid_fields:
            code, message = "PROJECT_TARGET_REGION_UNSUPPORTED", "目标地区不是系统支持的标准地区"
        else:
            code, message = "PROJECT_REQUEST_INVALID", "创建项目请求格式不正确"
        return JSONResponse(status_code=422, content={"error": {"code": code, "message": message}})

    @app.exception_handler(ProjectError)
    async def project_error_handler(_: Request, exc: ProjectError) -> JSONResponse:
        status_map = {
            "PROJECT_NAME_REQUIRED": 422,
            "PROJECT_NAME_TOO_LONG": 422,
            "PROJECT_TARGET_LANGUAGE_REQUIRED": 422,
            "PROJECT_TARGET_REGION_REQUIRED": 422,
            "PROJECT_WORKSPACE_INVALID": 409,
            "PROJECT_CREATE_FAILED": 500,
            "PROJECT_NOT_FOUND": 404,
            "PROJECT_WORKSPACE_MISSING": 409,
            "PROJECT_MANIFEST_INVALID": 409,
        }
        return JSONResponse(status_code=status_map.get(exc.code, 500), content={"error": {"code": exc.code, "message": exc.message}})

    @app.exception_handler(SourceVideoError)
    async def source_video_error_handler(_: Request, exc: SourceVideoError) -> JSONResponse:
        status_map = {
            "SOURCE_VIDEO_ALREADY_EXISTS": 409,
            "SOURCE_VIDEO_EMPTY": 422,
            "SOURCE_VIDEO_FFPROBE_UNAVAILABLE": 503,
            "SOURCE_VIDEO_PROBE_FAILED": 422,
            "SOURCE_VIDEO_UNSUPPORTED": 422,
            "SOURCE_VIDEO_IMPORT_FAILED": 500,
            "SOURCE_VIDEO_FINALIZATION_PENDING": 500,
            "SOURCE_VIDEO_FILE_MISSING": 409,
        }
        return JSONResponse(status_code=status_map.get(exc.code, 500), content={"error": {"code": exc.code, "message": exc.message}})

    @app.exception_handler(PreprocessError)
    async def preprocess_error_handler(_: Request, exc: PreprocessError) -> JSONResponse:
        status_map = {
            "PREPROCESS_SOURCE_REQUIRED": 409,
            "PREPROCESS_ALREADY_EXISTS": 409,
            "PREPROCESS_IN_PROGRESS": 409,
            "PREPROCESS_RECOVERY_REQUIRED": 409,
            "SOURCE_VIDEO_INTEGRITY_MISMATCH": 409,
            "PREPROCESS_FFMPEG_UNAVAILABLE": 503,
            "PREPROCESS_FFPROBE_UNAVAILABLE": 503,
            "PREPROCESS_GENERATION_FAILED": 500,
            "PREPROCESS_PROCESSING_FAILED": 500,
            "PREPROCESS_VALIDATION_FAILED": 500,
            "PREPROCESS_FINALIZATION_PENDING": 500,
            "PREPROCESS_FILE_MISSING": 409,
        }
        return JSONResponse(status_code=status_map.get(exc.code, 500), content={"error": {"code": exc.code, "message": exc.message}})

    @app.exception_handler(ShotDetectionError)
    async def shot_detection_error_handler(_: Request, exc: ShotDetectionError) -> JSONResponse:
        status_map = {
            "SHOT_DETECTION_PREPROCESS_REQUIRED": 409,
            "SHOT_DETECTION_ALREADY_EXISTS": 409,
            "SHOT_DETECTION_IN_PROGRESS": 409,
            "SHOT_DETECTION_RERUN_NOT_READY": 409,
            "SHOT_DETECTION_RERUN_CONFLICT": 409,
            "SHOT_DETECTION_PROXY_INTEGRITY_MISMATCH": 409,
            "SHOT_DETECTION_UPSTREAM_CHANGED": 409,
            "SHOT_DETECTION_MODEL_UNAVAILABLE": 503,
            "SHOT_DETECTION_MODEL_INVALID": 503,
            "SHOT_DETECTION_FFPROBE_UNAVAILABLE": 503,
            "SHOT_DETECTION_FRAME_ALIGNMENT_FAILED": 500,
            "SHOT_DETECTION_INVALID_RESULT": 500,
            "SHOT_DETECTION_FAILED": 500,
        }
        return JSONResponse(status_code=status_map.get(exc.code, 500), content={"error": {"code": exc.code, "message": exc.message}})

    @app.exception_handler(ShotWorkbenchError)
    async def shot_workbench_error_handler(_: Request, exc: ShotWorkbenchError) -> JSONResponse:
        """把 F05 Final Shot/媒体错误映射为稳定 HTTP 状态。"""

        status_map = {
            "SHOT_WORKBENCH_DETECTION_REQUIRED": 409,
            "SHOT_WORKBENCH_INVALID_UPSTREAM": 409,
            "SHOT_WORKBENCH_UPSTREAM_CHANGED": 409,
            "SHOT_WORKBENCH_NOT_INITIALIZED": 409,
            "SHOT_WORKBENCH_CONFIRMED": 409,
            "SHOT_WORKBENCH_SHOT_NOT_FOUND": 404,
            "SHOT_WORKBENCH_BOUNDARY_INVALID": 422,
            "SHOT_WORKBENCH_SPLIT_INVALID": 422,
            "SHOT_WORKBENCH_MERGE_INVALID": 422,
            "SHOT_WORKBENCH_FRAME_TIME_INVALID": 422,
            "SHOT_WORKBENCH_MEDIA_MISSING": 409,
            "SHOT_WORKBENCH_FFMPEG_UNAVAILABLE": 503,
            "SHOT_WORKBENCH_FRAME_FAILED": 500,
            "SHOT_WORKBENCH_INITIALIZE_FAILED": 500,
            "SHOT_WORKBENCH_INVALID_RESULT": 500,
        }
        return JSONResponse(status_code=status_map.get(exc.code, 500), content={"error": {"code": exc.code, "message": exc.message}})

    @app.get("/api/health")
    def health_api() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/projects", response_model=list[ProjectResponse])
    def list_projects_api() -> list[dict]:
        return [project.to_dict() for project in list_projects()]

    @app.post("/api/projects", response_model=ProjectResponse, status_code=201)
    def create_project_api(payload: CreateProjectRequest) -> dict:
        return create_project(**payload.model_dump(mode="json")).to_dict()

    @app.post("/api/projects/{project_id}/open", response_model=ProjectResponse)
    def open_project_api(project_id: str) -> dict:
        return open_project(project_id=project_id).to_dict()

    @app.get("/api/projects/{project_id}/source-video", response_model=SourceVideoResponse | None)
    def get_source_video_api(project_id: str) -> dict | None:
        source_video = get_source_video(project_id=project_id)
        return source_video.to_dict() if source_video else None

    @app.post("/api/projects/{project_id}/source-video", response_model=SourceVideoResponse, status_code=201)
    async def import_source_video_api(project_id: str, file: UploadFile = File(...)) -> dict:
        try:
            source_video = await import_source_video(project_id=project_id, upload_file=file, original_filename=file.filename or "source-video")
            return source_video.to_dict()
        finally:
            await file.close()

    @app.get("/api/projects/{project_id}/preprocess", response_model=SourcePreprocessResponse | None)
    def get_source_preprocess_api(project_id: str) -> dict | None:
        record = get_source_preprocess(project_id=project_id)
        return record.to_dict() if record else None

    @app.post("/api/projects/{project_id}/preprocess", response_model=SourcePreprocessResponse, status_code=201)
    def preprocess_source_video_api(project_id: str) -> dict:
        return preprocess_source_video(project_id=project_id).to_dict()

    @app.get("/api/projects/{project_id}/shot-detection", response_model=ShotDetectionResponse | None)
    def get_shot_detection_api(project_id: str) -> dict | None:
        record = get_shot_detection(project_id=project_id)
        return record.to_dict() if record else None

    @app.post("/api/projects/{project_id}/shot-detection", response_model=ShotDetectionResponse, status_code=201)
    def run_shot_detection_api(project_id: str) -> dict:
        return run_shot_detection(project_id=project_id).to_dict()

    @app.post("/api/projects/{project_id}/shot-detection/rerun", response_model=ShotDetectionResponse)
    def rerun_shot_detection_api(project_id: str) -> dict:
        return rerun_shot_detection(project_id=project_id).to_dict()

    @app.get("/api/projects/{project_id}/shot-workbench", response_model=ShotWorkbenchResponse | None)
    def get_shot_workbench_api(project_id: str) -> dict | None:
        """读取 F05 Final Shot 工作区；尚未初始化返回 200 null。"""

        record = get_shot_workbench(project_id=project_id)
        return record.to_dict() if record else None

    @app.post("/api/projects/{project_id}/shot-workbench/initialize", response_model=ShotWorkbenchResponse, status_code=201)
    def initialize_shot_workbench_api(project_id: str) -> dict:
        """把 F04 Auto Candidate 复制成独立 Final Shot Draft。"""

        return initialize_shot_workbench(project_id=project_id).to_dict()

    @app.post("/api/projects/{project_id}/shot-workbench/boundary", response_model=ShotWorkbenchResponse)
    def adjust_shot_boundary_api(project_id: str, payload: AdjustBoundaryRequest) -> dict:
        """移动相邻镜头公共边界；后端同时更新左右 Shot。"""

        return adjust_shot_boundary(
            project_id=project_id,
            left_shot_id=payload.left_shot_id,
            boundary_us=payload.boundary_us,
        ).to_dict()

    @app.post("/api/projects/{project_id}/shot-workbench/split", response_model=ShotWorkbenchResponse)
    def split_final_shot_api(project_id: str, payload: SplitShotRequest) -> dict:
        """在指定播放点拆分当前 Shot（新增镜头）。"""

        return split_final_shot(project_id=project_id, shot_id=payload.shot_id, split_us=payload.split_us).to_dict()

    @app.post("/api/projects/{project_id}/shot-workbench/merge", response_model=ShotWorkbenchResponse)
    def merge_final_shots_api(project_id: str, payload: MergeShotsRequest) -> dict:
        """删除左 Shot 与其下一 Shot 的公共边界（合并镜头）。"""

        return merge_final_shots(project_id=project_id, left_shot_id=payload.left_shot_id).to_dict()

    @app.post("/api/projects/{project_id}/shot-workbench/confirm", response_model=ShotWorkbenchResponse)
    def confirm_final_shots_api(project_id: str) -> dict:
        """人工确认并锁定 Final Shot Timeline。"""

        return confirm_final_shots(project_id=project_id).to_dict()

    @app.get("/api/projects/{project_id}/shot-workbench/media/proxy")
    def shot_workbench_proxy_api(project_id: str) -> FileResponse:
        """把 F03 Proxy 作为本地播放器媒体返回；不生成新视频副本。"""

        path = get_workbench_proxy_path(project_id=project_id)
        return FileResponse(path, media_type="video/mp4")

    @app.get("/api/projects/{project_id}/shot-workbench/frame")
    def shot_workbench_frame_api(
        project_id: str,
        source_time_us: int = Query(description="Source Domain integer microseconds"),
    ) -> FileResponse:
        """按 Source 时间返回 F05 工作台缩略图/关键帧 JPEG。"""

        path = render_workbench_frame(project_id=project_id, source_time_us=source_time_us)
        return FileResponse(path, media_type="image/jpeg")

    return app


app = create_app()
