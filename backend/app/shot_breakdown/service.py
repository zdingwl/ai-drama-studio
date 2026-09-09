import hashlib
import json
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactNode
from app.artifacts.service import create_artifact_relation, invalidate_current_artifact_type
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.time import utc_now
from app.evidence.models import SourceDialogueUtterance, SourceEvidenceSet, SourceVisualTextSpan
from app.preprocessing.models import ShotAnchor, ShotBoundarySet
from app.projects.enums import SOURCE_BIBLE_PROJECT_TYPES
from app.projects.service import get_project
from app.shot_breakdown.models import SourceShotFactsRevision
from app.shot_breakdown.providers import (
    P8_PROFESSIONAL_SKILL_ID,
    P8_PROMPT_VERSION,
    P8_SCHEMA_VERSION,
    P8_SOURCE_TRUTH_CONTRACT,
    EpisodeShotBreakdownInput,
    ShotBreakdownProvider,
    build_shot_breakdown_provider,
)
from app.shot_breakdown.schemas import (
    BoundSubjectRef,
    CanonicalDialogueBinding,
    EpisodeShotBreakdownSemantic,
    ShotBreakdownProvenance,
    ShotBreakdownRead,
    ShotBreakdownResultStatus,
    ShotBreakdownRevisionSummary,
    SourceShotBindings,
    SourceShotFact,
    SourceShotFactsContent,
    SourceShotFactsEpisode,
)
from app.skills.models import ArtifactType, Capability
from app.skills.professional import get_professional_skill
from app.sources.models import Episode, SourceAsset
from app.sources.storage import resolve_source_asset_path
from app.understanding.models import SourceBibleRevision
from app.understanding.schemas import SourceBibleContent, SourceBibleEpisode, SourceBibleProvenance
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


P8_TASK_TYPE = "P8_SHOT_BREAKDOWN"


@dataclass(frozen=True)
class EpisodeContext:
    episode: Episode
    asset: SourceAsset
    source_bible_episode: SourceBibleEpisode
    shot_boundary: ShotBoundarySet
    shot_anchors: list[ShotAnchor]
    evidence_set: SourceEvidenceSet
    dialogue: list[SourceDialogueUtterance]
    visual_text: list[SourceVisualTextSpan]


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


def _source_episode_ids(source: ArtifactNode) -> list[str]:
    raw_ids = source.metadata_json.get("episode_ids") or [
        item.get("episode_id") for item in (source.metadata_json.get("episodes") or [])
    ]
    ids = [str(item) for item in raw_ids if item]
    if not ids or len(ids) != len(set(ids)):
        raise AppError("SOURCE_VIDEO_EPISODE_SET_INVALID", "SOURCE_VIDEO Episode 集合无效", status_code=409)
    return ids


def _required_source(db: Session, project_id: str) -> ArtifactNode:
    source = _current_artifact(db, project_id, ArtifactType.SOURCE_VIDEO)
    if source is None:
        raise AppError("SOURCE_VIDEO_REQUIRED", "P8 需要 CURRENT SOURCE_VIDEO", status_code=409)
    return source


def _required_dialogue(db: Session, project_id: str, source: ArtifactNode) -> ArtifactNode:
    dialogue = _current_artifact(db, project_id, ArtifactType.SOURCE_DIALOGUE)
    if dialogue is None:
        raise AppError("SOURCE_DIALOGUE_REQUIRED", "P8 需要 CURRENT P6 canonical Source Evidence", status_code=409)
    if str(dialogue.metadata_json.get("source_video_artifact_id") or "") != source.id:
        raise AppError("SOURCE_EVIDENCE_STALE", "P8 Source Evidence 与当前完整原片 revision 不一致", status_code=409)
    if not dialogue.metadata_json.get("complete"):
        raise AppError("SOURCE_EVIDENCE_INCOMPLETE", "P8 Source Evidence 尚未覆盖全部 Episode", status_code=409)
    required = set(_source_episode_ids(source))
    actual = {
        str(item.get("episode_id"))
        for item in (dialogue.metadata_json.get("episode_sets") or [])
        if item.get("episode_id")
    }
    if actual != required:
        raise AppError("SOURCE_EVIDENCE_INCOMPLETE", "P8 Source Evidence Episode 集合与完整原片不一致", status_code=409)
    return dialogue


def _required_shots(db: Session, project_id: str, source: ArtifactNode) -> ArtifactNode:
    shots = _current_artifact(db, project_id, ArtifactType.SHOT_ANCHORS)
    if shots is None:
        raise AppError("SHOT_ANCHORS_REQUIRED", "P8 需要 CURRENT P5 SHOT_ANCHORS", status_code=409)
    if str(shots.metadata_json.get("source_video_artifact_id") or "") != source.id:
        raise AppError("SHOT_ANCHORS_STALE", "P8 Shot Anchors 与当前完整原片 revision 不一致", status_code=409)
    required = set(_source_episode_ids(source))
    actual = {
        str(item.get("episode_id"))
        for item in (shots.metadata_json.get("episode_sets") or [])
        if item.get("episode_id")
    }
    if actual != required:
        raise AppError("SHOT_ANCHORS_INCOMPLETE", "P8 Shot Anchors 尚未覆盖全部 Episode", status_code=409)
    return shots


