import hashlib
import json
import math
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactNode
from app.artifacts.service import create_artifact, create_artifact_relation, invalidate_current_artifact_type
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.time import utc_now
from app.evidence.models import SourceDialogueUtterance, SourceEvidenceSet, SourceVisualTextSpan
from app.preprocessing.models import ShotAnchor, ShotBoundarySet
from app.projects.enums import SOURCE_BIBLE_PROJECT_TYPES
from app.projects.service import get_project
from app.skills.models import ArtifactType, Capability
from app.sources.models import Episode, SourceAsset
from app.sources.storage import resolve_source_asset_path
from app.understanding.models import SourceBibleRevision
from app.understanding.providers import (
    EpisodeUnderstandingInput,
    SourceEpisodeUnderstandingProvider,
    build_source_episode_understanding_provider,
)
from app.understanding.schemas import (
    MaterialBaseline,
    SourceBibleContent,
    SourceBibleEditCommand,
    SourceBibleEpisode,
    SourceBibleProvenance,
    SourceBibleRead,
    SourceBibleResultStatus,
    SourceBibleRevisionSummary,
)
from app.workflow.models import Task, TaskStatus
from app.workflow.provider_service import ProviderDispatchResult, dispatch_provider_call
from app.workflow.schemas import TaskCommandCreate, TaskWorkerRead
from app.workflow.task_service import (
    TaskCancelled,
    create_task_from_command,
    mark_task_failed,
    mark_task_succeeded,
    publish_validated_task_artifact,
)
from app.workflow.worker import TaskExecutionContext

P7_TASK_TYPE = "P7_SOURCE_BIBLE"
P7_PROFILE_VERSION = "p7-source-bible-v1"
P7_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class EpisodeContext:
    episode: Episode
    asset: SourceAsset
    evidence_set: SourceEvidenceSet
    dialogue: list[SourceDialogueUtterance]
    visual_text: list[SourceVisualTextSpan]
    shot_boundary: ShotBoundarySet | None
    shot_anchors: list[ShotAnchor]


def _sha(payload: object) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _current_artifact(db: Session, project_id: str, artifact_type: ArtifactType) -> ArtifactNode | None:
    return db.scalar(
        select(ArtifactNode).where(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == artifact_type.value,
            ArtifactNode.validity == ArtifactValidity.CURRENT,
            ArtifactNode.is_current.is_(True),
        )
    )


def _required_source(db: Session, project_id: str) -> ArtifactNode:
    source = _current_artifact(db, project_id, ArtifactType.SOURCE_VIDEO)
    if source is None:
        raise AppError("SOURCE_VIDEO_REQUIRED", "P7 需要 CURRENT SOURCE_VIDEO", status_code=409)
    return source


def _source_episode_ids(source: ArtifactNode) -> list[str]:
    raw_ids = source.metadata_json.get("episode_ids") or [
        item.get("episode_id") for item in (source.metadata_json.get("episodes") or [])
    ]
    ids = [str(item) for item in raw_ids if item]
    if not ids or len(ids) != len(set(ids)):
        raise AppError("SOURCE_VIDEO_EPISODE_SET_INVALID", "SOURCE_VIDEO Episode 集合无效", status_code=409)
    return ids


def _required_dialogue(db: Session, project_id: str, source: ArtifactNode) -> ArtifactNode:
    dialogue = _current_artifact(db, project_id, ArtifactType.SOURCE_DIALOGUE)
    if dialogue is None:
        raise AppError("SOURCE_DIALOGUE_REQUIRED", "P7 需要 CURRENT Source Evidence", status_code=409)
    if str(dialogue.metadata_json.get("source_video_artifact_id") or "") != source.id:
        raise AppError("SOURCE_EVIDENCE_STALE", "Source Evidence 与当前完整原片 revision 不一致", status_code=409)
    if not dialogue.metadata_json.get("complete"):
        raise AppError("SOURCE_EVIDENCE_INCOMPLETE", "Source Evidence 尚未覆盖全部 Episode", status_code=409)
    required = set(_source_episode_ids(source))
    actual = {
        str(item.get("episode_id"))
        for item in (dialogue.metadata_json.get("episode_sets") or [])
        if item.get("episode_id")
    }
    if required != actual:
        raise AppError("SOURCE_EVIDENCE_INCOMPLETE", "Source Evidence Episode 集合与完整原片不一致", status_code=409)
    return dialogue


def _optional_shots(db: Session, project_id: str, source: ArtifactNode) -> ArtifactNode | None:
    shots = _current_artifact(db, project_id, ArtifactType.SHOT_ANCHORS)
    if shots is None:
        return None
    if str(shots.metadata_json.get("source_video_artifact_id") or "") != source.id:
        return None
    return shots


