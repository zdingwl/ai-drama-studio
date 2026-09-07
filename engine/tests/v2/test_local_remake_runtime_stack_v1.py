from __future__ import annotations

from scripts.check_local_remake_runtime_stack import (
    RUNTIME_ORDER,
    blockers,
    normalize_backend,
    normalize_h3,
    normalize_worker,
    stack_result,
)


def _ready_stack():
    return {
        "backend": {"ready": True},
        "h3_fl2va": {"ready": True},
        "h3_ref2va": {"ready": True},
        "qwen38_visual": {"ready": True, "provider": "qwen38-video-understanding"},
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


def test_runtime_inventory_uses_local_qwen38_visual_not_legacy_http_vlm() -> None:
    assert "qwen38_visual" in RUNTIME_ORDER
    assert "qwen3_vl" not in RUNTIME_ORDER

    values = _ready_stack()
    values["qwen38_visual"] = {
        "ready": False,
        "provider": "qwen38-video-understanding",
        "acceptance_scope": "RUNTIME_READINESS_ONLY",
        "error": "checkpoint missing",
    }
    assert blockers(values) == ["qwen38_visual"]
    assert stack_result(values)["status"] == "BLOCKED"


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


def test_backend_non_ok_and_missing_qwen38_readiness_cannot_pass() -> None:
    assert normalize_backend({"status": "starting"})["ready"] is False
    values = _ready_stack()
    values["backend"] = {"ready": False}
    values["qwen38_visual"] = {"ready": False, "error": "runtime not installed"}
    assert blockers(values) == ["backend", "qwen38_visual"]
