import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactEdge, ArtifactNode
from app.artifacts.service import _invalidate_project_plan, _mark_stale_with_downstream, expected_namespace
from app.core.errors import AppError
from app.projects.enums import SOURCE_BIBLE_PROJECT_TYPES
from app.projects.service import get_project
from app.skills.models import ArtifactType
from app.skills.professional import get_professional_skill
from app.source_resolution.models import SourceResolutionRevision
from app.source_resolution.schemas import (
    CharacterResolutionContent,
    PropResolutionContent,
    SceneResolutionContent,
    SourceResolutionKind,
    SourceResolutionProvenance,
    SpeakerResolutionContent,
)
from app.source_resolution.service import P9Inputs, _load_inputs as _load_p9_inputs
from app.source_snapshot.models import SourceVideoSnapshotRevision
from app.source_snapshot.schemas import (
    P10_PROFESSIONAL_SKILL_ID,
    P10_PUBLICATION_MODE,
    P10_REQUIRED_ARTIFACT_TYPES,
    P10_SCHEMA_VERSION,
    P10_SNAPSHOT_CONTRACT,
    P10_SOURCE_TRUTH_CONTRACT,
    FrozenArtifactRef,
    SnapshotDialogueUtterance,
    SnapshotShotAnchor,
    SnapshotVisualTextSpan,
    SourceVideoSnapshotContent,
    SourceVideoSnapshotEpisode,
    SourceVideoSnapshotEpisodeProvenance,
    SourceVideoSnapshotProvenance,
    SourceVideoSnapshotRead,
    SourceVideoSnapshotResultStatus,
    SourceVideoSnapshotRevisionSummary,
)


_RESOLUTION_TYPE_KIND = {
    ArtifactType.SOURCE_CHARACTERS: SourceResolutionKind.CHARACTER,
    ArtifactType.SOURCE_SPEAKERS: SourceResolutionKind.SPEAKER,
    ArtifactType.SOURCE_SCENES: SourceResolutionKind.SCENE,
    ArtifactType.SOURCE_PROPS: SourceResolutionKind.PROP,
}
_RESOLUTION_CONTENT = {
    SourceResolutionKind.CHARACTER: CharacterResolutionContent,
    SourceResolutionKind.SPEAKER: SpeakerResolutionContent,
    SourceResolutionKind.SCENE: SceneResolutionContent,
    SourceResolutionKind.PROP: PropResolutionContent,
}
_DEPENDENCY_RELATIONS = {
    ArtifactType.SOURCE_VIDEO: ArtifactRelationType.DERIVED_FROM,
    ArtifactType.SHOT_ANCHORS: ArtifactRelationType.DERIVED_FROM,
    ArtifactType.SOURCE_DIALOGUE: ArtifactRelationType.DERIVED_FROM,
    ArtifactType.SOURCE_BIBLE: ArtifactRelationType.USES,
    ArtifactType.STORY_SKELETON: ArtifactRelationType.USES,
    ArtifactType.RHYTHM_SKELETON: ArtifactRelationType.USES,
    ArtifactType.SOURCE_SHOT_FACTS: ArtifactRelationType.DERIVED_FROM,
    ArtifactType.SOURCE_CHARACTERS: ArtifactRelationType.CONTAINS,
    ArtifactType.SOURCE_SPEAKERS: ArtifactRelationType.CONTAINS,
    ArtifactType.SOURCE_SCENES: ArtifactRelationType.CONTAINS,
    ArtifactType.SOURCE_PROPS: ArtifactRelationType.CONTAINS,
}


@dataclass(frozen=True)
class P10Inputs:
    p9: P9Inputs
    artifacts: dict[ArtifactType, ArtifactNode]
    characters: CharacterResolutionContent
    speakers: SpeakerResolutionContent
    scenes: SceneResolutionContent
    props: PropResolutionContent
    resolution_provenance: dict[SourceResolutionKind, SourceResolutionProvenance]


