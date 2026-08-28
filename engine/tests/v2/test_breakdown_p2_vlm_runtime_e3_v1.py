from __future__ import annotations

from engine.app import breakdown_p2_vlm_runtime_v1 as runtime


def semantic(summary: str) -> dict:
    return {
        "scene": {
            "location_hint": "",
            "interior_exterior": "UNKNOWN",
            "time_of_day": "",
            "environment_description": "背景虚化。",
        },
        "shot": {
            "summary": summary,
            "visual_description": "人物站在桌边，背景虚化。",
            "shot_type_hint": "近景",
            "camera_motion_hint": "静止",
            "narrative_function_hint": "人物反应",
            "composition_hint": "人物居中",
        },
        "subjects": [{
            "label": "subject_A",
            "appearance_summary": "黑色短发，白色上衣",
            "activity_summary": "低头看向桌面",
            "screen_position": "中央",
            "visibility": "FULL",
            "speaking_state": "UNKNOWN",
        }],
        "events": [{
            "event_type": "ACTION",
            "start_ratio": 0.1,
            "end_ratio": 0.8,
            "content": "人物低头看向桌面。",
            "subject_labels": ["subject_A"],
        }],
        "props": [{
            "label": "手机",
            "importance": "MEDIUM",
            "narrative_reason": "手机位于桌面。",
            "subject_labels": ["subject_A"],
        }],
    }


def test_text_only_e3_cannot_replace_visual_presence_or_photographic_facts() -> None:
    e2 = semantic("E2 当前镜头")
    refined = semantic("结合对白后的当前镜头摘要")
    refined["scene"] = {
        "location_hint": "客厅",
        "interior_exterior": "INT",
        "time_of_day": "白天",
        "environment_description": "上下文表明人物仍在客厅。",
    }
    refined["shot"].update({
        "visual_description": "错误地描述了邻镜头的人物拥抱。",
        "shot_type_hint": "全景",
        "camera_motion_hint": "推近",
        "composition_hint": "双人构图",
        "narrative_function_hint": "人物意识到手机消息很重要",
    })
    refined["subjects"] = [{
        "label": "subject_X",
        "appearance_summary": "邻镜头人物",
        "activity_summary": "拥抱",
        "screen_position": "左侧",
        "visibility": "FULL",
        "speaking_state": "LIKELY_SPEAKING",
    }]
    refined["events"] = [{
        "event_type": "ACTION",
        "start_ratio": 0.0,
        "end_ratio": 1.0,
        "content": "邻镜头人物拥抱。",
        "subject_labels": ["subject_X"],
    }]
    refined["props"] = [
        {
            "label": "黑色手机",
            "importance": "HIGH",
            "narrative_reason": "结合上下文可知手机消息推动剧情。",
            "subject_labels": ["subject_A"],
        },
        {
            "label": "钥匙",
            "importance": "HIGH",
            "narrative_reason": "只在邻镜头出现。",
            "subject_labels": [],
        },
    ]

    grounded = runtime._ground_contextual_semantic(e2, refined)

    assert grounded["scene"]["location_hint"] == "客厅"
    assert grounded["shot"]["summary"] == "结合对白后的当前镜头摘要"
    assert grounded["shot"]["narrative_function_hint"] == "人物意识到手机消息很重要"
    assert grounded["shot"]["visual_description"] == "人物站在桌边，背景虚化。"
    assert grounded["shot"]["shot_type_hint"] == "近景"
    assert grounded["shot"]["camera_motion_hint"] == "静止"
    assert grounded["shot"]["composition_hint"] == "人物居中"
    assert grounded["subjects"] == e2["subjects"]
    assert grounded["events"] == e2["events"]
    assert [item["label"] for item in grounded["props"]] == ["手机"]
    assert grounded["props"][0]["importance"] == "HIGH"
    assert grounded["props"][0]["narrative_reason"] == "结合上下文可知手机消息推动剧情。"
    assert runtime.VLM_CONTEXTUAL_GROUNDING_POLICY == "e3-text-only-preserve-e2-visual-facts-v1"
