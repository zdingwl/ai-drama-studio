import hashlib
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.errors import AppError
from app.p14.audio_contract import P14_AUDIO_TASK_TYPE, _binding_maps, _flatten_dialogue, _load_target_audio_inputs, _select_binding
from app.p14.common import _checkpoint, _claim_specific, _mark_stage_failed, _text_sha
from app.p14.models import ReplicaTargetAudioCandidate
from app.p14.provider import OpenAICompatibleTTSProvider, probe_audio
from app.p14.schemas import P14_AUDIO_SCHEMA_VERSION, P14_AUDIO_SKILL_ID, CandidateReviewStatus, ReplicaTargetAudioContent, TargetAudioCandidateProvenance, TargetAudioClip, TargetAudioGenerateCommand, TargetVoiceBinding
from app.projects.models import Project
from app.skills.models import Capability
from app.skills.professional import get_professional_skill
from app.workflow.models import ProviderJob, ProviderJobStatus, Task, TaskStatus
from app.workflow.provider_service import ProviderDispatchResult, dispatch_provider_call, mark_provider_job_succeeded
from app.workflow.schemas import TaskWorkerRead
from app.workflow.task_service import mark_task_failed, mark_task_succeeded


def _audio_storage_dir(project_id: str, task_id: str) -> Path:
    root = get_settings().artifact_root / "p14_target_audio" / project_id / task_id
    root.mkdir(parents=True, exist_ok=True)
    return root


