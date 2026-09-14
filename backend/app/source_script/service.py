import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artifacts.enums import ArtifactNamespace, ArtifactRelationType, ArtifactValidity
from app.artifacts.models import ArtifactNode
from app.artifacts.service import create_artifact, create_artifact_relation, invalidate_current_artifact_type
from app.core.errors import AppError
from app.evidence.models import SourceDialogueUtterance
from app.skills.models import ArtifactType
from app.source_script.models import SourceScriptRevision
from app.source_script.schemas import (
    SOURCE_SCRIPT_CONTRACT,
    SOURCE_SCRIPT_SCHEMA_VERSION,
    SourceScriptArtifactRead,
    SourceScriptCharacter,
    SourceScriptContent,
    SourceScriptDialogueLine,
    SourceScriptEpisode,
    SourceScriptProp,
    SourceScriptProvenance,
    SourceScriptResultStatus,
    SourceScriptSceneIdentity,
    SourceScriptStorySegment,
)
from app.understanding.models import SourceBibleRevision
from app.understanding.schemas import SourceBibleContent, SourceBibleProvenance


SOURCE_SCRIPT_SKILL_ID = "source-script-projection"
SOURCE_SCRIPT_SKILL_VERSION = "1.0.0"


def _sha(payload: object) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _current(db: Session, project_id: str, artifact_type: ArtifactType) -> ArtifactNode | None:
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
        raise AppError("SOURCE_SCRIPT_CURRENT_AMBIGUOUS", f"{artifact_type.value} 存在多个 CURRENT Artifact", status_code=409)
    return rows[0] if rows else None


def _latest(db: Session, project_id: str) -> ArtifactNode | None:
    return db.scalar(
        select(ArtifactNode)
        .where(ArtifactNode.project_id == project_id, ArtifactNode.artifact_type == ArtifactType.SOURCE_SCRIPT.value)
        .order_by(ArtifactNode.revision.desc(), ArtifactNode.created_at.desc())
        .limit(1)
    )


def _inputs(db: Session, project_id: str) -> tuple[ArtifactNode, ArtifactNode, ArtifactNode, SourceBibleContent, SourceBibleProvenance]:
    source = _current(db, project_id, ArtifactType.SOURCE_VIDEO)
    dialogue = _current(db, project_id, ArtifactType.SOURCE_DIALOGUE)
    bible = _current(db, project_id, ArtifactType.SOURCE_BIBLE)
    if source is None or dialogue is None or bible is None:
        raise AppError("SOURCE_SCRIPT_INPUTS_REQUIRED", "生成原片剧本需要 CURRENT SOURCE_VIDEO + SOURCE_DIALOGUE + SOURCE_BIBLE", status_code=409)
    row = db.scalar(select(SourceBibleRevision).where(SourceBibleRevision.artifact_id == bible.id))
    if row is None:
        raise AppError("SOURCE_SCRIPT_BIBLE_CONTENT_MISSING", "CURRENT SOURCE_BIBLE 缺少 typed revision", status_code=500)
    content = SourceBibleContent.model_validate(row.content_json)
    provenance = SourceBibleProvenance.model_validate(row.provenance_json)
    if provenance.source_video_artifact_id != source.id or provenance.source_dialogue_artifact_id != dialogue.id:
        raise AppError("SOURCE_SCRIPT_LINEAGE_MISMATCH", "CURRENT SOURCE_BIBLE 与 CURRENT Source Video / Dialogue lineage 不一致", status_code=409)
    return source, dialogue, bible, content, provenance


