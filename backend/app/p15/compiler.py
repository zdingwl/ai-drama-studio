import math
import os
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artifacts.enums import ArtifactValidity
from app.artifacts.models import ArtifactNode
from app.core.errors import AppError
from app.p14.models import ReplicaTargetAudioRevision, ReplicaTimingPlanRevision
from app.p14.schemas import ReplicaTargetAudioContent, ReplicaTimingPlanContent, TimingFitStatus
from app.p15.schemas import (
    GenerationSegment,
    P15CandidateProvenance,
    ReplicaGenerationSegmentsContent,
    ReplicaStoryboardBundle,
    ReplicaTargetStoryboardContent,
    StoryboardDialogueRef,
    TargetStoryboardShot,
)
from app.skills.models import ArtifactType
from app.skills.professional import get_professional_skill
from app.source_snapshot.models import SourceVideoSnapshotRevision
from app.source_snapshot.schemas import SourceVideoSnapshotContent
from app.target_assets.models import ReplicaTargetAssetsRevision
from app.target_assets.schemas import ReplicaTargetAssetsContent, TargetAssetRef
from app.target_bible.models import ReplicaTargetRevision
from app.target_bible.schemas import ReplicaTargetBibleContent, TargetBibleArtifactKind
from app.target_script.models import ReplicaTargetScriptRevision
from app.target_script.schemas import ReplicaTargetScriptContent


@dataclass(frozen=True)
class P15Inputs:
    project_id: str
    target_language: str
    target_region: str
    source_snapshot_artifact: ArtifactNode
    source_snapshot: SourceVideoSnapshotContent
    target_bible_artifact: ArtifactNode
    target_bible: ReplicaTargetBibleContent
    target_script_artifact: ArtifactNode
    target_script: ReplicaTargetScriptContent
    target_assets_artifact: ArtifactNode
    target_assets: ReplicaTargetAssetsContent
    target_audio_artifact: ArtifactNode
    target_audio: ReplicaTargetAudioContent
    timing_plan_artifact: ArtifactNode
    timing_plan: ReplicaTimingPlanContent


def max_segment_duration_us() -> int:
    raw = os.getenv("AI_DRAMA_P15_GENERATION_SEGMENT_MAX_DURATION_SECONDS", "6.0")
    try:
        seconds = float(raw)
    except ValueError as exc:
        raise AppError("P15_CONFIG_INVALID", "P15 generation segment max duration 配置无效", status_code=500) from exc
    if not 0.5 <= seconds <= 30.0:
        raise AppError("P15_CONFIG_INVALID", "P15 generation segment max duration 必须在 0.5~30 秒", status_code=500)
    return int(round(seconds * 1_000_000))


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
        raise AppError("P15_INPUT_REQUIRED", f"P15 需要 CURRENT {artifact_type.value}", status_code=409)
    if len(rows) != 1:
        raise AppError("P15_INPUT_AMBIGUOUS", f"{artifact_type.value} 存在多个 CURRENT Artifact", status_code=409)
    return rows[0]


def _typed(db: Session, model, artifact_id: str, code: str):
    row = db.scalar(select(model).where(model.artifact_id == artifact_id))
    if row is None:
        raise AppError(code, "P15 硬输入缺少 typed revision", status_code=500)
    return row


