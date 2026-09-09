"""P7 provider-boundary Evidence reference transport.

Language/multimodal models should not be responsible for byte-perfect copying of database UUIDs.
The provider receives short deterministic aliases (D0001/O0001); this module resolves every
returned Evidence reference back to the exact CURRENT P6 canonical ID before SOURCE_BIBLE
publication. Unknown aliases are intentionally left unchanged so the existing fail-closed
validation still rejects hallucinated references.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import AppError
from app.core.time import utc_now
from app.skills.models import Capability
from app.understanding import service as core
from app.understanding.providers import (
    P7_GROUNDING_CONTRACT,
    P7_PROFESSIONAL_SKILL_ID,
    EpisodeUnderstandingInput,
    validate_episode_understanding_grounding,
)
from app.understanding.schemas import EpisodeUnderstandingSemantic, SourceBibleContent, SourceBibleProvenance
from app.workflow.models import Task, TaskStatus
from app.workflow.provider_service import dispatch_provider_call
from app.workflow.schemas import TaskWorkerRead
from app.workflow.task_service import TaskCancelled, mark_task_failed, mark_task_succeeded
from app.workflow.worker import TaskExecutionContext

P7_EVIDENCE_REF_ENCODING = "short-alias-v1"


def _provider_evidence_payload(context: core.EpisodeContext) -> tuple[dict, dict[str, str], dict[str, str]]:
    dialogue_map: dict[str, str] = {}
    dialogue: list[dict] = []
    for index, item in enumerate(context.dialogue, 1):
        ref = f"D{index:04d}"
        dialogue_map[ref] = item.id
        dialogue.append(
            {
                "id": ref,
                "start_us": item.start_us,
                "end_us": item.end_us,
                "text": item.text,
                "language": item.language,
            }
        )

    visual_map: dict[str, str] = {}
    visual_text: list[dict] = []
    for index, item in enumerate(context.visual_text, 1):
        ref = f"O{index:04d}"
        visual_map[ref] = item.id
        visual_text.append(
            {
                "id": ref,
                "start_us": item.start_us,
                "end_us": item.end_us,
                "text": item.text,
                "confidence": item.confidence,
            }
        )

    return (
        {
            "source_evidence_set_ref": "CURRENT_EPISODE_EVIDENCE",
            "reference_encoding": P7_EVIDENCE_REF_ENCODING,
            "dialogue": dialogue,
            "visual_text": visual_text,
        },
        dialogue_map,
        visual_map,
    )


def _replace_evidence_refs(value, dialogue_map: dict[str, str], visual_map: dict[str, str]):
    if isinstance(value, list):
        return [_replace_evidence_refs(item, dialogue_map, visual_map) for item in value]
    if not isinstance(value, dict):
        return value

    replaced: dict = {}
    for key, nested in value.items():
        if key == "dialogue_evidence_ids" and isinstance(nested, list):
            replaced[key] = [dialogue_map.get(str(item), str(item)) for item in nested]
        elif key == "visual_text_evidence_ids" and isinstance(nested, list):
            replaced[key] = [visual_map.get(str(item), str(item)) for item in nested]
        else:
            replaced[key] = _replace_evidence_refs(nested, dialogue_map, visual_map)
    return replaced


def _canonicalize_semantic(
    semantic: EpisodeUnderstandingSemantic,
    *,
    dialogue_map: dict[str, str],
    visual_map: dict[str, str],
) -> EpisodeUnderstandingSemantic:
    payload = _replace_evidence_refs(
        semantic.model_dump(mode="json"),
        dialogue_map,
        visual_map,
    )
    return EpisodeUnderstandingSemantic.model_validate(payload)


def _canonical_validation_input(
    provider_input: EpisodeUnderstandingInput,
    episode_context: core.EpisodeContext,
) -> EpisodeUnderstandingInput:
    return EpisodeUnderstandingInput(
        source_path=provider_input.source_path,
        source_filename=provider_input.source_filename,
        mime_type=provider_input.mime_type,
        episode_id=provider_input.episode_id,
        episode_order=provider_input.episode_order,
        duration_us=provider_input.duration_us,
        source_language=provider_input.source_language,
        evidence_payload=core._evidence_payload(episode_context),
        shot_hints=provider_input.shot_hints,
    )


def _execute(context: TaskExecutionContext, task: TaskWorkerRead) -> tuple[SourceBibleContent, SourceBibleProvenance]:
    with context.session_factory() as db:
        project = core.get_project(db, task.project_id)
        if project.project_type not in core.SOURCE_BIBLE_PROJECT_TYPES:
            raise AppError("SOURCE_BIBLE_NOT_ALLOWED", "当前项目类型不执行 SOURCE_BIBLE 整集原片理解", status_code=422)
        source = core._required_source(db, task.project_id)
        dialogue = core._required_dialogue(db, task.project_id, source)
        shots = core._optional_shots(db, task.project_id, source)
        expected_inputs = {source.id, dialogue.id, *([shots.id] if shots else [])}
        if set(task.input_artifact_ids_json) != expected_inputs:
            raise AppError("STALE_ARTIFACT_INPUT", "P7 输入 Artifact 已变化，请重新创建任务", status_code=409)
        episode_contexts = core._episode_contexts(
            db,
            project_id=task.project_id,
            source=source,
            dialogue_artifact=dialogue,
            shots_artifact=shots,
        )
        provider = core._provider_for_project(project)
        if task.input_fingerprint != core._fingerprint_inputs(source, dialogue, shots, episode_contexts, provider):
            raise AppError("STALE_ARTIFACT_INPUT", "P7 输入 fingerprint 或 Provider 已变化，请重新创建任务", status_code=409)

    episodes = []
    provider_jobs: list[dict] = []
    total = len(episode_contexts)
    for index, episode_context in enumerate(episode_contexts, 1):
        progress = 5 + int((index - 1) / total * 80)
        context.checkpoint(
            {
                "stage": "episode_understanding",
                "episode_order": episode_context.episode.episode_order,
                "input": "FULL_EPISODE",
                "evidence_ref_encoding": P7_EVIDENCE_REF_ENCODING,
            },
            progress_percent=progress,
        )
        source_path = core.resolve_source_asset_path(episode_context.asset.relative_path)
        provider_evidence, dialogue_map, visual_map = _provider_evidence_payload(episode_context)
        provider_input = EpisodeUnderstandingInput(
            source_path=source_path,
            source_filename=episode_context.asset.original_filename,
            mime_type=episode_context.asset.mime_type,
            episode_id=episode_context.episode.id,
            episode_order=episode_context.episode.episode_order,
            duration_us=episode_context.episode.duration_us,
            source_language=project.source_language,
            evidence_payload=provider_evidence,
            shot_hints=core._shot_hints(episode_context),
        )
        job_payload = {
            "profile": core.P7_PROFILE_VERSION,
            "schema_version": core.P7_SCHEMA_VERSION,
            "episode_id": episode_context.episode.id,
            "source_asset_sha256": episode_context.asset.sha256,
            "source_evidence_set_id": episode_context.evidence_set.id,
            "source_evidence_fingerprint": episode_context.evidence_set.input_fingerprint,
            "dialogue_count": len(episode_context.dialogue),
            "visual_text_count": len(episode_context.visual_text),
            "evidence_ref_encoding": P7_EVIDENCE_REF_ENCODING,
            "optional_shot_boundary_set_id": episode_context.shot_boundary.id if episode_context.shot_boundary else None,
            "optional_shot_anchor_count": len(episode_context.shot_anchors),
            "provider_profile": provider.profile,
        }
        with context.session_factory() as db:
            job, dispatched = dispatch_provider_call(
                db,
                task_id=task.id,
                provider=provider.provider_name,
                model=provider.model_name,
                capability=Capability.EPISODE_UNDERSTANDING,
                payload=job_payload,
                episode_id=episode_context.episode.id,
                artifact_id=dialogue.id,
                remote_call=lambda _job, provider_input=provider_input: core._dispatch(provider, provider_input),
            )

        semantic = dispatched.value
        if not hasattr(semantic, "timed_script"):
            raise AppError("SOURCE_BIBLE_PROVIDER_OUTPUT_INVALID", "P7 Provider 返回了无效结构", status_code=502)

        canonical_semantic = _canonicalize_semantic(
            semantic,
            dialogue_map=dialogue_map,
            visual_map=visual_map,
        )
        canonical_input = _canonical_validation_input(provider_input, episode_context)
        try:
            validate_episode_understanding_grounding(canonical_semantic, canonical_input)
        except ValueError as exc:
            raise AppError(
                "SOURCE_BIBLE_GROUNDING_INVALID",
                "P7 Provider 输出未通过 Source Truth grounding 校验",
                status_code=422,
                details={"reason": str(exc)[:500]},
            ) from exc

        episodes.append(core._compose_episode(episode_context, canonical_semantic))
        provider_jobs.append(
            {
                "provider_job_id": job.id,
                "episode_id": episode_context.episode.id,
                "provider": job.provider,
                "model": job.model,
                "payload_fingerprint": job.payload_fingerprint,
                "remote_job_id": job.remote_job_id,
            }
        )
        context.checkpoint(
            {"stage": "episode_understanding_done", "episode_order": episode_context.episode.episode_order},
            progress_percent=5 + int(index / total * 80),
        )

    provider_profile = provider.profile
    content = SourceBibleContent(schema_version=core.P7_SCHEMA_VERSION, episodes=episodes)
    provenance = SourceBibleProvenance(
        source_video_artifact_id=source.id,
        source_video_fingerprint=source.input_fingerprint,
        source_dialogue_artifact_id=dialogue.id,
        source_dialogue_fingerprint=dialogue.input_fingerprint,
        shot_anchors_artifact_id=shots.id if shots else None,
        shot_anchors_fingerprint=shots.input_fingerprint if shots else None,
        episode_evidence_sets=[
            {
                "episode_id": item.episode.id,
                "source_evidence_set_id": item.evidence_set.id,
                "evidence_fingerprint": item.evidence_set.input_fingerprint,
            }
            for item in episode_contexts
        ],
        provider_jobs=provider_jobs,
        provider=provider.provider_name,
        model=provider.model_name,
        prompt_version=core.P7_PROFILE_VERSION,
        schema_version=core.P7_SCHEMA_VERSION,
        professional_skill_id=str(provider_profile.get("professional_skill_id") or P7_PROFESSIONAL_SKILL_ID),
        professional_skill_version=str(provider_profile.get("professional_skill_version") or "") or None,
        grounding_contract=str(provider_profile.get("grounding_contract") or P7_GROUNDING_CONTRACT),
        generated_by_task_id=task.id,
    )
    return content, provenance


def _safe_task_error(exc: AppError) -> str:
    base = f"P7 源作概览分析失败（{exc.code}）：{exc.message}"
    details = exc.details if isinstance(exc.details, dict) else {}
    if exc.code == "SOURCE_BIBLE_EVIDENCE_REF_INVALID":
        dialogue_ids = [str(item) for item in details.get("dialogue_ids", [])][:6]
        visual_ids = [str(item) for item in details.get("visual_text_ids", [])][:6]
        pieces = []
        if dialogue_ids:
            pieces.append(f"非法对白引用={','.join(dialogue_ids)}")
        if visual_ids:
            pieces.append(f"非法OCR引用={','.join(visual_ids)}")
        if pieces:
            return f"{base}；{'；'.join(pieces)}"
    if exc.code == "SOURCE_BIBLE_GROUNDING_INVALID" and details.get("reason"):
        return f"{base}；{str(details['reason'])[:300]}"
    return base


def _fail_if_running(factory: sessionmaker[Session], task_id: str, worker_id: str, error: str) -> None:
    with factory() as db:
        task = db.get(Task, task_id)
        if task is not None and task.status == TaskStatus.RUNNING and task.worker_id == worker_id:
            mark_task_failed(db, task_id, safe_error=error, worker_id=worker_id)


def run_p7_source_bible_task(session_factory: sessionmaker[Session], task_id: str) -> None:
    worker_id = f"p7-source-bible-{uuid4()}"
    with session_factory() as db:
        claimed = core._claim(db, task_id, worker_id)
        if claimed is None:
            return
        snapshot = TaskWorkerRead.model_validate(claimed)
    context = TaskExecutionContext(session_factory=session_factory, task_id=snapshot.id, worker_id=worker_id)
    try:
        content, provenance = _execute(context, snapshot)
        context.checkpoint({"stage": "validate_source_bible"}, progress_percent=92)
    except TaskCancelled:
        return
    except AppError as exc:
        _fail_if_running(session_factory, snapshot.id, worker_id, _safe_task_error(exc))
        return
    except Exception as exc:
        _fail_if_running(
            session_factory,
            snapshot.id,
            worker_id,
            f"P7 源作概览分析失败（{type(exc).__name__}）",
        )
        return

    with session_factory() as db:
        finished = mark_task_succeeded(db, snapshot.id, worker_id=worker_id)
    if finished.status == TaskStatus.CANCELLED:
        return
    try:
        with session_factory() as db:
            core._publish(db, task_id=snapshot.id, content=content, provenance=provenance)
    except Exception as exc:
        with session_factory() as db:
            task = db.get(Task, snapshot.id)
            if task is not None and task.status == TaskStatus.SUCCEEDED:
                now = utc_now()
                task.status = TaskStatus.FAILED
                task.progress_percent = min(task.progress_percent, 99)
                task.last_error = f"P7 SOURCE_BIBLE 发布失败（{type(exc).__name__}）"
                task.finished_at = now
                task.updated_at = now
                db.add(task)
                db.commit()