def _episode_contexts(
    db: Session,
    *,
    project_id: str,
    source: ArtifactNode,
    dialogue_artifact: ArtifactNode,
    shots_artifact: ArtifactNode | None,
) -> list[EpisodeContext]:
    evidence_meta = {
        str(item.get("episode_id")): item
        for item in (dialogue_artifact.metadata_json.get("episode_sets") or [])
        if item.get("episode_id")
    }
    shot_meta = {
        str(item.get("episode_id")): item
        for item in ((shots_artifact.metadata_json.get("episode_sets") if shots_artifact else None) or [])
        if item.get("episode_id")
    }
    contexts: list[EpisodeContext] = []
    for episode_id in _source_episode_ids(source):
        row = db.execute(
            select(Episode, SourceAsset)
            .join(SourceAsset, Episode.source_asset_id == SourceAsset.id)
            .where(Episode.id == episode_id, Episode.project_id == project_id)
        ).one_or_none()
        if row is None:
            raise AppError("EPISODE_NOT_FOUND", "SOURCE_VIDEO 引用了不存在的 Episode", status_code=409)
        episode, asset = row
        evidence_id = str((evidence_meta.get(episode_id) or {}).get("source_evidence_set_id") or "")
        evidence_set = db.get(SourceEvidenceSet, evidence_id) if evidence_id else None
        if (
            evidence_set is None
            or evidence_set.project_id != project_id
            or evidence_set.episode_id != episode_id
            or evidence_set.source_video_artifact_id != source.id
            or not evidence_set.is_current
        ):
            raise AppError("SOURCE_EVIDENCE_STALE", "Episode 的 CURRENT Source Evidence 无效", status_code=409)
        utterances = list(
            db.scalars(
                select(SourceDialogueUtterance)
                .where(SourceDialogueUtterance.source_evidence_set_id == evidence_set.id)
                .order_by(SourceDialogueUtterance.utterance_number)
            ).all()
        )
        visual = list(
            db.scalars(
                select(SourceVisualTextSpan)
                .where(SourceVisualTextSpan.source_evidence_set_id == evidence_set.id)
                .order_by(SourceVisualTextSpan.span_number)
            ).all()
        )
        boundary = None
        anchors: list[ShotAnchor] = []
        boundary_id = str((shot_meta.get(episode_id) or {}).get("shot_boundary_set_id") or "")
        if boundary_id:
            candidate = db.get(ShotBoundarySet, boundary_id)
            if (
                candidate is not None
                and candidate.episode_id == episode_id
                and candidate.source_video_artifact_id == source.id
                and candidate.is_current
            ):
                boundary = candidate
                anchors = list(
                    db.scalars(
                        select(ShotAnchor)
                        .where(ShotAnchor.shot_boundary_set_id == candidate.id)
                        .order_by(ShotAnchor.shot_number)
                    ).all()
                )
        contexts.append(
            EpisodeContext(
                episode=episode,
                asset=asset,
                evidence_set=evidence_set,
                dialogue=utterances,
                visual_text=visual,
                shot_boundary=boundary,
                shot_anchors=anchors,
            )
        )
    contexts.sort(key=lambda item: item.episode.episode_order)
    return contexts


def _fingerprint_inputs(
    source: ArtifactNode,
    dialogue: ArtifactNode,
    shots: ArtifactNode | None,
    contexts: list[EpisodeContext],
    provider: SourceEpisodeUnderstandingProvider,
) -> str:
    return _sha(
        {
            "task": P7_TASK_TYPE,
            "profile": P7_PROFILE_VERSION,
            "schema_version": P7_SCHEMA_VERSION,
            "source_video": [source.id, source.input_fingerprint],
            "source_dialogue": [dialogue.id, dialogue.input_fingerprint],
            "shot_anchors": [shots.id, shots.input_fingerprint] if shots else None,
            "episodes": [
                {
                    "episode_id": item.episode.id,
                    "asset_sha256": item.asset.sha256,
                    "duration_us": item.episode.duration_us,
                    "evidence_set_id": item.evidence_set.id,
                    "evidence_fingerprint": item.evidence_set.input_fingerprint,
                    "shot_boundary_set_id": item.shot_boundary.id if item.shot_boundary else None,
                }
                for item in contexts
            ],
            "provider": provider.profile,
        }
    )


def _provider_for_project(project) -> SourceEpisodeUnderstandingProvider:
    return build_source_episode_understanding_provider(
        get_settings(),
        project.source_understanding_provider,
    )