def _compose_content(db: Session, bible: SourceBibleContent, provenance: SourceBibleProvenance) -> SourceScriptContent:
    evidence_by_episode = {item.episode_id: item.source_evidence_set_id for item in provenance.episode_evidence_sets}
    episodes: list[SourceScriptEpisode] = []
    for episode in sorted(bible.episodes, key=lambda item: item.material_baseline.episode_order):
        episode_id = episode.material_baseline.episode_id
        evidence_set_id = evidence_by_episode.get(episode_id)
        if not evidence_set_id:
            raise AppError("SOURCE_SCRIPT_EVIDENCE_MISSING", "SOURCE_BIBLE 缺少 Episode canonical dialogue lineage", status_code=409, details={"episode_id": episode_id})
        dialogue_rows = list(
            db.scalars(
                select(SourceDialogueUtterance)
                .where(SourceDialogueUtterance.source_evidence_set_id == evidence_set_id)
                .order_by(SourceDialogueUtterance.utterance_number.asc())
            ).all()
        )
        dialogue_ids = {item.id for item in dialogue_rows}
        attribution_by_utterance = {item.utterance_id: item for item in episode.dialogue_attributions}
        character_names = {item.character_id: item.name for item in episode.characters}
        segments = [
            SourceScriptStorySegment(
                segment_number=item.segment_number,
                time_range=item.time_range,
                visual_description=item.visual_description,
                story_summary=item.story_summary,
                narrative_function=item.narrative_function,
                dialogue_utterance_ids=[value for value in item.dialogue_evidence_ids if value in dialogue_ids],
            )
            for item in episode.timed_script
        ]
        episodes.append(
            SourceScriptEpisode(
                episode_id=episode_id,
                episode_order=episode.material_baseline.episode_order,
                source_filename=episode.material_baseline.source_filename,
                duration_us=episode.material_baseline.media_duration_us,
                story_summary=episode.overall_analysis.story_summary,
                story_background=episode.overall_analysis.story_background,
                narrative_structure=episode.overall_analysis.narrative_structure,
                dialogue=[
                    SourceScriptDialogueLine(
                        utterance_id=item.id,
                        utterance_number=item.utterance_number,
                        start_us=item.start_us,
                        end_us=item.end_us,
                        text=item.text,
                        language=item.language,
                        source_character_id=(attribution_by_utterance.get(item.id).source_character_id if attribution_by_utterance.get(item.id) is not None else None),
                        speaker_name=(
                            character_names.get(attribution_by_utterance[item.id].source_character_id or "")
                            if item.id in attribution_by_utterance
                            else None
                        ) or (attribution_by_utterance[item.id].speaker_label if item.id in attribution_by_utterance else "说话人待确认"),
                    )
                    for item in dialogue_rows
                ],
                story_segments=segments,
                characters=[
                    SourceScriptCharacter(
                        source_character_id=item.character_id,
                        name=item.name,
                        story_function=item.story_function,
                        appearance_baseline=item.appearance_baseline,
                    )
                    for item in episode.characters
                ],
                scenes=[
                    SourceScriptSceneIdentity(
                        source_scene_id=item.scene_id,
                        name=item.name,
                        time_ranges=item.time_ranges,
                        spatial_relationship=item.spatial_relationship,
                        environment_details=item.environment_details,
                    )
                    for item in episode.scenes
                ],
                props=[
                    SourceScriptProp(
                        source_prop_id=item.prop_id,
                        name=item.name,
                        time_ranges=item.time_ranges,
                        appearance_state=item.appearance_state,
                        story_function=item.story_function,
                    )
                    for item in episode.key_props
                ],
                story_skeleton=episode.story_skeleton,
                rhythm_skeleton=episode.rhythm_skeleton,
            )
        )
    return SourceScriptContent(episodes=episodes)


