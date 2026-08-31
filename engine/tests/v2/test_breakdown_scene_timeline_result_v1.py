from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import pytest

from engine.app import breakdown_scene_timeline_result_v1 as result
from engine.app.breakdown_scene_grounding_v1 import build_scene_grounding_packet_v1
from engine.app.breakdown_scene_narrative_validator_v1 import validate_scene_narrative_v1


def _draft(*, status: str = "READY") -> dict[str, Any]:
    return {
        "run": {
            "id": "BREAKDOWNRUN_G25",
            "project_id": "PROJECT_G25",
            "episode_id": "EPISODE_G25",
            "source_shot_revision_id": "SHOTREV_G25",
            "status": status,
            "is_current": True,
        }
    }


def _timeline() -> dict[str, Any]:
    return {
        "schema_version": "scene-timeline-v1",
        "source_breakdown_run_id": "BREAKDOWNRUN_G25",
        "source_shot_revision_id": "SHOTREV_G25",
        "episode_id": "EPISODE_G25",
        "status": "READY",
        "is_current": True,
        "scene_count": 1,
        "shot_count": 0,
        "warnings": [],
        "scenes": [
            {
                "ordinal": 1,
                "start_us": 0,
                "end_us": 2_000_000,
                "duration_us": 2_000_000,
                "title": "走廊",
                "scene_info": {
                    "location": "走廊",
                    "interior_exterior": "室内",
                    "time_of_day": "白天",
                    "environment": "住宅走廊",
                },
                "people": [],
                "story_summary": "走廊内发生争执",
                "shots": [],
            }
        ],
    }


def _fact_id(packet: dict[str, Any], kind: str) -> str:
    return next(item["fact_id"] for item in packet["facts"] if item["kind"] == kind)


def _valid_overlay(timeline: dict[str, Any]) -> dict[str, Any]:
    packet = build_scene_grounding_packet_v1(timeline, 1)
    candidate = {
        "scene_ordinal": 1,
        "readable_title": {
            "text": "走廊争执",
            "support": [
                _fact_id(packet, "SCENE_LOCATION"),
                _fact_id(packet, "SCENE_BASE_SUMMARY"),
            ],
        },
        "story_summary": {
            "text": "走廊内发生争执",
            "support": [_fact_id(packet, "SCENE_BASE_SUMMARY")],
        },
    }
    accepted, warnings = validate_scene_narrative_v1(packet, candidate)
    assert warnings == []
    return {
        "schema_version": "scene-narrative-v1",
        "source_breakdown_run_id": timeline["source_breakdown_run_id"],
        "source_shot_revision_id": timeline["source_shot_revision_id"],
        "episode_id": timeline["episode_id"],
        "status": "READY",
        "scenes": [accepted],
        "warnings": [],
    }


def _patch_timeline(monkeypatch: pytest.MonkeyPatch, timeline: dict[str, Any]) -> None:
    monkeypatch.setattr(result, "assemble_scene_timeline_v1", lambda _draft: deepcopy(timeline))


def _patch_artifact_path(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    monkeypatch.setattr(result, "scene_narrative_artifact_path_v1", lambda _draft: path)


def test_missing_narrative_artifact_returns_deterministic_timeline_with_user_warning(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    timeline = _timeline()
    _patch_timeline(monkeypatch, timeline)
    _patch_artifact_path(monkeypatch, tmp_path / "missing.json")

    payload = result.build_scene_timeline_result_v1(_draft())

    assert payload["scenes"][0]["title"] == "走廊"
    assert result.NARRATIVE_MISSING_WARNING in payload["warnings"]
    serialized = json.dumps(payload, ensure_ascii=False)
    assert '"support"' not in serialized
    assert "source_fingerprint" not in serialized


def test_valid_materialized_overlay_applies_title_and_never_leaks_support(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    timeline = _timeline()
    artifact = tmp_path / "scene-timeline" / "narrative-overlay-v1.json"
    _patch_timeline(monkeypatch, timeline)
    _patch_artifact_path(monkeypatch, artifact)

    persisted = result.persist_scene_narrative_overlay_v1(_draft(), _valid_overlay(timeline))
    payload = result.build_scene_timeline_result_v1(_draft())

    assert persisted == artifact
    assert artifact.is_file()
    assert payload["scenes"][0]["title"] == "走廊争执"
    assert payload["scenes"][0]["story_summary"] == "走廊内发生争执"
    assert result.NARRATIVE_MISSING_WARNING not in payload["warnings"]
    assert result.NARRATIVE_FALLBACK_WARNING not in payload["warnings"]
    serialized = json.dumps(payload, ensure_ascii=False)
    assert '"support"' not in serialized
    assert "source_fingerprint" not in serialized
    assert "F000" not in serialized


def test_persist_rejects_handwritten_claim_that_bypasses_g24_support_rules(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    timeline = _timeline()
    artifact = tmp_path / "narrative-overlay-v1.json"
    _patch_timeline(monkeypatch, timeline)
    _patch_artifact_path(monkeypatch, artifact)
    overlay = _valid_overlay(timeline)
    overlay["scenes"][0]["readable_title"] = {
        "text": "火星爆炸",
        "support": overlay["scenes"][0]["readable_title"]["support"],
    }

    with pytest.raises(result.SceneNarrativeArtifactError):
        result.persist_scene_narrative_overlay_v1(_draft(), overlay)

    assert not artifact.exists()


def test_stale_materialized_overlay_falls_back_without_exposing_validator_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    timeline = _timeline()
    artifact = tmp_path / "narrative-overlay-v1.json"
    _patch_timeline(monkeypatch, timeline)
    _patch_artifact_path(monkeypatch, artifact)
    overlay = _valid_overlay(timeline)
    overlay["scenes"][0]["source_fingerprint"] = "0" * 64
    artifact.write_text(json.dumps(overlay, ensure_ascii=False), encoding="utf-8")

    payload = result.build_scene_timeline_result_v1(_draft())

    assert payload["scenes"][0]["title"] == "走廊"
    assert payload["warnings"] == [result.NARRATIVE_FALLBACK_WARNING]
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "fingerprint" not in serialized.lower()
    assert "validator" not in serialized.lower()
    assert "F000" not in serialized


def test_non_ready_run_is_not_exposed_as_ordinary_user_scene_timeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        result,
        "assemble_scene_timeline_v1",
        lambda _draft: pytest.fail("non-ready result must be rejected before assembly"),
    )

    with pytest.raises(result.SceneTimelineResultError):
        result.build_scene_timeline_result_v1(_draft(status="PROCESSING"))
