"""P8 speaker-candidate contract v2 runtime adapter.

The existing P8 service remains the single Task / ProviderJob / publication lifecycle. This module
versions the provider contract and replaces only the typed composition step so canonical P6 text can
carry a provisional CURRENT-P7 character candidate without entering P9 identity resolution.
"""

import json

from app.core.errors import AppError
from app.shot_breakdown import providers as _providers
from app.shot_breakdown.schemas import (
    BoundSubjectRef,
    CanonicalDialogueBinding,
    EpisodeShotBreakdownSemantic,
    SourceShotBindings,
    SourceShotFact,
    SourceShotFactsEpisode,
)


P8_PROMPT_VERSION = "p8-shot-breakdown-v2"
P8_SCHEMA_VERSION = "1.1"
P8_SOURCE_TRUTH_CONTRACT = "source-bible-shot-facts-v2"


def _prompt_v2(payload: _providers.EpisodeShotBreakdownInput) -> str:
    skill = _providers._professional_skill()
    skill_rules = "\n".join(f"{index}. {rule}" for index, rule in enumerate(skill.provider_rules, 1))
    bible_json = json.dumps(payload.source_bible_episode, ensure_ascii=False, separators=(",", ":"))
    shots_json = json.dumps(payload.shot_context, ensure_ascii=False, separators=(",", ":"))
    schema_json = json.dumps(_providers._response_schema(), ensure_ascii=False, separators=(",", ":"))
    return f"""你正在执行 AI Drama Studio Professional Skill：{skill.name}（{skill.id}@{skill.version}）。
任务是 P8《带 Source Bible 的逐镜精细拉片》，不是 P7 整集故事重写，也不是 P9 最终身份归一。

Professional Skill 执行规则：
{skill_rules}

Source Truth 权威层级：
1. 当前上传的完整 Episode 是视觉、表演与声音现场的最高层原片事实源；必须直接观看完整 Episode。
2. CURRENT P5 Shot Anchors 已由服务端给出；只能按 shot_number 分析，不能输出或修改 start/end/duration。
3. CURRENT P6 canonical dialogue/OCR 已由服务端给出；dialogue_annotations 只能标 delivery，不能输出 dialogue text 或重新听写。
4. CURRENT P7 SOURCE_BIBLE 是人物、关系、故事、场景、道具、Story/Rhythm 的整集全局知识；不得让每个 Shot 各猜一套故事。
5. character_ids / scene_ids / prop_ids 只能从 SOURCE_BIBLE 已存在的 candidate ID 中选择，不创建新 ID。
6. dialogue_speakers 必须对本 Episode 每条 canonical utterance 恰好输出一次；speaker_character_id 只能是 CURRENT SOURCE_BIBLE.characters 的 character_id，无法可靠判断时填 null。
7. speaker candidate 属于 canonical utterance，不属于 Shot；同一 utterance 跨多个 Shot 时服务端会把同一个 candidate 注入全部 overlap。
8. speaker_character_id 只是 P8 provisional candidate hint，不是 P9 最终 Speaker Truth；禁止声纹聚类、跨 Episode speaker identity、SourceSpeaker 物化或最终人物归一。
9. sound_effects / ambience 只写该 Shot 实际可听见的声音；无法可靠判断就留空。
10. 镜头语言无法可靠判断时明确写“无法可靠判断”，不得为了填满字段而猜测。
11. 必须对 shot_context 中每个 shot_number 恰好输出一次，不能漏镜、增镜、重复或重编号。
12. 每个 Shot 的 dialogue_annotations 必须与该 Shot canonical_dialogue_overlaps 的 utterance_number 集合完全一致。
13. 输出模型禁止额外字段；不得加入 shot 时间、dialogue text、speaker label、推理过程或解释。

Episode:
- episode_id: {payload.episode_id}
- episode_order: {payload.episode_order}
- source_filename: {payload.source_filename}
- duration_us: {payload.duration_us}
- source_language: {payload.source_language or 'unknown'}

CURRENT SOURCE_BIBLE（本 Episode 全局上下文）:
{bible_json}

CURRENT Shot Context（P5 权威边界 + 服务端计算的 P6 overlap；时间只用于观察定位，不得在输出中重写）:
{shots_json}

只输出一个符合下列 Schema 的 JSON object，不输出 Markdown、解释、思考过程或额外文本。
内容使用与原片相适应的自然中文表达。

Output JSON Schema:
{schema_json}
"""


# Version provider constants/prompt before importing the original service so its copied constants,
# fingerprint inputs and Provider profile are v2 from first load.
_providers.P8_PROMPT_VERSION = P8_PROMPT_VERSION
_providers.P8_SCHEMA_VERSION = P8_SCHEMA_VERSION
_providers.P8_SOURCE_TRUTH_CONTRACT = P8_SOURCE_TRUTH_CONTRACT
_providers._prompt = _prompt_v2

from app.shot_breakdown import service as _base  # noqa: E402

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
create_shot_breakdown_task = _base.create_shot_breakdown_task
get_shot_breakdown = _base.get_shot_breakdown
list_shot_breakdown_revisions = _base.list_shot_breakdown_revisions
run_p8_shot_breakdown_task = _base.run_p8_shot_breakdown_task
