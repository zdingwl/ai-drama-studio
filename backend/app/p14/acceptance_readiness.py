import hashlib

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.p14.audio_review import resolve_target_audio_media_path
from app.p14.common import _assert_replica, _current_artifact
from app.p14.models import ReplicaTargetAudioRevision, ReplicaTimingPlanRevision
from app.p14.provider import probe_audio
from app.p14.schemas import ReplicaTargetAudioContent, ReplicaTimingPlanContent
from app.p14.timing_service import _compose_timing
from app.projects.service import get_project
from app.skills.models import ArtifactType
from app.target_script.models import ReplicaTargetScriptRevision
from app.target_script.schemas import ReplicaTargetScriptContent
from app.workflow.models import ProviderJob, ProviderJobStatus


MANUAL_CHECKS_REQUIRED = [
    "逐句人工试听：目标对白清晰、完整，无明显截断、吞字、爆音或异常静音。",
    "人物声线人工确认：同一人物的音色与表演风格在当前成片范围内稳定。",
    "对白人工确认：实际听到的内容与 Final Target Dialogue 一致，表演指令没有被念出来。",
    "Retake 人工确认：语气、情绪强度与 duration factor 的调整符合剧情表演意图。",
    "Timing 人工确认：所有对白 FIT，余量可接受，没有通过静默改词、极端变速或拉伸镜头解决。",
    "最终仍需用户明确确认 P14 PASS；技术就绪检查本身绝不等于 P14 PASS。",
]


class P14AcceptanceReadiness(BaseModel):
    project_id: str
    technical_ready: bool
    target_audio_artifact_id: str | None = None
    target_audio_revision: int | None = None
    timing_plan_artifact_id: str | None = None
    timing_plan_revision: int | None = None
    clip_count: int = Field(default=0, ge=0)
    timing_item_count: int = Field(default=0, ge=0)
    provider_job_count: int = Field(default=0, ge=0)
    provider_jobs_succeeded: int = Field(default=0, ge=0)
    media_verified_count: int = Field(default=0, ge=0)
    duration_verified_count: int = Field(default=0, ge=0)
    blockers: list[str] = Field(default_factory=list)
    manual_checks_required: list[str] = Field(default_factory=lambda: list(MANUAL_CHECKS_REQUIRED))


def _append_once(blockers: list[str], message: str) -> None:
    if message not in blockers:
        blockers.append(message)


def _sample_ids(values: list[str]) -> str:
    shown = values[:8]
    suffix = f" 等共 {len(values)} 条" if len(values) > len(shown) else ""
    return "、".join(shown) + suffix


