from __future__ import annotations

import pytest

from engine.app.source_drama_snapshot_contract_v1 import SourceDramaEpisodeSnapshotV1
from engine.app.source_story_skills_v1 import (
    SourceStorySkillError,
    compile_shot_facts_v1,
    compile_source_screenplay_v1,
)


def _snapshot() -> SourceDramaEpisodeSnapshotV1:
    return SourceDramaEpisodeSnapshotV1.model_validate({
        "schema_version": "source-drama-snapshot-v1",
        "status": "READY",
        "project_id": "PROJECT_1",
        "episode_id": "EP_1",
        "episode_title": "偷花",
        "episode_order": 1,
        "source_language": "zh-CN",
        "source_breakdown_run_id": "BREAKDOWN_1",
        "source_shot_revision_id": "SHOTREV_1",
        "source_asset_revision_id": "ASSETREV_1",
        "source_fingerprint": "a" * 64,
        "scene_count": 1,
        "shot_count": 2,
        "resolved_character_count": 1,
        "unresolved_person_count": 0,
        "source_dialogue_count": 1,
        "source_dialogue_projection_count": 2,
        "source_on_screen_text_count": 0,
        "warnings": [],
        "source_dialogue_utterances": [{
            "dialogue_group_id": "DIALOGUE_1",
            "start_us": 500_000,
            "end_us": 2_500_000,
            "source_text": "你凭什么说是我偷的花？",
            "source_language": "zh-CN",
            "speakers": ["PERSON_1"],
            "projection_count": 2,
            "projections": [
                {
                    "dialogue_key": "D1_SHOT1",
                    "shot_key": "SHOT_1",
                    "scene_key": "SCENE_1",
                    "projection_index": 1,
                    "start_us": 500_000,
                    "end_us": 1_500_000,
                    "source_text": "你凭什么说是我",
                },
                {
                    "dialogue_key": "D1_SHOT2",
                    "shot_key": "SHOT_2",
                    "scene_key": "SCENE_1",
                    "projection_index": 2,
                    "start_us": 1_500_000,
                    "end_us": 2_500_000,
                    "source_text": "偷的花？",
                },
            ],
        }],
        "scenes": [{
            "scene_key": "SCENE_1",
            "ordinal": 1,
            "start_us": 0,
            "end_us": 3_000_000,
            "duration_us": 3_000_000,
            "title": "院子",
            "story_summary": "两人在院子里围绕偷花一事发生争执。",
            "scene_info": {
                "location": "院子",
                "interior_exterior": "外景",
                "time_of_day": "白天",
                "environment": "住宅院落",
            },
            "final_scene": None,
            "people": [{
                "person_key": "PERSON_1",
                "scene_person_ref": "P1",
                "display_name": "人物1",
                "appearance": "成年女性",
                "character": {
                    "id": "CHAR_1",
                    "name": "女邻居",
                    "cover_url": None,
                },
            }],
            "shots": [
                {
                    "shot_key": "SHOT_1",
                    "ordinal": 1,
                    "source_shot_id": "SOURCE_SHOT_1",
                    "source_revision_item_id": "REV_ITEM_1",
                    "start_us": 0,
                    "end_us": 1_500_000,
                    "duration_us": 1_500_000,
                    "visual_description": "女邻居站在院子里看向画外人物。",
                    "people": ["PERSON_1"],
                    "performance": [{"text": "人物1转头看向对方。", "people": ["PERSON_1"]}],
                    "performance_details": {
                        "expression": "不满",
                        "posture": "站立",
                        "gaze": "看向对方",
                        "interaction": None,
                    },
                    "source_dialogue": [{
                        "dialogue_key": "D1_SHOT1",
                        "dialogue_group_id": "DIALOGUE_1",
                        "projection_index": 1,
                        "start_us": 500_000,
                        "end_us": 1_500_000,
                        "source_text": "你凭什么说是我",
                        "speakers": ["PERSON_1"],
                    }],
                    "observed_props": [],
                    "final_props": [],
                    "cinematography": {
                        "shot_type": "中景",
                        "camera_angle": "平视",
                        "composition": "人物居中",
                        "camera_motion": "固定",
                        "lighting": "自然光",
                    },
                    "source_on_screen_text": [],
                },
                {
                    "shot_key": "SHOT_2",
                    "ordinal": 2,
                    "source_shot_id": "SOURCE_SHOT_2",
                    "source_revision_item_id": "REV_ITEM_2",
                    "start_us": 1_500_000,
                    "end_us": 3_000_000,
                    "duration_us": 1_500_000,
                    "visual_description": "女邻居继续面向对方说话。",
                    "people": ["PERSON_1"],
                    "performance": [{"text": "人物1继续质问。", "people": ["PERSON_1"]}],
                    "performance_details": {
                        "expression": "愤怒",
                        "posture": "站立",
                        "gaze": "看向对方",
                        "interaction": None,
                    },
                    "source_dialogue": [{
                        "dialogue_key": "D1_SHOT2",
                        "dialogue_group_id": "DIALOGUE_1",
                        "projection_index": 2,
                        "start_us": 1_500_000,
                        "end_us": 2_500_000,
                        "source_text": "偷的花？",
                        "speakers": ["PERSON_1"],
                    }],
                    "observed_props": [],
                    "final_props": [],
                    "cinematography": {
                        "shot_type": "近景",
                        "camera_angle": "平视",
                        "composition": "人物居中",
                        "camera_motion": "固定",
                        "lighting": "自然光",
                    },
                    "source_on_screen_text": [],
                },
            ],
        }],
    })