def load_inputs(db: Session, project) -> P15Inputs:
    snapshot_artifact = _current(db, project.id, ArtifactType.SOURCE_VIDEO_SNAPSHOT)
    bible_artifact = _current(db, project.id, ArtifactType.TARGET_BIBLE)
    script_artifact = _current(db, project.id, ArtifactType.TARGET_SCRIPT)
    assets_artifact = _current(db, project.id, ArtifactType.TARGET_ASSETS)
    audio_artifact = _current(db, project.id, ArtifactType.TARGET_AUDIO)
    timing_artifact = _current(db, project.id, ArtifactType.TIMING_PLAN)

    snapshot_row = _typed(db, SourceVideoSnapshotRevision, snapshot_artifact.id, "P15_SOURCE_SNAPSHOT_CONTENT_MISSING")
    bible_row = _typed(db, ReplicaTargetRevision, bible_artifact.id, "P15_TARGET_BIBLE_CONTENT_MISSING")
    if bible_row.artifact_kind != TargetBibleArtifactKind.TARGET_BIBLE.value:
        raise AppError("P15_TARGET_BIBLE_CONTENT_INVALID", "CURRENT TARGET_BIBLE typed revision 类型错误", status_code=500)
    script_row = _typed(db, ReplicaTargetScriptRevision, script_artifact.id, "P15_TARGET_SCRIPT_CONTENT_MISSING")
    assets_row = _typed(db, ReplicaTargetAssetsRevision, assets_artifact.id, "P15_TARGET_ASSETS_CONTENT_MISSING")
    audio_row = _typed(db, ReplicaTargetAudioRevision, audio_artifact.id, "P15_TARGET_AUDIO_CONTENT_MISSING")
    timing_row = _typed(db, ReplicaTimingPlanRevision, timing_artifact.id, "P15_TIMING_CONTENT_MISSING")

    snapshot = SourceVideoSnapshotContent.model_validate(snapshot_row.content_json)
    bible = ReplicaTargetBibleContent.model_validate(bible_row.content_json)
    script = ReplicaTargetScriptContent.model_validate(script_row.content_json)
    assets = ReplicaTargetAssetsContent.model_validate(assets_row.content_json)
    audio = ReplicaTargetAudioContent.model_validate(audio_row.content_json)
    timing = ReplicaTimingPlanContent.model_validate(timing_row.content_json)

    if bible.source_snapshot_artifact_id != snapshot_artifact.id:
        raise AppError("P15_LINEAGE_MISMATCH", "TARGET_BIBLE 不属于 CURRENT SOURCE_VIDEO_SNAPSHOT", status_code=409)
    if (
        script.source_snapshot_artifact_id != snapshot_artifact.id
        or script.target_bible_artifact_id != bible_artifact.id
    ):
        raise AppError("P15_LINEAGE_MISMATCH", "TARGET_SCRIPT lineage 与 CURRENT Snapshot/Bible 不一致", status_code=409)
    if assets.target_bible_artifact_id != bible_artifact.id:
        raise AppError("P15_LINEAGE_MISMATCH", "TARGET_ASSETS 不属于 CURRENT TARGET_BIBLE", status_code=409)
    if audio.target_script_artifact_id != script_artifact.id or audio.target_bible_artifact_id != bible_artifact.id:
        raise AppError("P15_LINEAGE_MISMATCH", "TARGET_AUDIO lineage 与 CURRENT Script/Bible 不一致", status_code=409)
    if timing.target_script_artifact_id != script_artifact.id or timing.target_audio_artifact_id != audio_artifact.id:
        raise AppError("P15_LINEAGE_MISMATCH", "TIMING_PLAN lineage 与 CURRENT Script/Audio 不一致", status_code=409)
    if timing.has_overflow or any(item.fit_status == TimingFitStatus.OVERFLOW for item in timing.items):
        raise AppError("P15_TIMING_OVERFLOW", "P15 不能消费仍有 OVERFLOW 的 TIMING_PLAN", status_code=409)
    if bible.target_language != project.target_language or bible.target_region != project.target_region:
        raise AppError("P15_TARGET_CONFIG_MISMATCH", "Target Bible 与项目目标语言/地区不一致", status_code=409)

    return P15Inputs(
        project_id=project.id,
        target_language=project.target_language,
        target_region=project.target_region,
        source_snapshot_artifact=snapshot_artifact,
        source_snapshot=snapshot,
        target_bible_artifact=bible_artifact,
        target_bible=bible,
        target_script_artifact=script_artifact,
        target_script=script,
        target_assets_artifact=assets_artifact,
        target_assets=assets,
        target_audio_artifact=audio_artifact,
        target_audio=audio,
        timing_plan_artifact=timing_artifact,
        timing_plan=timing,
    )


def input_artifact_ids(inputs: P15Inputs) -> list[str]:
    return [
        inputs.source_snapshot_artifact.id,
        inputs.target_bible_artifact.id,
        inputs.target_script_artifact.id,
        inputs.target_assets_artifact.id,
        inputs.target_audio_artifact.id,
        inputs.timing_plan_artifact.id,
    ]


