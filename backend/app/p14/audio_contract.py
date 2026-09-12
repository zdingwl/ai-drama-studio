from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artifacts.models import ArtifactNode
from app.core.config import get_settings
from app.core.errors import AppError
from app.p14.common import _assert_replica, _current_artifact, _existing_command_task, _next_generation_sequence, _sha
from app.p14.models import ReplicaTargetAudioCandidate
from app.p14.provider import OpenAICompatibleTTSProvider
from app.p14.schemas import TargetAudioGenerateCommand, TargetVoiceBinding, VoiceBindingScope
from app.projects.models import Project
from app.projects.service import get_project
from app.skills.models import ArtifactType
from app.target_bible.models import ReplicaTargetRevision
from app.target_bible.schemas import ReplicaTargetBibleContent, TargetBibleArtifactKind
from app.target_script.models import ReplicaTargetScriptRevision
from app.target_script.schemas import ReplicaTargetScriptContent
from app.workflow.models import Task
from app.workflow.schemas import TaskCommandCreate
from app.workflow.task_service import create_task_from_command

P14_AUDIO_TASK_TYPE = "replica_target_audio"


def _load_target_audio_inputs(
    db: Session, project_id: str
) -> tuple[Project, ArtifactNode, ReplicaTargetScriptContent, ArtifactNode, ReplicaTargetBibleContent]:
    project = get_project(db, project_id)
    _assert_replica(project)
    script_artifact = _current_artifact(db, project_id, ArtifactType.TARGET_SCRIPT)
    if script_artifact is None:
        raise AppError("P14_TARGET_SCRIPT_REQUIRED", "P14 目标配音需要 CURRENT TARGET_SCRIPT", status_code=409)
    bible_artifact = _current_artifact(db, project_id, ArtifactType.TARGET_BIBLE)
    if bible_artifact is None:
        raise AppError("P14_TARGET_BIBLE_REQUIRED", "P14 目标配音需要 CURRENT TARGET_BIBLE", status_code=409)
    script_row = db.scalar(
        select(ReplicaTargetScriptRevision).where(ReplicaTargetScriptRevision.artifact_id == script_artifact.id)
    )
    bible_row = db.scalar(
        select(ReplicaTargetRevision).where(
            ReplicaTargetRevision.artifact_id == bible_artifact.id,
            ReplicaTargetRevision.artifact_kind == TargetBibleArtifactKind.TARGET_BIBLE.value,
        )
    )
    if script_row is None:
        raise AppError("P14_TARGET_SCRIPT_CONTENT_MISSING", "TARGET_SCRIPT 缺少 typed revision", status_code=500)
    if bible_row is None:
        raise AppError("P14_TARGET_BIBLE_CONTENT_MISSING", "TARGET_BIBLE 缺少 typed revision", status_code=500)
    script = ReplicaTargetScriptContent.model_validate(script_row.content_json)
    bible = ReplicaTargetBibleContent.model_validate(bible_row.content_json)
    if script.target_bible_artifact_id != bible_artifact.id:
        raise AppError("P14_TARGET_LINEAGE_MISMATCH", "TARGET_SCRIPT 与 CURRENT TARGET_BIBLE lineage 不一致", status_code=409)
    return project, script_artifact, script, bible_artifact, bible


def _flatten_dialogue(script: ReplicaTargetScriptContent) -> list[tuple[str, int, object]]:
    return [
        (episode.episode_id, episode.episode_order, line)
        for episode in script.episodes
        for line in episode.dialogue
    ]