def _sha(payload: object) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _current_artifact(db: Session, project_id: str, artifact_type: ArtifactType) -> ArtifactNode | None:
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
    if len(rows) > 1:
        raise AppError(
            "P10_MULTIPLE_CURRENT_ARTIFACTS",
            "P10 检测到同类型多个 CURRENT Source Artifact",
            status_code=409,
            details={"artifact_type": artifact_type.value},
        )
    return rows[0] if rows else None


def _latest_artifact(db: Session, project_id: str, artifact_type: ArtifactType) -> ArtifactNode | None:
    return db.scalar(
        select(ArtifactNode)
        .where(ArtifactNode.project_id == project_id, ArtifactNode.artifact_type == artifact_type.value)
        .order_by(ArtifactNode.revision.desc())
        .limit(1)
    )


def _require_current(db: Session, project_id: str, artifact_type: ArtifactType) -> ArtifactNode:
    artifact = _current_artifact(db, project_id, artifact_type)
    if artifact is None:
        raise AppError(
            "P10_SOURCE_ARTIFACT_REQUIRED",
            "P10 需要完整 CURRENT P5~P9 Source Artifact 链",
            status_code=409,
            details={"artifact_type": artifact_type.value},
        )
    if artifact.namespace != ArtifactNamespace.SOURCE:
        raise AppError("P10_SOURCE_NAMESPACE_INVALID", "P10 只允许冻结 SOURCE namespace Artifact", status_code=409)
    return artifact


def _resolution_row(
    db: Session,
    *,
    artifact: ArtifactNode,
    expected_kind: SourceResolutionKind,
) -> tuple[Any, SourceResolutionProvenance]:
    row = db.scalar(select(SourceResolutionRevision).where(SourceResolutionRevision.artifact_id == artifact.id))
    if row is None or row.resolution_kind != expected_kind.value:
        raise AppError(
            "P10_P9_REVISION_MISSING",
            "P10 需要 P9 正式 typed resolution revision",
            status_code=409,
            details={"artifact_type": artifact.artifact_type, "artifact_id": artifact.id},
        )
    try:
        content = _RESOLUTION_CONTENT[expected_kind].model_validate(row.content_json)
        provenance = SourceResolutionProvenance.model_validate(row.provenance_json)
    except Exception as exc:
        raise AppError("P10_P9_TYPED_CONTENT_INVALID", "P9 typed resolution 无法通过 P10 数据契约校验", status_code=409) from exc
    if provenance.resolution_kind != expected_kind:
        raise AppError("P10_P9_PROVENANCE_INVALID", "P9 provenance resolution kind 与 Artifact 不一致", status_code=409)
    return content, provenance


def _validate_story_rhythm(artifacts: dict[ArtifactType, ArtifactNode], p9: P9Inputs) -> None:
    story = artifacts[ArtifactType.STORY_SKELETON]
    rhythm = artifacts[ArtifactType.RHYTHM_SKELETON]
    if story.metadata_json.get("source_bible_artifact_id") != p9.bible.id:
        raise AppError("P10_STORY_SKELETON_STALE", "CURRENT STORY_SKELETON 未绑定 CURRENT SOURCE_BIBLE", status_code=409)
    if rhythm.metadata_json.get("source_bible_artifact_id") != p9.bible.id:
        raise AppError("P10_RHYTHM_SKELETON_STALE", "CURRENT RHYTHM_SKELETON 未绑定 CURRENT SOURCE_BIBLE", status_code=409)

    expected_story = [
        {
            "episode_id": episode.material_baseline.episode_id,
            "episode_order": episode.material_baseline.episode_order,
            "story_skeleton": episode.story_skeleton.model_dump(mode="json"),
        }
        for episode in p9.bible_content.episodes
    ]
    expected_rhythm = [
        {
            "episode_id": episode.material_baseline.episode_id,
            "episode_order": episode.material_baseline.episode_order,
            "rhythm_skeleton": episode.rhythm_skeleton.model_dump(mode="json"),
        }
        for episode in p9.bible_content.episodes
    ]
    if story.metadata_json.get("episode_skeletons") != expected_story:
        raise AppError("P10_STORY_SKELETON_MISMATCH", "STORY_SKELETON 与 CURRENT SOURCE_BIBLE typed 内容不一致", status_code=409)
    if rhythm.metadata_json.get("episode_skeletons") != expected_rhythm:
        raise AppError("P10_RHYTHM_SKELETON_MISMATCH", "RHYTHM_SKELETON 与 CURRENT SOURCE_BIBLE typed 内容不一致", status_code=409)