def _media_url(project_id: str, task_id: str, clip_id: str) -> str:
    return f"/api/v3/projects/{project_id}/target-audio/media/{task_id}/{clip_id}"


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def _write_json_atomic(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _recover_clip(
    db: Session,
    *,
    project_id: str,
    task_id: str,
    clip_id: str,
    expected_text_sha: str,
    expected_voice_id: str,
) -> TargetAudioClip | None:
    sidecar = _audio_storage_dir(project_id, task_id) / f"{clip_id}.json"
    if not sidecar.is_file():
        return None
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        clip = TargetAudioClip.model_validate(payload)
    except Exception:
        return None
    if clip.final_target_dialogue_sha256 != expected_text_sha or clip.voice_id != expected_voice_id:
        return None
    media_name = payload.get("storage_filename")
    if not isinstance(media_name, str):
        return None
    media_path = sidecar.parent / media_name
    if not media_path.is_file() or hashlib.sha256(media_path.read_bytes()).hexdigest() != clip.media_sha256:
        return None
    job = db.get(ProviderJob, clip.provider_job_id)
    if job is not None and job.status in {ProviderJobStatus.RUNNING, ProviderJobStatus.SUBMITTED}:
        mark_provider_job_succeeded(db, job.id)
    return clip


def _synthesize_clip(
    db: Session,
    *,
    task: TaskWorkerRead,
    project: Project,
    episode_id: str,
    episode_order: int,
    line: object,
    binding: TargetVoiceBinding,
    provider: OpenAICompatibleTTSProvider,
) -> TargetAudioClip:
    clip_id = str(uuid5(NAMESPACE_URL, f"p14-target-audio:{project.id}:{line.utterance_id}"))
    text_sha = _text_sha(line.final_target_dialogue)
    recovered = _recover_clip(
        db,
        project_id=project.id,
        task_id=task.id,
        clip_id=clip_id,
        expected_text_sha=text_sha,
        expected_voice_id=binding.voice_id,
    )
    if recovered is not None:
        return recovered

    job_payload = {
        "contract": "target-dialogue-tts-media-v1",
        "utterance_id": line.utterance_id,
        "target_character_id": line.target_character_id,
        "final_target_dialogue_sha256": text_sha,
        "voice_id": binding.voice_id,
        "model": provider.model_name,
        "response_format": provider.response_format,
    }
    storage_dir = _audio_storage_dir(project.id, task.id)

    def remote_call(job: ProviderJob) -> ProviderDispatchResult:
        result = provider.synthesize(text=line.final_target_dialogue, voice_id=binding.voice_id)
        media_filename = f"{clip_id}.{result.file_extension}"
        media_path = storage_dir / media_filename
        _write_atomic(media_path, result.audio_bytes)
        media_sha = hashlib.sha256(result.audio_bytes).hexdigest()
        probed = probe_audio(get_settings(), media_path)
        clip = TargetAudioClip(
            clip_id=clip_id,
            episode_id=episode_id,
            episode_order=episode_order,
            utterance_id=line.utterance_id,
            utterance_number=line.utterance_number,
            target_character_id=line.target_character_id,
            final_target_dialogue=line.final_target_dialogue,
            final_target_dialogue_sha256=text_sha,
            voice_id=binding.voice_id,
            voice_label=binding.voice_label,
            provider=provider.provider_name,
            model=provider.model_name,
            provider_job_id=job.id,
            media_url=_media_url(project.id, task.id, clip_id),
            media_sha256=media_sha,
            mime_type=result.mime_type,
            actual_speech_duration_us=probed.duration_us,
            sample_rate_hz=probed.sample_rate_hz,
            channel_count=probed.channel_count,
        )
        sidecar_payload = {**clip.model_dump(mode="json"), "storage_filename": media_filename}
        _write_json_atomic(storage_dir / f"{clip_id}.json", sidecar_payload)
        return ProviderDispatchResult(
            value=clip.model_dump(mode="json"),
            remote_job_id=result.remote_job_id,
            completed=True,
        )

    _job, dispatched = dispatch_provider_call(
        db,
        task_id=task.id,
        provider=provider.provider_name,
        model=provider.model_name,
        capability=Capability.TTS,
        payload=job_payload,
        artifact_id=task.input_artifact_ids_json[0],
        remote_call=remote_call,
    )
    return TargetAudioClip.model_validate(dispatched.value)


def run_target_audio_task(factory: sessionmaker[Session], task_id: str) -> None:
    worker_id = f"p14-audio-{uuid4()}"
    with factory() as db:
        claimed = _claim_specific(db, task_id, P14_AUDIO_TASK_TYPE, worker_id)
        if claimed is None:
            return
        snapshot = TaskWorkerRead.model_validate(claimed)
        command = TargetAudioGenerateCommand.model_validate(snapshot.checkpoint_json.get("p14_audio_command") or {})
        sequence = int(snapshot.checkpoint_json.get("generation_sequence") or 0)
    try:
        with factory() as db:
            project, script_artifact, script, bible_artifact, bible = _load_target_audio_inputs(db, snapshot.project_id)
            if snapshot.input_artifact_ids_json != [script_artifact.id, bible_artifact.id]:
                raise AppError("P14_AUDIO_INPUT_CHANGED", "P14 目标配音输入已变化，请重新生成", status_code=409)
            character_bindings, utterance_bindings = _binding_maps(command, script, bible)
            provider = OpenAICompatibleTTSProvider(get_settings())
            lines = _flatten_dialogue(script)
            clips: list[TargetAudioClip] = []
            for index, (episode_id, episode_order, line) in enumerate(lines):
                binding = _select_binding(line, character_bindings, utterance_bindings)
                clip = _synthesize_clip(
                    db,
                    task=snapshot,
                    project=project,
                    episode_id=episode_id,
                    episode_order=episode_order,
                    line=line,
                    binding=binding,
                    provider=provider,
                )
                clips.append(clip)
                progress = 10 + int(((index + 1) / max(1, len(lines))) * 80)
                _checkpoint(
                    factory,
                    snapshot.id,
                    worker_id,
                    progress=min(progress, 90),
                    completed_clips={item.utterance_id: item.model_dump(mode="json") for item in clips},
                )
            content = ReplicaTargetAudioContent(
                target_language=project.target_language,
                target_region=project.target_region,
                target_script_artifact_id=script_artifact.id,
                target_bible_artifact_id=bible_artifact.id,
                clips=clips,
            )
            job_ids = [clip.provider_job_id for clip in clips]
            skill = get_professional_skill(P14_AUDIO_SKILL_ID)
            provenance = TargetAudioCandidateProvenance(
                target_script_artifact_id=script_artifact.id,
                target_script_revision=script_artifact.revision,
                target_script_fingerprint=script_artifact.input_fingerprint,
                target_bible_artifact_id=bible_artifact.id,
                target_bible_revision=bible_artifact.revision,
                target_bible_fingerprint=bible_artifact.input_fingerprint,
                target_language=project.target_language,
                target_region=project.target_region,
                generation_sequence=sequence,
                professional_skill_version=skill.version,
                provider=provider.provider_name,
                model=provider.model_name,
                provider_job_ids=job_ids,
                generated_by_task_id=snapshot.id,
            )
        with factory() as db:
            finished = mark_task_succeeded(db, snapshot.id, worker_id=worker_id)
            if finished.status == TaskStatus.CANCELLED:
                return
            existing = db.scalar(select(ReplicaTargetAudioCandidate).where(ReplicaTargetAudioCandidate.generated_by_task_id == snapshot.id))
            if existing is None:
                candidate = ReplicaTargetAudioCandidate(
                    project_id=snapshot.project_id,
                    target_script_artifact_id=content.target_script_artifact_id,
                    target_bible_artifact_id=content.target_bible_artifact_id,
                    generated_by_task_id=snapshot.id,
                    generation_sequence=sequence,
                    input_fingerprint=snapshot.input_fingerprint,
                    schema_version=P14_AUDIO_SCHEMA_VERSION,
                    content_json=content.model_dump(mode="json"),
                    provenance_json=provenance.model_dump(mode="json"),
                    review_status=CandidateReviewStatus.NEEDS_REVIEW.value,
                )
                db.add(candidate)
                db.commit()
    except Exception as exc:
        message = f"P14 目标配音失败（{exc.code}）：{exc.message}" if isinstance(exc, AppError) else f"P14 目标配音失败（{type(exc).__name__}）"
        with factory() as db:
            task = db.get(Task, snapshot.id)
            if task is not None and task.status == TaskStatus.RUNNING and task.worker_id == worker_id:
                mark_task_failed(db, snapshot.id, safe_error=message, worker_id=worker_id)
                return
        _mark_stage_failed(factory, snapshot.id, message)
