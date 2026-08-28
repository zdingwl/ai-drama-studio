from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_prompt_module():
    repo_root = Path(__file__).resolve().parents[3]
    path = repo_root / "scripts" / "breakdown_vlm_prompt_zh_v1.py"
    spec = importlib.util.spec_from_file_location("breakdown_vlm_prompt_zh_v1_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prompt_forces_simplified_chinese_natural_language_fields() -> None:
    module = _load_prompt_module()
    prompt = module.build_prompt("en-US")

    assert module.PROMPT_PROFILE == "breakdown-p2-vlm-zh-draft-v1"
    assert module.DRAFT_TEXT_LANGUAGE == "zh-CN"
    assert "项目原始语言是 en-US" in prompt
    assert "所有由 VLM 生成的自然语言描述字段必须使用简体中文" in prompt
    assert "不要输出英文描述句子" in prompt
    assert "shot.summary" in prompt
    assert "subjects[].activity_summary" in prompt
    assert "events[].content" in prompt
    assert "props[].narrative_reason" in prompt
    assert "scene.location_hint 必须是简短、通用、稳定的地点类别" in prompt
    assert "appearance_summary 使用稳定顺序" in prompt


def test_prompt_keeps_machine_contract_tokens_and_provider_boundaries() -> None:
    module = _load_prompt_module()
    prompt = module.build_prompt("zh-CN")

    assert "INT|EXT|MIXED|UNKNOWN" in prompt
    assert "FULL|PARTIAL|OCCLUDED|UNKNOWN" in prompt
    assert "LIKELY_SPEAKING|NOT_SPEAKING|UNKNOWN" in prompt
    assert "VISUAL|ACTION" in prompt
    assert "LOW|MEDIUM|HIGH" in prompt
    assert "subject_A" in prompt
    assert "ASR/OCR 是独立 Provider" in prompt
    assert "不要转录对白、字幕、招牌、手机屏幕、文件" in prompt


def test_chinese_semantic_language_guard_accepts_chinese_draft() -> None:
    module = _load_prompt_module()
    semantic = {
        "scene": {
            "location_hint": "走廊",
            "time_of_day": "白天",
            "environment_description": "狭长走廊，两侧有房门。",
        },
        "shot": {
            "summary": "两名女子在走廊中面对面交谈。",
            "visual_description": "年轻女子站在左侧，年长女子站在右侧并拿着黑色塑料袋。",
            "shot_type_hint": "中景",
            "camera_motion_hint": "静止",
        },
        "subjects": [
            {
                "appearance_summary": "黑色长发，白色上衣，浅色长裤。",
                "activity_summary": "抬手指向对方。",
                "screen_position": "左侧",
            }
        ],
        "events": [{"content": "女子抬手示意。"}],
        "props": [{"label": "黑色塑料袋", "narrative_reason": "由右侧女子手持。"}],
    }

    result = module.validate_semantic_language(semantic)

    assert result["draft_text_language"] == "zh-CN"
    assert result["chinese_field_ratio"] >= 0.6


def test_chinese_semantic_language_guard_rejects_english_draft() -> None:
    module = _load_prompt_module()
    semantic = {
        "scene": {
            "location_hint": "hallway",
            "environment_description": "A long narrow hallway with doors on both sides.",
        },
        "shot": {
            "summary": "Two women are standing face-to-face in a hallway.",
            "visual_description": "A younger woman gestures toward an older woman.",
        },
        "events": [{"content": "The younger woman raises her hand."}],
    }

    with pytest.raises(ValueError, match="not Simplified Chinese"):
        module.validate_semantic_language(semantic)


def test_production_strict_runner_installs_prompt_before_diagnostic_runner() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    source = (repo_root / "scripts" / "run_breakdown_vlm_qwen3_strict_reader.py").read_text(
        encoding="utf-8"
    )

    install_index = source.index("\n    _install_draft_prompt()\n")
    diagnostic_index = source.index("import run_breakdown_vlm_qwen3_diagnostic as diagnostic")
    assert install_index < diagnostic_index
    assert "breakdown_vlm_prompt_zh_v1" in source