def _validate_resolution_provenance(
    *,
    inputs: P9Inputs,
    artifacts: dict[ArtifactType, ArtifactNode],
    provenance: dict[SourceResolutionKind, SourceResolutionProvenance],
) -> None:
    characters = artifacts[ArtifactType.SOURCE_CHARACTERS]
    for kind, prov in provenance.items():
        if (
            prov.source_video_artifact_id != inputs.source.id
            or prov.source_video_fingerprint != inputs.source.input_fingerprint
            or prov.source_bible_artifact_id != inputs.bible.id
            or prov.source_bible_fingerprint != inputs.bible.input_fingerprint
            or prov.source_shot_facts_artifact_id != inputs.facts.id
            or prov.source_shot_facts_fingerprint != inputs.facts.input_fingerprint
            or prov.shot_anchors_artifact_id != inputs.shots.id
            or prov.shot_anchors_fingerprint != inputs.shots.input_fingerprint
        ):
            raise AppError(
                "P10_P9_PROVENANCE_INVALID",
                "P9 provenance 未绑定当前 P5/P7/P8/SOURCE_VIDEO Source 链",
                status_code=409,
                details={"resolution_kind": kind.value},
            )
        if kind == SourceResolutionKind.SPEAKER:
            if (
                prov.source_dialogue_artifact_id != inputs.dialogue.id
                or prov.source_dialogue_fingerprint != inputs.dialogue.input_fingerprint
                or prov.source_characters_artifact_id != characters.id
                or prov.source_characters_fingerprint != characters.input_fingerprint
            ):
                raise AppError(
                    "P10_SPEAKER_PROVENANCE_INVALID",
                    "CURRENT SOURCE_SPEAKERS 必须绑定 CURRENT SOURCE_DIALOGUE 与 SOURCE_CHARACTERS",
                    status_code=409,
                )


def _validate_speaker_truth(inputs: P9Inputs, characters: CharacterResolutionContent, speakers: SpeakerResolutionContent) -> None:
    canonical: dict[str, tuple[str, Any]] = {}
    for context in inputs.contexts:
        for utterance in context.dialogue:
            if utterance.id in canonical:
                raise AppError("P10_P6_UTTERANCE_DUPLICATED", "CURRENT P6 canonical utterance id 重复", status_code=409)
            canonical[utterance.id] = (context.episode.id, utterance)

    ids = [item.utterance_id for item in speakers.attributions]
    if len(ids) != len(set(ids)) or set(ids) != set(canonical):
        raise AppError("P10_SPEAKER_UTTERANCE_SET_INVALID", "SOURCE_SPEAKERS attribution 必须覆盖 CURRENT P6 canonical utterance", status_code=409)
    for attribution in speakers.attributions:
        episode_id, utterance = canonical[attribution.utterance_id]
        if (
            attribution.episode_id != episode_id
            or attribution.utterance_number != utterance.utterance_number
            or attribution.start_us != utterance.start_us
            or attribution.end_us != utterance.end_us
            or attribution.text != utterance.text
        ):
            raise AppError("P10_P6_CANONICAL_MISMATCH", "SOURCE_SPEAKERS dialogue 与 CURRENT P6 canonical text/time 不一致", status_code=409)

    character_ids = {item.character_id for item in characters.entities}
    for speaker in speakers.entities:
        if speaker.character_id is not None and speaker.character_id not in character_ids:
            raise AppError("P10_SPEAKER_CHARACTER_LINK_INVALID", "SOURCE_SPEAKERS 引用了非 CURRENT SOURCE_CHARACTERS identity", status_code=409)


