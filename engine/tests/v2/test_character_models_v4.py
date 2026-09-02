from __future__ import annotations

from pathlib import Path

import pytest

from engine.app import content_models_v2


def test_require_models_fails_hard_when_character_v10_model_is_missing(monkeypatch, tmp_path: Path) -> None:
    """职责：锁住“缺模型不能发布空人物新版本”的 V10 底层门槛。"""

    monkeypatch.setattr(content_models_v2, "model_dir", lambda: tmp_path)

    with pytest.raises(content_models_v2.RequiredCharacterModelError, match="人物识别 V10 模型未准备完整"):
        content_models_v2.require_models()


def test_model_status_exposes_v10_models_runtime_tracking_and_final_gate(monkeypatch, tmp_path: Path) -> None:
    """职责：前端必须能看到 Person/ReID、可选 Face、MOT 与 V10 Final Gate。"""

    monkeypatch.setattr(content_models_v2, "model_dir", lambda: tmp_path)
    status = content_models_v2.model_status()

    logical_ids = {item["logical_id"] for item in status["models"]}
    assert logical_ids == {
        "face_detection.yunet.2023mar",
        "face_recognition.sface.2021dec",
        "person_detection.yolox.2022nov",
        "person_reid.youtu.2021nov",
    }
    assert status["ready"] is False
    assert status["profile"] == "character-v10-capture-first-model-classification"
    assert "runtime" in status
    assert "tracking_runtime" in status
    assert "YoutuReID model classify" in str(status["identity_policy"])
    assert status["final_policy"] == "Only confirmed V10 person identity classes can become Final Character"
    assert "Face is not required" in str((status.get("face_runtime") or {}).get("detail"))
