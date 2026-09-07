from __future__ import annotations

from pathlib import Path

from engine.app import breakdown_p2_pipeline_v1 as pipeline
from engine.app import breakdown_p2_sidecar_v1 as p2
from engine.app.source_video_understanding_provider_v1 import (
    CANONICAL_DIALOGUE_POLICY,
    DEFAULT_QWEN38_MODEL,
    QWEN38_PROVIDER_NAME,
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


def test_default_p2_pipeline_uses_qwen38_visual_provider() -> None:
    providers = pipeline._default_providers()
    visual = next(provider for provider in providers if provider.component == "VLM")

    assert isinstance(visual, Qwen38VideoUnderstandingProvider)
    assert visual.model_name == DEFAULT_QWEN38_MODEL


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
    assert SOURCE_VIDEO_PROVIDER_PROFILE == "source-video-understanding-qwen38-v1"
    assert QWEN38_PROVIDER_NAME == "qwen38-video-understanding"
    assert CANONICAL_DIALOGUE_POLICY == "asr-ocr-owned-visual-provider-cannot-overwrite-v1"