def _validate_scene_truth(inputs: P9Inputs, scenes: SceneResolutionContent) -> None:
    authoritative: dict[str, tuple[str, Any]] = {}
    for context in inputs.contexts:
        for anchor in context.shot_anchors:
            if anchor.id in authoritative:
                raise AppError("P10_P5_SHOT_DUPLICATED", "CURRENT P5 shot_anchor_id 重复", status_code=409)
            authoritative[anchor.id] = (context.episode.id, anchor)
    ids = [item.shot_anchor_id for item in scenes.assignments]
    if len(ids) != len(set(ids)) or set(ids) != set(authoritative):
        raise AppError("P10_SCENE_SHOT_SET_INVALID", "SOURCE_SCENES 必须覆盖 CURRENT P5 Shot 集合", status_code=409)
    for assignment in scenes.assignments:
        episode_id, anchor = authoritative[assignment.shot_anchor_id]
        if (
            assignment.episode_id != episode_id
            or assignment.shot_number != anchor.shot_number
            or assignment.start_us != anchor.start_us
            or assignment.end_us != anchor.end_us
        ):
            raise AppError("P10_P5_TIME_AUTHORITY_VIOLATION", "SOURCE_SCENES Shot 时间与 CURRENT P5 不一致", status_code=409)


def _load_inputs(db: Session, project_id: str) -> P10Inputs:
    project = get_project(db, project_id)
    if project.project_type not in SOURCE_BIBLE_PROJECT_TYPES:
        raise AppError("SOURCE_VIDEO_SNAPSHOT_NOT_ALLOWED", "当前项目类型未进入 P10 完整 Source Snapshot 链", status_code=422)

    p9 = _load_p9_inputs(db, project_id)
    artifacts: dict[ArtifactType, ArtifactNode] = {}
    for artifact_type in P10_REQUIRED_ARTIFACT_TYPES:
        artifacts[artifact_type] = _require_current(db, project_id, artifact_type)

    if (
        artifacts[ArtifactType.SOURCE_VIDEO].id != p9.source.id
        or artifacts[ArtifactType.SHOT_ANCHORS].id != p9.shots.id
        or artifacts[ArtifactType.SOURCE_DIALOGUE].id != p9.dialogue.id
        or artifacts[ArtifactType.SOURCE_BIBLE].id != p9.bible.id
        or artifacts[ArtifactType.SOURCE_SHOT_FACTS].id != p9.facts.id
    ):
        raise AppError("P10_SOURCE_CHAIN_CHANGED", "P10 Source 输入在校验期间发生变化", status_code=409)

    resolution_content: dict[SourceResolutionKind, Any] = {}
    resolution_provenance: dict[SourceResolutionKind, SourceResolutionProvenance] = {}
    for artifact_type, kind in _RESOLUTION_TYPE_KIND.items():
        content, prov = _resolution_row(db, artifact=artifacts[artifact_type], expected_kind=kind)
        resolution_content[kind] = content
        resolution_provenance[kind] = prov

    _validate_story_rhythm(artifacts, p9)
    _validate_resolution_provenance(inputs=p9, artifacts=artifacts, provenance=resolution_provenance)
    characters = resolution_content[SourceResolutionKind.CHARACTER]
    speakers = resolution_content[SourceResolutionKind.SPEAKER]
    scenes = resolution_content[SourceResolutionKind.SCENE]
    props = resolution_content[SourceResolutionKind.PROP]
    _validate_speaker_truth(p9, characters, speakers)
    _validate_scene_truth(p9, scenes)

    return P10Inputs(
        p9=p9,
        artifacts=artifacts,
        characters=characters,
        speakers=speakers,
        scenes=scenes,
        props=props,
        resolution_provenance=resolution_provenance,
    )


def _frozen_refs(inputs: P10Inputs) -> list[FrozenArtifactRef]:
    return [
        FrozenArtifactRef(
            artifact_type=artifact_type,
            artifact_id=inputs.artifacts[artifact_type].id,
            revision=inputs.artifacts[artifact_type].revision,
            input_fingerprint=inputs.artifacts[artifact_type].input_fingerprint,
        )
        for artifact_type in P10_REQUIRED_ARTIFACT_TYPES
    ]