def _required_bible(
    db: Session,
    project_id: str,
    source: ArtifactNode,
    dialogue: ArtifactNode,
) -> tuple[ArtifactNode, SourceBibleContent, SourceBibleProvenance]:
    bible = _current_artifact(db, project_id, ArtifactType.SOURCE_BIBLE)
    if bible is None:
        raise AppError("SOURCE_BIBLE_REQUIRED", "P8 需要 CURRENT SOURCE_BIBLE", status_code=409)
    row = db.scalar(select(SourceBibleRevision).where(SourceBibleRevision.artifact_id == bible.id))
    if row is None:
        raise AppError("SOURCE_BIBLE_CONTENT_MISSING", "CURRENT SOURCE_BIBLE 缺少正式 revision 内容", status_code=500)
    content = SourceBibleContent.model_validate(row.content_json)
    provenance = SourceBibleProvenance.model_validate(row.provenance_json)
    if (
        provenance.source_video_artifact_id != source.id
        or provenance.source_video_fingerprint != source.input_fingerprint
        or provenance.source_dialogue_artifact_id != dialogue.id
        or provenance.source_dialogue_fingerprint != dialogue.input_fingerprint
    ):
        raise AppError("SOURCE_BIBLE_STALE", "CURRENT SOURCE_BIBLE provenance 与当前 Source Truth / Evidence 不一致", status_code=409)
    required = set(_source_episode_ids(source))
    actual = [item.material_baseline.episode_id for item in content.episodes]
    if len(actual) != len(set(actual)) or set(actual) != required:
        raise AppError("SOURCE_BIBLE_EPISODE_SET_INVALID", "CURRENT SOURCE_BIBLE Episode 集合与完整原片不一致", status_code=409)
    return bible, content, provenance


def _validate_anchor_sequence(context: EpisodeContext) -> None:
    anchors = context.shot_anchors
    if not anchors:
        raise AppError("SHOT_ANCHORS_EMPTY", "P8 Episode 没有可用 Shot Anchor", status_code=409)
    numbers = [item.shot_number for item in anchors]
    if numbers != list(range(1, len(anchors) + 1)):
        raise AppError("SHOT_ANCHORS_ORDER_INVALID", "P8 Shot Anchor 编号必须连续且从 1 开始", status_code=409)
    previous_end = 0
    for anchor in anchors:
        if anchor.start_us != previous_end or anchor.end_us <= anchor.start_us or anchor.duration_us != anchor.end_us - anchor.start_us:
            raise AppError("SHOT_ANCHORS_RANGE_INVALID", "P8 Shot Anchor 时间必须连续、非重叠且 duration 一致", status_code=409)
        previous_end = anchor.end_us
    if previous_end > context.episode.duration_us + 250_000:
        raise AppError("SHOT_ANCHORS_TIME_OUT_OF_RANGE", "P8 Shot Anchor 超出 Episode 时长", status_code=409)


