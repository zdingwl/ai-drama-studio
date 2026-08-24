"""AI Drama Studio V2 FastAPI 入口。

当前可用范围：
F01 项目管理、F02 多剧集导入与排序、F03 视频预处理、F04 自动拉片与 Reference Clip。
F05-F13 的数据实体已经预留，但不会用占位按钮伪装为已实现能力。
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from engine.app.media_v2 import MediaPipelineError, detect_episode_shots, preprocess_episode
from engine.app.studio_v2 import (
    create_project,
    delete_episode,
    get_episode,
    get_project,
    get_shot_path,
    import_episode,
    init_database,
    list_episode_records,
    list_projects,
    list_shots,
    reorder_episodes,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    yield


app = FastAPI(title="AI Drama Studio", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    source_language: str = Field(min_length=1, max_length=32)
    target_language: str = Field(min_length=1, max_length=32)
    target_region: str = Field(min_length=1, max_length=64)


class EpisodeReorder(BaseModel):
    episode_ids: list[str]


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail=message)


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "architecture": "reference-video-v2"}


@app.get("/api/projects")
def api_list_projects() -> list[dict[str, Any]]:
    return list_projects()


@app.post("/api/projects", status_code=201)
def api_create_project(payload: ProjectCreate) -> dict[str, Any]:
    try:
        return create_project(**payload.model_dump())
    except ValueError as exc:
        raise _bad_request(exc) from exc


@app.get("/api/projects/{project_id}")
def api_get_project(project_id: str) -> dict[str, Any]:
    project = get_project(project_id)
    if project is None:
        raise _not_found("项目不存在")
    return project


@app.post("/api/projects/{project_id}/episodes", status_code=201)
def api_import_episode(project_id: str, file: UploadFile = File(...), title: str | None = Form(default=None)) -> dict[str, Any]:
    try:
        return import_episode(project_id=project_id, upload=file, title=title)
    except LookupError as exc:
        raise _not_found(str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise _bad_request(exc) from exc


@app.post("/api/projects/{project_id}/episodes/batch", status_code=201)
def api_import_episodes(project_id: str, files: list[UploadFile] = File(...)) -> list[dict[str, Any]]:
    if not files:
        raise HTTPException(status_code=400, detail="至少选择一个视频")
    results: list[dict[str, Any]] = []
    for upload in files:
        try:
            results.append(import_episode(project_id=project_id, upload=upload))
        except LookupError as exc:
            raise _not_found(str(exc)) from exc
        except (ValueError, OSError) as exc:
            raise _bad_request(exc) from exc
    return results


@app.patch("/api/projects/{project_id}/episodes/reorder")
def api_reorder_episodes(project_id: str, payload: EpisodeReorder) -> list[dict[str, Any]]:
    try:
        return reorder_episodes(project_id=project_id, episode_ids=payload.episode_ids)
    except ValueError as exc:
        raise _bad_request(exc) from exc


@app.delete("/api/episodes/{episode_id}", status_code=204)
def api_delete_episode(episode_id: str) -> None:
    try:
        delete_episode(episode_id)
    except LookupError as exc:
        raise _not_found(str(exc)) from exc


@app.get("/api/episodes/{episode_id}")
def api_get_episode(episode_id: str) -> dict[str, Any]:
    episode = get_episode(episode_id)
    if episode is None:
        raise _not_found("剧集不存在")
    return episode


@app.post("/api/episodes/{episode_id}/preprocess")
def api_preprocess_episode(episode_id: str) -> dict[str, Any]:
    try:
        return preprocess_episode(episode_id)
    except LookupError as exc:
        raise _not_found(str(exc)) from exc
    except MediaPipelineError as exc:
        raise _bad_request(exc) from exc


@app.post("/api/projects/{project_id}/preprocess-batch")
def api_preprocess_project(project_id: str) -> dict[str, Any]:
    if get_project(project_id) is None:
        raise _not_found("项目不存在")
    results: list[dict[str, Any]] = []
    for episode in list_episode_records(project_id):
        try:
            info = preprocess_episode(episode.id)
            results.append({"episode_id": episode.id, "status": "READY", "media": info})
        except Exception as exc:
            results.append({"episode_id": episode.id, "status": "FAILED", "error": str(exc)})
            break
    return {"mode": "sequential", "results": results}


@app.post("/api/episodes/{episode_id}/shots/analyze")
def api_analyze_episode_shots(episode_id: str) -> list[dict[str, Any]]:
    try:
        return detect_episode_shots(episode_id)
    except LookupError as exc:
        raise _not_found(str(exc)) from exc
    except MediaPipelineError as exc:
        raise _bad_request(exc) from exc


@app.post("/api/projects/{project_id}/shots/analyze-batch")
def api_analyze_project_shots(project_id: str) -> dict[str, Any]:
    if get_project(project_id) is None:
        raise _not_found("项目不存在")
    results: list[dict[str, Any]] = []
    for episode in list_episode_records(project_id):
        try:
            shots = detect_episode_shots(episode.id)
            results.append({"episode_id": episode.id, "status": "READY", "shot_count": len(shots)})
        except Exception as exc:
            results.append({"episode_id": episode.id, "status": "FAILED", "error": str(exc)})
            break
    return {"mode": "sequential", "results": results}


@app.get("/api/episodes/{episode_id}/shots")
def api_list_episode_shots(episode_id: str) -> list[dict[str, Any]]:
    if get_episode(episode_id) is None:
        raise _not_found("剧集不存在")
    return list_shots(episode_id)


@app.get("/api/shots/{shot_id}/reference")
def api_reference_clip(shot_id: str) -> FileResponse:
    path = get_shot_path(shot_id, "reference")
    if path is None or not path.is_file():
        raise _not_found("Reference Clip 不存在")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@app.get("/api/shots/{shot_id}/thumbnail")
def api_shot_thumbnail(shot_id: str) -> FileResponse:
    path = get_shot_path(shot_id, "thumbnail")
    if path is None or not path.is_file():
        raise _not_found("镜头缩略图不存在")
    return FileResponse(path, media_type="image/jpeg", filename=path.name)