def _snapshot_episodes(inputs: P10Inputs) -> list[SourceVideoSnapshotEpisode]:
    episodes: list[SourceVideoSnapshotEpisode] = []
    for context in inputs.p9.contexts:
        if context.shot_boundary is None:
            raise AppError("P10_SHOT_BOUNDARY_REQUIRED", "P10 需要每个 Episode 的 CURRENT ShotBoundarySet", status_code=409)
        episodes.append(
            SourceVideoSnapshotEpisode(
                episode_id=context.episode.id,
                source_asset_id=context.asset.id,
                episode_order=context.episode.episode_order,
                source_filename=context.asset.original_filename,
                source_asset_sha256=context.asset.sha256,
                duration_us=context.episode.duration_us,
                width=context.episode.width,
                height=context.episode.height,
                codec_name=context.episode.codec_name,
                avg_frame_rate=context.episode.avg_frame_rate,
                has_audio=context.episode.has_audio,
                shot_boundary_set_id=context.shot_boundary.id,
                shot_boundary_fingerprint=context.shot_boundary.input_fingerprint,
                source_evidence_set_id=context.evidence_set.id,
                source_evidence_fingerprint=context.evidence_set.input_fingerprint,
                shot_anchors=[
                    SnapshotShotAnchor(
                        shot_anchor_id=item.id,
                        shot_number=item.shot_number,
                        start_us=item.start_us,
                        end_us=item.end_us,
                        duration_us=item.duration_us,
                    )
                    for item in context.shot_anchors
                ],
                canonical_dialogue=[
                    SnapshotDialogueUtterance(
                        utterance_id=item.id,
                        utterance_number=item.utterance_number,
                        start_us=item.start_us,
                        end_us=item.end_us,
                        text=item.text,
                        language=item.language,
                    )
                    for item in context.dialogue
                ],
                canonical_visual_text=[
                    SnapshotVisualTextSpan(
                        span_id=item.id,
                        span_number=item.span_number,
                        start_us=item.start_us,
                        end_us=item.end_us,
                        text=item.text,
                        confidence=item.confidence,
                    )
                    for item in context.visual_text
                ],
            )
        )
    return episodes


def _build_content(inputs: P10Inputs) -> SourceVideoSnapshotContent:
    return SourceVideoSnapshotContent(
        frozen_artifacts=_frozen_refs(inputs),
        episodes=_snapshot_episodes(inputs),
        source_bible=inputs.p9.bible_content,
        source_shot_facts=inputs.p9.facts_content,
        source_characters=inputs.characters,
        source_speakers=inputs.speakers,
        source_scenes=inputs.scenes,
        source_props=inputs.props,
    )


def _source_chain_fingerprint(inputs: P10Inputs, content: SourceVideoSnapshotContent) -> str:
    skill = get_professional_skill(P10_PROFESSIONAL_SKILL_ID)
    return _sha(
        {
            "snapshot_contract": P10_SNAPSHOT_CONTRACT,
            "schema_version": P10_SCHEMA_VERSION,
            "source_truth_contract": P10_SOURCE_TRUTH_CONTRACT,
            "professional_skill": [skill.id, skill.version],
            "frozen_artifacts": [item.model_dump(mode="json") for item in content.frozen_artifacts],
            "episodes": [item.model_dump(mode="json") for item in content.episodes],
            "typed_content_hashes": {
                "source_bible": _sha(content.source_bible.model_dump(mode="json")),
                "source_shot_facts": _sha(content.source_shot_facts.model_dump(mode="json")),
                "source_characters": _sha(content.source_characters.model_dump(mode="json")),
                "source_speakers": _sha(content.source_speakers.model_dump(mode="json")),
                "source_scenes": _sha(content.source_scenes.model_dump(mode="json")),
                "source_props": _sha(content.source_props.model_dump(mode="json")),
            },
        }
    )


def _artifact_fingerprint(source_chain_fingerprint: str, previous: ArtifactNode | None) -> str:
    return _sha(
        {
            "source_chain_fingerprint": source_chain_fingerprint,
            "previous_snapshot": [previous.id, previous.input_fingerprint] if previous is not None else None,
        }
    )