def create_source_bible_task(db: Session, *, project_id: str, idempotency_key: str) -> Task:
    project = get_project(db, project_id)
    if project.project_type not in SOURCE_BIBLE_PROJECT_TYPES:
        raise AppError("SOURCE_BIBLE_NOT_ALLOWED", "当前项目类型不执行 SOURCE_BIBLE 整集原片理解", status_code=422)
    source = _required_source(db, project_id)
    dialogue = _required_dialogue(db, project_id, source)
    shots = _optional_shots(db, project_id, source)
    contexts = _episode_contexts(
        db,
        project_id=project_id,
        source=source,
        dialogue_artifact=dialogue,
        shots_artifact=shots,
    )
    provider = _provider_for_project(project)
    fingerprint = _fingerprint_inputs(source, dialogue, shots, contexts, provider)
    inputs = [source.id, dialogue.id]
    if shots is not None:
        inputs.append(shots.id)
    return create_task_from_command(
        db,
        project_id=project_id,
        idempotency_key=idempotency_key,
        payload=TaskCommandCreate(
            task_type=P7_TASK_TYPE,
            task_name="整集多模态原片理解 / 源作概览分析",
            input_fingerprint=fingerprint,
            input_artifact_ids=inputs,
            max_attempts=3,
        ),
    )


def _evidence_payload(context: EpisodeContext) -> dict:
    return {
        "source_evidence_set_id": context.evidence_set.id,
        "dialogue": [
            {
                "id": item.id,
                "start_us": item.start_us,
                "end_us": item.end_us,
                "text": item.text,
                "language": item.language,
            }
            for item in context.dialogue
        ],
        "visual_text": [
            {
                "id": item.id,
                "start_us": item.start_us,
                "end_us": item.end_us,
                "text": item.text,
                "confidence": item.confidence,
            }
            for item in context.visual_text
        ],
    }


def _shot_hints(context: EpisodeContext) -> list[dict]:
    return [
        {
            "shot_number": item.shot_number,
            "start_us": item.start_us,
            "end_us": item.end_us,
        }
        for item in context.shot_anchors
    ]


def _all_ranges(episode: SourceBibleEpisode):
    if episode.material_baseline.effective_content_range:
        yield episode.material_baseline.effective_content_range
    for item in episode.timed_script:
        yield item.time_range
    for character in episode.characters:
        for state in character.states:
            yield state.time_range
    for scene in episode.scenes:
        yield from scene.time_ranges
    for prop in episode.key_props:
        yield from prop.time_ranges
    for event in episode.story_events:
        yield event.time_range
    for beat in episode.emotion_timeline:
        yield beat.time_range
    for beat in episode.story_skeleton.beats:
        yield beat.time_range
    for phase in episode.rhythm_skeleton.phases:
        yield phase.time_range


def _validate_episode_output(episode: SourceBibleEpisode, context: EpisodeContext) -> None:
    duration = context.episode.duration_us
    for time_range in _all_ranges(episode):
        if time_range.end_us > duration:
            raise AppError(
                "SOURCE_BIBLE_TIME_RANGE_INVALID",
                "SOURCE_BIBLE 时间窗口超出完整 Episode",
                status_code=422,
                details={"episode_id": context.episode.id, "end_us": time_range.end_us, "duration_us": duration},
            )
    numbers = [item.segment_number for item in episode.timed_script]
    if len(numbers) != len(set(numbers)):
        raise AppError("SOURCE_BIBLE_SEGMENT_DUPLICATED", "时间化剧情 segment_number 重复", status_code=422)
    dialogue_ids = {item.id for item in context.dialogue}
    visual_ids = {item.id for item in context.visual_text}
    invalid_dialogue = sorted(
        {
            evidence_id
            for segment in episode.timed_script
            for evidence_id in segment.dialogue_evidence_ids
            if evidence_id not in dialogue_ids
        }
    )
    invalid_visual = sorted(
        {
            evidence_id
            for segment in episode.timed_script
            for evidence_id in segment.visual_text_evidence_ids
            if evidence_id not in visual_ids
        }
    )
    if invalid_dialogue or invalid_visual:
        raise AppError(
            "SOURCE_BIBLE_EVIDENCE_REF_INVALID",
            "SOURCE_BIBLE 引用了不属于 CURRENT Source Evidence 的 ID",
            status_code=422,
            details={"dialogue_ids": invalid_dialogue, "visual_text_ids": invalid_visual},
        )
    character_ids = {item.character_id for item in episode.characters}
    if len(character_ids) != len(episode.characters):
        raise AppError("SOURCE_BIBLE_CHARACTER_ID_DUPLICATED", "人物 candidate ID 重复", status_code=422)
    for relation in episode.relationships:
        if relation.source_character_id not in character_ids or relation.target_character_id not in character_ids:
            raise AppError("SOURCE_BIBLE_RELATION_REF_INVALID", "人物关系引用了不存在的人物 candidate", status_code=422)