def _understanding(_prompt: str) -> dict[str, object]:
    return {
        "episode_summary": "女邻居在院子里针对偷花指责进行反驳和质问。",
        "episode_summary_supporting_fact_refs": ["scene:SCENE_1", "utterance:DIALOGUE_1"],
        "scene_blocks": [{
            "block_id": "B01",
            "title": "偷花争执",
            "shot_keys": ["SHOT_1", "SHOT_2"],
            "summary": "人物围绕偷花一事发生争执。",
            "supporting_fact_refs": ["scene:SCENE_1", "utterance:DIALOGUE_1"],
            "confidence": 0.95,
        }],
        "story_beats": [{
            "beat_id": "BEAT01",
            "beat_type": "ESCALATION",
            "shot_keys": ["SHOT_1", "SHOT_2"],
            "description": "连续质问使冲突升级。",
            "supporting_fact_refs": ["shot:SHOT_1", "shot:SHOT_2", "utterance:DIALOGUE_1"],
            "confidence": 0.9,
        }],
        "information_flow": [{
            "claim": "观众听到人物否认偷花指责。",
            "supporting_fact_refs": ["utterance:DIALOGUE_1"],
            "confidence": 0.9,
        }],
        "emotion_curve": [{
            "claim": "人物的可见情绪从不满推进到愤怒。",
            "supporting_fact_refs": ["shot:SHOT_1", "shot:SHOT_2"],
            "confidence": 0.9,
        }],
        "shot_functions": [
            {
                "shot_key": "SHOT_1",
                "function": "SETUP",
                "reason": "建立人物面对对方进行质问的冲突状态。",
                "supporting_fact_refs": ["shot:SHOT_1", "utterance:DIALOGUE_1"],
                "confidence": 0.88,
            },
            {
                "shot_key": "SHOT_2",
                "function": "ESCALATION",
                "reason": "近景延续质问并加强愤怒反应。",
                "supporting_fact_refs": ["shot:SHOT_2", "utterance:DIALOGUE_1"],
                "confidence": 0.88,
            },
        ],
        "remake_invariants": [{
            "invariant_type": "CONFLICT",
            "description": "重做时保留人物对偷花指责的正面反驳和冲突升级功能。",
            "supporting_fact_refs": ["utterance:DIALOGUE_1", "shot:SHOT_1", "shot:SHOT_2"],
        }],
        "inferences": [],
        "unresolved": [],
    }


def test_shot_facts_keeps_one_canonical_utterance_and_two_projections() -> None:
    result = compile_shot_facts_v1(_snapshot())

    assert len(result.source_dialogue_utterances) == 1
    assert [ref for shot in result.shots for ref in shot.dialogue_projection_refs] == [
        "utterance:DIALOGUE_1",
        "utterance:DIALOGUE_1",
    ]
    assert result.shots[0].facts["actions"][0]["text"] == "人物1转头看向对方。"


def test_full_chain_reconstructs_complete_dialogue_exactly_once() -> None:
    result = compile_source_screenplay_v1(
        _snapshot(),
        episode_understanding_provider=_understanding,
    )

    dialogue = [row for scene in result.screenplay.scenes for row in scene.dialogue]
    assert len(dialogue) == 1
    assert dialogue[0].dialogue_group_id == "DIALOGUE_1"
    assert dialogue[0].text == "你凭什么说是我偷的花？"
    assert result.screenplay.screenplay_text.count("你凭什么说是我偷的花？") == 1
    assert "你凭什么说是我\n" not in result.screenplay.screenplay_text
    assert [item.id for item in result.skill_chain] == [
        "shot_facts",
        "episode_understanding",
        "screenplay_reconstruction",
    ]


def test_episode_understanding_prompt_is_source_only() -> None:
    captured: list[str] = []

    def provider(prompt: str) -> dict[str, object]:
        captured.append(prompt)
        return _understanding(prompt)

    compile_source_screenplay_v1(_snapshot(), episode_understanding_provider=provider)

    assert captured
    assert "你凭什么说是我偷的花？" in captured[0]
    assert "target_language" not in captured[0]
    assert "target_region" not in captured[0]
    assert "不做目标国家改编" in captured[0]


def test_episode_understanding_rejects_unknown_source_ref() -> None:
    def unsafe(prompt: str) -> dict[str, object]:
        payload = _understanding(prompt)
        payload["episode_summary_supporting_fact_refs"] = ["shot:DOES_NOT_EXIST"]
        return payload

    with pytest.raises(SourceStorySkillError, match="unknown episode summary refs"):
        compile_source_screenplay_v1(
            _snapshot(),
            episode_understanding_provider=unsafe,
        )


def test_same_source_and_same_model_result_are_fingerprint_stable() -> None:
    first = compile_source_screenplay_v1(
        _snapshot(),
        episode_understanding_provider=_understanding,
    )
    second = compile_source_screenplay_v1(
        _snapshot(),
        episode_understanding_provider=_understanding,
    )

    assert first.input_fingerprint == second.input_fingerprint
    assert first.output_fingerprint == second.output_fingerprint