def get_p14_acceptance_readiness(db: Session, project_id: str) -> P14AcceptanceReadiness:
    project = get_project(db, project_id)
    _assert_replica(project)
    blockers: list[str] = []

    script_artifact = _current_artifact(db, project_id, ArtifactType.TARGET_SCRIPT)
    bible_artifact = _current_artifact(db, project_id, ArtifactType.TARGET_BIBLE)
    audio_artifact = _current_artifact(db, project_id, ArtifactType.TARGET_AUDIO)
    timing_artifact = _current_artifact(db, project_id, ArtifactType.TIMING_PLAN)

    if script_artifact is None:
        _append_once(blockers, "缺少 CURRENT TARGET_SCRIPT。")
    if bible_artifact is None:
        _append_once(blockers, "缺少 CURRENT TARGET_BIBLE。")
    if audio_artifact is None:
        _append_once(blockers, "缺少人工确认后的 CURRENT TARGET_AUDIO。")
    if timing_artifact is None:
        _append_once(blockers, "缺少人工确认后的 CURRENT TIMING_PLAN。")

    clip_count = 0
    timing_item_count = 0
    provider_job_count = 0
    provider_jobs_succeeded = 0
    media_verified_count = 0
    duration_verified_count = 0

    audio: ReplicaTargetAudioContent | None = None
    audio_row: ReplicaTargetAudioRevision | None = None
    if audio_artifact is not None:
        audio_row = db.scalar(
            select(ReplicaTargetAudioRevision).where(
                ReplicaTargetAudioRevision.artifact_id == audio_artifact.id
            )
        )
        if audio_row is None:
            _append_once(blockers, "CURRENT TARGET_AUDIO 缺少 typed revision。")
        else:
            try:
                audio = ReplicaTargetAudioContent.model_validate(audio_row.content_json)
            except Exception:
                _append_once(blockers, "CURRENT TARGET_AUDIO typed content 无效。")
            if audio is not None:
                clip_count = len(audio.clips)
                if script_artifact is not None and audio.target_script_artifact_id != script_artifact.id:
                    _append_once(blockers, "CURRENT TARGET_AUDIO 不属于 CURRENT TARGET_SCRIPT。")
                if bible_artifact is not None and audio.target_bible_artifact_id != bible_artifact.id:
                    _append_once(blockers, "CURRENT TARGET_AUDIO 不属于 CURRENT TARGET_BIBLE。")
                invalid_delivery = [
                    f"#{clip.utterance_number}"
                    for clip in audio.clips
                    if not 0.8 <= clip.duration_factor <= 1.25
                ]
                if invalid_delivery:
                    _append_once(
                        blockers,
                        f"存在超出 P14 0.8~1.25 产品边界的 duration_factor：{_sample_ids(invalid_delivery)}。",
                    )
                if not audio_row.generated_by_task_id:
                    _append_once(blockers, "CURRENT TARGET_AUDIO 缺少生成 Task lineage，无法验证媒体。")
                else:
                    failed_jobs: list[str] = []
                    invalid_media: list[str] = []
                    duration_mismatches: list[str] = []
                    provider_job_ids = list(dict.fromkeys(clip.provider_job_id for clip in audio.clips))
                    provider_job_count = len(provider_job_ids)
                    succeeded_ids: set[str] = set()
                    for clip in audio.clips:
                        job = db.get(ProviderJob, clip.provider_job_id)
                        if (
                            job is None
                            or job.project_id != project_id
                            or job.status != ProviderJobStatus.SUCCEEDED
                            or job.provider != clip.provider
                            or job.model != clip.model
                        ):
                            failed_jobs.append(f"#{clip.utterance_number}")
                        else:
                            succeeded_ids.add(job.id)

                        try:
                            media_path = resolve_target_audio_media_path(
                                project_id,
                                audio_row.generated_by_task_id,
                                clip.clip_id,
                            )
                            media_sha = hashlib.sha256(media_path.read_bytes()).hexdigest()
                            if media_sha != clip.media_sha256:
                                invalid_media.append(f"#{clip.utterance_number}")
                                continue
                            media_verified_count += 1
                            probed = probe_audio(get_settings(), media_path)
                            if probed.duration_us != clip.actual_speech_duration_us:
                                duration_mismatches.append(f"#{clip.utterance_number}")
                                continue
                            duration_verified_count += 1
                        except (AppError, OSError):
                            invalid_media.append(f"#{clip.utterance_number}")
                    provider_jobs_succeeded = len(succeeded_ids)
                    if failed_jobs:
                        _append_once(
                            blockers,
                            f"存在不可验收的 ProviderJob：{_sample_ids(failed_jobs)}。",
                        )
                    if invalid_media:
                        _append_once(
                            blockers,
                            f"存在媒体缺失或 SHA/ffprobe 校验失败：{_sample_ids(invalid_media)}。",
                        )
                    if duration_mismatches:
                        _append_once(
                            blockers,
                            f"存在实际时长与重新 ffprobe 结果不一致：{_sample_ids(duration_mismatches)}。",
                        )

    expected_timing: ReplicaTimingPlanContent | None = None
    if script_artifact is not None and audio_artifact is not None and audio is not None:
        script_row = db.scalar(
            select(ReplicaTargetScriptRevision).where(
                ReplicaTargetScriptRevision.artifact_id == script_artifact.id
            )
        )
        if script_row is None:
            _append_once(blockers, "CURRENT TARGET_SCRIPT 缺少 typed revision。")
        else:
            try:
                script = ReplicaTargetScriptContent.model_validate(script_row.content_json)
                expected_timing = _compose_timing(
                    script_artifact,
                    script,
                    audio_artifact,
                    audio,
                )
            except Exception:
                _append_once(blockers, "CURRENT TARGET_AUDIO 无法按正式 Timing 合同精确覆盖当前目标对白。")

    if timing_artifact is not None:
        timing_row = db.scalar(
            select(ReplicaTimingPlanRevision).where(
                ReplicaTimingPlanRevision.artifact_id == timing_artifact.id
            )
        )
        if timing_row is None:
            _append_once(blockers, "CURRENT TIMING_PLAN 缺少 typed revision。")
        else:
            try:
                timing = ReplicaTimingPlanContent.model_validate(timing_row.content_json)
            except Exception:
                timing = None
                _append_once(blockers, "CURRENT TIMING_PLAN typed content 无效。")
            if timing is not None:
                timing_item_count = len(timing.items)
                if script_artifact is not None and timing.target_script_artifact_id != script_artifact.id:
                    _append_once(blockers, "CURRENT TIMING_PLAN 不属于 CURRENT TARGET_SCRIPT。")
                if audio_artifact is not None and timing.target_audio_artifact_id != audio_artifact.id:
                    _append_once(blockers, "CURRENT TIMING_PLAN 不属于 CURRENT TARGET_AUDIO。")
                if timing.has_overflow or timing.total_overflow_us > 0:
                    _append_once(blockers, "CURRENT TIMING_PLAN 仍包含未解决的 OVERFLOW。")
                if (
                    expected_timing is not None
                    and timing.model_dump(mode="json") != expected_timing.model_dump(mode="json")
                ):
                    _append_once(blockers, "CURRENT TIMING_PLAN 与当前真实音频时长重新计算结果不一致。")

    return P14AcceptanceReadiness(
        project_id=project_id,
        technical_ready=not blockers,
        target_audio_artifact_id=audio_artifact.id if audio_artifact else None,
        target_audio_revision=audio_artifact.revision if audio_artifact else None,
        timing_plan_artifact_id=timing_artifact.id if timing_artifact else None,
        timing_plan_revision=timing_artifact.revision if timing_artifact else None,
        clip_count=clip_count,
        timing_item_count=timing_item_count,
        provider_job_count=provider_job_count,
        provider_jobs_succeeded=provider_jobs_succeeded,
        media_verified_count=media_verified_count,
        duration_verified_count=duration_verified_count,
        blockers=blockers,
    )