def publish_source_script(db: Session, project_id: str, *, generated_by_task_id: str | None = None) -> SourceScriptArtifactRead:
    source, dialogue, bible, bible_content, bible_provenance = _inputs(db, project_id)
    fingerprint = _sha(
        {
            "contract": SOURCE_SCRIPT_CONTRACT,
            "source_video": [source.id, source.input_fingerprint],
            "source_dialogue": [dialogue.id, dialogue.input_fingerprint],
            "source_bible": [bible.id, bible.input_fingerprint],
        }
    )
    current = _current(db, project_id, ArtifactType.SOURCE_SCRIPT)
    if current is not None and current.input_fingerprint == fingerprint:
        return get_source_script_artifact(db, project_id)
    previous = current or _latest(db, project_id)
    content = _compose_content(db, bible_content, bible_provenance)
    artifact = create_artifact(
        db,
        project_id=project_id,
        artifact_type=ArtifactType.SOURCE_SCRIPT,
        namespace=ArtifactNamespace.SOURCE,
        label="原片剧本",
        input_fingerprint=fingerprint,
        skill_id=SOURCE_SCRIPT_SKILL_ID,
        skill_version=SOURCE_SCRIPT_SKILL_VERSION,
        metadata_json={
            "schema_version": SOURCE_SCRIPT_SCHEMA_VERSION,
            "contract": SOURCE_SCRIPT_CONTRACT,
            "source_video_artifact_id": source.id,
            "source_dialogue_artifact_id": dialogue.id,
            "source_bible_artifact_id": bible.id,
            "episode_count": len(content.episodes),
            "dialogue_count": sum(len(item.dialogue) for item in content.episodes),
        },
    )
    provenance = SourceScriptProvenance(
        source_video_artifact_id=source.id,
        source_video_revision=source.revision,
        source_video_fingerprint=source.input_fingerprint,
        source_dialogue_artifact_id=dialogue.id,
        source_dialogue_revision=dialogue.revision,
        source_dialogue_fingerprint=dialogue.input_fingerprint,
        source_bible_artifact_id=bible.id,
        source_bible_revision=bible.revision,
        source_bible_fingerprint=bible.input_fingerprint,
        generated_by_task_id=generated_by_task_id,
        supersedes_artifact_id=previous.id if previous is not None else None,
    )
    try:
        db.add(
            SourceScriptRevision(
                project_id=project_id,
                artifact_id=artifact.id,
                source_video_artifact_id=source.id,
                source_dialogue_artifact_id=dialogue.id,
                source_bible_artifact_id=bible.id,
                generated_by_task_id=generated_by_task_id,
                schema_version=SOURCE_SCRIPT_SCHEMA_VERSION,
                content_json=content.model_dump(mode="json"),
                provenance_json=provenance.model_dump(mode="json"),
            )
        )
        db.commit()
        for parent in (source, dialogue, bible):
            create_artifact_relation(
                db,
                project_id=project_id,
                source_node_id=parent.id,
                target_node_id=artifact.id,
                relation_type=ArtifactRelationType.DERIVED_FROM,
            )
        if previous is not None and previous.id != artifact.id:
            create_artifact_relation(
                db,
                project_id=project_id,
                source_node_id=artifact.id,
                target_node_id=previous.id,
                relation_type=ArtifactRelationType.SUPERSEDES,
            )
    except Exception:
        invalidate_current_artifact_type(db, project_id=project_id, artifact_type=ArtifactType.SOURCE_SCRIPT)
        raise
    return get_source_script_artifact(db, project_id)


def get_source_script_artifact(db: Session, project_id: str) -> SourceScriptArtifactRead:
    current = _current(db, project_id, ArtifactType.SOURCE_SCRIPT)
    latest = current or _latest(db, project_id)
    if latest is None:
        return SourceScriptArtifactRead(project_id=project_id, status=SourceScriptResultStatus.NOT_BUILT)
    row = db.scalar(select(SourceScriptRevision).where(SourceScriptRevision.artifact_id == latest.id))
    if row is None:
        raise AppError("SOURCE_SCRIPT_CONTENT_MISSING", "SOURCE_SCRIPT 缺少 typed revision", status_code=500)
    return SourceScriptArtifactRead(
        project_id=project_id,
        status=SourceScriptResultStatus.CURRENT if current is not None else SourceScriptResultStatus.STALE,
        artifact_id=latest.id,
        revision=latest.revision,
        input_fingerprint=latest.input_fingerprint,
        content=SourceScriptContent.model_validate(row.content_json),
        provenance=SourceScriptProvenance.model_validate(row.provenance_json),
    )