def _asset_ref(artifact_id: str, asset) -> TargetAssetRef:
    return TargetAssetRef(
        target_assets_artifact_id=artifact_id,
        target_asset_id=asset.target_asset_id,
        target_asset_revision=asset.target_asset_revision,
        asset_type=asset.asset_type,
        target_entity_id=asset.target_entity_id,
    )


def _nearest_h3_ratio(width: int, height: int) -> str:
    value = width / height
    options = {
        "21:9": 21 / 9,
        "16:9": 16 / 9,
        "4:3": 4 / 3,
        "1:1": 1.0,
        "3:4": 3 / 4,
        "9:16": 9 / 16,
    }
    return min(options, key=lambda key: abs(math.log(value / options[key])))


def compile_bundle(inputs: P15Inputs) -> ReplicaStoryboardBundle:
    char_map = {item.source_character_id: item for item in inputs.target_bible.characters}
    scene_map = {item.source_scene_id: item for item in inputs.target_bible.scenes}
    prop_map = {item.source_prop_id: item for item in inputs.target_bible.props}
    char_assets = {item.target_character_id: item for item in inputs.target_assets.characters}
    scene_assets = {item.target_scene_id: item for item in inputs.target_assets.scenes}
    prop_assets = {item.target_prop_id: item for item in inputs.target_assets.props}
    script_lines = {line.utterance_id: line for episode in inputs.target_script.episodes for line in episode.dialogue}
    audio_clips = {clip.utterance_id: clip for clip in inputs.target_audio.clips}
    timing_items = {item.utterance_id: item for item in inputs.timing_plan.items}

    if set(script_lines) != set(audio_clips) or set(script_lines) != set(timing_items):
        raise AppError("P15_DIALOGUE_COVERAGE_INVALID", "Script / Audio / Timing 必须精确覆盖同一 utterance 集合", status_code=409)

    max_us = max_segment_duration_us()
    storyboard_shots: list[TargetStoryboardShot] = []
    segments: list[GenerationSegment] = []
    episode_segment_counts: dict[str, int] = {}
    episode_media = {item.episode_id: item for item in inputs.source_snapshot.episodes}

    for episode in sorted(inputs.source_snapshot.source_shot_facts.episodes, key=lambda item: item.episode_order):
        for shot in sorted(episode.shots, key=lambda item: item.shot_number):
            target_characters = []
            target_scenes = []
            target_props = []
            refs: list[TargetAssetRef] = []
            continuity = list(inputs.target_bible.continuity_rules)
            negatives: list[str] = []
            target_description = shot.visual_description
            detail_parts = [f"Visual style: {inputs.target_assets.visual_style}"]

            for bound in shot.bindings.characters:
                target = char_map.get(bound.id)
                if target is None:
                    raise AppError("P15_CHARACTER_MAPPING_MISSING", "Source Character 缺少 Target 映射", status_code=409, details={"source_character_id": bound.id})
                asset = char_assets.get(target.target_character_id)
                if asset is None:
                    raise AppError("P15_CHARACTER_ASSET_MISSING", "Target Character 缺少 CURRENT 视觉资产", status_code=409, details={"target_character_id": target.target_character_id})
                target_characters.append(target.target_character_id)
                refs.append(_asset_ref(inputs.target_assets_artifact.id, asset))
                target_description = target_description.replace(bound.label, target.display_name)
                continuity.extend(target.continuity_rules)
                continuity.extend(asset.continuity_constraints)
                negatives.extend(asset.negative_constraints)
                detail_parts.append(f"Character {target.display_name}: {asset.identity_direction}; wardrobe {asset.wardrobe_baseline}")

            for bound in shot.bindings.scenes:
                target = scene_map.get(bound.id)
                if target is None:
                    raise AppError("P15_SCENE_MAPPING_MISSING", "Source Scene 缺少 Target 映射", status_code=409, details={"source_scene_id": bound.id})
                asset = scene_assets.get(target.target_scene_id)
                if asset is None:
                    raise AppError("P15_SCENE_ASSET_MISSING", "Target Scene 缺少 CURRENT 视觉资产", status_code=409, details={"target_scene_id": target.target_scene_id})
                target_scenes.append(target.target_scene_id)
                refs.append(_asset_ref(inputs.target_assets_artifact.id, asset))
                target_description = target_description.replace(bound.label, target.display_name)
                continuity.extend(target.continuity_rules)
                continuity.extend(asset.continuity_constraints)
                negatives.extend(asset.negative_constraints)
                detail_parts.append(f"Scene {target.display_name}: {asset.spatial_identity}; {asset.layout}; lighting {asset.lighting_baseline}")

            for bound in shot.bindings.props:
                target = prop_map.get(bound.id)
                if target is None:
                    raise AppError("P15_PROP_MAPPING_MISSING", "Source Prop 缺少 Target 映射", status_code=409, details={"source_prop_id": bound.id})
                asset = prop_assets.get(target.target_prop_id)
                if asset is None:
                    raise AppError("P15_PROP_ASSET_MISSING", "Target Prop 缺少 CURRENT 视觉资产", status_code=409, details={"target_prop_id": target.target_prop_id})
                target_props.append(target.target_prop_id)
                refs.append(_asset_ref(inputs.target_assets_artifact.id, asset))
                target_description = target_description.replace(bound.label, target.display_name)
                continuity.extend(target.continuity_rules)
                continuity.extend(asset.continuity_constraints)
                negatives.extend(asset.negative_constraints)
                detail_parts.append(f"Prop {target.display_name}: {asset.functional_identity}; {asset.visual_form}")

            dialogue_refs: list[StoryboardDialogueRef] = []
            for binding in shot.dialogue:
                line = script_lines.get(binding.utterance_id)
                clip = audio_clips.get(binding.utterance_id)
                timing = timing_items.get(binding.utterance_id)
                if line is None or clip is None or timing is None:
                    raise AppError("P15_DIALOGUE_LINEAGE_MISSING", "Shot dialogue 无法落到 CURRENT Script/Audio/Timing", status_code=409, details={"utterance_id": binding.utterance_id})
                dialogue_refs.append(
                    StoryboardDialogueRef(
                        utterance_id=line.utterance_id,
                        utterance_number=line.utterance_number,
                        delivery=binding.delivery,
                        target_character_id=line.target_character_id,
                        final_target_dialogue=line.final_target_dialogue,
                        target_audio_clip_id=clip.clip_id,
                        media_url=clip.media_url,
                        planned_speech_start_us=timing.planned_speech_start_us,
                        planned_speech_end_us=timing.planned_speech_end_us,
                    )
                )

            storyboard_shot_id = f"sb:{episode.episode_id}:{shot.shot_anchor_id}"
            target_visual_description = f"{target_description}\n" + "\n".join(detail_parts)
            storyboard = TargetStoryboardShot(
                storyboard_shot_id=storyboard_shot_id,
                episode_id=episode.episode_id,
                episode_order=episode.episode_order,
                source_shot_anchor_id=shot.shot_anchor_id,
                shot_number=shot.shot_number,
                start_us=shot.start_us,
                end_us=shot.end_us,
                duration_us=shot.duration_us,
                camera_language=shot.camera_language,
                source_visual_description=shot.visual_description,
                target_visual_description=target_visual_description,
                target_scene_ids=list(dict.fromkeys(target_scenes)),
                target_character_ids=list(dict.fromkeys(target_characters)),
                target_prop_ids=list(dict.fromkeys(target_props)),
                target_asset_refs=list({ref.target_asset_id: ref for ref in refs}.values()),
                dialogue_refs=dialogue_refs,
                continuity_constraints=list(dict.fromkeys(continuity)),
                negative_constraints=list(dict.fromkeys(negatives)),
                sound_effects=list(shot.sound_effects),
                ambience=list(shot.ambience),
            )
            storyboard_shots.append(storyboard)

            part_count = max(1, math.ceil(shot.duration_us / max_us))
            for part_index in range(part_count):
                start_us = shot.start_us + part_index * max_us
                end_us = min(shot.end_us, start_us + max_us)
                episode_segment_counts[episode.episode_id] = episode_segment_counts.get(episode.episode_id, 0) + 1
                segment_no = episode_segment_counts[episode.episode_id]
                media = episode_media.get(episode.episode_id)
                if media is None:
                    raise AppError("P15_EPISODE_MEDIA_MISSING", "Source Snapshot 缺少 Episode 媒体尺寸", status_code=409)
                output_ratio = _nearest_h3_ratio(media.width, media.height)
                overlapping_dialogue = [
                    item for item in dialogue_refs
                    if item.planned_speech_start_us < end_us and item.planned_speech_end_us > start_us
                ]
                dialogue_prompt = " ".join(
                    f"Dialogue {item.utterance_number} ({item.delivery.value}): {item.final_target_dialogue}"
                    for item in overlapping_dialogue
                )
                camera = storyboard.camera_language
                prompt = (
                    f"Replica shot {storyboard.shot_number}, continuation {part_index + 1}/{part_count}. "
                    f"Preserve source composition and action timing. {storyboard.target_visual_description}. "
                    f"Camera: shot size {camera.shot_size}; composition {camera.composition}; "
                    f"angle/type {camera.angle_or_type}; movement {camera.movement}; lens/DOF {camera.focal_length_dof}. "
                    f"{dialogue_prompt} Continuity: {'; '.join(storyboard.continuity_constraints)}"
                ).strip()
                segment = GenerationSegment(
                    generation_segment_id=f"seg:{episode.episode_id}:{segment_no:04d}",
                    episode_id=episode.episode_id,
                    episode_order=episode.episode_order,
                    segment_number=segment_no,
                    storyboard_shot_ids=[storyboard_shot_id],
                    start_us=start_us,
                    end_us=end_us,
                    duration_us=end_us - start_us,
                    output_ratio=output_ratio,
                    continuation_index=part_index + 1,
                    continuation_count=part_count,
                    generation_prompt=prompt,
                    negative_prompt="; ".join(storyboard.negative_constraints),
                    target_asset_refs=storyboard.target_asset_refs,
                    requires_lip_sync=any(item.delivery.value == "DIALOGUE" for item in overlapping_dialogue),
                )
                segments.append(segment)

    return ReplicaStoryboardBundle(
        storyboard=ReplicaTargetStoryboardContent(
            source_snapshot_artifact_id=inputs.source_snapshot_artifact.id,
            target_bible_artifact_id=inputs.target_bible_artifact.id,
            target_script_artifact_id=inputs.target_script_artifact.id,
            target_assets_artifact_id=inputs.target_assets_artifact.id,
            target_audio_artifact_id=inputs.target_audio_artifact.id,
            timing_plan_artifact_id=inputs.timing_plan_artifact.id,
            target_language=inputs.target_language,
            target_region=inputs.target_region,
            shots=storyboard_shots,
        ),
        generation_segments=ReplicaGenerationSegmentsContent(
            target_assets_artifact_id=inputs.target_assets_artifact.id,
            max_segment_duration_us=max_us,
            segments=segments,
        ),
    )


