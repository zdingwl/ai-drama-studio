import pytest

from scripts import run_breakdown_vlm_exact_shot_compact_v2 as compact


def batch() -> list[dict]:
    return [
        {"revision_item_id": "ITEM_10", "ordinal": 10, "frames": [{"path": "unused-a.jpg"}]},
        {"revision_item_id": "ITEM_11", "ordinal": 11, "frames": [{"path": "unused-b.jpg"}]},
    ]


def test_compact_exact_shot_expands_to_canonical_semantic() -> None:
    value = {
        "shots": [
            {
                "i": 1,
                "scene": {"loc": "公寓走廊", "ie": "INT", "tod": "白天"},
                "visible": "白衣长发女性站在走廊中，旁边有一部手机。",
                "shot_type": "中景",
                "camera": "静止",
                "composition": "人物居中",
                "people": [
                    {
                        "appearance": "黑色长发，白色露肩上衣",
                        "activity": "站立并看向前方",
                        "position": "中央",
                        "visibility": "FULL",
                    }
                ],
                "props": [
                    {
                        "label": "手机",
                        "importance": "MEDIUM",
                        "people": [1],
                        "interaction": "人物手持",
                    }
                ],
            },
            {
                "i": 2,
                "scene": {"loc": "公寓走廊", "ie": "INT", "tod": "白天"},
                "visible": "灰白卷发人物站在走廊内。",
                "shot_type": "近景",
                "camera": "UNKNOWN",
                "composition": "人物居中",
                "people": [
                    {
                        "appearance": "灰白卷发，橙色花卉衬衫",
                        "activity": "站立",
                        "position": "中央",
                        "visibility": "FULL",
                    }
                ],
                "props": [],
            },
        ]
    }

    result = compact.expand_compact(value, batch())

    assert [item["revision_item_id"] for item in result] == ["ITEM_10", "ITEM_11"]
    first = result[0]["semantic"]
    assert first["shot"]["summary"] == first["shot"]["visual_description"]
    assert first["shot"]["narrative_function_hint"] == ""
    assert first["scene"]["environment_description"] == ""
    assert first["subjects"][0]["label"] == "subject_A"
    assert first["subjects"][0]["speaking_state"] == "UNKNOWN"
    assert first["events"] == []
    assert first["props"][0]["subject_labels"] == ["subject_A"]
    assert first["props"][0]["narrative_reason"] == "人物手持"


def test_subject_order_generates_shot_local_labels_only() -> None:
    value = {
        "shots": [{
            "i": 1,
            "scene": {},
            "visible": "两个人站在画面中。",
            "people": [
                {"appearance": "白衣长发女性"},
                {"appearance": "灰白卷发人物"},
            ],
            "props": [{"label": "袋子", "people": [2]}],
        }, {
            "i": 2,
            "scene": {},
            "visible": "空走廊。",
            "people": [],
            "props": [],
        }]
    }

    result = compact.expand_compact(value, batch())
    subjects = result[0]["semantic"]["subjects"]
    assert [item["label"] for item in subjects] == ["subject_A", "subject_B"]
    assert result[0]["semantic"]["props"][0]["subject_labels"] == ["subject_B"]


@pytest.mark.parametrize(
    "shots",
    [
        [{"i": 1, "visible": "a"}],
        [{"i": 1, "visible": "a"}, {"i": 1, "visible": "b"}],
        [{"i": 1, "visible": "a"}, {"i": 3, "visible": "b"}],
    ],
)
def test_compact_exact_shot_requires_exact_local_index_coverage(shots: list[dict]) -> None:
    with pytest.raises(ValueError):
        compact.expand_compact({"shots": shots}, batch())


def test_prompt_uses_batch_local_index_and_not_frozen_ids_or_subject_labels() -> None:
    prompt = compact._prompt(
        "zh-CN",
        batch(),
        [{"i": 1, "scene_ctx": []}, {"i": 2, "scene_ctx": []}],
    )

    assert "ITEM_10" not in prompt
    assert "ITEM_11" not in prompt
    assert "subject_A" not in prompt
    assert "subject_B" not in prompt
    assert "ShotIndex" in prompt
    assert "people" in prompt