def _binding_maps(
    command: TargetAudioGenerateCommand,
    script: ReplicaTargetScriptContent,
    bible: ReplicaTargetBibleContent,
) -> tuple[dict[str, TargetVoiceBinding], dict[str, TargetVoiceBinding]]:
    character_bindings: dict[str, TargetVoiceBinding] = {}
    utterance_bindings: dict[str, TargetVoiceBinding] = {}
    valid_characters = {item.target_character_id for item in bible.characters}
    valid_utterances = {line.utterance_id for _, _, line in _flatten_dialogue(script)}
    for binding in command.bindings:
        if binding.scope == VoiceBindingScope.CHARACTER:
            assert binding.target_character_id is not None
            if binding.target_character_id not in valid_characters:
                raise AppError(
                    "P14_VOICE_CHARACTER_UNKNOWN",
                    "Voice binding 引用了不存在的 Target Character",
                    status_code=422,
                    details={"target_character_id": binding.target_character_id},
                )
            if binding.target_character_id in character_bindings:
                raise AppError("P14_VOICE_BINDING_DUPLICATE", "同一 Target Character 不能重复绑定 voice", status_code=422)
            character_bindings[binding.target_character_id] = binding
        else:
            assert binding.utterance_id is not None
            if binding.utterance_id not in valid_utterances:
                raise AppError(
                    "P14_VOICE_UTTERANCE_UNKNOWN",
                    "Voice binding 引用了不存在的 Target Script utterance",
                    status_code=422,
                    details={"utterance_id": binding.utterance_id},
                )
            if binding.utterance_id in utterance_bindings:
                raise AppError("P14_VOICE_BINDING_DUPLICATE", "同一 utterance 不能重复绑定 voice", status_code=422)
            utterance_bindings[binding.utterance_id] = binding
    for _, _, line in _flatten_dialogue(script):
        if line.target_character_id and line.target_character_id not in valid_characters:
            raise AppError(
                "P14_TARGET_CHARACTER_LINEAGE_INVALID",
                "Target Script 引用了 CURRENT Target Bible 中不存在的 Target Character",
                status_code=409,
                details={"utterance_id": line.utterance_id, "target_character_id": line.target_character_id},
            )
        if line.utterance_id in utterance_bindings:
            continue
        if line.target_character_id and line.target_character_id in character_bindings:
            continue
        raise AppError(
            "P14_VOICE_BINDING_REQUIRED",
            "每条目标对白都必须能解析到显式 voice；未知说话人必须使用 utterance-level binding，禁止猜 voice",
            status_code=409,
            details={"utterance_id": line.utterance_id, "target_character_id": line.target_character_id},
        )
    return character_bindings, utterance_bindings


def _select_binding(
    line: object,
    character_bindings: dict[str, TargetVoiceBinding],
    utterance_bindings: dict[str, TargetVoiceBinding],
) -> TargetVoiceBinding:
    utterance_id = line.utterance_id
    if utterance_id in utterance_bindings:
        return utterance_bindings[utterance_id]
    target_character_id = line.target_character_id
    if target_character_id and target_character_id in character_bindings:
        return character_bindings[target_character_id]
    raise AppError("P14_VOICE_BINDING_REQUIRED", "目标对白缺少显式 voice binding", status_code=409)


def create_target_audio_task(
    db: Session,
    *,
    project_id: str,
    idempotency_key: str,
    command: TargetAudioGenerateCommand,
    regenerate: bool = False,
) -> Task:
    project, script_artifact, script, bible_artifact, bible = _load_target_audio_inputs(db, project_id)
    command_payload = command.model_dump(mode="json")
    existing = _existing_command_task(
        db,
        project_id=project_id,
        idempotency_key=idempotency_key,
        task_type=P14_AUDIO_TASK_TYPE,
        command_payload=command_payload,
    )
    if existing is not None:
        return existing
    _binding_maps(command, script, bible)
    current = _current_artifact(db, project_id, ArtifactType.TARGET_AUDIO)
    if current is not None and not regenerate:
        raise AppError("P14_TARGET_AUDIO_ALREADY_CURRENT", "已有 CURRENT TARGET_AUDIO；重新生成必须使用显式 regenerate", status_code=409)
    sequence = _next_generation_sequence(db, project_id, ReplicaTargetAudioCandidate)
    provider = OpenAICompatibleTTSProvider(get_settings())
    fingerprint = _sha(
        {
            "target_script": [script_artifact.id, script_artifact.revision, script_artifact.input_fingerprint],
            "target_bible": [bible_artifact.id, bible_artifact.revision, bible_artifact.input_fingerprint],
            "bindings": command_payload,
            "provider": {"provider": provider.provider_name, "model": provider.model_name},
            "generation_sequence": sequence,
        }
    )
    task = create_task_from_command(
        db,
        project_id=project.id,
        payload=TaskCommandCreate(
            task_type=P14_AUDIO_TASK_TYPE,
            task_name="生成目标配音",
            input_fingerprint=fingerprint,
            input_artifact_ids=[script_artifact.id, bible_artifact.id],
            max_attempts=3,
        ),
        idempotency_key=idempotency_key,
    )
    if not task.checkpoint_json.get("p14_audio_command"):
        task.checkpoint_json = {
            **task.checkpoint_json,
            "p14_audio_command": command_payload,
            "generation_sequence": sequence,
            "completed_clips": {},
        }
        db.add(task)
        db.commit()
        db.refresh(task)
    return task