def _build_provenance(
    inputs: P10Inputs,
    *,
    source_chain_fingerprint: str,
    previous: ArtifactNode | None,
) -> SourceVideoSnapshotProvenance:
    skill = get_professional_skill(P10_PROFESSIONAL_SKILL_ID)
    return SourceVideoSnapshotProvenance(
        professional_skill_version=skill.version,
        source_chain_fingerprint=source_chain_fingerprint,
        frozen_artifacts=_frozen_refs(inputs),
        episode_inputs=[
            SourceVideoSnapshotEpisodeProvenance(
                episode_id=context.episode.id,
                source_asset_id=context.asset.id,
                source_asset_sha256=context.asset.sha256,
                shot_boundary_set_id=context.shot_boundary.id,
                shot_boundary_fingerprint=context.shot_boundary.input_fingerprint,
                source_evidence_set_id=context.evidence_set.id,
                source_evidence_fingerprint=context.evidence_set.input_fingerprint,
            )
            for context in inputs.p9.contexts
        ],
        provider_jobs=[],
        supersedes_artifact_id=previous.id if previous is not None else None,
    )


def _assert_storage_ready(db: Session) -> None:
    if not inspect(db.get_bind()).has_table(SourceVideoSnapshotRevision.__tablename__):
        raise AppError(
            "P10_DATABASE_MIGRATION_REQUIRED",
            "P10 数据库迁移尚未应用，请先执行 alembic upgrade head",
            status_code=503,
        )


def _assert_inputs_still_current(db: Session, inputs: P10Inputs) -> None:
    for artifact_type in P10_REQUIRED_ARTIFACT_TYPES:
        current = _current_artifact(db, inputs.p9.source.project_id, artifact_type)
        expected = inputs.artifacts[artifact_type]
        if current is None or current.id != expected.id or current.input_fingerprint != expected.input_fingerprint:
            raise AppError("STALE_ARTIFACT_INPUT", "P10 输入 Artifact 在定稿前已变化，请重新执行", status_code=409)


