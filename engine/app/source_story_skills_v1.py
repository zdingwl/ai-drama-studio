"""Runtime orchestration for source understanding -> source screenplay.

This module is deliberately side-effect free:
- it consumes the current SourceDramaSnapshot only;
- it never mutates Shot/Dialogue/Character/Scene source truth;
- it keeps model interpretation in a separate episode-understanding layer;
- screenplay reconstruction is a deterministic projection of source facts so one
  canonical SourceDialogueUtterance is emitted exactly once.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from engine.app.local_qwen_text_v1 import request_local_qwen_json
from engine.app.source_drama_snapshot_contract_v1 import SourceDramaEpisodeSnapshotV1
from engine.skills.registry import validate_runtime_skill_ref

SHOT_FACTS_SKILL = ("shot_facts", "1.0.0")
EPISODE_UNDERSTANDING_SKILL = ("episode_understanding", "1.0.0")
SCREENPLAY_RECONSTRUCTION_SKILL = ("screenplay_reconstruction", "1.0.0")
SOURCE_SCREENPLAY_COMPILATION_SCHEMA_VERSION = "source-screenplay-compilation-v1"

BeatType = Literal[
    "SETUP", "REVEAL", "SUSPICION", "ESCALATION", "REACTION",
    "REVERSAL", "PAYOFF", "HOOK", "TRANSITION", "OTHER",
]
ShotFunctionType = Literal[
    "SETUP", "CLUE", "CONCEAL", "REACTION", "ESCALATION", "PAUSE",
    "REVERSAL", "PAYOFF", "HOOK", "TRANSITION", "OTHER",
]
InvariantType = Literal[
    "CAUSALITY", "RELATIONSHIP", "INFORMATION_ORDER", "CONFLICT",
    "REVERSAL", "CLIMAX", "PAYOFF", "HOOK", "SHOT_FUNCTION", "OTHER",
]


class SourceStorySkillError(RuntimeError):
    """Raised when a derived source-story artifact cannot be safely produced."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeSkillRefV1(_StrictModel):
    id: str
    version: str


class ShotFactsShotV1(_StrictModel):
    shot_key: str
    scene_key: str
    ordinal: int = Field(ge=1)
    source_shot_id: str | None = None
    source_revision_item_id: str | None = None
    start_us: int = Field(ge=0)
    end_us: int = Field(ge=0)
    duration_us: int = Field(ge=0)
    facts: dict[str, Any]
    dialogue_projection_refs: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)


class ShotFactsEpisodeV1(_StrictModel):
    episode_revision: str
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    episode_id: str
    skill: RuntimeSkillRefV1
    shots: list[ShotFactsShotV1]
    source_dialogue_utterances: list[dict[str, Any]]


class SupportedInferenceV1(_StrictModel):
    claim: str = Field(min_length=1)
    supporting_fact_refs: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class StoryBlockV1(_StrictModel):
    block_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    shot_keys: list[str] = Field(min_length=1)
    summary: str = Field(min_length=1)
    supporting_fact_refs: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class StoryBeatV1(_StrictModel):
    beat_id: str = Field(min_length=1)
    beat_type: BeatType
    shot_keys: list[str] = Field(min_length=1)
    description: str = Field(min_length=1)
    supporting_fact_refs: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class ShotFunctionV1(_StrictModel):
    shot_key: str = Field(min_length=1)
    function: ShotFunctionType
    reason: str = Field(min_length=1)
    supporting_fact_refs: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class RemakeInvariantV1(_StrictModel):
    invariant_type: InvariantType
    description: str = Field(min_length=1)
    supporting_fact_refs: list[str] = Field(min_length=1)


class EpisodeUnderstandingCandidateV1(_StrictModel):
    episode_summary: str = Field(min_length=1)
    episode_summary_supporting_fact_refs: list[str] = Field(min_length=1)
    scene_blocks: list[StoryBlockV1] = Field(min_length=1)
    story_beats: list[StoryBeatV1] = Field(default_factory=list)
    information_flow: list[SupportedInferenceV1] = Field(default_factory=list)
    emotion_curve: list[SupportedInferenceV1] = Field(default_factory=list)
    shot_functions: list[ShotFunctionV1] = Field(default_factory=list)
    remake_invariants: list[RemakeInvariantV1] = Field(default_factory=list)
    inferences: list[SupportedInferenceV1] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)


