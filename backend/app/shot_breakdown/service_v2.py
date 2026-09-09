"""P8 speaker-candidate contract v2 service adapter.

The original P8 service remains the single Task / ProviderJob / publication lifecycle. Provider
constants and Prompt are natively v2 in ``providers.py``. This adapter replaces only the typed
composition step so P6 canonical text can carry a provisional CURRENT-P7 character candidate,
and lets an explicit new P8 command retry the same failed business task without bypassing the
unified Task retry guardrails.
"""

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.shot_breakdown import service as _base
from app.shot_breakdown.providers import (
    P8_PROMPT_VERSION,
    P8_SCHEMA_VERSION,
    P8_SOURCE_TRUTH_CONTRACT,
)
from app.shot_breakdown.schemas import (
    BoundSubjectRef,
    CanonicalDialogueBinding,
    EpisodeShotBreakdownSemantic,
    SourceShotBindings,
    SourceShotFact,
    SourceShotFactsEpisode,
)
from app.workflow.models import TaskStatus
from app.workflow.task_service import retry_task


# The base service imports these constants by value. Keep its fingerprint/publication contract
# explicitly pinned to the v2 values used by providers.py.
_base.P8_PROMPT_VERSION = P8_PROMPT_VERSION
_base.P8_SCHEMA_VERSION = P8_SCHEMA_VERSION
_base.P8_SOURCE_TRUTH_CONTRACT = P8_SOURCE_TRUTH_CONTRACT


def _compose_episode_v2(
    context: _base.EpisodeContext,
    semantic: EpisodeShotBreakdownSemantic,
) -> SourceShotFactsEpisode:
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
    character_map, scene_map, prop_map = _base._candidate_maps(context.source_bible_episode)
    utterance_by_number = {item.utterance_number: item for item in context.dialogue}
    if len(utterance_by_number) != len(context.dialogue):
        raise AppError("SOURCE_DIALOGUE_NUMBER_DUPLICATED", "P6 canonical utterance_number 重复", status_code=409)

    # Speaker is an Episode-level property of the canonical P6 utterance. The Provider returns one
    # candidate per utterance; the server maps only CURRENT P7 candidate IDs to user-readable labels.
    speaker_by_utterance = {
        item.utterance_number: item.speaker_character_id
        for item in semantic.dialogue_speakers
    }
    expected_utterance_numbers = set(utterance_by_number)
    if set(speaker_by_utterance) != expected_utterance_numbers:
        raise AppError(
            "P8_SPEAKER_CANDIDATE_SET_INVALID",
            "P8 dialogue_speakers 必须对本 Episode 每条 canonical utterance 恰好输出一次，且不能增删 utterance",
            status_code=422,
            details={
                "expected": sorted(expected_utterance_numbers),
                "actual": sorted(speaker_by_utterance),
            },
        )
    invalid_speakers = sorted(
        {
            speaker_id
            for speaker_id in speaker_by_utterance.values()
            if speaker_id is not None and speaker_id not in character_map
        }
    )
    if invalid_speakers:
        raise AppError(
            "P8_SPEAKER_CANDIDATE_INVALID",
            "P8 speaker candidate 引用了 CURRENT SOURCE_BIBLE 不存在的人物 candidate ID",
            status_code=422,
            details={"candidate_ids": invalid_speakers},
        )

    shots: list[SourceShotFact] = []
    for anchor in context.shot_anchors:
        item = semantic_by_number[anchor.shot_number]
        expected_utterances = [
            utterance
            for utterance in context.dialogue
            if _base._overlap(anchor.start_us, anchor.end_us, utterance.start_us, utterance.end_us) is not None
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
            overlap = _base._overlap(anchor.start_us, anchor.end_us, utterance.start_us, utterance.end_us)
            assert overlap is not None
            speaker_id = speaker_by_utterance[utterance.utterance_number]
            speaker = None if speaker_id is None else BoundSubjectRef(id=speaker_id, label=character_map[speaker_id])
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
                    speaker=speaker,
                )
            )

        visual_text_ids = [
            span.id
            for span in context.visual_text
            if _base._overlap(anchor.start_us, anchor.end_us, span.start_us, span.end_us) is not None
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
                    characters=_base._bound_refs("character", item.bindings.character_ids, character_map),
                    scenes=_base._bound_refs("scene", item.bindings.scene_ids, scene_map),
                    props=_base._bound_refs("prop", item.bindings.prop_ids, prop_map),
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


# Reuse the original lifecycle and replace only typed composition.
_base._compose_episode = _compose_episode_v2
P8_TASK_TYPE = _base.P8_TASK_TYPE


def create_shot_breakdown_task(db: Session, *, project_id: str, idempotency_key: str):
    """Create P8 work or explicitly retry the identical failed business task.

    The global Task table intentionally has one business_key per project/input. A new explicit P8
    command therefore cannot create a second row for exactly the same failed inputs. If the caller
    supplies a new Idempotency-Key, route the existing FAILED row through the standard retry guard
    instead. Same-key replay remains idempotent and does not consume another attempt.
    """

    task = _base.create_shot_breakdown_task(db, project_id=project_id, idempotency_key=idempotency_key)
    if task.status == TaskStatus.FAILED and task.idempotency_key != idempotency_key.strip():
        return retry_task(db, project_id, task.id)
    return task


get_shot_breakdown = _base.get_shot_breakdown
list_shot_breakdown_revisions = _base.list_shot_breakdown_revisions
run_p8_shot_breakdown_task = _base.run_p8_shot_breakdown_task
