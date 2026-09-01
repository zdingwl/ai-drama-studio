"""R5 TargetDialogue / target voice / local Qwen3-TTS product APIs."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from engine.app.qwen3_tts_runtime_v1 import runtime_status
from engine.app.source_drama_snapshot_v1 import SourceDramaSnapshotError
from engine.app.studio_v2 import get_session
from engine.app.target_dialogue_contract_v1 import TargetDialogueBundleV1, TargetDialogueV1
from engine.app.target_dialogue_v1 import (
    TargetDialogue,
    TargetDialogueError,
    generate_target_dialogue_text_v1,
    generate_target_dialogue_v1,
    get_target_dialogue_v1,
    materialize_target_dialogue_audio_v1,
    update_target_dialogue_v1,
)


# Mounted by target_localization_routes_v1, whose parent already owns the /api prefix.
router = APIRouter(tags=["target-dialogue"])


class TargetDialogueGenerateRequest(BaseModel):
    synthesize_audio: bool = True


class TargetDialogueEditRequest(BaseModel):
    translated_text: str | None = Field(default=None, max_length=12000)
    localized_text: str | None = Field(default=None, max_length=12000)
    final_text: str = Field(min_length=1, max_length=12000)


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, SourceDramaSnapshotError):
        return HTTPException(status_code=409, detail="SourceDramaSnapshot 当前不可用")
    if isinstance(exc, TargetDialogueError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=409, detail=f"目标对白当前不可用：{exc}")


@router.get("/tts/runtime-status")
def api_tts_runtime_status():
    """Infrastructure status only; TTS setup is not a separate user workflow page."""
    return runtime_status()


@router.post("/projects/{project_id}/target-dialogue/generate", response_model=TargetDialogueBundleV1)
def api_generate_target_dialogue(project_id: str, payload: TargetDialogueGenerateRequest):
    try:
        return generate_target_dialogue_v1(project_id, synthesize_audio=payload.synthesize_audio)
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/projects/{project_id}/target-dialogue/generate-text", response_model=TargetDialogueBundleV1)
def api_generate_target_dialogue_text(project_id: str):
    try:
        return generate_target_dialogue_text_v1(project_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/projects/{project_id}/target-dialogue/materialize-audio", response_model=TargetDialogueBundleV1)
def api_materialize_target_dialogue_audio(project_id: str):
    try:
        return materialize_target_dialogue_audio_v1(project_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/projects/{project_id}/target-dialogue", response_model=TargetDialogueBundleV1)
def api_get_target_dialogue(project_id: str):
    try:
        return get_target_dialogue_v1(project_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.patch("/target-dialogues/{target_dialogue_id}", response_model=TargetDialogueV1)
def api_update_target_dialogue(target_dialogue_id: str, payload: TargetDialogueEditRequest):
    try:
        return update_target_dialogue_v1(target_dialogue_id, **payload.model_dump())
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/target-dialogues/{target_dialogue_id}/audio")
def api_target_dialogue_audio(target_dialogue_id: str):
    with get_session() as session:
        row = session.get(TargetDialogue, target_dialogue_id)
        if row is None:
            raise HTTPException(status_code=404, detail="目标对白不存在")
        if row.audio_status != "READY" or not row.audio_path:
            raise HTTPException(status_code=409, detail="目标对白音频尚未生成")
        path = Path(row.audio_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="目标对白音频文件不存在，请重新生成")
    return FileResponse(path, media_type="audio/wav", filename=path.name)


__all__ = ["router"]