class EpisodeUnderstandingV1(EpisodeUnderstandingCandidateV1):
    episode_revision: str
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    episode_id: str
    skill: RuntimeSkillRefV1


class ScreenplayActionV1(_StrictModel):
    text: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)


class ScreenplayDialogueV1(_StrictModel):
    dialogue_group_id: str = Field(min_length=1)
    speaker: str = Field(min_length=1)
    text: str = Field(min_length=1)
    start_us: int = Field(ge=0)
    end_us: int = Field(ge=0)
    source_refs: list[str] = Field(min_length=1)


class ScreenplaySceneV1(_StrictModel):
    scene_key: str = Field(min_length=1)
    heading: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)
    actions: list[ScreenplayActionV1] = Field(default_factory=list)
    dialogue: list[ScreenplayDialogueV1] = Field(default_factory=list)
    story_beat_refs: list[str] = Field(default_factory=list)


class ScreenplayReconstructionV1(_StrictModel):
    source_revision: str
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    episode_id: str
    skill: RuntimeSkillRefV1
    title: str = Field(min_length=1)
    status: Literal["READY", "READY_WITH_WARNINGS"]
    scenes: list[ScreenplaySceneV1]
    screenplay_text: str = Field(min_length=1)
    unresolved: list[str] = Field(default_factory=list)


class SourceScreenplayCompilationV1(_StrictModel):
    schema_version: Literal["source-screenplay-compilation-v1"] = SOURCE_SCREENPLAY_COMPILATION_SCHEMA_VERSION
    status: Literal["READY", "READY_WITH_WARNINGS"]
    episode_id: str
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    skill_chain: list[RuntimeSkillRefV1]
    shot_facts: ShotFactsEpisodeV1
    episode_understanding: EpisodeUnderstandingV1
    screenplay: ScreenplayReconstructionV1

    @model_validator(mode="after")
    def _same_source(self) -> "SourceScreenplayCompilationV1":
        if self.shot_facts.source_fingerprint != self.source_fingerprint:
            raise ValueError("shot_facts source_fingerprint mismatch")
        if self.episode_understanding.source_fingerprint != self.source_fingerprint:
            raise ValueError("episode_understanding source_fingerprint mismatch")
        if self.screenplay.source_fingerprint != self.source_fingerprint:
            raise ValueError("screenplay source_fingerprint mismatch")
        return self


def _skill_ref(skill: tuple[str, str]) -> RuntimeSkillRefV1:
    contract = validate_runtime_skill_ref(*skill, require_runtime_ready=True)
    return RuntimeSkillRefV1(id=contract.skill_id, version=contract.version)


