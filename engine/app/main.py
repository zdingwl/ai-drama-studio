"""AI Drama Studio V2 FastAPI 入口。

当前可用范围：
多剧集管理、自动初始化 + 拉片、Shot 人工修正、Final Asset / Shot Binding，以及统一后台 Task / Progress API。
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from engine.app.asset_batch_routes_v4 import router as asset_batch_router
from engine.app.asset_routes_v3 import router as asset_router
from engine.app.character_gallery_routes_v10 import router as character_gallery_router
from engine.app.content_analysis_v2 import (
    ContentAnalysisError,
    content_model_status,
    get_analysis_run,
    get_candidate_cover,
    get_current_analysis,
    run_content_analysis,
)
from engine.app.content_models_v2 import ContentModelError, prepare_models
from engine.app.media_v2 import MediaPipelineError, detect_episode_shots, preprocess_episode
from engine.app.shot_cache_routes_v51 import router as shot_cache_router
from engine.app.shot_edit_routes_v2 import router as shot_edit_router
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
from engine.app.task_progress_v2 import recover_interrupted_tasks
from engine.app.task_routes_v2 import router as task_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    # asset_routes_v3 / asset_batch_routes_v4 / content_analysis_v2 / task_progress_v2 已在本模块 import，
    # Final Asset / Binding / Revision 表会进入同一个 Base metadata。
    init_database()
    recover_interrupted_tasks()
    yield


app = FastAPI(title="AI Drama Studio", version="2.4.1", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(task_router)
app.include_router(shot_cache_router)
app.include_router(shot_edit_router)
app.include_router(asset_router)
app.include_router(asset_batch_router)
app.include_router(character_gallery_router)


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
    return {"status": "ok", "architecture": "reference-video-v2", "app_version": "2.4.1"}


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


# 下面同步接口继续保留兼容旧测试/调试；正式 UI 已改走后台 Task。
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


# ---------------------------- AI Evidence 兼容接口 ----------------------------


@app.get("/api/models/f05/status")
def api_f05_model_status() -> dict[str, object]:
    """查看人物视觉模型是否已经在本机准备完成。"""
    return content_model_status()


@app.post("/api/models/f05/prepare")
def api_prepare_f05_models() -> dict[str, object]:
    """显式下载并校验固定人物视觉模型。运行分析时不会静默联网下载。"""
    try:
        return prepare_models()
    except ContentModelError as exc:
        raise _bad_request(exc) from exc


@app.post("/api/projects/{project_id}/content-analysis")
def api_run_content_analysis(project_id: str) -> dict[str, Any]:
    """同步兼容接口；正式资产页使用 /api/projects/{project_id}/assets/tasks/extract。"""
    if get_project(project_id) is None:
        raise _not_found("项目不存在")
    try:
        return run_content_analysis(project_id)
    except LookupError as exc:
        raise _not_found(str(exc)) from exc
    except (ContentAnalysisError, ContentModelError, ValueError, OSError) as exc:
        raise _bad_request(exc) from exc


@app.get("/api/projects/{project_id}/content-analysis/current")
def api_current_content_analysis(project_id: str) -> dict[str, Any] | None:
    if get_project(project_id) is None:
        raise _not_found("项目不存在")
    return get_current_analysis(project_id)


@app.get("/api/content-analysis/{run_id}")
def api_get_content_analysis(run_id: str) -> dict[str, Any]:
    payload = get_analysis_run(run_id)
    if payload is None:
        raise _not_found("资产分析 Run 不存在")
    return payload


@app.get("/api/content-analysis/characters/{candidate_id}/cover")
def api_character_candidate_cover(candidate_id: str) -> FileResponse:
    path = get_candidate_cover(candidate_id, "character")
    if path is None or not path.is_file():
        raise _not_found("人物候选封面不存在")
    return FileResponse(path, media_type="image/jpeg", filename=path.name)


@app.get("/api/content-analysis/scenes/{candidate_id}/cover")
def api_scene_candidate_cover(candidate_id: str) -> FileResponse:
    path = get_candidate_cover(candidate_id, "scene")
    if path is None or not path.is_file():
        raise _not_found("场景候选封面不存在")
    return FileResponse(path, media_type="image/jpeg", filename=path.name)