def _publish_snapshot(
    db: Session,
    *,
    inputs: P10Inputs,
    content: SourceVideoSnapshotContent,
    source_chain_fingerprint: str,
    previous: ArtifactNode | None,
) -> ArtifactNode:
    _assert_inputs_still_current(db, inputs)
    project_id = inputs.p9.source.project_id
    project = get_project(db, project_id)
    current_snapshots = list(
        db.scalars(
            select(ArtifactNode).where(
                ArtifactNode.project_id == project_id,
                ArtifactNode.artifact_type == ArtifactType.SOURCE_VIDEO_SNAPSHOT.value,
                ArtifactNode.validity == ArtifactValidity.CURRENT,
                ArtifactNode.is_current.is_(True),
            )
        ).all()
    )
    if len(current_snapshots) > 1:
        raise AppError("P10_MULTIPLE_CURRENT_SNAPSHOTS", "检测到多个 CURRENT SOURCE_VIDEO_SNAPSHOT", status_code=409)

    latest_revision = db.scalar(
        select(func.max(ArtifactNode.revision)).where(
            ArtifactNode.project_id == project_id,
            ArtifactNode.artifact_type == ArtifactType.SOURCE_VIDEO_SNAPSHOT.value,
        )
    )
    skill = get_professional_skill(P10_PROFESSIONAL_SKILL_ID)
    provenance = _build_provenance(
        inputs,
        source_chain_fingerprint=source_chain_fingerprint,
        previous=previous,
    )
    artifact = ArtifactNode(
        project_id=project_id,
        artifact_type=ArtifactType.SOURCE_VIDEO_SNAPSHOT.value,
        namespace=expected_namespace(ArtifactType.SOURCE_VIDEO_SNAPSHOT),
        label="原片分析定稿",
        revision=(latest_revision or 0) + 1,
        input_fingerprint=_artifact_fingerprint(source_chain_fingerprint, previous),
        skill_id=skill.id,
        skill_version=skill.version,
        validity=ArtifactValidity.CURRENT,
        is_current=True,
        metadata_json={
            "schema_version": P10_SCHEMA_VERSION,
            "snapshot_contract": P10_SNAPSHOT_CONTRACT,
            "source_truth_contract": P10_SOURCE_TRUTH_CONTRACT,
            "publication_mode": P10_PUBLICATION_MODE,
            "source_chain_fingerprint": source_chain_fingerprint,
            "frozen_artifact_ids": [item.artifact_id for item in content.frozen_artifacts],
            "episode_count": len(content.episodes),
            "shot_count": sum(len(item.shot_anchors) for item in content.episodes),
            "dialogue_count": sum(len(item.canonical_dialogue) for item in content.episodes),
            "visual_text_count": sum(len(item.canonical_visual_text) for item in content.episodes),
            "character_count": len(content.source_characters.entities),
            "speaker_count": len(content.source_speakers.entities),
            "scene_count": len(content.source_scenes.entities),
            "prop_count": len(content.source_props.entities),
            "professional_skill_id": skill.id,
            "professional_skill_version": skill.version,
            "document_title": "原片分析定稿",
        },
    )
    db.add(artifact)
    db.flush()

    refs = {item.artifact_type: item for item in content.frozen_artifacts}
    row = SourceVideoSnapshotRevision(
        project_id=project_id,
        artifact_id=artifact.id,
        source_video_artifact_id=refs[ArtifactType.SOURCE_VIDEO].artifact_id,
        shot_anchors_artifact_id=refs[ArtifactType.SHOT_ANCHORS].artifact_id,
        source_dialogue_artifact_id=refs[ArtifactType.SOURCE_DIALOGUE].artifact_id,
        source_bible_artifact_id=refs[ArtifactType.SOURCE_BIBLE].artifact_id,
        story_skeleton_artifact_id=refs[ArtifactType.STORY_SKELETON].artifact_id,
        rhythm_skeleton_artifact_id=refs[ArtifactType.RHYTHM_SKELETON].artifact_id,
        source_shot_facts_artifact_id=refs[ArtifactType.SOURCE_SHOT_FACTS].artifact_id,
        source_characters_artifact_id=refs[ArtifactType.SOURCE_CHARACTERS].artifact_id,
        source_speakers_artifact_id=refs[ArtifactType.SOURCE_SPEAKERS].artifact_id,
        source_scenes_artifact_id=refs[ArtifactType.SOURCE_SCENES].artifact_id,
        source_props_artifact_id=refs[ArtifactType.SOURCE_PROPS].artifact_id,
        generated_by_task_id=None,
        schema_version=P10_SCHEMA_VERSION,
        content_json=content.model_dump(mode="json"),
        provenance_json=provenance.model_dump(mode="json"),
    )
    db.add(row)

    for artifact_type in P10_REQUIRED_ARTIFACT_TYPES:
        db.add(
            ArtifactEdge(
                project_id=project_id,
                source_node_id=inputs.artifacts[artifact_type].id,
                target_node_id=artifact.id,
                relation_type=_DEPENDENCY_RELATIONS[artifact_type],
            )
        )
    if previous is not None:
        db.add(
            ArtifactEdge(
                project_id=project_id,
                source_node_id=artifact.id,
                target_node_id=previous.id,
                relation_type=ArtifactRelationType.SUPERSEDES,
            )
        )

    if current_snapshots:
        _mark_stale_with_downstream(db, current_snapshots)
    _invalidate_project_plan(db, project)
    db.commit()
    db.refresh(artifact)
    return artifact


