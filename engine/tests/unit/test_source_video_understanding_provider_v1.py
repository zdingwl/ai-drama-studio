from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from engine.app import breakdown_p2_pipeline_v1 as pipeline
from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app.source_video_understanding_provider_v1 import (
    CANONICAL_DIALOGUE_POLICY,
    DEFAULT_QWEN38_MODEL,
    QWEN38_PROVIDER_NAME,
    QWEN38_REASONING_POLICY,
    Qwen38VideoUnderstandingProvider,
    SOURCE_VIDEO_PROVIDER_PROFILE,
    SourceVideoUnderstandingProvider,
    source_video_input_fingerprint,
)


def _context() -> p2.P2RunContext:
    return p2.P2RunContext(
        run_id="RUN_1",
        project_id="PROJECT_1",
        episode_id="EPISODE_1",
        source_language="zh-CN",
        source_shot_revision_id="SHOTREV_1",
        audio_path=None,
        shots=(
            p2.P2ShotInput(
                revision_item_id="ITEM_1",
                original_shot_id="SHOT_1",
                ordinal=1,
                start_us=0,
                end_us=2_000_000,
                duration_us=2_000_000,
                reference_clip_path="/source/reference/shot-000001.mp4",
                thumbnail_path=None,
                keyframes=(),
            ),
        ),
    )


def test_qwen38_is_business_source_video_provider_with_dedicated_runner() -> None:
    provider = Qwen38VideoUnderstandingProvider(
        unified_inference_runner=lambda config, video_path, windows: (),
    )

    assert isinstance(provider, SourceVideoUnderstandingProvider)
    assert provider.component == "VLM"
    assert provider.model_name == DEFAULT_QWEN38_MODEL
    assert provider.runner_script.name == "run_breakdown_vlm_fast_grounded_qwen38.py"
    assert "Qwen38Visual" in str(provider.python_executable)
    assert "Qwen38Visual" in str(provider.model_path)
    assert "TransVLM" not in str(provider.python_executable)
    assert "TransVLM" not in str(provider.model_path)


def test_default_p2_pipeline_uses_qwen38_visual_provider() -> None:
    providers = pipeline._default_providers()
    visual = next(provider for provider in providers if provider.component == "VLM")

    assert isinstance(visual, Qwen38VideoUnderstandingProvider)
    assert visual.model_name == DEFAULT_QWEN38_MODEL
    assert "Qwen38Visual" in str(visual.python_executable)


def test_visual_semantic_whitelist_drops_dialogue_and_target_fields() -> None:
    provider = Qwen38VideoUnderstandingProvider(
        unified_inference_runner=lambda config, video_path, windows: (),
    )
    semantic = provider._normalize_semantic({
        "scene": {
            "location_hint": "办公室",
            "interior_exterior": "INT",
        },
        "shot": {
            "summary": "一名男子站在办公桌旁。",
            "visual_description": "男子站在桌旁看向门口。",
            "canonical_dialogue": "不允许进入视觉事实",
        },
        "subjects": [{
            "label": "subject_A",
            "appearance_summary": "黑色西装",
            "activity_summary": "站立",
            "source_text": "不允许进入视觉事实",
        }],
        "events": [],
        "props": [],
        "source_dialogue": [{"text": "不允许进入视觉事实"}],
        "canonical_source_dialogue": "不允许进入视觉事实",
        "target_dialogue": "绝不能进入 Source",
        "target_character_id": "TARGET_1",
    })

    assert semantic is not None
    assert set(semantic) == {"schema_version", "scene", "shot", "subjects", "events", "props"}
    assert "canonical_dialogue" not in semantic["shot"]
    assert "source_text" not in semantic["subjects"][0]
    assert "source_dialogue" not in semantic
    assert "canonical_source_dialogue" not in semantic
    assert "target_dialogue" not in semantic
    assert "target_character_id" not in semantic


def test_input_fingerprint_changes_with_source_revision_or_model() -> None:
    context = _context()
    current = source_video_input_fingerprint(context, model_name=DEFAULT_QWEN38_MODEL)
    same = source_video_input_fingerprint(context, model_name=DEFAULT_QWEN38_MODEL)
    other_model = source_video_input_fingerprint(context, model_name="Qwen/Qwen3.8-27B-FP8")
    other_revision = p2.P2RunContext(
        run_id=context.run_id,
        project_id=context.project_id,
        episode_id=context.episode_id,
        source_language=context.source_language,
        source_shot_revision_id="SHOTREV_2",
        audio_path=context.audio_path,
        shots=context.shots,
    )

    assert current == same
    assert current != other_model
    assert current != source_video_input_fingerprint(
        other_revision,
        model_name=DEFAULT_QWEN38_MODEL,
    )


def test_qwen38_runtime_entry_uses_current_multimodal_auto_model_loader() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    source = (repo_root / "scripts" / "run_breakdown_vlm_fast_grounded_qwen38.py").read_text(
        encoding="utf-8"
    )

    assert "from transformers import AutoModelForMultimodalLM, AutoProcessor" in source
    assert "from transformers import AutoProcessor, Qwen3VLForConditionalGeneration" not in source
    assert "dtype=dtype" in source
    assert "enable_thinking=False" in source
    assert "preserve_thinking=False" in source
    assert SOURCE_VIDEO_PROVIDER_PROFILE == "source-video-understanding-qwen38-v1"
    assert QWEN38_PROVIDER_NAME == "qwen38-video-understanding"
    assert QWEN38_REASONING_POLICY == "non-thinking-structured-visual-json-v1"
    assert CANONICAL_DIALOGUE_POLICY == "asr-ocr-owned-visual-provider-cannot-overwrite-v1"


def test_qwen38_runtime_checker_accepts_official_qwen35_architecture_tag(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    checker_path = repo_root / "scripts" / "check_qwen38_visual_runtime.py"
    spec = importlib.util.spec_from_file_location("qwen38_runtime_checker_test", checker_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    model_dir = tmp_path / "Qwen3.8-27B"
    model_dir.mkdir()
    (model_dir / "config.json").write_text(json.dumps({
        "model_type": "qwen3_5",
        "architectures": ["Qwen3_5ForConditionalGeneration"],
        "language_model_only": False,
        "vision_config": {"hidden_size": 1024},
        "video_token_id": 248056,
    }), encoding="utf-8")

    ready, detail = module._checkpoint_config_status(model_dir)
    assert ready is True
    assert "model_type=qwen3_5" in detail


def test_qwen38_setup_and_acceptance_tools_do_not_default_to_old_http_vlm() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    setup = (repo_root / "scripts" / "setup_breakdown_vlm_runtime.ps1").read_text(encoding="utf-8")
    stack = (repo_root / "scripts" / "check_local_remake_runtime_stack.py").read_text(encoding="utf-8")
    acceptance = (repo_root / "scripts" / "run_real_project_acceptance_v1.py").read_text(encoding="utf-8")

    assert "Qwen/Qwen3.8-27B" in setup
    assert "Qwen3-VL-4B-Instruct" not in setup
    assert ".runtime\\Qwen38Visual" in setup
    assert '"qwen38_visual"' in stack
    assert '"qwen3_vl"' not in stack
    assert '"qwen38_visual"' in acceptance
    assert '"qwen3_vl"' not in acceptance
