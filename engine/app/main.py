"""F01 的最小 FastAPI 应用与 HTTP Controller。

Controller 只做 HTTP 边界：接收请求、调用项目业务函数、返回响应。
不在本文件直接执行项目 SQL、mkdir 或写 project.json。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from engine.app.core.database import init_database
from engine.app.projects import (
    ProjectError,
    create_project,
    list_projects,
    open_project,
    recover_creating_projects,
)


class CreateProjectRequest(BaseModel):
    """前端创建项目时允许提交的 F01 基础字段。"""

    name: str = Field(description="用户看到的项目名称")
    source_language: str | None = Field(default=None, description="原片语言代码；可为空")
    target_language: str = Field(description="重制目标语言代码，例如 en")
    target_region: str = Field(description="本土化目标地区代码，例如 US")
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


@asynccontextmanager
async def _lifespan(_: FastAPI):
    """应用启动时先初始化数据库，并恢复简单 creating 状态。"""

    init_database()
    recover_creating_projects()
    yield


def create_app() -> FastAPI:
    """创建 F01 最小 FastAPI Application。

    只负责注册中间件、异常处理和 4 个 Controller；启动阶段初始化数据库与简单恢复。
    不负责创建任何具体 Project，也不实现 F02 业务。
    """

    app = FastAPI(title="AI Drama Studio", version="0.1.0", lifespan=_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(ProjectError)
    async def project_error_handler(_: Request, exc: ProjectError) -> JSONResponse:
        """把业务错误统一转换成前端可识别的 JSON；不处理项目业务本身。"""

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
        """新建项目 HTTP 入口。

        只负责接收前端请求、调用 create_project() 并返回结果。
        不负责生成 Project ID、创建目录、写 project.json 或直接执行 SQL。
        """
        return create_project(**payload.model_dump()).to_dict()

    @app.post("/api/projects/{project_id}/open", response_model=ProjectResponse)
    def open_project_api(project_id: str) -> dict:
        """打开项目 HTTP 入口：调用 open_project() 完成完整性检查和打开时间更新。"""
        return open_project(project_id=project_id).to_dict()

    return app


app = create_app()