def _baseline(context: EpisodeContext, semantic) -> MaterialBaseline:
    gcd = math.gcd(context.episode.width, context.episode.height)
    aspect = f"{context.episode.width // gcd}:{context.episode.height // gcd}"
    return MaterialBaseline(
        episode_id=context.episode.id,
        episode_order=context.episode.episode_order,
        source_filename=context.asset.original_filename,
        media_duration_us=context.episode.duration_us,
        width=context.episode.width,
        height=context.episode.height,
        aspect_ratio=aspect,
        avg_frame_rate=context.episode.avg_frame_rate,
        codec_name=context.episode.codec_name,
        has_audio=context.episode.has_audio,
        effective_content_range=semantic.effective_content_range,
        visual_format_notes=semantic.visual_format_notes,
    )


def _compose_episode(context: EpisodeContext, semantic) -> SourceBibleEpisode:
    episode = SourceBibleEpisode(
        material_baseline=_baseline(context, semantic),
        overall_analysis=semantic.overall_analysis,
        timed_script=semantic.timed_script,
        characters=semantic.characters,
        relationships=semantic.relationships,
        scenes=semantic.scenes,
        key_props=semantic.key_props,
        story_events=semantic.story_events,
        emotion_timeline=semantic.emotion_timeline,
        story_skeleton=semantic.story_skeleton,
        rhythm_skeleton=semantic.rhythm_skeleton,
    )
    _validate_episode_output(episode, context)
    return episode


def _execute(context: TaskExecutionContext, task: TaskWorkerRead) -> tuple[SourceBibleContent, SourceBibleProvenance]:
    with context.session_factory() as db:
        project = get_project(db, task.project_id)
        if project.project_type not in SOURCE_BIBLE_PROJECT_TYPES:
            raise AppError("SOURCE_BIBLE_NOT_ALLOWED", "当前项目类型不执行 SOURCE_BIBLE 整集原片理解", status_code=422)
        source = _required_source(db, task.project_id)
        dialogue = _required_dialogue(db, task.project_id, source)
        shots = _optional_shots(db, task.project_id, source)
        expected_inputs = {source.id, dialogue.id, *([shots.id] if shots else [])}
        if set(task.input_artifact_ids_json) != expected_inputs:
            raise AppError("STALE_ARTIFACT_INPUT", "P7 输入 Artifact 已变化，请重新创建任务", status_code=409)
        episode_contexts = _episode_contexts(
            db,
            project_id=task.project_id,
            source=source,
            dialogue_artifact=dialogue,
            shots_artifact=shots,
        )
        provider = _provider_for_project(project)
        if task.input_fingerprint != _fingerprint_inputs(source, dialogue, shots, episode_contexts, provider):
            raise AppError("STALE_ARTIFACT_INPUT", "P7 输入 fingerprint 或 Provider 已变化，请重新创建任务", status_code=409)

    episodes: list[SourceBibleEpisode] = []
    provider_jobs: list[dict] = []
    total = len(episode_contexts)
    for index, episode_context in enumerate(episode_contexts, 1):
        progress = 5 + int((index - 1) / total * 80)
        context.checkpoint(
            {"stage": "episode_understanding", "episode_order": episode_context.episode.episode_order, "input": "FULL_EPISODE"},
            progress_percent=progress,
        )
        source_path = resolve_source_asset_path(episode_context.asset.relative_path)
        provider_input = EpisodeUnderstandingInput(
            source_path=source_path,
            source_filename=episode_context.asset.original_filename,
            mime_type=episode_context.asset.mime_type,
            episode_id=episode_context.episode.id,
            episode_order=episode_context.episode.episode_order,
            duration_us=episode_context.episode.duration_us,
            source_language=project.source_language,
            evidence_payload=_evidence_payload(episode_context),
            shot_hints=_shot_hints(episode_context),
        )
        job_payload = {
            "profile": P7_PROFILE_VERSION,
            "schema_version": P7_SCHEMA_VERSION,
            "episode_id": episode_context.episode.id,
            "source_asset_sha256": episode_context.asset.sha256,
            "source_evidence_set_id": episode_context.evidence_set.id,
            "source_evidence_fingerprint": episode_context.evidence_set.input_fingerprint,
            "dialogue_count": len(episode_context.dialogue),
            "visual_text_count": len(episode_context.visual_text),
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
                remote_call=lambda _job, provider_input=provider_input: _dispatch(provider, provider_input),
            )
        semantic = dispatched.value
        if not hasattr(semantic, "timed_script"):
            raise AppError("SOURCE_BIBLE_PROVIDER_OUTPUT_INVALID", "P7 Provider 返回了无效结构", status_code=502)
        episodes.append(_compose_episode(episode_context, semantic))
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

    content = SourceBibleContent(schema_version=P7_SCHEMA_VERSION, episodes=episodes)
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
        prompt_version=P7_PROFILE_VERSION,
        schema_version=P7_SCHEMA_VERSION,
        generated_by_task_id=task.id,
    )
    return content, provenance


