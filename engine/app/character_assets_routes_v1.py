"""人物资产工作区：显式归并、目标设计、四视图生成与人工选版。"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from engine.app.source_person_assets_v1 import LOCK, assign, inventory, digest
from engine.app.studio_v2 import Project, get_session, new_id, project_dir, utcnow
from engine.app.target_localization_v1 import TargetCharacter, _character_contexts, _serialize_character
from engine.app.source_drama_snapshot_v1 import load_project_source_drama_snapshot_v1
from engine.app.h3_reference_assets_v1 import _extract_frame, _ffmpeg, _wait_for_job
from engine.app.minimax_h3_provider_v1 import get_video_generation_provider_v1
from engine.app.video_generation_provider_v1 import VideoGenerationRequestV1
from engine.app.task_progress_v2 import BackgroundTaskRecord, create_task, start_task, finish_task, fail_task, serialize_task, update_task

router = APIRouter(prefix="/api", tags=["character-assets"])
VIEWS = ("front", "left", "back", "right")


class Assignment(BaseModel):
    keys: list[str] = Field(min_length=1, max_length=500)
    name: str = Field(default="", max_length=200)
    character_id: str | None = None
    expected_revision: str
    localizations: dict = Field(default_factory=dict)


class Design(BaseModel):
    source_character_id: str
    expected_revision: str
    expected_target_fingerprint: str | None = None
    target_name: str = Field(min_length=1, max_length=200)
    appearance_profile: str = Field(min_length=1, max_length=8000)
    generation_prompt: str = Field(min_length=1, max_length=8000)


def signature(character):
    return digest({k: character[k] for k in ("id", "source_character_signature", "target_language", "target_region", "target_name", "appearance_profile", "generation_prompt")})


def target_context(project_id):
    snapshot = load_project_source_drama_snapshot_v1(project_id)
    return snapshot, {c["source_character_id"]: c for c in _character_contexts(snapshot)}


def require_current(target_id):
    with get_session() as session:
        row = session.get(TargetCharacter, target_id)
        if row is None:
            raise HTTPException(404, "目标人物不存在")
        character = _serialize_character(row)
        project = session.get(Project, row.project_id)
        locale_matches = project and row.target_language == project.target_language and row.target_region == project.target_region
    _, contexts = target_context(character["project_id"])
    context = contexts.get(character["source_character_id"])
    if not context or context["signature"] != character["source_character_signature"] or not locale_matches or character["status"] != "READY":
        raise HTTPException(409, "原片人物或目标设计已变化，请重新保存目标设计")
    return character


def version_root(project_id, task_id):
    return project_dir(project_id) / "target" / "four-views" / task_id


@router.get("/projects/{project_id}/character-assets")
def get_workspace(project_id: str):
    result = inventory(project_id)
    try:
        _, contexts = target_context(project_id)
        result["snapshot_error"] = None
    except Exception as exc:
        contexts = {}
        result["snapshot_error"] = str(exc)
    with get_session() as session:
        project = session.get(Project, project_id)
        if not project:
            raise HTTPException(404, "项目不存在")
        result["target_region"] = project.target_region
        result["designable_ids"] = list(contexts)
        targets = [_serialize_character(c) for c in session.scalars(select(TargetCharacter).where(TargetCharacter.project_id == project_id)).all()]
        task_rows = session.scalars(select(BackgroundTaskRecord).where(BackgroundTaskRecord.project_id == project_id, BackgroundTaskRecord.task_type == "CHARACTER_FOUR_VIEWS").order_by(BackgroundTaskRecord.created_at.desc())).all()
        for c in targets:
            c["current"] = bool(contexts.get(c["source_character_id"], {}).get("signature") == c["source_character_signature"] and c["target_language"] == project.target_language and c["target_region"] == project.target_region)
            c["fingerprint"] = signature(c)
            c["versions"] = []
            for task in task_rows:
                receipt = json.loads(task.result_json or "{}")
                if receipt.get("target_id") != c["id"]:
                    continue
                version = {"id": task.id, "status": task.status, "error": task.error_message, "current": c["current"] and receipt.get("fingerprint") == c["fingerprint"], "accepted": receipt.get("accepted", False), "images": []}
                if task.status == "READY":
                    version["images"] = [{"view": view, "url": f"/api/character-view-versions/{task.id}/{view}"} for view in VIEWS]
                c["versions"].append(version)
        result["targets"] = targets
    return result


@router.post("/projects/{project_id}/character-assets/assign")
def assign_people(project_id: str, payload: Assignment):
    try:
        assign(project_id, payload.keys, payload.name, payload.character_id, payload.expected_revision, payload.localizations)
        return get_workspace(project_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/projects/{project_id}/character-assets/design")
def save_design(project_id: str, payload: Design):
    with LOCK:
        if inventory(project_id)["revision"] != payload.expected_revision:
            raise HTTPException(409, "原片人物已变化，请刷新后重新设计")
        _, contexts = target_context(project_id)
        source = contexts.get(payload.source_character_id)
        if not source:
            raise HTTPException(409, "请先完成原片人物归并和分镜绑定，形成当前原片快照")
        with get_session() as session:
            project = session.get(Project, project_id)
            row = session.scalar(select(TargetCharacter).where(TargetCharacter.project_id == project_id, TargetCharacter.source_character_id == payload.source_character_id))
            if row and signature(_serialize_character(row)) != payload.expected_target_fingerprint:
                raise HTTPException(409, "目标设计已被修改，请重新打开设计表单")
            if not row:
                row = TargetCharacter(id=new_id("TARGETCHAR"), project_id=project_id, source_character_id=payload.source_character_id)
                session.add(row)
            snapshot, _ = target_context(project_id)
            row.source_character_name = source["source_name"]
            row.source_character_signature = source["signature"]
            row.source_fingerprint = snapshot["source_fingerprint"]
            row.target_language = project.target_language
            row.target_region = project.target_region
            row.target_name = payload.target_name.strip()
            row.appearance_profile = payload.appearance_profile.strip()
            row.generation_prompt = payload.generation_prompt.strip()
            if not all((row.target_name, row.appearance_profile, row.generation_prompt)):
                raise HTTPException(400, "人物设计内容不能为空")
            row.status = "READY"
            row.decision_source = "MANUAL"
            row.updated_at = utcnow()
            row.reference_assets_json = "[]"
            session.commit()
        return get_workspace(project_id)


class GenerateRequest(BaseModel):
    fingerprint: str


def validate_reference_video(video):
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video)], check=True, capture_output=True, text=True, timeout=60)
    duration = float(json.loads(probe.stdout)["format"]["duration"])
    if not 7.5 <= duration <= 8.5:
        raise ValueError("四视图参考视频时长不符合 8 秒生成计划")
    _ffmpeg(["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"])


def run_views(task_id, character, receipt):
    try:
        start_task(task_id, stage_key="target_design", stage_label="生成目标人物四视图")
        provider = get_video_generation_provider_v1("MINIMAX_H3_LOCAL")
        root = version_root(character["project_id"], task_id)
        root.mkdir(parents=True, exist_ok=True)
        prompt = (
            "integrated_multimodal_description: One fictional replacement actor, full body, neutral studio background. "
            f'{character["target_name"]}: {character["appearance_profile"]}. {character["generation_prompt"]}. '
            "Fixed camera, same identity, hair and clothing throughout. No cuts, no other people, no text. "
            "0-2 seconds: hold front view. 2-4 seconds: turn and hold left profile. "
            "4-6 seconds: turn and hold back view. 6-8 seconds: turn and hold right profile. "
            "No speaking. Keep entire body inside frame.\n\noverall_soundscape: Quiet.\n\nnon_diegetic_music: N/A"
        )
        request = VideoGenerationRequestV1(mode="FL2VA", prompt=prompt, duration_seconds=8, short_edge=768, aspect_ratio="9:16", seed=int(digest(task_id)[:8], 16) & 0x7fffffff)
        submitted = provider.submit(request)
        _wait_for_job(provider, mode="FL2VA", job_id=submitted.external_job_id)
        video = provider.download(mode="FL2VA", external_job_id=submitted.external_job_id, destination=root / "reference.mp4")
        validate_reference_video(video)
        for index, view in enumerate(VIEWS):
            _extract_frame(video, 1.0 + index * 2, root / f"{view}.jpg")
            update_task(task_id, progress_percent=70 + index * 8, stage_label=f"提取 {view} 参考图")
        finish_task(task_id, result={**receipt, "accepted": False}, message="四视图候选已生成，请确认角度与人物一致性后采用")
    except Exception as exc:
        fail_task(task_id, exc)


@router.post("/target-characters/{target_id}/four-views")
def generate_views(target_id: str, payload: GenerateRequest, background: BackgroundTasks, idempotency_key: str = Header(..., min_length=1, max_length=200)):
    with LOCK:
        character = require_current(target_id)
        if payload.fingerprint != signature(character):
            raise HTTPException(409, "目标人物设计已变化，请刷新")
        with get_session() as session:
            for task in session.scalars(select(BackgroundTaskRecord).where(BackgroundTaskRecord.project_id == character["project_id"], BackgroundTaskRecord.task_type == "CHARACTER_FOUR_VIEWS")).all():
                receipt = json.loads(task.result_json or "{}")
                if receipt.get("key") == idempotency_key:
                    if receipt.get("target_id") != target_id or receipt.get("fingerprint") != payload.fingerprint:
                        raise HTTPException(409, "幂等请求与原请求内容不一致")
                    return serialize_task(task)
                if task.status in {"QUEUED", "PROCESSING"}:
                    raise HTTPException(409, "已有四视图任务正在执行，请等待完成")
        status = get_video_generation_provider_v1("MINIMAX_H3_LOCAL").status()
        if not (status.get("fl2va") or {}).get("ready"):
            raise HTTPException(503, "WAITING_RUNTIME：本地 H3 尚未就绪，未创建生成任务")
        task = create_task(project_id=character["project_id"], task_type="CHARACTER_FOUR_VIEWS", title=f'生成 {character["target_name"]} 四视图')
        receipt = {"target_id": target_id, "fingerprint": payload.fingerprint, "key": idempotency_key}
        with get_session() as session:
            session.get(BackgroundTaskRecord, task["id"]).result_json = json.dumps(receipt)
            session.commit()
        background.add_task(run_views, task["id"], character, receipt)
        return task


@router.get("/character-view-versions/{task_id}/{view}")
def view_image(task_id: str, view: str):
    if view not in VIEWS:
        raise HTTPException(404, "视图不存在")
    with get_session() as session:
        task = session.get(BackgroundTaskRecord, task_id)
        if not task or task.task_type != "CHARACTER_FOUR_VIEWS" or task.status != "READY":
            raise HTTPException(404, "四视图尚未生成")
        path = version_root(task.project_id, task.id) / f"{view}.jpg"
    if not path.is_file():
        raise HTTPException(404, "图片文件缺失")
    return FileResponse(path)


@router.post("/character-view-versions/{task_id}/accept")
def accept_views(task_id: str, payload: GenerateRequest):
    with LOCK, get_session() as session:
        task = session.get(BackgroundTaskRecord, task_id)
        if not task or task.task_type != "CHARACTER_FOUR_VIEWS" or task.status != "READY":
            raise HTTPException(409, "生成任务尚未完成")
        receipt = json.loads(task.result_json or "{}")
        character = require_current(receipt["target_id"])
        if receipt["fingerprint"] != payload.fingerprint or signature(character) != payload.fingerprint:
            raise HTTPException(409, "四视图已过期，请按当前人物设计重新生成")
        paths = [version_root(task.project_id, task.id) / f"{view}.jpg" for view in VIEWS]
        if not all(p.is_file() and p.stat().st_size for p in paths):
            raise HTTPException(409, "四张图片未完整生成")
        row = session.get(TargetCharacter, character["id"])
        for old in session.scalars(select(BackgroundTaskRecord).where(BackgroundTaskRecord.project_id == task.project_id, BackgroundTaskRecord.task_type == "CHARACTER_FOUR_VIEWS")).all():
            data = json.loads(old.result_json or "{}")
            if data.get("target_id") == row.id:
                data["accepted"] = old.id == task.id
                old.result_json = json.dumps(data)
        row.reference_assets_json = json.dumps([str(p) for p in paths])
        row.updated_at = utcnow()
        session.commit()
    return {"accepted": True}
