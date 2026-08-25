from __future__ import annotations

from pathlib import Path

import pytest

from engine.app import content_models_v2


def test_require_models_fails_hard_when_character_v6_model_is_missing(monkeypatch, tmp_path: Path) -> None:
    """职责：锁住“缺模型不能发布空人物新版本”的底层门槛。"""

    monkeypatch.setattr(content_models_v2, "model_dir", lambda: tmp_path)

    with pytest.raises(content_models_v2.RequiredCharacterModelError, match="人物识别 V6 模型未准备完整"):
        content_models_v2.require_models()


def test_model_status_exposes_v6_models_runtime_tracking_and_final_gate(monkeypatch, tmp_path: Path) -> None:
    """职责：前端必须能看到 Person/ReID GPU、Face provider、MOT 与 Global Identity Final Gate。"""

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
    assert status["profile"] == "character-v6-global-identity"
    assert "runtime" in status
    assert "tracking_runtime" in status
    assert "Global Identity Graph" in str(status["identity_policy"])
    assert status["final_policy"] == "Only RESOLVED Identity can become Final Character"