def _model_dump(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return dict(value.model_dump(mode="json"))
    return dict(value)


def _character_payload(person: Any) -> dict[str, Any]:
    character = person.character
    return {
        "person_key": person.person_key,
        "display_name": person.display_name,
        "appearance": person.appearance,
        "character": (
            {"id": character.id, "name": character.name}
            if character is not None else None
        ),
    }


def compile_shot_facts_v1(
    snapshot_payload: Mapping[str, Any] | SourceDramaEpisodeSnapshotV1,
) -> ShotFactsEpisodeV1:
    """Project current SourceDramaSnapshot into the shot_facts runtime contract.

    No model is called here. The existing grounded Breakdown/ASR/OCR/asset pipeline already
    produced the source truth; calling another VLM would duplicate inference and risk drift.
    """

    skill = _skill_ref(SHOT_FACTS_SKILL)
    snapshot = (
        snapshot_payload
        if isinstance(snapshot_payload, SourceDramaEpisodeSnapshotV1)
        else SourceDramaEpisodeSnapshotV1.model_validate(snapshot_payload)
    )
    shots: list[ShotFactsShotV1] = []
    for scene in snapshot.scenes:
        people_by_key = {person.person_key: person for person in scene.people}
        scene_ref = f"scene:{scene.scene_key}"
        for shot in scene.shots:
            shot_ref = f"shot:{shot.shot_key}"
            details = _model_dump(shot.performance_details)
            cinema = _model_dump(shot.cinematography)
            subjects = [
                _character_payload(people_by_key[key])
                for key in shot.people
                if key in people_by_key
            ]
            actions = [item.model_dump(mode="json") for item in shot.performance]
            interactions: list[dict[str, Any]] = []
            if details.get("interaction"):
                interactions.append({"text": details["interaction"], "source": shot_ref})
            for prop in shot.observed_props:
                if prop.interaction:
                    interactions.append({
                        "text": prop.interaction,
                        "prop": prop.label,
                        "source": shot_ref,
                    })
            projection_refs = [
                f"utterance:{dialogue.dialogue_group_id}"
                for dialogue in shot.source_dialogue
            ]
            evidence = [shot_ref, scene_ref, *projection_refs]
            evidence.extend(
                f"character:{person.character.id}"
                for person in (people_by_key.get(key) for key in shot.people)
                if person is not None and person.character is not None
            )
            evidence.extend(f"prop:{prop.id}" for prop in shot.final_props)
            uncertainties: list[str] = []
            for key in shot.people:
                person = people_by_key.get(key)
                if person is not None and person.character is None:
                    uncertainties.append(f"{key}:formal-character-unresolved")
            for dialogue in shot.source_dialogue:
                if not dialogue.speakers:
                    uncertainties.append(
                        f"{dialogue.dialogue_group_id}:speaker-unresolved"
                    )
            facts = {
                "subjects": subjects,
                "actions": actions,
                "expressions": ([details["expression"]] if details.get("expression") else []),
                "interactions": interactions,
                "scene": {
                    **scene.scene_info.model_dump(mode="json"),
                    "title": scene.title,
                    "story_summary": scene.story_summary,
                    "final_scene": (
                        scene.final_scene.model_dump(mode="json")
                        if scene.final_scene is not None else None
                    ),
                },
                "props": {
                    "observed": [item.model_dump(mode="json") for item in shot.observed_props],
                    "final": [item.model_dump(mode="json") for item in shot.final_props],
                },
                "camera": {"angle": cinema.get("camera_angle")},
                "framing": {"shot_type": cinema.get("shot_type")},
                "composition": {"description": cinema.get("composition")},
                "motion": {"camera_motion": cinema.get("camera_motion")},
                "lighting": {"description": cinema.get("lighting")},
                "continuity": {},
                "visual_description": shot.visual_description,
                "on_screen_text": [item.model_dump(mode="json") for item in shot.source_on_screen_text],
            }
            shots.append(ShotFactsShotV1(
                shot_key=shot.shot_key,
                scene_key=scene.scene_key,
                ordinal=shot.ordinal,
                source_shot_id=shot.source_shot_id,
                source_revision_item_id=shot.source_revision_item_id,
                start_us=shot.start_us,
                end_us=shot.end_us,
                duration_us=shot.duration_us,
                facts=facts,
                dialogue_projection_refs=projection_refs,
                evidence=list(dict.fromkeys(evidence)),
                uncertainties=list(dict.fromkeys(uncertainties)),
            ))
    shots.sort(key=lambda item: (item.start_us, item.ordinal, item.shot_key))
    return ShotFactsEpisodeV1(
        episode_revision=snapshot.source_shot_revision_id,
        source_fingerprint=snapshot.source_fingerprint,
        episode_id=snapshot.episode_id,
        skill=skill,
        shots=shots,
        source_dialogue_utterances=[
            item.model_dump(mode="json")
            for item in sorted(snapshot.source_dialogue_utterances, key=lambda row: (row.start_us, row.dialogue_group_id))
        ],
    )


def _episode_fact_packet(
    snapshot: SourceDramaEpisodeSnapshotV1,
    shot_facts: ShotFactsEpisodeV1,
) -> tuple[dict[str, Any], set[str], list[str]]:
    fact_refs: set[str] = set()
    shot_keys = [shot.shot_key for shot in shot_facts.shots]
    scenes: list[dict[str, Any]] = []
    for scene in snapshot.scenes:
        scene_ref = f"scene:{scene.scene_key}"
        fact_refs.add(scene_ref)
        scene_shots: list[dict[str, Any]] = []
        for shot in (row for row in shot_facts.shots if row.scene_key == scene.scene_key):
            ref = f"shot:{shot.shot_key}"
            fact_refs.add(ref)
            scene_shots.append({
                "ref": ref,
                "shot_key": shot.shot_key,
                "ordinal": shot.ordinal,
                "visual_description": shot.facts.get("visual_description"),
                "actions": shot.facts.get("actions") or [],
                "expressions": shot.facts.get("expressions") or [],
                "interactions": shot.facts.get("interactions") or [],
                "props": shot.facts.get("props") or {},
            })
        scenes.append({
            "ref": scene_ref,
            "scene_key": scene.scene_key,
            "title": scene.title,
            "story_summary": scene.story_summary,
            "scene_info": scene.scene_info.model_dump(mode="json"),
            "shots": scene_shots,
        })
    utterances: list[dict[str, Any]] = []
    for utterance in snapshot.source_dialogue_utterances:
        ref = f"utterance:{utterance.dialogue_group_id}"
        fact_refs.add(ref)
        utterances.append({
            "ref": ref,
            "dialogue_group_id": utterance.dialogue_group_id,
            "start_us": utterance.start_us,
            "end_us": utterance.end_us,
            "source_text": utterance.source_text,
            "speakers": utterance.speakers,
            "shot_keys": [item.shot_key for item in utterance.projections],
        })
    return ({
        "episode_id": snapshot.episode_id,
        "source_language": snapshot.source_language,
        "scenes": scenes,
        "utterances": utterances,
    }, fact_refs, shot_keys)


def _episode_understanding_prompt(packet: Mapping[str, Any]) -> str:
    serialized = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"""你是短剧原片的“整集剧情结构编译器”。你没有视频访问权，只能使用 <SOURCE_FACTS> 中的当前正式原片事实。

目标：解释镜头/镜头组在整集中的剧情作用，为后续“原剧本还原”提供结构层。你输出的是 inference layer，不得改写 source truth。

硬规则：
1. 不新增输入中不存在的具体人物身份、关系、动作、事件、道具、地点、对白或结局。
2. 对白中的指责/声称不等于客观事实；不得把人物说法升级为已证实事件。
3. 所有 summary/beat/flow/emotion/function/invariant/inference 都必须引用 supporting_fact_refs；引用只允许使用输入里的 ref。
4. scene_blocks 必须按时间顺序覆盖输入的每个 shot_key，且每个 shot_key 恰好一次。
5. shot_functions 必须给每个 shot_key 恰好一项。
6. story beat 类型只能是 SETUP/REVEAL/SUSPICION/ESCALATION/REACTION/REVERSAL/PAYOFF/HOOK/TRANSITION/OTHER。
7. shot function 只能是 SETUP/CLUE/CONCEAL/REACTION/ESCALATION/PAUSE/REVERSAL/PAYOFF/HOOK/TRANSITION/OTHER。
8. remake invariant 类型只能是 CAUSALITY/RELATIONSHIP/INFORMATION_ORDER/CONFLICT/REVERSAL/CLIMAX/PAYOFF/HOOK/SHOT_FUNCTION/OTHER。
9. 不做目标国家改编，不翻译，不生成新对白。
10. 只输出一个 JSON object，不要 Markdown。

固定输出字段：
{{
  "episode_summary": "...",
  "episode_summary_supporting_fact_refs": ["scene:..."],
  "scene_blocks": [{{"block_id":"B01","title":"...","shot_keys":["..."],"summary":"...","supporting_fact_refs":["..."],"confidence":0.0}}],
  "story_beats": [{{"beat_id":"BEAT01","beat_type":"SETUP","shot_keys":["..."],"description":"...","supporting_fact_refs":["..."],"confidence":0.0}}],
  "information_flow": [{{"claim":"...","supporting_fact_refs":["..."],"confidence":0.0}}],
  "emotion_curve": [{{"claim":"...","supporting_fact_refs":["..."],"confidence":0.0}}],
  "shot_functions": [{{"shot_key":"...","function":"SETUP","reason":"...","supporting_fact_refs":["..."],"confidence":0.0}}],
  "remake_invariants": [{{"invariant_type":"CAUSALITY","description":"...","supporting_fact_refs":["..." ]}}],
  "inferences": [{{"claim":"...","supporting_fact_refs":["..."],"confidence":0.0}}],
  "unresolved": []
}}

<SOURCE_FACTS>{serialized}</SOURCE_FACTS>"""


def _validate_understanding_candidate(
    candidate: EpisodeUnderstandingCandidateV1,
    *,
    fact_refs: set[str],
    shot_keys: list[str],
) -> None:
    def check_refs(refs: list[str], label: str) -> None:
        unknown = sorted(set(refs) - fact_refs)
        if unknown:
            raise SourceStorySkillError(f"episode_understanding returned unknown {label} refs")

    check_refs(candidate.episode_summary_supporting_fact_refs, "episode summary")
    for block in candidate.scene_blocks:
        check_refs(block.supporting_fact_refs, f"block {block.block_id}")
    for beat in candidate.story_beats:
        check_refs(beat.supporting_fact_refs, f"beat {beat.beat_id}")
    for item in [*candidate.information_flow, *candidate.emotion_curve, *candidate.inferences]:
        check_refs(item.supporting_fact_refs, "inference")
    for item in candidate.shot_functions:
        check_refs(item.supporting_fact_refs, f"shot function {item.shot_key}")
    for item in candidate.remake_invariants:
        check_refs(item.supporting_fact_refs, "remake invariant")

    allowed_shots = set(shot_keys)
    block_shots = [key for block in candidate.scene_blocks for key in block.shot_keys]
    if block_shots != shot_keys:
        raise SourceStorySkillError("episode_understanding scene_blocks must cover every Shot exactly once in order")
    for beat in candidate.story_beats:
        if not set(beat.shot_keys).issubset(allowed_shots):
            raise SourceStorySkillError("episode_understanding story beat references an unknown Shot")
    function_shots = [item.shot_key for item in candidate.shot_functions]
    if function_shots != shot_keys:
        raise SourceStorySkillError("episode_understanding shot_functions must cover every Shot exactly once in order")


def compile_episode_understanding_v1(
    snapshot_payload: Mapping[str, Any] | SourceDramaEpisodeSnapshotV1,
    shot_facts: ShotFactsEpisodeV1,
    *,
    provider: Callable[[str], Mapping[str, Any]] | None = None,
) -> EpisodeUnderstandingV1:
    skill = _skill_ref(EPISODE_UNDERSTANDING_SKILL)
    snapshot = (
        snapshot_payload
        if isinstance(snapshot_payload, SourceDramaEpisodeSnapshotV1)
        else SourceDramaEpisodeSnapshotV1.model_validate(snapshot_payload)
    )
    if shot_facts.source_fingerprint != snapshot.source_fingerprint:
        raise SourceStorySkillError("shot_facts is stale for the current SourceDramaSnapshot")
    packet, fact_refs, shot_keys = _episode_fact_packet(snapshot, shot_facts)
    if not shot_keys:
        raise SourceStorySkillError("episode_understanding requires at least one current Shot")
    prompt = _episode_understanding_prompt(packet)
    raw = dict((provider or request_local_qwen_json)(prompt))
    try:
        candidate = EpisodeUnderstandingCandidateV1.model_validate(raw)
    except ValidationError as exc:
        raise SourceStorySkillError("episode_understanding returned an invalid contract") from exc
    _validate_understanding_candidate(candidate, fact_refs=fact_refs, shot_keys=shot_keys)
    return EpisodeUnderstandingV1(
        **candidate.model_dump(mode="json"),
        episode_revision=snapshot.source_shot_revision_id,
        source_fingerprint=snapshot.source_fingerprint,
        episode_id=snapshot.episode_id,
        skill=skill,
    )


def _scene_heading(scene: Any) -> str:
    info = scene.scene_info
    space = (info.interior_exterior or "").strip().lower()
    if "内" in space or "int" in space:
        prefix = "INT."
    elif "外" in space or "ext" in space:
        prefix = "EXT."
    else:
        prefix = "SCENE"
    place = (
        scene.final_scene.name
        if scene.final_scene is not None
        else (info.location or scene.title)
    )
    time_of_day = (info.time_of_day or "").strip()
    return f"{prefix} {place}" + (f" - {time_of_day}" if time_of_day else "")


def reconstruct_source_screenplay_v1(
    snapshot_payload: Mapping[str, Any] | SourceDramaEpisodeSnapshotV1,
    shot_facts: ShotFactsEpisodeV1,
    understanding: EpisodeUnderstandingV1,
) -> ScreenplayReconstructionV1:
    skill = _skill_ref(SCREENPLAY_RECONSTRUCTION_SKILL)
    snapshot = (
        snapshot_payload
        if isinstance(snapshot_payload, SourceDramaEpisodeSnapshotV1)
        else SourceDramaEpisodeSnapshotV1.model_validate(snapshot_payload)
    )
    if shot_facts.source_fingerprint != snapshot.source_fingerprint:
        raise SourceStorySkillError("shot_facts is stale for screenplay reconstruction")
    if understanding.source_fingerprint != snapshot.source_fingerprint:
        raise SourceStorySkillError("episode_understanding is stale for screenplay reconstruction")

    person_names: dict[str, str] = {}
    for scene in snapshot.scenes:
        for person in scene.people:
            name = person.character.name if person.character is not None else person.display_name
            person_names.setdefault(person.person_key, name)

    beats_by_scene: dict[str, list[str]] = {scene.scene_key: [] for scene in snapshot.scenes}
    shot_to_scene = {
        shot.shot_key: scene.scene_key
        for scene in snapshot.scenes
        for shot in scene.shots
    }
    for beat in understanding.story_beats:
        for scene_key in dict.fromkeys(
            shot_to_scene[key] for key in beat.shot_keys if key in shot_to_scene
        ):
            beats_by_scene.setdefault(scene_key, []).append(beat.beat_id)

    utterances_by_scene: dict[str, list[Any]] = {scene.scene_key: [] for scene in snapshot.scenes}
    unresolved: list[str] = []
    for utterance in snapshot.source_dialogue_utterances:
        first_scene = utterance.projections[0].scene_key
        utterances_by_scene.setdefault(first_scene, []).append(utterance)
        if not utterance.speakers:
            unresolved.append(f"{utterance.dialogue_group_id}:speaker-unresolved")

    fact_shots = {item.shot_key: item for item in shot_facts.shots}
    screenplay_scenes: list[ScreenplaySceneV1] = []
    text_lines = [snapshot.episode_title]
    emitted_dialogues: set[str] = set()
    for scene in snapshot.scenes:
        heading = _scene_heading(scene)
        actions: list[ScreenplayActionV1] = []
        timed_lines: list[tuple[int, int, str]] = []
        for shot in scene.shots:
            item = fact_shots.get(shot.shot_key)
            if item is None:
                raise SourceStorySkillError(f"shot_facts is missing current Shot {shot.shot_key}")
            texts: list[str] = []
            visual = str(item.facts.get("visual_description") or "").strip()
            if visual:
                texts.append(visual)
            for action in item.facts.get("actions") or []:
                if isinstance(action, Mapping):
                    text = str(action.get("text") or "").strip()
                else:
                    text = str(action or "").strip()
                if text and text not in texts:
                    texts.append(text)
            for text in texts:
                actions.append(ScreenplayActionV1(text=text, source_refs=[f"shot:{shot.shot_key}"]))
                timed_lines.append((shot.start_us, 0, text))

        dialogue_rows: list[ScreenplayDialogueV1] = []
        for utterance in sorted(utterances_by_scene.get(scene.scene_key, []), key=lambda row: (row.start_us, row.dialogue_group_id)):
            if utterance.dialogue_group_id in emitted_dialogues:
                raise SourceStorySkillError("canonical SourceDialogueUtterance would be emitted more than once")
            emitted_dialogues.add(utterance.dialogue_group_id)
            names = [person_names.get(key, key) for key in utterance.speakers]
            speaker = " / ".join(dict.fromkeys(names)) if names else "未确认说话人"
            refs = [f"utterance:{utterance.dialogue_group_id}"]
            refs.extend(f"shot:{projection.shot_key}" for projection in utterance.projections)
            row = ScreenplayDialogueV1(
                dialogue_group_id=utterance.dialogue_group_id,
                speaker=speaker,
                text=utterance.source_text,
                start_us=utterance.start_us,
                end_us=utterance.end_us,
                source_refs=list(dict.fromkeys(refs)),
            )
            dialogue_rows.append(row)
            timed_lines.append((utterance.start_us, 1, f"{speaker}：{utterance.source_text}"))

        screenplay_scenes.append(ScreenplaySceneV1(
            scene_key=scene.scene_key,
            heading=heading,
            source_refs=[f"scene:{scene.scene_key}"] + [f"shot:{shot.shot_key}" for shot in scene.shots],
            actions=actions,
            dialogue=dialogue_rows,
            story_beat_refs=list(dict.fromkeys(beats_by_scene.get(scene.scene_key, []))),
        ))
        text_lines.extend(["", heading])
        text_lines.extend(text for _time, _kind, text in sorted(timed_lines))

    expected_dialogues = {item.dialogue_group_id for item in snapshot.source_dialogue_utterances}
    if emitted_dialogues != expected_dialogues:
        raise SourceStorySkillError("screenplay did not emit every canonical SourceDialogueUtterance exactly once")

    unresolved.extend(understanding.unresolved)
    unresolved = list(dict.fromkeys(unresolved))
    status = "READY_WITH_WARNINGS" if (snapshot.warnings or unresolved) else "READY"
    return ScreenplayReconstructionV1(
        source_revision=snapshot.source_shot_revision_id,
        source_fingerprint=snapshot.source_fingerprint,
        episode_id=snapshot.episode_id,
        skill=skill,
        title=snapshot.episode_title,
        status=status,
        scenes=screenplay_scenes,
        screenplay_text="\n".join(text_lines).strip(),
        unresolved=unresolved,
    )


def compile_source_screenplay_v1(
    snapshot_payload: Mapping[str, Any] | SourceDramaEpisodeSnapshotV1,
    *,
    episode_understanding_provider: Callable[[str], Mapping[str, Any]] | None = None,
) -> SourceScreenplayCompilationV1:
    """Run the three pinned source Skills without mutating source truth."""

    snapshot = (
        snapshot_payload
        if isinstance(snapshot_payload, SourceDramaEpisodeSnapshotV1)
        else SourceDramaEpisodeSnapshotV1.model_validate(snapshot_payload)
    )
    shot_facts = compile_shot_facts_v1(snapshot)
    understanding = compile_episode_understanding_v1(
        snapshot,
        shot_facts,
        provider=episode_understanding_provider,
    )
    screenplay = reconstruct_source_screenplay_v1(snapshot, shot_facts, understanding)
    skill_chain = [shot_facts.skill, understanding.skill, screenplay.skill]
    input_material = {
        "source_fingerprint": snapshot.source_fingerprint,
        "skill_chain": [item.model_dump(mode="json") for item in skill_chain],
    }
    input_fingerprint = hashlib.sha256(
        json.dumps(input_material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    output_material = {
        "input_fingerprint": input_fingerprint,
        "shot_facts": shot_facts.model_dump(mode="json"),
        "episode_understanding": understanding.model_dump(mode="json"),
        "screenplay": screenplay.model_dump(mode="json"),
    }
    output_fingerprint = hashlib.sha256(
        json.dumps(output_material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    status = (
        "READY_WITH_WARNINGS"
        if snapshot.warnings or understanding.unresolved or screenplay.unresolved
        else "READY"
    )
    return SourceScreenplayCompilationV1(
        status=status,
        episode_id=snapshot.episode_id,
        source_fingerprint=snapshot.source_fingerprint,
        input_fingerprint=input_fingerprint,
        output_fingerprint=output_fingerprint,
        skill_chain=skill_chain,
        shot_facts=shot_facts,
        episode_understanding=understanding,
        screenplay=screenplay,
    )


__all__ = [
    "EPISODE_UNDERSTANDING_SKILL",
    "SCREENPLAY_RECONSTRUCTION_SKILL",
    "SHOT_FACTS_SKILL",
    "EpisodeUnderstandingV1",
    "ScreenplayReconstructionV1",
    "ShotFactsEpisodeV1",
    "SourceScreenplayCompilationV1",
    "SourceStorySkillError",
    "compile_episode_understanding_v1",
    "compile_shot_facts_v1",
    "compile_source_screenplay_v1",
    "reconstruct_source_screenplay_v1",
]
