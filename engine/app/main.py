"""AI Drama Studio 本地 FastAPI 应用与 F01–F04 HTTP Controller。

Controller 只做 HTTP 边界：接收请求、调用业务函数、返回响应。
不在本文件直接执行项目/媒体 SQL、mkdir、写 project.json、转码、Hash、FFprobe、模型推理或 Recovery。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
from engine.app.source_videos import (
    SourceVideoError,
    get_source_video,
    import_source_video,
    recover_source_video_imports,
)

# F01 创建项目只允许保存下面这些稳定代码。
# 前端使用下拉框限制普通用户，API Schema 再限制直接请求，形成双层保护。
# 以后若新增支持语言/地区，必须同时更新前端 project-options.ts、这里的类型和相关测试。
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


@asynccontextmanager
async def _lifespan(_: FastAPI):
    """启动时升级数据库，并按依赖顺序恢复 F01、F02、F03、F04 中断状态。"""

    init_database()
    recover_creating_projects()
    recover_source_video_imports()
    recover_source_preprocesses()
    recover_shot_detections()
    yield


def create_app() -> FastAPI:
    """创建 AI Drama Studio 当前本地 FastAPI Application。

    F01–F03 已冻结 Controller 语义保持不变；F04 Additive 新增自动拉片 GET/POST 与显式重跑 POST。
    模型、PTS 对齐、完整性校验、DB 事务和 Recovery 全部由 F04 业务层负责。
    """

    app = FastAPI(title="AI Drama Studio", version="0.4.0", lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        # Vite 开发服务器在 5173 被占用时会自动切到其它端口。
        # 本地开发只允许 localhost / 127.0.0.1，不开放任意外部 Origin。
        allow_origins=[],
        allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        """把 Pydantic/FastAPI 请求格式错误转换成统一 error envelope。"""

        if request.url.path.endswith("/source-video"):
            return JSONResponse(
                status_code=422,
                content={
                    "error": {
                        "code": "SOURCE_VIDEO_REQUEST_INVALID",
                        "message": "原视频上传请求格式不正确",
                    }
                },
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
        """把 F01 项目业务错误统一转换成前端可识别 JSON。"""

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
        return JSONResponse(
            status_code=status_map.get(exc.code, 500),
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(SourceVideoError)
    async def source_video_error_handler(_: Request, exc: SourceVideoError) -> JSONResponse:
        """把 F02 Source Video 业务错误转换成稳定 HTTP 状态与 error envelope。"""

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
        return JSONResponse(
            status_code=status_map.get(exc.code, 500),
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(PreprocessError)
    async def preprocess_error_handler(_: Request, exc: PreprocessError) -> JSONResponse:
        """把 F03 预处理业务错误转换成稳定 HTTP 状态与统一 error envelope。"""

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
        return JSONResponse(
            status_code=status_map.get(exc.code, 500),
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(ShotDetectionError)
    async def shot_detection_error_handler(_: Request, exc: ShotDetectionError) -> JSONResponse:
        """把 F04 本地模型/PTS/完整性/显式重跑错误转换成稳定 HTTP error envelope。"""

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
        return JSONResponse(
            status_code=status_map.get(exc.code, 500),
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.get("/api/health")
    def health_api() -> dict[str, str]:
        """后端健康检查入口；只说明 FastAPI 已可响应。"""
        return {"status": "ok"}

    @app.get("/api/projects", response_model=list[ProjectResponse])
    def list_projects_api() -> list[dict]:
        """项目列表 HTTP 入口：只调用 list_projects()，不直接查询数据库。"""
        return [project.to_dict() for project in list_projects()]

    @app.post("/api/projects", response_model=ProjectResponse, status_code=201)
    def create_project_api(payload: CreateProjectRequest) -> dict:
        """新建项目 HTTP 入口；不直接生成 ID、mkdir、SQL 或写 Manifest。"""
        return create_project(**payload.model_dump(mode="json")).to_dict()

    @app.post("/api/projects/{project_id}/open", response_model=ProjectResponse)
    def open_project_api(project_id: str) -> dict:
        """打开项目 HTTP 入口：调用 open_project() 做完整性检查和打开时间更新。"""
        return open_project(project_id=project_id).to_dict()

    @app.get(
        "/api/projects/{project_id}/source-video",
        response_model=SourceVideoResponse | None,
    )
    def get_source_video_api(project_id: str) -> dict | None:
        """读取当前项目已完成原片的 HTTP 入口。"""
        source_video = get_source_video(project_id=project_id)
        return source_video.to_dict() if source_video else None

    @app.post(
        "/api/projects/{project_id}/source-video",
        response_model=SourceVideoResponse,
        status_code=201,
    )
    async def import_source_video_api(project_id: str, file: UploadFile = File(...)) -> dict:
        """原视频 multipart 上传 HTTP 入口；不在 Controller 搬运/Hash/FFprobe 文件。"""
        try:
            source_video = await import_source_video(
                project_id=project_id,
                upload_file=file,
                original_filename=file.filename or "source-video",
            )
            return source_video.to_dict()
        finally:
            await file.close()

    @app.get(
        "/api/projects/{project_id}/preprocess",
        response_model=SourcePreprocessResponse | None,
    )
    def get_source_preprocess_api(project_id: str) -> dict | None:
        """F03 页面读取 ready 预处理资产的 HTTP 入口；无结果返回 200 null。"""
        record = get_source_preprocess(project_id=project_id)
        return record.to_dict() if record else None

    @app.post(
        "/api/projects/{project_id}/preprocess",
        response_model=SourcePreprocessResponse,
        status_code=201,
    )
    def preprocess_source_video_api(project_id: str) -> dict:
        """F03 开始预处理 HTTP 入口。

        Controller 只传 Project ID。FFmpeg 参数、Source Integrity、staging、publish、DB ready
        和失败恢复全部由 preprocess_source_video() 负责。
        """
        return preprocess_source_video(project_id=project_id).to_dict()

    @app.get(
        "/api/projects/{project_id}/shot-detection",
        response_model=ShotDetectionResponse | None,
    )
    def get_shot_detection_api(project_id: str) -> dict | None:
        """F04 页面读取自动拉片结果；无 Detection Run 返回 200 null。"""

        record = get_shot_detection(project_id=project_id)
        return record.to_dict() if record else None

    @app.post(
        "/api/projects/{project_id}/shot-detection",
        response_model=ShotDetectionResponse,
        status_code=201,
    )
    def run_shot_detection_api(project_id: str) -> dict:
        """F04 首次自动拉片入口；ready 后重复 POST 仍然拒绝，不把重复请求当成重跑。"""

        return run_shot_detection(project_id=project_id).to_dict()

    @app.post(
        "/api/projects/{project_id}/shot-detection/rerun",
        response_model=ShotDetectionResponse,
    )
    def rerun_shot_detection_api(project_id: str) -> dict:
        """F04 显式重新自动拉片入口。

        只有用户主动点击“重新自动拉片”才调用本接口。旧 READY 结果会保留到新结果完整成功，
        最后由单一数据库事务原子替换，因此 GPU/模型失败不会把现有 Auto Evidence 删除。
        """

        return rerun_shot_detection(project_id=project_id).to_dict()

    return app


app = create_app()
