import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artifacts.enums import ArtifactValidity
from app.artifacts.models import ArtifactNode
from app.core.config import get_settings
from app.core.errors import AppError
from app.p14.models import ReplicaTargetAudioRevision, ReplicaTimingPlanRevision
from app.p14.schemas import ReplicaTargetAudioContent, ReplicaTimingPlanContent
from app.p16.models import ReplicaGeneratedVideoRevision, ReplicaGenerationSelectionRevision
from app.p16.schemas import ReplicaGeneratedVideoContent, ReplicaGenerationSelectionContent
from app.projects.enums import ProjectType
from app.skills.models import ArtifactType
from app.target_script.models import ReplicaTargetScriptRevision
from app.target_script.schemas import ReplicaTargetScriptContent


@dataclass(frozen=True)
class P17Inputs:
    project: object
    selection_artifact: ArtifactNode
    selection: ReplicaGenerationSelectionContent
    generated_video_artifact: ArtifactNode
    generated_video: ReplicaGeneratedVideoContent
    target_audio_artifact: ArtifactNode
    target_audio: ReplicaTargetAudioContent
    target_audio_task_id: str
    target_script_artifact: ArtifactNode
    target_script: ReplicaTargetScriptContent
    timing_artifact: ArtifactNode
    timing: ReplicaTimingPlanContent


def sha(payload: object) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _current(db: Session, project_id: str, artifact_type: ArtifactType) -> ArtifactNode:
    rows = list(
        db.scalars(
            select(ArtifactNode).where(
                ArtifactNode.project_id == project_id,
                ArtifactNode.artifact_type == artifact_type.value,
                ArtifactNode.validity == ArtifactValidity.CURRENT,
                ArtifactNode.is_current.is_(True),
            )
        ).all()
    )
    if not rows:
        raise AppError("P17_INPUT_REQUIRED", f"P17 需要 CURRENT {artifact_type.value}", status_code=409)
    if len(rows) != 1:
        raise AppError("P17_INPUT_AMBIGUOUS", f"{artifact_type.value} 存在多个 CURRENT Artifact", status_code=409)
    return rows[0]


