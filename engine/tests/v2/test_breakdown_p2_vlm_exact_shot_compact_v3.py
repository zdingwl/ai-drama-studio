from scripts import run_breakdown_vlm_exact_shot_compact_v3 as compact


def batch() -> list[dict]:
    return [
        {"revision_item_id": "ITEM_1", "ordinal": 1, "frames": [{"path": "unused-a.jpg"}]},
        {"revision_item_id": "ITEM_2", "ordinal": 2, "frames": [{"path": "unused-b.jpg"}]},
    ]


def test_prompt_requires_salient_reconstruction_objects_in_props() -> None:
    prompt = compact._prompt(
        "zh-CN",
        batch(),
        [{"i": 1, "scene_ctx": []}, {"i": 2, "scene_ctx": []}],
    )
    assert "对镜头重建重要" in prompt
    assert "花束" in prompt
    assert "花瓶" in prompt
    assert "visible 明确写到了这类具体物体，props 不能漏掉" in prompt
    assert "subject_A" not in prompt
    assert "subject_B" not in prompt
    assert "ITEM_1" not in prompt


def test_non_interacted_props_are_preserved_without_subject_binding() -> None:
    value = {
        "shots": [
            {
                "i": 1,
                "scene": {"loc": "客厅", "ie": "INT", "tod": "白天"},
                "visible": "蓝色玫瑰花束置于玻璃花瓶中",
                "people": [],
                "props": [
                    {"label": "蓝色玫瑰花束", "importance": "HIGH", "people": [], "interaction": ""},
                    {"label": "玻璃花瓶", "importance": "HIGH", "people": [], "interaction": ""},
                ],
            },
            {
                "i": 2,
                "scene": {},
                "visible": "空走廊",
                "people": [],
                "props": [],
            },
        ]
    }
    result = compact.expand_compact(value, batch())
    first = result[0]["semantic"]
    assert first["subjects"] == []
    assert [item["label"] for item in first["props"]] == ["蓝色玫瑰花束", "玻璃花瓶"]
    assert all(item["subject_labels"] == [] for item in first["props"])
    assert first["shot"]["camera_motion_hint"] == "UNKNOWN"
