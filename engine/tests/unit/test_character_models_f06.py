from __future__ import annotations

from pathlib import Path

import pytest

from engine.app.character_models import (
    CharacterModelError,
    SFACE_SPEC,
    YUNET_SPEC,
    require_character_models,
)


def test_f06_model_specs_are_pinned_to_expected_lfs_hashes() -> None:
    assert YUNET_SPEC.filename == "face_detection_yunet_2023mar.onnx"
    assert YUNET_SPEC.size_bytes == 232_589
    assert YUNET_SPEC.sha256 == "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"

    assert SFACE_SPEC.filename == "face_recognition_sface_2021dec.onnx"
    assert SFACE_SPEC.size_bytes == 38_696_353
    assert SFACE_SPEC.sha256 == "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"


def test_require_character_models_rejects_missing_files(tmp_path: Path) -> None:
    with pytest.raises(CharacterModelError) as error:
        require_character_models(tmp_path)
    assert error.value.code == "CHARACTER_MODEL_MISSING"
    assert "python -m engine.app.character_models" in error.value.message