def finalize_source_video_snapshot(db: Session, project_id: str) -> SourceVideoSnapshotRead:
    _assert_storage_ready(db)
    inputs = _load_inputs(db, project_id)
    content = _build_content(inputs)
    source_chain_fingerprint = _source_chain_fingerprint(inputs, content)

    current = _current_artifact(db, project_id, ArtifactType.SOURCE_VIDEO_SNAPSHOT)
    if current is not None and current.metadata_json.get("source_chain_fingerprint") == source_chain_fingerprint:
        return get_source_video_snapshot(db, project_id)

    previous = _latest_artifact(db, project_id, ArtifactType.SOURCE_VIDEO_SNAPSHOT)
    try:
        _publish_snapshot(
            db,
            inputs=inputs,
            content=content,
            source_chain_fingerprint=source_chain_fingerprint,
            previous=previous,
        )
    except Exception:
        db.rollback()
        raise
    return get_source_video_snapshot(db, project_id)


def _snapshot_read(db: Session, project_id: str, artifact: ArtifactNode, *, current: bool) -> SourceVideoSnapshotRead:
    row = db.scalar(select(SourceVideoSnapshotRevision).where(SourceVideoSnapshotRevision.artifact_id == artifact.id))
    if row is None:
        raise AppError("SOURCE_VIDEO_SNAPSHOT_CONTENT_MISSING", "SOURCE_VIDEO_SNAPSHOT 缺少正式 typed revision", status_code=500)
    try:
        content = SourceVideoSnapshotContent.model_validate(row.content_json)
        provenance = SourceVideoSnapshotProvenance.model_validate(row.provenance_json)
    except Exception as exc:
        raise AppError("SOURCE_VIDEO_SNAPSHOT_CONTENT_INVALID", "SOURCE_VIDEO_SNAPSHOT typed content 无法解析", status_code=500) from exc
    return SourceVideoSnapshotRead(
        project_id=project_id,
        status=SourceVideoSnapshotResultStatus.CURRENT if current else SourceVideoSnapshotResultStatus.STALE,
        artifact_id=artifact.id,
        revision=artifact.revision,
        input_fingerprint=artifact.input_fingerprint,
        content=content,
        provenance=provenance,
    )


def get_source_video_snapshot(db: Session, project_id: str) -> SourceVideoSnapshotRead:
    get_project(db, project_id)
    current = _current_artifact(db, project_id, ArtifactType.SOURCE_VIDEO_SNAPSHOT)
    latest = current or _latest_artifact(db, project_id, ArtifactType.SOURCE_VIDEO_SNAPSHOT)
    if latest is None:
        return SourceVideoSnapshotRead(project_id=project_id, status=SourceVideoSnapshotResultStatus.NOT_BUILT)
    return _snapshot_read(db, project_id, latest, current=current is not None and latest.id == current.id)


def list_source_video_snapshot_revisions(db: Session, project_id: str) -> list[SourceVideoSnapshotRevisionSummary]:
    get_project(db, project_id)
    rows = list(
        db.scalars(
            select(ArtifactNode)
            .where(
                ArtifactNode.project_id == project_id,
                ArtifactNode.artifact_type == ArtifactType.SOURCE_VIDEO_SNAPSHOT.value,
            )
            .order_by(ArtifactNode.revision.desc())
        ).all()
    )
    result: list[SourceVideoSnapshotRevisionSummary] = []
    for artifact in rows:
        revision = db.scalar(select(SourceVideoSnapshotRevision).where(SourceVideoSnapshotRevision.artifact_id == artifact.id))
        if revision is None:
            raise AppError("SOURCE_VIDEO_SNAPSHOT_CONTENT_MISSING", "SOURCE_VIDEO_SNAPSHOT 历史 revision 内容缺失", status_code=500)
        provenance = SourceVideoSnapshotProvenance.model_validate(revision.provenance_json)
        result.append(
            SourceVideoSnapshotRevisionSummary(
                artifact_id=artifact.id,
                revision=artifact.revision,
                status=(
                    SourceVideoSnapshotResultStatus.CURRENT
                    if artifact.is_current and artifact.validity == ArtifactValidity.CURRENT
                    else SourceVideoSnapshotResultStatus.STALE
                ),
                input_fingerprint=artifact.input_fingerprint,
                source_chain_fingerprint=provenance.source_chain_fingerprint,
                created_at=artifact.created_at.isoformat(),
                supersedes_artifact_id=provenance.supersedes_artifact_id,
            )
        )
    return result