def _episode_contexts(
    db: Session,
    *,
    project_id: str,
    source: ArtifactNode,
    dialogue_artifact: ArtifactNode,
    shots_artifact: ArtifactNode,
    bible_content: SourceBibleContent,
) -> list[EpisodeContext]:
    evidence_meta = {
        str(item.get("episode_id")): item
        for item in (dialogue_artifact.metadata_json.get("episode_sets") or [])
        if item.get("episode_id")
    }
    shot_meta = {
        str(item.get("episode_id")): item
        for item in (shots_artifact.metadata_json.get("episode_sets") or [])
        if item.get("episode_id")
    }
    bible_by_episode = {
        item.material_baseline.episode_id: item
        for item in bible_content.episodes
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

        shot_info = shot_meta.get(episode_id) or {}
        boundary_id = str(shot_info.get("shot_boundary_set_id") or "")
        boundary = db.get(ShotBoundarySet, boundary_id) if boundary_id else None
        if (
            boundary is None
            or boundary.project_id != project_id
            or boundary.episode_id != episode_id
            or boundary.source_video_artifact_id != source.id
            or not boundary.is_current
            or str(shot_info.get("set_fingerprint") or "") != boundary.input_fingerprint
        ):
            raise AppError("SHOT_ANCHORS_STALE", "Episode 的 CURRENT P5 Shot Boundary Set 无效", status_code=409)
        anchors = list(
            db.scalars(
                select(ShotAnchor)
                .where(ShotAnchor.shot_boundary_set_id == boundary.id)
                .order_by(ShotAnchor.shot_number)
            ).all()
        )

        evidence_info = evidence_meta.get(episode_id) or {}
        evidence_id = str(evidence_info.get("source_evidence_set_id") or "")
        evidence = db.get(SourceEvidenceSet, evidence_id) if evidence_id else None
        if (
            evidence is None
            or evidence.project_id != project_id
            or evidence.episode_id != episode_id
            or evidence.source_video_artifact_id != source.id
            or not evidence.is_current
            or str(evidence_info.get("set_fingerprint") or "") != evidence.input_fingerprint
        ):
            raise AppError("SOURCE_EVIDENCE_STALE", "Episode 的 CURRENT P6 Source Evidence Set 无效", status_code=409)
        utterances = list(
            db.scalars(
                select(SourceDialogueUtterance)
                .where(SourceDialogueUtterance.source_evidence_set_id == evidence.id)
                .order_by(SourceDialogueUtterance.utterance_number)
            ).all()
        )
        visual_text = list(
            db.scalars(
                select(SourceVisualTextSpan)
                .where(SourceVisualTextSpan.source_evidence_set_id == evidence.id)
                .order_by(SourceVisualTextSpan.span_number)
            ).all()
        )
        bible_episode = bible_by_episode.get(episode_id)
        if bible_episode is None:
            raise AppError("SOURCE_BIBLE_EPISODE_MISSING", "CURRENT SOURCE_BIBLE 缺少当前 Episode", status_code=409)
        episode_context = EpisodeContext(
            episode=episode,
            asset=asset,
            source_bible_episode=bible_episode,
            shot_boundary=boundary,
            shot_anchors=anchors,
            evidence_set=evidence,
            dialogue=utterances,
            visual_text=visual_text,
        )
        _validate_anchor_sequence(episode_context)
        contexts.append(episode_context)
    contexts.sort(key=lambda item: item.episode.episode_order)
    return contexts


def _overlap(start_a: int, end_a: int, start_b: int, end_b: int) -> tuple[int, int] | None:
    start = max(start_a, start_b)
    end = min(end_a, end_b)
    return (start, end) if end > start else None


def _shot_context(context: EpisodeContext) -> list[dict]:
    result: list[dict] = []
    for anchor in context.shot_anchors:
        dialogue_overlaps = []
        for utterance in context.dialogue:
            overlap = _overlap(anchor.start_us, anchor.end_us, utterance.start_us, utterance.end_us)
            if overlap is None:
                continue
            dialogue_overlaps.append(
                {
                    "utterance_number": utterance.utterance_number,
                    "utterance_start_us": utterance.start_us,
                    "utterance_end_us": utterance.end_us,
                    "overlap_start_us": overlap[0],
                    "overlap_end_us": overlap[1],
                    "text": utterance.text,
                    "language": utterance.language,
                }
            )
        visual_overlaps = []
        for item in context.visual_text:
            if _overlap(anchor.start_us, anchor.end_us, item.start_us, item.end_us) is None:
                continue
            visual_overlaps.append(
                {
                    "evidence_id": item.id,
                    "start_us": item.start_us,
                    "end_us": item.end_us,
                    "text": item.text,
                    "confidence": item.confidence,
                }
            )
        result.append(
            {
                "shot_number": anchor.shot_number,
                "start_us": anchor.start_us,
                "end_us": anchor.end_us,
                "duration_us": anchor.duration_us,
                "canonical_dialogue_overlaps": dialogue_overlaps,
                "canonical_visual_text_overlaps": visual_overlaps,
            }
        )
    return result


def _provider_for_project(project) -> ShotBreakdownProvider:
    return build_shot_breakdown_provider(get_settings(), project.source_understanding_provider)


def _fingerprint_inputs(
    source: ArtifactNode,
    bible: ArtifactNode,
    shots: ArtifactNode,
    dialogue: ArtifactNode,
    contexts: list[EpisodeContext],
    provider: ShotBreakdownProvider,
    previous_source_shot_facts_artifact_id: str | None,
) -> str:
    skill = get_professional_skill(P8_PROFESSIONAL_SKILL_ID)
    return _sha(
        {
            "task": P8_TASK_TYPE,
            "profile": P8_PROMPT_VERSION,
            "schema_version": P8_SCHEMA_VERSION,
            "source_truth_contract": P8_SOURCE_TRUTH_CONTRACT,
            "professional_skill": [skill.id, skill.version],
            "source_video": [source.id, source.input_fingerprint],
            "source_bible": [bible.id, bible.input_fingerprint],
            "shot_anchors": [shots.id, shots.input_fingerprint],
            "source_dialogue": [dialogue.id, dialogue.input_fingerprint],
            "previous_source_shot_facts_artifact_id": previous_source_shot_facts_artifact_id,
            "episodes": [
                {
                    "episode_id": item.episode.id,
                    "asset_sha256": item.asset.sha256,
                    "shot_boundary_set_id": item.shot_boundary.id,
                    "shot_boundary_fingerprint": item.shot_boundary.input_fingerprint,
                    "shots": [
                        [shot.id, shot.shot_number, shot.start_us, shot.end_us, shot.duration_us]
                        for shot in item.shot_anchors
                    ],
                    "source_evidence_set_id": item.evidence_set.id,
                    "source_evidence_fingerprint": item.evidence_set.input_fingerprint,
                    "dialogue": [
                        [utterance.id, utterance.utterance_number, utterance.start_us, utterance.end_us, utterance.text]
                        for utterance in item.dialogue
                    ],
                    "visual_text": [
                        [span.id, span.start_us, span.end_us, span.text]
                        for span in item.visual_text
                    ],
                }
                for item in contexts
            ],
            "provider": provider.profile,
        }
    )


def create_shot_breakdown_task(db: Session, *, project_id: str, idempotency_key: str) -> Task:
    project = get_project(db, project_id)
    if project.project_type not in SOURCE_BIBLE_PROJECT_TYPES:
        raise AppError("SHOT_BREAKDOWN_NOT_ALLOWED", "当前项目类型不执行 P8 逐镜精细拉片", status_code=422)
    source = _required_source(db, project_id)
    dialogue = _required_dialogue(db, project_id, source)
    bible, bible_content, _ = _required_bible(db, project_id, source, dialogue)
    shots = _required_shots(db, project_id, source)
    contexts = _episode_contexts(
        db,
        project_id=project_id,
        source=source,
        dialogue_artifact=dialogue,
        shots_artifact=shots,
        bible_content=bible_content,
    )
    provider = _provider_for_project(project)
    previous = db.scalar(
        select(ArtifactNode)
        .where(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == ArtifactType.SOURCE_SHOT_FACTS.value,
        )
        .order_by(ArtifactNode.revision.desc())
        .limit(1)
    )
    fingerprint = _fingerprint_inputs(
        source,
        bible,
        shots,
        dialogue,
        contexts,
        provider,
        previous.id if previous is not None else None,
    )
    return create_task_from_command(
        db,
        project_id=project_id,
        idempotency_key=idempotency_key,
        payload=TaskCommandCreate(
            task_type=P8_TASK_TYPE,
            task_name="带 Source Bible 的逐镜精细拉片",
            input_fingerprint=fingerprint,
            input_artifact_ids=[source.id, bible.id, shots.id, dialogue.id],
            max_attempts=3,
        ),
    )


def _candidate_maps(episode: SourceBibleEpisode) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    characters = {item.character_id: item.name for item in episode.characters}
    scenes = {item.scene_id: item.name for item in episode.scenes}
    props = {item.prop_id: item.name for item in episode.key_props}
    if len(characters) != len(episode.characters):
        raise AppError("SOURCE_BIBLE_CHARACTER_ID_DUPLICATED", "SOURCE_BIBLE 人物 candidate ID 重复", status_code=409)
    if len(scenes) != len(episode.scenes):
        raise AppError("SOURCE_BIBLE_SCENE_ID_DUPLICATED", "SOURCE_BIBLE 场景 candidate ID 重复", status_code=409)
    if len(props) != len(episode.key_props):
        raise AppError("SOURCE_BIBLE_PROP_ID_DUPLICATED", "SOURCE_BIBLE 道具 candidate ID 重复", status_code=409)
    return characters, scenes, props


def _assert_unique_binding_ids(label: str, values: list[str]) -> None:
    if len(values) != len(set(values)):
        raise AppError("P8_BINDING_DUPLICATED", f"{label} candidate binding 重复", status_code=422)


def _bound_refs(label: str, values: list[str], candidates: dict[str, str]) -> list[BoundSubjectRef]:
    _assert_unique_binding_ids(label, values)
    invalid = sorted(set(values) - set(candidates))
    if invalid:
        raise AppError(
            "P8_SOURCE_BIBLE_BINDING_INVALID",
            f"P8 {label} 引用了 CURRENT SOURCE_BIBLE 不存在的 candidate ID",
            status_code=422,
            details={"candidate_ids": invalid},
        )
    return [BoundSubjectRef(id=value, label=candidates[value]) for value in values]


def _compose_episode(context: EpisodeContext, semantic: EpisodeShotBreakdownSemantic) -> SourceShotFactsEpisode:
    expected_numbers = [item.shot_number for item in context.shot_anchors]
    actual_numbers = [item.shot_number for item in semantic.shots]
    if len(actual_numbers) != len(expected_numbers) or set(actual_numbers) != set(expected_numbers):
        raise AppError(
            "P8_SHOT_SET_MISMATCH",
            "P8 Provider 返回的 Shot 集合与 CURRENT P5 Shot Anchors 不一致",
            status_code=422,
            details={"expected": expected_numbers, "actual": actual_numbers},
        )
    semantic_by_number = {item.shot_number: item for item in semantic.shots}
    character_map, scene_map, prop_map = _candidate_maps(context.source_bible_episode)
    utterance_by_number = {item.utterance_number: item for item in context.dialogue}
    if len(utterance_by_number) != len(context.dialogue):
        raise AppError("SOURCE_DIALOGUE_NUMBER_DUPLICATED", "P6 canonical utterance_number 重复", status_code=409)

    shots: list[SourceShotFact] = []
    for anchor in context.shot_anchors:
        item = semantic_by_number[anchor.shot_number]
        expected_utterances = [
            utterance
            for utterance in context.dialogue
            if _overlap(anchor.start_us, anchor.end_us, utterance.start_us, utterance.end_us) is not None
        ]
        annotations = {annotation.utterance_number: annotation for annotation in item.dialogue_annotations}
        expected_annotation_numbers = {utterance.utterance_number for utterance in expected_utterances}
        if set(annotations) != expected_annotation_numbers:
            raise AppError(
                "P8_DIALOGUE_BINDING_INVALID",
                "P8 Provider 的 dialogue_annotations 与服务端 P5×P6 overlap 集合不一致",
                status_code=422,
                details={
                    "shot_number": anchor.shot_number,
                    "expected": sorted(expected_annotation_numbers),
                    "actual": sorted(annotations),
                },
            )
        dialogue_bindings: list[CanonicalDialogueBinding] = []
        for utterance in expected_utterances:
            overlap = _overlap(anchor.start_us, anchor.end_us, utterance.start_us, utterance.end_us)
            assert overlap is not None
            dialogue_bindings.append(
                CanonicalDialogueBinding(
                    utterance_id=utterance.id,
                    utterance_number=utterance.utterance_number,
                    utterance_start_us=utterance.start_us,
                    utterance_end_us=utterance.end_us,
                    overlap_start_us=overlap[0],
                    overlap_end_us=overlap[1],
                    text=utterance.text,
                    language=utterance.language,
                    delivery=annotations[utterance.utterance_number].delivery,
                )
            )
        visual_text_ids = [
            span.id
            for span in context.visual_text
            if _overlap(anchor.start_us, anchor.end_us, span.start_us, span.end_us) is not None
        ]
        shots.append(
            SourceShotFact(
                shot_anchor_id=anchor.id,
                shot_number=anchor.shot_number,
                start_us=anchor.start_us,
                end_us=anchor.end_us,
                duration_us=anchor.duration_us,
                visual_description=item.visual_description,
                camera_language=item.camera_language,
                bindings=SourceShotBindings(
                    characters=_bound_refs("character", item.bindings.character_ids, character_map),
                    scenes=_bound_refs("scene", item.bindings.scene_ids, scene_map),
                    props=_bound_refs("prop", item.bindings.prop_ids, prop_map),
                    unresolved_subject_notes=item.bindings.unresolved_subject_notes,
                ),
                dialogue=dialogue_bindings,
                sound_effects=item.sound_effects,
                ambience=item.ambience,
                visual_text_evidence_ids=visual_text_ids,
            )
        )
    return SourceShotFactsEpisode(
        episode_id=context.episode.id,
        episode_order=context.episode.episode_order,
        source_filename=context.asset.original_filename,
        shots=shots,
    )


def _dispatch(provider: ShotBreakdownProvider, payload: EpisodeShotBreakdownInput) -> ProviderDispatchResult:
    result = provider.analyze(payload)
    return ProviderDispatchResult(value=result.semantic, remote_job_id=result.remote_job_id, completed=True)


def _execute(context: TaskExecutionContext, task: TaskWorkerRead) -> tuple[SourceShotFactsContent, ShotBreakdownProvenance]:
    with context.session_factory() as db:
        project = get_project(db, task.project_id)
        if project.project_type not in SOURCE_BIBLE_PROJECT_TYPES:
            raise AppError("SHOT_BREAKDOWN_NOT_ALLOWED", "当前项目类型不执行 P8 逐镜精细拉片", status_code=422)
        source = _required_source(db, task.project_id)
        dialogue = _required_dialogue(db, task.project_id, source)
        bible, bible_content, _ = _required_bible(db, task.project_id, source, dialogue)
        shots = _required_shots(db, task.project_id, source)
        expected_inputs = {source.id, bible.id, shots.id, dialogue.id}
        if set(task.input_artifact_ids_json) != expected_inputs:
            raise AppError("STALE_ARTIFACT_INPUT", "P8 输入 Artifact 已变化，请重新创建任务", status_code=409)
        episode_contexts = _episode_contexts(
            db,
            project_id=task.project_id,
            source=source,
            dialogue_artifact=dialogue,
            shots_artifact=shots,
            bible_content=bible_content,
        )
        provider = _provider_for_project(project)
        previous = db.scalar(
            select(ArtifactNode)
            .where(
                ArtifactNode.project_id == task.project_id,
                ArtifactNode.artifact_type == ArtifactType.SOURCE_SHOT_FACTS.value,
            )
            .order_by(ArtifactNode.revision.desc())
            .limit(1)
        )
        if task.input_fingerprint != _fingerprint_inputs(
            source,
            bible,
            shots,
            dialogue,
            episode_contexts,
            provider,
            previous.id if previous is not None else None,
        ):
            raise AppError("STALE_ARTIFACT_INPUT", "P8 输入 fingerprint 或 Provider profile 已变化，请重新创建任务", status_code=409)

    episodes: list[SourceShotFactsEpisode] = []
    provider_jobs: list[dict] = []
    total = len(episode_contexts)
    for index, episode_context in enumerate(episode_contexts, 1):
        context.checkpoint(
            {
                "stage": "full_episode_shot_analysis",
                "episode_order": episode_context.episode.episode_order,
                "input": "FULL_EPISODE",
                "shot_count": len(episode_context.shot_anchors),
            },
            progress_percent=5 + int((index - 1) / max(1, total) * 80),
        )
        source_path = resolve_source_asset_path(episode_context.asset.relative_path)
        provider_input = EpisodeShotBreakdownInput(
            source_path=source_path,
            source_filename=episode_context.asset.original_filename,
            mime_type=episode_context.asset.mime_type,
            episode_id=episode_context.episode.id,
            episode_order=episode_context.episode.episode_order,
            duration_us=episode_context.episode.duration_us,
            source_language=project.source_language,
            source_bible_episode=episode_context.source_bible_episode.model_dump(mode="json"),
            shot_context=_shot_context(episode_context),
        )
        job_payload = {
            "profile": P8_PROMPT_VERSION,
            "schema_version": P8_SCHEMA_VERSION,
            "source_truth_contract": P8_SOURCE_TRUTH_CONTRACT,
            "episode_id": episode_context.episode.id,
            "source_asset_sha256": episode_context.asset.sha256,
            "source_bible_artifact_id": bible.id,
            "source_bible_fingerprint": bible.input_fingerprint,
            "shot_boundary_set_id": episode_context.shot_boundary.id,
            "shot_boundary_fingerprint": episode_context.shot_boundary.input_fingerprint,
            "source_evidence_set_id": episode_context.evidence_set.id,
            "source_evidence_fingerprint": episode_context.evidence_set.input_fingerprint,
            "shot_count": len(episode_context.shot_anchors),
            "dialogue_count": len(episode_context.dialogue),
            "visual_text_count": len(episode_context.visual_text),
            "provider_profile": provider.profile,
        }
        with context.session_factory() as db:
            job, dispatched = dispatch_provider_call(
                db,
                task_id=task.id,
                provider=provider.provider_name,
                model=provider.model_name,
                capability=Capability.SHOT_BREAKDOWN,
                payload=job_payload,
                episode_id=episode_context.episode.id,
                artifact_id=bible.id,
                remote_call=lambda _job, provider_input=provider_input: _dispatch(provider, provider_input),
            )
        semantic = dispatched.value
        if not isinstance(semantic, EpisodeShotBreakdownSemantic):
            try:
                semantic = EpisodeShotBreakdownSemantic.model_validate(semantic)
            except Exception as exc:
                raise AppError("P8_PROVIDER_OUTPUT_INVALID", "P8 Provider 返回了无效结构", status_code=502) from exc
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
            {"stage": "episode_shot_analysis_done", "episode_order": episode_context.episode.episode_order},
            progress_percent=5 + int(index / max(1, total) * 80),
        )

    profile = provider.profile
    content = SourceShotFactsContent(schema_version=P8_SCHEMA_VERSION, episodes=episodes)
    provenance = ShotBreakdownProvenance(
        source_video_artifact_id=source.id,
        source_video_fingerprint=source.input_fingerprint,
        source_bible_artifact_id=bible.id,
        source_bible_fingerprint=bible.input_fingerprint,
        shot_anchors_artifact_id=shots.id,
        shot_anchors_fingerprint=shots.input_fingerprint,
        source_dialogue_artifact_id=dialogue.id,
        source_dialogue_fingerprint=dialogue.input_fingerprint,
        episode_inputs=[
            {
                "episode_id": item.episode.id,
                "shot_boundary_set_id": item.shot_boundary.id,
                "shot_boundary_fingerprint": item.shot_boundary.input_fingerprint,
                "source_evidence_set_id": item.evidence_set.id,
                "source_evidence_fingerprint": item.evidence_set.input_fingerprint,
            }
            for item in episode_contexts
        ],
        provider_jobs=provider_jobs,
        provider=provider.provider_name,
        model=provider.model_name,
        prompt_version=P8_PROMPT_VERSION,
        schema_version=P8_SCHEMA_VERSION,
        professional_skill_id=str(profile.get("professional_skill_id") or P8_PROFESSIONAL_SKILL_ID),
        professional_skill_version=str(profile.get("professional_skill_version") or "") or None,
        source_truth_contract=str(profile.get("source_truth_contract") or P8_SOURCE_TRUTH_CONTRACT),
        generated_by_task_id=task.id,
    )
    return content, provenance