def _dispatch(provider: SourceEpisodeUnderstandingProvider, payload: EpisodeUnderstandingInput) -> ProviderDispatchResult:
    result = provider.analyze(payload)
    return ProviderDispatchResult(value=result.semantic, remote_job_id=result.remote_job_id, completed=True)


def _materialize_story_rhythm(
    db: Session,
    *,
    project_id: str,
    project_skill_id: str,
    project_skill_version: str,
    bible_artifact: ArtifactNode,
    content: SourceBibleContent,
) -> tuple[ArtifactNode, ArtifactNode]:
    story_payload = [
        {
            "episode_id": episode.material_baseline.episode_id,
            "episode_order": episode.material_baseline.episode_order,
            "story_skeleton": episode.story_skeleton.model_dump(mode="json"),
        }
        for episode in content.episodes
    ]
    rhythm_payload = [
        {
            "episode_id": episode.material_baseline.episode_id,
            "episode_order": episode.material_baseline.episode_order,
            "rhythm_skeleton": episode.rhythm_skeleton.model_dump(mode="json"),
        }
        for episode in content.episodes
    ]
    story = create_artifact(
        db,
        project_id=project_id,
        artifact_type=ArtifactType.STORY_SKELETON,
        namespace=ArtifactNamespace.SOURCE,
        label="源作故事骨架",
        input_fingerprint=_sha({"source_bible_artifact_id": bible_artifact.id, "content": story_payload}),
        skill_id=project_skill_id,
        skill_version=project_skill_version,
        metadata_json={"source_bible_artifact_id": bible_artifact.id, "episode_skeletons": story_payload},
    )
    rhythm = create_artifact(
        db,
        project_id=project_id,
        artifact_type=ArtifactType.RHYTHM_SKELETON,
        namespace=ArtifactNamespace.SOURCE,
        label="源作节奏骨架",
        input_fingerprint=_sha({"source_bible_artifact_id": bible_artifact.id, "content": rhythm_payload}),
        skill_id=project_skill_id,
        skill_version=project_skill_version,
        metadata_json={"source_bible_artifact_id": bible_artifact.id, "episode_skeletons": rhythm_payload},
    )
    create_artifact_relation(
        db,
        project_id=project_id,
        source_node_id=bible_artifact.id,
        target_node_id=story.id,
        relation_type=ArtifactRelationType.CONTAINS,
    )
    create_artifact_relation(
        db,
        project_id=project_id,
        source_node_id=bible_artifact.id,
        target_node_id=rhythm.id,
        relation_type=ArtifactRelationType.CONTAINS,
    )
    return story, rhythm


