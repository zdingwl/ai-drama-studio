from __future__ import annotations

from scripts.check_local_remake_runtime_stack import (
    blockers,
    normalize_backend,
    normalize_h3,
    normalize_vlm_models,
    normalize_worker,
    stack_result,
)


def _ready_stack():
    return {
        "backend": {"ready": True},
        "h3_fl2va": {"ready": True},
        "h3_ref2va": {"ready": True},
        "qwen3_vl": {"ready": True},
        "qwen3_tts": {"ready": True},
        "latentsync": {"ready": True},
        "audio_separator": {"ready": True},
    }


def test_normalizers_preserve_runtime_truth() -> None:
    backend = normalize_backend({"status": "ok", "architecture": "localized-remake-h3-local-v1", "app_version": "2.7.0"})
    assert backend["ready"] is True
    assert backend["app_version"] == "2.7.0"

    h3 = normalize_h3({
        "fl2va": {"ready": True, "base_url": "http://127.0.0.1:30010", "probe": "/health"},
        "ref2va": {"ready": False, "base_url": "http://127.0.0.1:30011", "error": "offline"},
    })
    assert h3["h3_fl2va"]["ready"] is True
    assert h3["h3_ref2va"]["ready"] is False

    worker = normalize_worker({"ready": True, "reachable": True, "base_url": "http://127.0.0.1:7861"})
    assert worker["ready"] is True
    assert worker["reachable"] is True


def test_vlm_model_list_mismatch_is_diagnostic_not_false_blocker() -> None:
    result = normalize_vlm_models(
        {"data": [{"id": "C:/models/Qwen3-VL-4B-Instruct"}]},
        base_url="http://127.0.0.1:8001/v1",
        model="Qwen3-VL-4B-Instruct",
    )
    assert result["ready"] is True
    assert result["model_list_match"] is False
    assert result["available_models"] == ["C:/models/Qwen3-VL-4B-Instruct"]


def test_complete_stack_requires_every_real_acceptance_runtime() -> None:
    values = _ready_stack()
    assert blockers(values) == []
    assert stack_result(values)["status"] == "READY"
    assert stack_result(values)["ready"] is True

    values["latentsync"] = {"ready": False, "error": "offline"}
    values["audio_separator"] = {"ready": False, "error": "offline"}
    assert blockers(values) == ["latentsync", "audio_separator"]
    result = stack_result(values)
    assert result["status"] == "BLOCKED"
    assert result["ready"] is False


def test_backend_non_ok_and_unconfigured_vlm_cannot_pass() -> None:
    assert normalize_backend({"status": "starting"})["ready"] is False
    vlm = normalize_vlm_models({}, base_url="", model="")
    assert vlm["ready"] is False