def load_inputs(db: Session, project) -> P17Inputs:
    if project.project_type != ProjectType.REPLICA:
        raise AppError("P17_REPLICA_ONLY", "P17 成片后期当前只允许 REPLICA 项目", status_code=422)

    selection_artifact = _current(db, project.id, ArtifactType.GENERATION_SELECTION)
    target_audio_artifact = _current(db, project.id, ArtifactType.TARGET_AUDIO)
    target_script_artifact = _current(db, project.id, ArtifactType.TARGET_SCRIPT)
    timing_artifact = _current(db, project.id, ArtifactType.TIMING_PLAN)

    selection_row = db.scalar(
        select(ReplicaGenerationSelectionRevision).where(
            ReplicaGenerationSelectionRevision.artifact_id == selection_artifact.id
        )
    )
    audio_row = db.scalar(
        select(ReplicaTargetAudioRevision).where(ReplicaTargetAudioRevision.artifact_id == target_audio_artifact.id)
    )
    script_row = db.scalar(
        select(ReplicaTargetScriptRevision).where(ReplicaTargetScriptRevision.artifact_id == target_script_artifact.id)
    )
    timing_row = db.scalar(
        select(ReplicaTimingPlanRevision).where(ReplicaTimingPlanRevision.artifact_id == timing_artifact.id)
    )
    if selection_row is None or audio_row is None or script_row is None or timing_row is None:
        raise AppError("P17_TYPED_INPUT_MISSING", "P17 CURRENT 输入缺少 typed revision", status_code=500)
    if not audio_row.generated_by_task_id:
        raise AppError("P17_AUDIO_MEDIA_LINEAGE_MISSING", "CURRENT TARGET_AUDIO 缺少生成 Task lineage", status_code=409)

    selection = ReplicaGenerationSelectionContent.model_validate(selection_row.content_json)
    audio = ReplicaTargetAudioContent.model_validate(audio_row.content_json)
    script = ReplicaTargetScriptContent.model_validate(script_row.content_json)
    timing = ReplicaTimingPlanContent.model_validate(timing_row.content_json)

    generated_video_id = selection.generated_video_artifact_id
    if not generated_video_id:
        raise AppError("P17_GENERATED_VIDEO_LINEAGE_MISSING", "GENERATION_SELECTION 缺少正式 GENERATED_VIDEO lineage", status_code=409)
    generated_video_artifact = db.get(ArtifactNode, generated_video_id)
    if (
        generated_video_artifact is None
        or generated_video_artifact.project_id != project.id
        or generated_video_artifact.artifact_type != ArtifactType.GENERATED_VIDEO.value
        or generated_video_artifact.validity != ArtifactValidity.CURRENT
        or not generated_video_artifact.is_current
    ):
        raise AppError("P17_GENERATED_VIDEO_NOT_CURRENT", "GENERATION_SELECTION 指向的 GENERATED_VIDEO 不是 CURRENT", status_code=409)
    generated_row = db.scalar(
        select(ReplicaGeneratedVideoRevision).where(ReplicaGeneratedVideoRevision.artifact_id == generated_video_artifact.id)
    )
    if generated_row is None:
        raise AppError("P17_GENERATED_VIDEO_CONTENT_MISSING", "GENERATED_VIDEO 缺少 typed revision", status_code=500)
    generated = ReplicaGeneratedVideoContent.model_validate(generated_row.content_json)

    if generated.generation_segments_artifact_id != selection.generation_segments_artifact_id:
        raise AppError("P17_SELECTION_LINEAGE_MISMATCH", "GENERATION_SELECTION 与 GENERATED_VIDEO 的 segment lineage 不一致", status_code=409)
    if generated.target_storyboard_artifact_id != selection.target_storyboard_artifact_id:
        raise AppError("P17_SELECTION_LINEAGE_MISMATCH", "GENERATION_SELECTION 与 GENERATED_VIDEO 的 storyboard lineage 不一致", status_code=409)
    if generated.target_assets_artifact_id != selection.target_assets_artifact_id:
        raise AppError("P17_SELECTION_LINEAGE_MISMATCH", "GENERATION_SELECTION 与 GENERATED_VIDEO 的 assets lineage 不一致", status_code=409)

    selected = {item.generation_segment_id: item.selected_attempt_id for item in selection.selections}
    generated_selected = {item.generation_segment_id: item.selected_attempt_id for item in generated.clips}
    if selected != generated_selected:
        raise AppError("P17_SELECTION_COVERAGE_MISMATCH", "GENERATION_SELECTION 与 GENERATED_VIDEO 的正式选片不一致", status_code=409)

    if audio.target_script_artifact_id != target_script_artifact.id:
        raise AppError("P17_AUDIO_SCRIPT_LINEAGE_MISMATCH", "TARGET_AUDIO 不属于 CURRENT TARGET_SCRIPT", status_code=409)
    if timing.target_script_artifact_id != target_script_artifact.id or timing.target_audio_artifact_id != target_audio_artifact.id:
        raise AppError("P17_TIMING_LINEAGE_MISMATCH", "TIMING_PLAN 不属于 CURRENT TARGET_SCRIPT + TARGET_AUDIO", status_code=409)
    if timing.has_overflow or timing.total_overflow_us:
        raise AppError("P17_TIMING_OVERFLOW", "TIMING_PLAN 仍存在 overflow，禁止进入成片", status_code=409)

    script_ids = {line.utterance_id for episode in script.episodes for line in episode.dialogue}
    audio_ids = {clip.utterance_id for clip in audio.clips}
    timing_ids = {item.utterance_id for item in timing.items}
    if script_ids != audio_ids or script_ids != timing_ids:
        raise AppError("P17_DIALOGUE_COVERAGE_INVALID", "TARGET_SCRIPT / TARGET_AUDIO / TIMING_PLAN utterance 覆盖不一致", status_code=409)

    return P17Inputs(
        project=project,
        selection_artifact=selection_artifact,
        selection=selection,
        generated_video_artifact=generated_video_artifact,
        generated_video=generated,
        target_audio_artifact=target_audio_artifact,
        target_audio=audio,
        target_audio_task_id=audio_row.generated_by_task_id,
        target_script_artifact=target_script_artifact,
        target_script=script,
        timing_artifact=timing_artifact,
        timing=timing,
    )


def input_artifact_ids(inputs: P17Inputs) -> list[str]:
    return [
        inputs.selection_artifact.id,
        inputs.target_audio_artifact.id,
        inputs.target_script_artifact.id,
        inputs.timing_artifact.id,
    ]


def storage_dir(project_id: str, task_id: str) -> Path:
    root = get_settings().artifact_root / "p17_final_output" / project_id / task_id
    root.mkdir(parents=True, exist_ok=True)
    return root


def episode_key(episode_id: str) -> str:
    return hashlib.sha256(episode_id.encode("utf-8")).hexdigest()[:20]


def episode_sidecar_path(project_id: str, task_id: str, episode_id: str) -> Path:
    return storage_dir(project_id, task_id) / f"episode-{episode_key(episode_id)}.json"


def resolve_episode_media(project_id: str, task_id: str, episode_id: str, kind: str) -> Path:
    if Path(project_id).name != project_id or Path(task_id).name != task_id:
        raise AppError("P17_MEDIA_PATH_INVALID", "P17 media path 无效", status_code=422)
    if kind not in {"video", "subtitle"}:
        raise AppError("P17_MEDIA_KIND_INVALID", "P17 media kind 无效", status_code=422)
    sidecar = episode_sidecar_path(project_id, task_id, episode_id)
    if not sidecar.is_file():
        raise AppError("P17_MEDIA_NOT_FOUND", "P17 Episode media index 不存在", status_code=404)
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        filename = str(payload[f"{kind}_filename"])
    except Exception as exc:
        raise AppError("P17_MEDIA_INDEX_INVALID", "P17 Episode media index 损坏", status_code=500) from exc
    if Path(filename).name != filename:
        raise AppError("P17_MEDIA_PATH_INVALID", "P17 Episode media filename 无效", status_code=500)
    path = sidecar.parent / filename
    if not path.is_file():
        raise AppError("P17_MEDIA_NOT_FOUND", "P17 Episode media 不存在", status_code=404)
    return path