def _persist_revision(
    db: Session,
    *,
    artifact: ArtifactNode,
    content: SourceBibleContent,
    provenance: SourceBibleProvenance,
) -> SourceBibleRevision:
    row = SourceBibleRevision(
        project_id=artifact.project_id,
        artifact_id=artifact.id,
        source_video_artifact_id=provenance.source_video_artifact_id,
        source_dialogue_artifact_id=provenance.source_dialogue_artifact_id,
        shot_anchors_artifact_id=provenance.shot_anchors_artifact_id,
        generated_by_task_id=provenance.generated_by_task_id,
        edit_parent_artifact_id=provenance.edit_parent_artifact_id,
        schema_version=content.schema_version,
        content_json=content.model_dump(mode="json"),
        provenance_json=provenance.model_dump(mode="json"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _publish(
    db: Session,
    *,
    task_id: str,
    content: SourceBibleContent,
    provenance: SourceBibleProvenance,
) -> ArtifactNode:
    task = db.get(Task, task_id)
    if task is None:
        raise AppError("TASK_NOT_FOUND", "P7 任务不存在", status_code=404)
    project = get_project(db, task.project_id)
    if project.project_type not in SOURCE_BIBLE_PROJECT_TYPES:
        raise AppError("SOURCE_BIBLE_NOT_ALLOWED", "当前项目类型不执行 SOURCE_BIBLE 整集原片理解", status_code=422)
    source = _required_source(db, task.project_id)
    dialogue = _required_dialogue(db, task.project_id, source)
    shots = _optional_shots(db, task.project_id, source)
    expected = {source.id, dialogue.id, *([shots.id] if shots else [])}
    if set(task.input_artifact_ids_json) != expected:
        raise AppError("STALE_ARTIFACT_INPUT", "P7 发布时上游 Artifact 已变化", status_code=409)
    contexts = _episode_contexts(
        db,
        project_id=task.project_id,
        source=source,
        dialogue_artifact=dialogue,
        shots_artifact=shots,
    )
    current_provider = _provider_for_project(project)
    if task.input_fingerprint != _fingerprint_inputs(source, dialogue, shots, contexts, current_provider):
        raise AppError("STALE_ARTIFACT_INPUT", "P7 发布时 Provider 或输入 fingerprint 已变化", status_code=409)
    artifact = publish_validated_task_artifact(
        db,
        task_id=task.id,
        validation_passed=True,
        artifact_type=ArtifactType.SOURCE_BIBLE,
        namespace=ArtifactNamespace.SOURCE,
        label="源作概览分析",
        input_fingerprint=task.input_fingerprint,
        skill_id=project.root_skill_id,
        skill_version=project.root_skill_version,
        metadata_json={
            "schema_version": P7_SCHEMA_VERSION,
            "source_video_artifact_id": source.id,
            "source_dialogue_artifact_id": dialogue.id,
            "shot_anchors_artifact_id": shots.id if shots else None,
            "episode_count": len(content.episodes),
            "provider": provenance.provider,
            "model": provenance.model,
            "source_understanding_provider": project.source_understanding_provider.value,
            "editable": True,
            "document_title": "源作概览分析",
        },
    )
    try:
        _persist_revision(db, artifact=artifact, content=content, provenance=provenance)
        create_artifact_relation(
            db,
            project_id=task.project_id,
            source_node_id=source.id,
            target_node_id=artifact.id,
            relation_type=ArtifactRelationType.DERIVED_FROM,
        )
        create_artifact_relation(
            db,
            project_id=task.project_id,
            source_node_id=dialogue.id,
            target_node_id=artifact.id,
            relation_type=ArtifactRelationType.DERIVED_FROM,
        )
        if shots is not None:
            create_artifact_relation(
                db,
                project_id=task.project_id,
                source_node_id=shots.id,
                target_node_id=artifact.id,
                relation_type=ArtifactRelationType.USES,
            )
        _materialize_story_rhythm(
            db,
            project_id=task.project_id,
            project_skill_id=project.root_skill_id,
            project_skill_version=project.root_skill_version,
            bible_artifact=artifact,
            content=content,
        )
    except Exception:
        invalidate_current_artifact_type(db, project_id=task.project_id, artifact_type=ArtifactType.SOURCE_BIBLE)
        invalidate_current_artifact_type(db, project_id=task.project_id, artifact_type=ArtifactType.STORY_SKELETON)
        invalidate_current_artifact_type(db, project_id=task.project_id, artifact_type=ArtifactType.RHYTHM_SKELETON)
        raise
    return artifact


def _claim(db: Session, task_id: str, worker_id: str) -> Task | None:
    task = db.get(Task, task_id)
    if task is None or task.task_type != P7_TASK_TYPE or task.status != TaskStatus.QUEUED or task.attempt >= task.max_attempts:
        return None
    now = utc_now()
    result = db.execute(
        update(Task)
        .where(Task.id == task_id, Task.task_type == P7_TASK_TYPE, Task.status == TaskStatus.QUEUED, Task.attempt < Task.max_attempts)
        .values(
            status=TaskStatus.RUNNING,
            attempt=task.attempt + 1,
            worker_id=worker_id,
            heartbeat_at=now,
            started_at=func.coalesce(Task.started_at, now),
            finished_at=None,
            updated_at=now,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        return None
    db.commit()
    claimed = db.get(Task, task_id)
    if claimed is not None:
        db.refresh(claimed)
    return claimed


def _fail_if_running(factory: sessionmaker[Session], task_id: str, worker_id: str, error: str) -> None:
    with factory() as db:
        task = db.get(Task, task_id)
        if task is not None and task.status == TaskStatus.RUNNING and task.worker_id == worker_id:
            mark_task_failed(db, task_id, safe_error=error, worker_id=worker_id)


def run_p7_source_bible_task(session_factory: sessionmaker[Session], task_id: str) -> None:
    worker_id = f"p7-source-bible-{uuid4()}"
    with session_factory() as db:
        claimed = _claim(db, task_id, worker_id)
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
        _fail_if_running(session_factory, snapshot.id, worker_id, f"P7 源作概览分析失败（{exc.code}）")
        return
    except Exception as exc:
        _fail_if_running(session_factory, snapshot.id, worker_id, f"P7 源作概览分析失败（{type(exc).__name__}）")
        return

    with session_factory() as db:
        finished = mark_task_succeeded(db, snapshot.id, worker_id=worker_id)
    if finished.status == TaskStatus.CANCELLED:
        return
    try:
        with session_factory() as db:
            _publish(db, task_id=snapshot.id, content=content, provenance=provenance)
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


def _artifact_story_rhythm(db: Session, project_id: str, bible_id: str) -> tuple[str | None, str | None]:
    story = _current_artifact(db, project_id, ArtifactType.STORY_SKELETON)
    rhythm = _current_artifact(db, project_id, ArtifactType.RHYTHM_SKELETON)
    story_id = story.id if story is not None and story.metadata_json.get("source_bible_artifact_id") == bible_id else None
    rhythm_id = rhythm.id if rhythm is not None and rhythm.metadata_json.get("source_bible_artifact_id") == bible_id else None
    return story_id, rhythm_id


def get_source_bible(db: Session, project_id: str) -> SourceBibleRead:
    get_project(db, project_id)
    current = _current_artifact(db, project_id, ArtifactType.SOURCE_BIBLE)
    if current is not None:
        row = db.scalar(select(SourceBibleRevision).where(SourceBibleRevision.artifact_id == current.id))
        if row is None:
            raise AppError("SOURCE_BIBLE_CONTENT_MISSING", "CURRENT SOURCE_BIBLE 缺少正式内容记录", status_code=500)
        story_id, rhythm_id = _artifact_story_rhythm(db, project_id, current.id)
        return SourceBibleRead(
            project_id=project_id,
            status=SourceBibleResultStatus.CURRENT,
            artifact_id=current.id,
            revision=current.revision,
            input_fingerprint=current.input_fingerprint,
            content=SourceBibleContent.model_validate(row.content_json),
            provenance=SourceBibleProvenance.model_validate(row.provenance_json),
            story_skeleton_artifact_id=story_id,
            rhythm_skeleton_artifact_id=rhythm_id,
        )
    latest = db.scalar(
        select(ArtifactNode)
        .where(ArtifactNode.project_id == project_id, ArtifactNode.artifact_type == ArtifactType.SOURCE_BIBLE.value)
        .order_by(ArtifactNode.revision.desc())
        .limit(1)
    )
    if latest is None:
        return SourceBibleRead(project_id=project_id, status=SourceBibleResultStatus.NOT_BUILT)
    row = db.scalar(select(SourceBibleRevision).where(SourceBibleRevision.artifact_id == latest.id))
    return SourceBibleRead(
        project_id=project_id,
        status=SourceBibleResultStatus.STALE,
        artifact_id=latest.id,
        revision=latest.revision,
        input_fingerprint=latest.input_fingerprint,
        content=SourceBibleContent.model_validate(row.content_json) if row else None,
        provenance=SourceBibleProvenance.model_validate(row.provenance_json) if row else None,
    )


def list_source_bible_revisions(db: Session, project_id: str) -> list[SourceBibleRevisionSummary]:
    get_project(db, project_id)
    rows = list(
        db.execute(
            select(ArtifactNode, SourceBibleRevision)
            .join(SourceBibleRevision, SourceBibleRevision.artifact_id == ArtifactNode.id)
            .where(ArtifactNode.project_id == project_id, ArtifactNode.artifact_type == ArtifactType.SOURCE_BIBLE.value)
            .order_by(ArtifactNode.revision.desc())
        ).all()
    )
    return [
        SourceBibleRevisionSummary(
            artifact_id=artifact.id,
            revision=artifact.revision,
            status=(
                SourceBibleResultStatus.CURRENT
                if artifact.validity == ArtifactValidity.CURRENT and artifact.is_current
                else SourceBibleResultStatus.STALE
            ),
            input_fingerprint=artifact.input_fingerprint,
            created_at=artifact.created_at.isoformat(),
            edit_parent_artifact_id=revision.edit_parent_artifact_id,
        )
        for artifact, revision in rows
    ]


def edit_source_bible(
    db: Session,
    *,
    project_id: str,
    command: SourceBibleEditCommand,
) -> SourceBibleRead:
    project = get_project(db, project_id)
    current = _current_artifact(db, project_id, ArtifactType.SOURCE_BIBLE)
    if current is None:
        raise AppError("SOURCE_BIBLE_REQUIRED", "请先生成 CURRENT SOURCE_BIBLE", status_code=409)
    row = db.scalar(select(SourceBibleRevision).where(SourceBibleRevision.artifact_id == current.id))
    if row is None:
        raise AppError("SOURCE_BIBLE_CONTENT_MISSING", "CURRENT SOURCE_BIBLE 缺少正式内容记录", status_code=500)
    parent_content = SourceBibleContent.model_validate(row.content_json)
    parent_provenance = SourceBibleProvenance.model_validate(row.provenance_json)
    edited = command.content.model_copy(deep=True)
    parent_by_id = {item.material_baseline.episode_id: item for item in parent_content.episodes}
    edited_ids = [item.material_baseline.episode_id for item in edited.episodes]
    if set(edited_ids) != set(parent_by_id) or len(edited_ids) != len(set(edited_ids)):
        raise AppError("SOURCE_BIBLE_EDIT_SCOPE_INVALID", "编辑不能新增、删除或替换 Episode", status_code=422)
    parent_source = db.get(ArtifactNode, parent_provenance.source_video_artifact_id)
    parent_dialogue = db.get(ArtifactNode, parent_provenance.source_dialogue_artifact_id)
    parent_shots = (
        db.get(ArtifactNode, parent_provenance.shot_anchors_artifact_id)
        if parent_provenance.shot_anchors_artifact_id
        else None
    )
    if parent_source is None or parent_dialogue is None:
        raise AppError("SOURCE_BIBLE_PROVENANCE_INVALID", "SOURCE_BIBLE 上游 provenance 已损坏", status_code=409)
    contexts = _episode_contexts(
        db,
        project_id=project_id,
        source=parent_source,
        dialogue_artifact=parent_dialogue,
        shots_artifact=parent_shots,
    )
    context_by_id = {item.episode.id: item for item in contexts}
    for item in edited.episodes:
        parent_episode = parent_by_id[item.material_baseline.episode_id]
        item.material_baseline = parent_episode.material_baseline.model_copy(deep=True)
        _validate_episode_output(item, context_by_id[item.material_baseline.episode_id])
    edited.schema_version = P7_SCHEMA_VERSION
    fingerprint = _sha(
        {
            "edit_profile": "p7-source-bible-edit-v1",
            "parent_artifact_id": current.id,
            "parent_revision": current.revision,
            "content": edited.model_dump(mode="json"),
        }
    )
    new_artifact = create_artifact(
        db,
        project_id=project_id,
        artifact_type=ArtifactType.SOURCE_BIBLE,
        namespace=ArtifactNamespace.SOURCE,
        label="源作概览分析",
        input_fingerprint=fingerprint,
        skill_id=project.root_skill_id,
        skill_version=project.root_skill_version,
        metadata_json={
            **current.metadata_json,
            "edited": True,
            "edit_parent_artifact_id": current.id,
            "schema_version": P7_SCHEMA_VERSION,
        },
    )
    provenance = parent_provenance.model_copy(
        update={
            "provider_jobs": [],
            "generated_by_task_id": None,
            "edit_parent_artifact_id": current.id,
            "prompt_version": "p7-source-bible-edit-v1",
        }
    )
    try:
        _persist_revision(db, artifact=new_artifact, content=edited, provenance=provenance)
        for upstream_id, relation in (
            (parent_provenance.source_video_artifact_id, ArtifactRelationType.DERIVED_FROM),
            (parent_provenance.source_dialogue_artifact_id, ArtifactRelationType.DERIVED_FROM),
        ):
            create_artifact_relation(
                db,
                project_id=project_id,
                source_node_id=upstream_id,
                target_node_id=new_artifact.id,
                relation_type=relation,
            )
        if parent_provenance.shot_anchors_artifact_id:
            create_artifact_relation(
                db,
                project_id=project_id,
                source_node_id=parent_provenance.shot_anchors_artifact_id,
                target_node_id=new_artifact.id,
                relation_type=ArtifactRelationType.USES,
            )
        create_artifact_relation(
            db,
            project_id=project_id,
            source_node_id=new_artifact.id,
            target_node_id=current.id,
            relation_type=ArtifactRelationType.SUPERSEDES,
        )
        _materialize_story_rhythm(
            db,
            project_id=project_id,
            project_skill_id=project.root_skill_id,
            project_skill_version=project.root_skill_version,
            bible_artifact=new_artifact,
            content=edited,
        )
    except Exception:
        invalidate_current_artifact_type(db, project_id=project_id, artifact_type=ArtifactType.SOURCE_BIBLE)
        invalidate_current_artifact_type(db, project_id=project_id, artifact_type=ArtifactType.STORY_SKELETON)
        invalidate_current_artifact_type(db, project_id=project_id, artifact_type=ArtifactType.RHYTHM_SKELETON)
        raise
    return get_source_bible(db, project_id)
