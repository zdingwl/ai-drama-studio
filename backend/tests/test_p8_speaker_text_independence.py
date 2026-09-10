from types import SimpleNamespace

from app.shot_breakdown.schemas import EpisodeShotBreakdownSemantic
from app.shot_breakdown.service_v2 import _compose_episode_v2


def test_p8_identical_text_different_utterances_keep_independent_speaker_candidates() -> None:
    """Speaker belongs to a canonical utterance ID/number, never to the text string itself."""

    repeated_text = "你还真去报警啊"
    context = SimpleNamespace(
        episode=SimpleNamespace(id="episode-1", episode_order=1),
        asset=SimpleNamespace(original_filename="episode.mp4"),
        source_bible_episode=SimpleNamespace(
            characters=[SimpleNamespace(character_id="char-zhou", name="周宇")],
            scenes=[],
            key_props=[],
        ),
        shot_anchors=[
            SimpleNamespace(
                id="shot-1",
                shot_number=1,
                start_us=0,
                end_us=1_000_000,
                duration_us=1_000_000,
            )
        ],
        dialogue=[
            SimpleNamespace(
                id="utterance-real",
                utterance_number=1,
                start_us=100_000,
                end_us=450_000,
                text=repeated_text,
                language="zh",
            ),
            SimpleNamespace(
                id="utterance-other",
                utterance_number=2,
                start_us=500_000,
                end_us=850_000,
                text=repeated_text,
                language="zh",
            ),
        ],
        visual_text=[],
    )
    semantic = EpisodeShotBreakdownSemantic.model_validate(
        {
            "shots": [
                {
                    "shot_number": 1,
                    "visual_description": "人物在室内完成对话。",
                    "camera_language": {
                        "shot_size": "近景",
                        "composition": "居中",
                        "angle_or_type": "平视",
                        "movement": "固定镜头",
                        "focal_length_dof": "浅景深",
                    },
                    "bindings": {
                        "character_ids": [],
                        "scene_ids": [],
                        "prop_ids": [],
                        "unresolved_subject_notes": [],
                    },
                    "dialogue_annotations": [
                        {"utterance_number": 1, "delivery": "DIALOGUE"},
                        {"utterance_number": 2, "delivery": "DIALOGUE"},
                    ],
                    "sound_effects": [],
                    "ambience": [],
                }
            ],
            "dialogue_speakers": [
                {"utterance_number": 1, "speaker_character_id": "char-zhou"},
                {"utterance_number": 2, "speaker_character_id": None},
            ],
        }
    )

    result = _compose_episode_v2(context, semantic)
    dialogue = result.shots[0].dialogue

    assert [item.text for item in dialogue] == [repeated_text, repeated_text]
    assert dialogue[0].speaker is not None
    assert dialogue[0].speaker.id == "char-zhou"
    assert dialogue[0].speaker.label == "周宇"
    assert dialogue[1].speaker is None