def provenance(inputs: P15Inputs, *, generation_sequence: int, task_id: str) -> P15CandidateProvenance:
    skill = get_professional_skill("storyboard-directing")
    return P15CandidateProvenance(
        source_snapshot_artifact_id=inputs.source_snapshot_artifact.id,
        source_snapshot_revision=inputs.source_snapshot_artifact.revision,
        source_snapshot_fingerprint=inputs.source_snapshot_artifact.input_fingerprint,
        target_bible_artifact_id=inputs.target_bible_artifact.id,
        target_bible_revision=inputs.target_bible_artifact.revision,
        target_bible_fingerprint=inputs.target_bible_artifact.input_fingerprint,
        target_script_artifact_id=inputs.target_script_artifact.id,
        target_script_revision=inputs.target_script_artifact.revision,
        target_script_fingerprint=inputs.target_script_artifact.input_fingerprint,
        target_assets_artifact_id=inputs.target_assets_artifact.id,
        target_assets_revision=inputs.target_assets_artifact.revision,
        target_assets_fingerprint=inputs.target_assets_artifact.input_fingerprint,
        target_audio_artifact_id=inputs.target_audio_artifact.id,
        target_audio_revision=inputs.target_audio_artifact.revision,
        target_audio_fingerprint=inputs.target_audio_artifact.input_fingerprint,
        timing_plan_artifact_id=inputs.timing_plan_artifact.id,
        timing_plan_revision=inputs.timing_plan_artifact.revision,
        timing_plan_fingerprint=inputs.timing_plan_artifact.input_fingerprint,
        generation_sequence=generation_sequence,
        professional_skill_version=skill.version,
        generated_by_task_id=task_id,
    )
