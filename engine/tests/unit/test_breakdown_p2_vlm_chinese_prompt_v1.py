from __future__ import annotations

import importlib.util
from pathlib import Path


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


def test_production_strict_runner_installs_prompt_before_diagnostic_runner() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    source = (repo_root / "scripts" / "run_breakdown_vlm_qwen3_strict_reader.py").read_text(
        encoding="utf-8"
    )

    install_index = source.index("\n    _install_draft_prompt()\n")
    diagnostic_index = source.index("import run_breakdown_vlm_qwen3_diagnostic as diagnostic")
    assert install_index < diagnostic_index
    assert "breakdown_vlm_prompt_zh_v1" in source
