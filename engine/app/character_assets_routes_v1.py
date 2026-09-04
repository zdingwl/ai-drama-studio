"""人物资产工作区：显式归并、目标人物设计、四视图生成与人工选版。

Source Character 与 Target Character 分层：
- 原片人物归并 / Shot Binding 写 Character + ShotCharacterBinding；
- 目标人物设计写 TargetCharacter；
- 四视图是 TargetCharacter 的可版本化 Reference Set，只有人工采用的当前版本
  才写入 TargetCharacter.reference_assets_json 给 H3 下游消费。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from engine.app.h3_reference_assets_v1 import _extract_frame, _ffmpeg, _wait_for_job
from engine.app.minimax_h3_provider_v1 import get_video_generation_provider_v1
from engine.app.source_drama_snapshot_v1 import load_project_source_drama_snapshot_v1
from engine.app.source_person_assets_v1 import LOCK, assign, digest, inventory
from engine.app.studio_v2 import Project, get_session, new_id, project_dir, utcnow
from engine.app.target_localization_v1 import TargetCharacter, _character_contexts, _serialize_character
from engine.app.task_progress_v2 import (
    BackgroundTaskRecord,
    create_task,
    fail_task,
    finish_task,
    serialize_task,
    start_task,
    update_task,
)
from engine.app.video_generation_provider_v1 import VideoGenerationRequestV1

router = APIRouter(prefix="/api", tags=["character-assets"])

# v2 是当前标准：正面 / 45° / 侧面 / 背面。
# legacy-v1 只用于读取已经生成的历史 four-view task，避免升级后历史图片 URL 失效。
VIEW_SCHEMA_V2 = "character-reference-v2"
VIEWS_V2 = ("front", "three_quarter", "side", "back")
VIEWS_LEGACY = ("front", "left", "back", "right")
# 兼容已有调用和历史测试。新代码必须显式使用 VIEWS_V2 或 _views_for_receipt。
VIEWS = VIEWS_LEGACY
ALL_VIEWS = frozenset((*VIEWS_V2, *VIEWS_LEGACY))


class Assignment(BaseModel):
    keys: list[str] = Field(min_length=1, max_length=500)
    name: str = Field(default="", max_length=200)
    character_id: str | None = None
    expected_revision: str
    # 用户已经明确选择 Local Person 时允许不重复框人；只有 UI 真正提交定位框时才校验坐标。
    localizations: dict | None = None


class PresenceSupplement(BaseModel):
    character_id: str = ''
    expected_revision: str
    localization: dict
    issue_id: str | None = None
    candidate_id: str | None = None
    decision: str = 'BIND'
    reason: str = Field(default='', max_length=2000)


@router.get('/projects/{project_id}/character-assets/shots/{shot_id}/presence')
def get_presence_context(project_id: str, shot_id: str):
    from engine.app.source_presence_correction_v1 import context
    try:
        return context(project_id, shot_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post('/projects/{project_id}/character-assets/shots/{shot_id}/presence')
def add_presence(project_id: str, shot_id: str, payload: PresenceSupplement):
    from engine.app.source_presence_correction_v1 import supplement
    try:
        return supplement(project_id, shot_id, payload.character_id, payload.localization, payload.expected_revision,
                          issue_id=payload.issue_id, candidate_id=payload.candidate_id, decision=payload.decision, reason=payload.reason)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get('/projects/{project_id}/presence-frames/{frame_id}')
def get_presence_frame(project_id: str, frame_id: str):
    from engine.app.source_presence_audit_v1 import frame_path
    if not project_id.startswith('PROJECT_') or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in project_id):
        raise HTTPException(404, '项目不存在')
    try:
        path = frame_path(project_id, frame_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    if not path.is_file():
        raise HTTPException(404, '核对画面不存在')
    return FileResponse(path, media_type='image/jpeg')


class Design(BaseModel):
    source_character_id: str
    expected_revision: str
    expected_target_fingerprint: str | None = None
    target_name: str = Field(min_length=1, max_length=200)
    appearance_profile: str = Field(min_length=1, max_length=8000)
    generation_prompt: str = Field(min_length=1, max_length=8000)


class GenerateRequest(BaseModel):
    fingerprint: str


def signature(character: dict) -> str:
    return digest({
        key: character[key]
        for key in (
            "id",
            "source_character_signature",
            "target_language",
            "target_region",
            "target_name",
            "appearance_profile",
            "generation_prompt",
        )
    })


def target_context(project_id: str):
    snapshot = load_project_source_drama_snapshot_v1(project_id)
    return snapshot, {item["source_character_id"]: item for item in _character_contexts(snapshot)}


def require_current(target_id: str) -> dict:
    with get_session() as session:
        row = session.get(TargetCharacter, target_id)
        if row is None:
            raise HTTPException(404, "目标人物不存在")
        character = _serialize_character(row)
        project = session.get(Project, row.project_id)
        locale_matches = bool(
            project
            and row.target_language == project.target_language
            and row.target_region == project.target_region
        )
    _, contexts = target_context(character["project_id"])
    context = contexts.get(character["source_character_id"])
    if (
        not context
        or context["signature"] != character["source_character_signature"]
        or not locale_matches
        or character["status"] != "READY"
    ):
        raise HTTPException(409, "原片人物或目标设计已变化，请重新保存目标设计")
    return character


def version_root(project_id: str, task_id: str) -> Path:
    return project_dir(project_id) / "target" / "four-views" / task_id


def _views_for_receipt(receipt: dict) -> tuple[str, ...]:
    if receipt.get("view_schema") == VIEW_SCHEMA_V2:
        return VIEWS_V2
    return VIEWS_LEGACY


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
        result["target_language"] = project.target_language
        result["designable_ids"] = list(contexts)

        targets = [
            _serialize_character(character)
            for character in session.scalars(
                select(TargetCharacter).where(TargetCharacter.project_id == project_id)
            ).all()
        ]
        task_rows = session.scalars(
            select(BackgroundTaskRecord)
            .where(
                BackgroundTaskRecord.project_id == project_id,
                BackgroundTaskRecord.task_type == "CHARACTER_FOUR_VIEWS",
            )
            .order_by(BackgroundTaskRecord.created_at.desc())
        ).all()

        for character in targets:
            character["current"] = bool(
                contexts.get(character["source_character_id"], {}).get("signature")
                == character["source_character_signature"]
                and character["target_language"] == project.target_language
                and character["target_region"] == project.target_region
            )
            character["fingerprint"] = signature(character)
            character["versions"] = []
            for task in task_rows:
                receipt = json.loads(task.result_json or "{}")
                if receipt.get("target_id") != character["id"]:
                    continue
                views = _views_for_receipt(receipt)
                version = {
                    "id": task.id,
                    "status": task.status,
                    "error": task.error_message,
                    "current": bool(
                        character["current"]
                        and receipt.get("fingerprint") == character["fingerprint"]
                    ),
                    "accepted": receipt.get("accepted", False),
                    "view_schema": receipt.get("view_schema") or "legacy-v1",
                    "images": [],
                }
                if task.status == "READY":
                    version["images"] = [
                        {
                            "view": view,
                            "url": f"/api/character-view-versions/{task.id}/{view}",
                        }
                        for view in views
                    ]
                character["versions"].append(version)
        result["targets"] = targets
    return result


@router.post("/projects/{project_id}/character-assets/assign")
def assign_people(project_id: str, payload: Assignment):
    try:
        assign(
            project_id,
            payload.keys,
            payload.name,
            payload.character_id,
            payload.expected_revision,
            payload.localizations,
        )
        return get_workspace(project_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/projects/{project_id}/character-assets/review-plan")
def get_person_review_plan(project_id: str):
    """只读候选分组与定位证据，不持久化自动身份，不运行模型。"""
    from engine.app.source_person_auto_resolver_v1 import build_auto_resolution_plan

    workspace = inventory(project_id)
    return {"workspace": workspace, "proposals": build_auto_resolution_plan(project_id, workspace["observations"])}


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
            if project is None:
                raise HTTPException(404, "项目不存在")
            row = session.scalar(
                select(TargetCharacter).where(
                    TargetCharacter.project_id == project_id,
                    TargetCharacter.source_character_id == payload.source_character_id,
                )
            )
            if row and signature(_serialize_character(row)) != payload.expected_target_fingerprint:
                raise HTTPException(409, "目标设计已被修改，请重新打开设计表单")
            if not row:
                row = TargetCharacter(
                    id=new_id("TARGETCHAR"),
                    project_id=project_id,
                    source_character_id=payload.source_character_id,
                )
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
            # 设计变化后旧 Reference Set 必须失效，不能继续给 H3 使用。
            row.reference_assets_json = "[]"
            session.commit()
        return get_workspace(project_id)


def validate_reference_video(video: Path) -> None:
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(video),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    duration = float(json.loads(probe.stdout)["format"]["duration"])
    if not 7.5 <= duration <= 8.5:
        raise ValueError("四视图参考视频时长不符合 8 秒生成计划")
    _ffmpeg(["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"])


def run_views(task_id: str, character: dict, receipt: dict) -> None:
    """一次连续生成同一身份的四角度参考，再从固定时间点抽帧。

    这样比四次独立图片生成更能保持脸、发型、服装和体型一致。
    """

    try:
        start_task(task_id, stage_key="target_design", stage_label="生成目标人物四视图")
        provider = get_video_generation_provider_v1("MINIMAX_H3_LOCAL")
        root = version_root(character["project_id"], task_id)
        root.mkdir(parents=True, exist_ok=True)
        prompt = (
            "integrated_multimodal_description: One fictional replacement actor, full body, neutral studio background. "
            f'{character["target_name"]}: {character["appearance_profile"]}. '
            f'{character["generation_prompt"]}. '
            "This is one continuous identity reference turntable. Keep exactly the same face identity, age, "
            "skin tone, body proportions, hairstyle, hair color, clothing, accessories and shoes for the entire video. "
            "Fixed camera, eye-level, soft even studio light, full body completely inside frame, no cuts, no zoom, "
            "no other people, no props, no text, no speaking. "
            "0-2 seconds: hold straight front full-body view. "
            "2-4 seconds: rotate to and hold a 45-degree three-quarter full-body view. "
            "4-6 seconds: rotate to and hold a clean side-profile full-body view. "
            "6-8 seconds: rotate to and hold a straight back full-body view. "
            "Transitions should be smooth but each requested angle must be still and clearly readable at the midpoint.\n\n"
            "overall_soundscape: Quiet.\n\nnon_diegetic_music: N/A"
        )
        request = VideoGenerationRequestV1(
            mode="FL2VA",
            prompt=prompt,
            duration_seconds=8,
            short_edge=768,
            aspect_ratio="9:16",
            seed=int(digest(task_id)[:8], 16) & 0x7FFFFFFF,
        )
        submitted = provider.submit(request)
        _wait_for_job(provider, mode="FL2VA", job_id=submitted.external_job_id)
        video = provider.download(
            mode="FL2VA",
            external_job_id=submitted.external_job_id,
            destination=root / "reference.mp4",
        )
        validate_reference_video(video)

        for index, view in enumerate(VIEWS_V2):
            _extract_frame(video, 1.0 + index * 2.0, root / f"{view}.jpg")
            update_task(
                task_id,
                progress_percent=70 + index * 8,
                stage_label=f"提取 {view} 参考图",
            )
        finish_task(
            task_id,
            result={**receipt, "view_schema": VIEW_SCHEMA_V2, "accepted": False},
            message="四视图候选已生成，请确认正面、45°、侧面、背面及人物一致性后采用",
        )
    except Exception as exc:
        fail_task(task_id, exc)


@router.post("/target-characters/{target_id}/four-views")
def generate_views(
    target_id: str,
    payload: GenerateRequest,
    background: BackgroundTasks,
    idempotency_key: str = Header(..., min_length=1, max_length=200),
):
    with LOCK:
        character = require_current(target_id)
        if payload.fingerprint != signature(character):
            raise HTTPException(409, "目标人物设计已变化，请刷新")

        with get_session() as session:
            tasks = session.scalars(
                select(BackgroundTaskRecord).where(
                    BackgroundTaskRecord.project_id == character["project_id"],
                    BackgroundTaskRecord.task_type == "CHARACTER_FOUR_VIEWS",
                )
            ).all()
            for task in tasks:
                receipt = json.loads(task.result_json or "{}")
                if receipt.get("key") == idempotency_key:
                    if (
                        receipt.get("target_id") != target_id
                        or receipt.get("fingerprint") != payload.fingerprint
                    ):
                        raise HTTPException(409, "幂等请求与原请求内容不一致")
                    return serialize_task(task)
                if task.status in {"QUEUED", "PROCESSING"}:
                    raise HTTPException(409, "已有四视图任务正在执行，请等待完成")

        status = get_video_generation_provider_v1("MINIMAX_H3_LOCAL").status()
        if not (status.get("fl2va") or {}).get("ready"):
            raise HTTPException(503, "WAITING_RUNTIME：本地 H3 尚未就绪，未创建生成任务")

        task = create_task(
            project_id=character["project_id"],
            task_type="CHARACTER_FOUR_VIEWS",
            title=f'生成 {character["target_name"]} 四视图',
        )
        receipt = {
            "target_id": target_id,
            "fingerprint": payload.fingerprint,
            "key": idempotency_key,
            "view_schema": VIEW_SCHEMA_V2,
        }
        with get_session() as session:
            row = session.get(BackgroundTaskRecord, task["id"])
            if row is None:
                raise HTTPException(500, "四视图任务创建失败")
            row.result_json = json.dumps(receipt)
            session.commit()
        background.add_task(run_views, task["id"], character, receipt)
        return task


@router.get("/character-view-versions/{task_id}/{view}")
def view_image(task_id: str, view: str):
    if view not in ALL_VIEWS:
        raise HTTPException(404, "视图不存在")
    with get_session() as session:
        task = session.get(BackgroundTaskRecord, task_id)
        if not task or task.task_type != "CHARACTER_FOUR_VIEWS" or task.status != "READY":
            raise HTTPException(404, "四视图尚未生成")
        receipt = json.loads(task.result_json or "{}")
        if view not in _views_for_receipt(receipt):
            raise HTTPException(404, "该版本不包含此视图")
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

        views = _views_for_receipt(receipt)
        paths = [version_root(task.project_id, task.id) / f"{view}.jpg" for view in views]
        if not all(path.is_file() and path.stat().st_size for path in paths):
            raise HTTPException(409, "四张人物参考图未完整生成")

        row = session.get(TargetCharacter, character["id"])
        if row is None:
            raise HTTPException(404, "目标人物不存在")
        old_tasks = session.scalars(
            select(BackgroundTaskRecord).where(
                BackgroundTaskRecord.project_id == task.project_id,
                BackgroundTaskRecord.task_type == "CHARACTER_FOUR_VIEWS",
            )
        ).all()
        for old in old_tasks:
            data = json.loads(old.result_json or "{}")
            if data.get("target_id") == row.id:
                data["accepted"] = old.id == task.id
                old.result_json = json.dumps(data)

        # 保持下游现有接口：四张已采用图片路径仍写 reference_assets_json。
        # Task receipt 保留 view_schema，读取历史版本不会因升级角度标准而失效。
        row.reference_assets_json = json.dumps([str(path) for path in paths])
        row.updated_at = utcnow()
        session.commit()
    return {"accepted": True, "view_schema": receipt.get("view_schema") or "legacy-v1"}