def _persist_revision(
    db: Session,
    *,
    artifact: ArtifactNode,
    content: SourceShotFactsContent,
    provenance: ShotBreakdownProvenance,
) -> SourceShotFactsRevision:
    row = SourceShotFactsRevision(
        project_id=artifact.project_id,
        artifact_id=artifact.id,
        source_video_artifact_id=provenance.source_video_artifact_id,
        source_bible_artifact_id=provenance.source_bible_artifact_id,
        shot_anchors_artifact_id=provenance.shot_anchors_artifact_id,
        source_dialogue_artifact_id=provenance.source_dialogue_artifact_id,
        generated_by_task_id=provenance.generated_by_task_id,
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
    content: SourceShotFactsContent,
    provenance: ShotBreakdownProvenance,
) -> ArtifactNode:
    task = db.get(Task, task_id)
    if task is None:
        raise AppError("TASK_NOT_FOUND", "P8 任务不存在", status_code=404)
    project = get_project(db, task.project_id)
    source = _required_source(db, task.project_id)
    dialogue = _required_dialogue(db, task.project_id, source)
    bible, bible_content, _ = _required_bible(db, task.project_id, source, dialogue)
    shots = _required_shots(db, task.project_id, source)
    expected_inputs = {source.id, bible.id, shots.id, dialogue.id}
    if set(task.input_artifact_ids_json) != expected_inputs:
        raise AppError("STALE_ARTIFACT_INPUT", "P8 发布时上游 Artifact 已变化", status_code=409)
    episode_contexts = _episode_contexts(
        db,
        project_id=task.project_id,
        source=source,
        dialogue_artifact=dialogue,
        shots_artifact=shots,
        bible_content=bible_content,
    )
    provider = _provider_for_project(project)
    previous = db.scalar(
        select(ArtifactNode)
        .where(
            ArtifactNode.project_id == task.project_id,
            ArtifactNode.artifact_type == ArtifactType.SOURCE_SHOT_FACTS.value,
        )
        .order_by(ArtifactNode.revision.desc())
        .limit(1)
    )
    if task.input_fingerprint != _fingerprint_inputs(
        source,
        bible,
        shots,
        dialogue,
        episode_contexts,
        provider,
        previous.id if previous is not None else None,
    ):
        raise AppError("STALE_ARTIFACT_INPUT", "P8 发布时 Provider 或输入 fingerprint 已变化", status_code=409)

    previous = db.scalar(
        select(ArtifactNode)
        .where(
            ArtifactNode.project_id == task.project_id,
            ArtifactNode.artifact_type == ArtifactType.SOURCE_SHOT_FACTS.value,
        )
        .order_by(ArtifactNode.revision.desc())
        .limit(1)
    )
    final_provenance = provenance.model_copy(
        update={"supersedes_artifact_id": previous.id if previous is not None else None}
    )
    skill = get_professional_skill(P8_PROFESSIONAL_SKILL_ID)
    artifact = publish_validated_task_artifact(
        db,
        task_id=task.id,
        validation_passed=True,
        artifact_type=ArtifactType.SOURCE_SHOT_FACTS,
        namespace=ArtifactNamespace.SOURCE,
        label="逐镜精细拉片",
        input_fingerprint=task.input_fingerprint,
        skill_id=skill.id,
        skill_version=skill.version,
        metadata_json={
            "schema_version": P8_SCHEMA_VERSION,
            "source_video_artifact_id": source.id,
            "source_bible_artifact_id": bible.id,
            "shot_anchors_artifact_id": shots.id,
            "source_dialogue_artifact_id": dialogue.id,
            "episode_count": len(content.episodes),
            "shot_count": sum(len(item.shots) for item in content.episodes),
            "provider": final_provenance.provider,
            "model": final_provenance.model,
            "professional_skill_id": skill.id,
            "professional_skill_version": skill.version,
            "source_truth_contract": P8_SOURCE_TRUTH_CONTRACT,
            "document_title": "逐镜精细拉片",
        },
    )
    try:
        _persist_revision(db, artifact=artifact, content=content, provenance=final_provenance)
        for upstream_id, relation in (
            (source.id, ArtifactRelationType.DERIVED_FROM),
            (bible.id, ArtifactRelationType.USES),
            (shots.id, ArtifactRelationType.DERIVED_FROM),
            (dialogue.id, ArtifactRelationType.DERIVED_FROM),
        ):
            create_artifact_relation(
                db,
                project_id=task.project_id,
                source_node_id=upstream_id,
                target_node_id=artifact.id,
                relation_type=relation,
            )
        if previous is not None:
            create_artifact_relation(
                db,
                project_id=task.project_id,
                source_node_id=artifact.id,
                target_node_id=previous.id,
                relation_type=ArtifactRelationType.SUPERSEDES,
            )
    except Exception:
        invalidate_current_artifact_type(
            db,
            project_id=task.project_id,
            artifact_type=ArtifactType.SOURCE_SHOT_FACTS,
        )
        raise
    return artifact


