from scripts import run_breakdown_vlm_exact_shot_compact_v3 as compact


def batch() -> list[dict]:
    return [
        {"revision_item_id": "ITEM_1", "ordinal": 1, "frames": [{"path": "unused-a.jpg"}]},
        {"revision_item_id": "ITEM_2", "ordinal": 2, "frames": [{"path": "unused-b.jpg"}]},
    ]


def test_prompt_requires_salient_reconstruction_objects_and_h3_facts() -> None:
    prompt = compact._prompt(
        "zh-CN",
        batch(),
        [{"i": 1, "scene_ctx": []}, {"i": 2, "scene_ctx": []}],
    )
    assert "对镜头重建重要" in prompt
    assert "花束" in prompt
    assert "花瓶" in prompt
    assert "visible 明确写到了这类具体物体，props 不能漏掉" in prompt
    assert '"angle"' in prompt
    assert '"lighting"' in prompt
    assert '"continuity"' in prompt
    assert '"expression"' in prompt
    assert '"posture"' in prompt
    assert '"gaze"' in prompt
    assert '"interaction"' in prompt
    assert "当前 Shot 图片直接支持" in prompt
    assert "subject_A" not in prompt
    assert "subject_B" not in prompt
    assert "ITEM_1" not in prompt


def test_non_interacted_props_and_h3_fields_are_preserved_without_subject_binding() -> None:
    value = {
        "shots": [
            {
                "i": 1,
                "scene": {"loc": "客厅", "ie": "INT", "tod": "白天"},
                "visible": "蓝色玫瑰花束置于玻璃花瓶中",
                "shot_type": "特写",
                "angle": "俯拍",
                "composition": "主体居中",
                "lighting": "右侧柔和暖光",
                "continuity": "同场景延续",
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
                "people": [{
                    "appearance": "黑发女性",
                    "activity": "站立",
                    "expression": "神情紧张",
                    "posture": "身体微前倾",
                    "gaze": "看向画外右侧",
                    "interaction": "右手握手机",
                    "position": "中央",
                    "visibility": "FULL",
                }],
                "props": [],
            },
        ]
    }
    result = compact.expand_compact(value, batch())
    first = result[0]["semantic"]
    second = result[1]["semantic"]

    assert first["subjects"] == []
    assert [item["label"] for item in first["props"]] == ["蓝色玫瑰花束", "玻璃花瓶"]
    assert all(item["subject_labels"] == [] for item in first["props"])
    assert first["shot"]["shot_type_hint"] == "特写"
    assert first["shot"]["camera_angle_hint"] == "俯拍"
    assert first["shot"]["composition_hint"] == "主体居中"
    assert first["shot"]["lighting_hint"] == "右侧柔和暖光"
    assert first["shot"]["continuity_hint"] == "同场景延续"
    # Static Exact-Shot frames never pretend to know temporal camera motion.
    assert first["shot"]["camera_motion_hint"] == "UNKNOWN"

    person = second["subjects"][0]
    assert person["expression_summary"] == "神情紧张"
    assert person["posture_summary"] == "身体微前倾"
    assert person["gaze_summary"] == "看向画外右侧"
    assert person["interaction_summary"] == "右手握手机"
