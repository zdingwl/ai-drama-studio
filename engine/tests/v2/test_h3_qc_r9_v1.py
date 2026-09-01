from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.app import h3_qc_core_v1 as qc_core
from engine.app import h3_retry_execution_v1 as retry_runtime
from engine.app.h3_qc_v1 import semantic_qc_policy_v1, structural_h3_qc_v1
from engine.app.review_issue_v1 import DOMAIN_EDITED_ISSUE_TYPES


def _segment(**overrides):
    value = {
        "id": "SEG_1",
        "project_id": "PROJECT_1",
        "episode_id": "EP_1",
        "input_fingerprint": "a" * 64,
        "generation_mode": "REF2VA",
        "target_characters": [{"target_name": "Alex", "appearance_profile": "adult actor"}],
        "target_scene": {"decision": "KEEP"},
        "continuity_from_segment_id": None,
    }
    value.update(overrides)
    return value


def test_semantic_qc_passes_only_when_required_dimensions_clear_thresholds() -> None:
    status, quality, semantic, reason, retry = semantic_qc_policy_v1({
        "visual_integrity": 0.93,
        "target_character_consistency": 0.88,
        "scene_consistency": 0.84,
        "action_camera_consistency": 0.81,
        "continuity_consistency": None,
        "confidence": 0.91,
        "source_actor_leak": False,
        "obvious_visual_artifact": False,
        "reasons": [],
        "retry_instruction": "",
    }, _segment())
    assert status == "PASS"
    assert quality is not None and quality > 0.8
    assert semantic["source_actor_leak"] is False
    assert reason == "H3 结构与语义质检通过"
    assert retry is None


def test_source_actor_leak_forces_retry_even_with_high_scores() -> None:
    status, _quality, _semantic, reason, retry = semantic_qc_policy_v1({
        "visual_integrity": 0.98,
        "target_character_consistency": 0.95,
        "scene_consistency": 0.95,
        "action_camera_consistency": 0.95,
        "confidence": 0.95,
        "source_actor_leak": True,
        "obvious_visual_artifact": False,
        "reasons": ["source actor face remains visible"],
        "retry_instruction": "Replace source actor identity.",
    }, _segment())
    assert status == "RETRY"
    assert "原演员" in reason
    assert retry == "Replace source actor identity."


def test_low_qc_confidence_goes_to_review_not_fake_pass() -> None:
    status, *_ = semantic_qc_policy_v1({
        "visual_integrity": 0.9,
        "target_character_consistency": 0.9,
        "scene_consistency": 0.9,
        "action_camera_consistency": 0.9,
        "confidence": 0.3,
        "source_actor_leak": False,
        "obvious_visual_artifact": False,
        "reasons": ["faces are too small to judge"],
    }, _segment())
    assert status == "REVIEW"


def test_structural_qc_checks_exact_duration_and_full_decode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output = tmp_path / "attempt.mp4"
    output.write_bytes(b"not-a-real-video-but-run-is-stubbed")
    calls: list[str] = []

    def fake_run(command: list[str], *, timeout_seconds: int):
        calls.append(command[0])
        if command[0] == "ffprobe":
            class Result:
                stdout = json.dumps({
                    "format": {"duration": "1.250000"},
                    "streams": [{"codec_type": "video", "width": 720, "height": 1280, "avg_frame_rate": "24/1"}],
                })
            return Result()
        class Result:
            stdout = ""
        return Result()

    monkeypatch.setattr(qc_core, "_run", fake_run)
    result = structural_h3_qc_v1(output, expected_duration_us=1_250_000)
    assert result["has_video"] is True
    assert result["decode_ok"] is True
    assert result["duration_ok"] is True
    assert result["actual_duration_us"] == 1_250_000
    assert calls == ["ffprobe", "ffmpeg"]


def test_retry_context_changes_seed_and_adds_qc_feedback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(retry_runtime, "compile_h3_context_v1", lambda project_id, segment_id: {
        "status": "READY",
        "reason": "ready",
        "workspace_dir": "/tmp/h3-context",
        "request": {
            "provider": "MINIMAX_H3_LOCAL",
            "mode": "FL2VA",
            "prompt": "base prompt",
            "conditions": [],
            "duration_seconds": 4,
            "short_edge": 768,
            "aspect_ratio": "9:16",
            "seed": 123,
        },
    })
    request, fingerprint = retry_runtime._retry_request(
        "PROJECT_1",
        _segment(generation_mode="FL2VA", target_characters=[], target_scene=None),
        retry_index=2,
        retry_feedback="Keep the target face stable.",
    )
    assert request.seed != 123
    assert "qc_retry_correction" in request.prompt
    assert "Keep the target face stable." in request.prompt
    assert len(fingerprint) == 64


def test_h3_qc_is_domain_edited_issue() -> None:
    assert "H3_QC" in DOMAIN_EDITED_ISSUE_TYPES


def test_r9_routes_are_registered_under_api_prefix() -> None:
    from engine.app.main import app

    paths = {route.path for route in app.routes}
    assert "/api/projects/{project_id}/h3-quality" in paths
    assert "/api/generation-attempts/{attempt_id}/quality-check" in paths
    assert "/api/generation-attempts/{attempt_id}/select" in paths
    assert "/api/generation-segments/{segment_id}/selected-video" in paths
    assert "/api/projects/{project_id}/generation-segments/{segment_id}/tasks/h3-qc-retry" in paths