def _claim(db: Session, task_id: str, worker_id: str) -> Task | None:
    task = db.get(Task, task_id)
    if task is None or task.task_type != P8_TASK_TYPE or task.status != TaskStatus.QUEUED or task.attempt >= task.max_attempts:
        return None
    now = utc_now()
    result = db.execute(
        update(Task)
        .where(
            Task.id == task_id,
            Task.task_type == P8_TASK_TYPE,
            Task.status == TaskStatus.QUEUED,
            Task.attempt < Task.max_attempts,
        )
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


def run_p8_shot_breakdown_task(session_factory: sessionmaker[Session], task_id: str) -> None:
    worker_id = f"p8-shot-breakdown-{uuid4()}"
    with session_factory() as db:
        claimed = _claim(db, task_id, worker_id)
        if claimed is None:
            return
        snapshot = TaskWorkerRead.model_validate(claimed)
    context = TaskExecutionContext(session_factory=session_factory, task_id=snapshot.id, worker_id=worker_id)
    try:
        content, provenance = _execute(context, snapshot)
        context.checkpoint({"stage": "validate_source_shot_facts"}, progress_percent=92)
    except TaskCancelled:
        return
    except AppError as exc:
        _fail_if_running(session_factory, snapshot.id, worker_id, f"P8 逐镜精细拉片失败（{exc.code}）")
        return
    except Exception as exc:
        _fail_if_running(session_factory, snapshot.id, worker_id, f"P8 逐镜精细拉片失败（{type(exc).__name__}）")
        return

    with session_factory() as db:
        finished = mark_task_succeeded(db, snapshot.id, worker_id=worker_id)
    if finished.status == TaskStatus.CANCELLED:
        return
    try:
        with session_factory() as db:
            _publish(db, task_id=snapshot.id, content=content, provenance=provenance)
    except AppError as exc:
        with session_factory() as db:
            task = db.get(Task, snapshot.id)
            if task is not None and task.status == TaskStatus.SUCCEEDED:
                now = utc_now()
                task.status = TaskStatus.FAILED
                task.progress_percent = min(task.progress_percent, 99)
                task.last_error = f"P8 SOURCE_SHOT_FACTS 发布失败（{exc.code}）"
                task.finished_at = now
                task.updated_at = now
                db.add(task)
                db.commit()
    except Exception as exc:
        with session_factory() as db:
            task = db.get(Task, snapshot.id)
            if task is not None and task.status == TaskStatus.SUCCEEDED:
                now = utc_now()
                task.status = TaskStatus.FAILED
                task.progress_percent = min(task.progress_percent, 99)
                task.last_error = f"P8 SOURCE_SHOT_FACTS 发布失败（{type(exc).__name__}）"
                task.finished_at = now
                task.updated_at = now
                db.add(task)
                db.commit()


def get_shot_breakdown(db: Session, project_id: str) -> ShotBreakdownRead:
    get_project(db, project_id)
    current = _current_artifact(db, project_id, ArtifactType.SOURCE_SHOT_FACTS)
    if current is not None:
        row = db.scalar(select(SourceShotFactsRevision).where(SourceShotFactsRevision.artifact_id == current.id))
        if row is None:
            raise AppError("SOURCE_SHOT_FACTS_CONTENT_MISSING", "CURRENT SOURCE_SHOT_FACTS 缺少正式 revision 内容", status_code=500)
        return ShotBreakdownRead(
            project_id=project_id,
            status=ShotBreakdownResultStatus.CURRENT,
            artifact_id=current.id,
            revision=current.revision,
            input_fingerprint=current.input_fingerprint,
            content=SourceShotFactsContent.model_validate(row.content_json),
            provenance=ShotBreakdownProvenance.model_validate(row.provenance_json),
        )
    latest = db.scalar(
        select(ArtifactNode)
        .where(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == ArtifactType.SOURCE_SHOT_FACTS.value,
        )
        .order_by(ArtifactNode.revision.desc())
        .limit(1)
    )
    if latest is None:
        return ShotBreakdownRead(project_id=project_id, status=ShotBreakdownResultStatus.NOT_BUILT)
    row = db.scalar(select(SourceShotFactsRevision).where(SourceShotFactsRevision.artifact_id == latest.id))
    return ShotBreakdownRead(
        project_id=project_id,
        status=ShotBreakdownResultStatus.STALE,
        artifact_id=latest.id,
        revision=latest.revision,
        input_fingerprint=latest.input_fingerprint,
        content=SourceShotFactsContent.model_validate(row.content_json) if row else None,
        provenance=ShotBreakdownProvenance.model_validate(row.provenance_json) if row else None,
    )


def list_shot_breakdown_revisions(db: Session, project_id: str) -> list[ShotBreakdownRevisionSummary]:
    get_project(db, project_id)
    rows = list(
        db.execute(
            select(ArtifactNode, SourceShotFactsRevision)
            .join(SourceShotFactsRevision, SourceShotFactsRevision.artifact_id == ArtifactNode.id)
            .where(
                ArtifactNode.project_id == project_id,
                ArtifactNode.artifact_type == ArtifactType.SOURCE_SHOT_FACTS.value,
            )
            .order_by(ArtifactNode.revision.desc())
        ).all()
    )
    return [
        ShotBreakdownRevisionSummary(
            artifact_id=artifact.id,
            revision=artifact.revision,
            status=(
                ShotBreakdownResultStatus.CURRENT
                if artifact.validity == ArtifactValidity.CURRENT and artifact.is_current
                else ShotBreakdownResultStatus.STALE
            ),
            input_fingerprint=artifact.input_fingerprint,
            created_at=artifact.created_at.isoformat(),
            supersedes_artifact_id=revision.provenance_json.get("supersedes_artifact_id"),
        )
        for artifact, revision in rows
    ]
