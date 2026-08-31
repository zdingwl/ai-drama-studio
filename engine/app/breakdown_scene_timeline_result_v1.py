"""G2.5 ordinary-user Scene Timeline result resolver and Narrative artifact store.

This layer is intentionally thin:
- frozen G2.2 assembler remains the only source of Scene/Shot truth;
- frozen G2.3/G2.4 code remains the only authority allowed to validate/apply Narrative text;
- GET/read paths never start Qwen or any other model;
- accepted Narrative overlays are materialized explicitly into the Episode workspace and revalidated
  against Run / ShotRevision / Scene source fingerprints every time they are consumed;
- primary user payloads remain exactly ``scene-timeline-v1`` and never expose support Fxxxx,
  Evidence IDs, LocalSubject IDs, provider/model diagnostics or raw validator output.
"""
from __future__ import annotations

from collections.abc import Mapping
import json
import os
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from engine.app import studio_v2
from engine.app.breakdown_scene_grounding_v1 import build_scene_grounding_packet_v1
from engine.app.breakdown_scene_narrative_contract_v1 import SceneNarrativeOverlayPayloadV1
from engine.app.breakdown_scene_narrative_v1 import apply_scene_narrative_overlay_v1
from engine.app.breakdown_scene_narrative_validator_v1 import (
    SceneNarrativeValidationError,
    validate_scene_narrative_v1,
)
from engine.app.breakdown_scene_timeline_assembler_v1 import assemble_scene_timeline_v1
from engine.app.breakdown_scene_timeline_contract_v1 import SceneTimelinePayloadV1


SCENE_TIMELINE_RESULT_PROFILE = "breakdown-g2-scene-timeline-api-v1"
SCENE_NARRATIVE_ARTIFACT_FILENAME = "narrative-overlay-v1.json"
READY_STATUSES = frozenset({"READY", "READY_WITH_WARNINGS"})
NARRATIVE_MISSING_WARNING = "场景标题与剧情摘要暂未完成可读整理，当前展示基础拉片结果。"
NARRATIVE_FALLBACK_WARNING = "场景可读整理与当前拉片结果不一致，当前展示基础拉片结果。"
NARRATIVE_PARTIAL_WARNING = "部分场景的标题或剧情摘要使用基础拉片结果。"


class SceneTimelineResultError(RuntimeError):
    """G2.5 cannot safely expose the requested result."""


class SceneNarrativeArtifactError(SceneTimelineResultError):
    """Persisted Narrative artifact is missing required structure or cannot be read safely."""


def _run_payload(draft: Mapping[str, Any]) -> Mapping[str, Any]:
    run = draft.get("run")
    if not isinstance(run, Mapping):
        raise SceneTimelineResultError("Breakdown Draft 缺少 Run 锚点")
    return run


def assert_scene_timeline_ready_draft_v1(draft: Mapping[str, Any]) -> None:
    """Refuse PROCESSING/FAILED/STALE drafts on the ordinary-user result surface."""

    run = _run_payload(draft)
    status = str(run.get("status") or "").strip().upper()
    if status not in READY_STATUSES:
        raise SceneTimelineResultError("Scene Timeline 仅提供已完成的拉片结果")


def scene_narrative_artifact_path_v1(draft: Mapping[str, Any]) -> Path:
    """Return the canonical validated Narrative overlay path for one immutable Breakdown Run."""

    run = _run_payload(draft)
    project_id = str(run.get("project_id") or "").strip()
    episode_id = str(run.get("episode_id") or "").strip()
    run_id = str(run.get("id") or "").strip()
    if not project_id or not episode_id or not run_id:
        raise SceneNarrativeArtifactError("Breakdown Run 缺少 workspace 锚点")
    return (
        studio_v2.episode_dir(project_id, episode_id)
        / "breakdown"
        / run_id
        / "scene-timeline"
        / SCENE_NARRATIVE_ARTIFACT_FILENAME
    )


def _stable_json(payload: Mapping[str, Any]) -> str:
    try:
        return json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise SceneNarrativeArtifactError("Scene Narrative artifact 必须可安全 JSON 序列化") from exc


def _append_user_warning(timeline: Mapping[str, Any], warning: str) -> dict[str, Any]:
    result = dict(timeline)
    raw_warnings = result.get("warnings")
    warnings = [str(item) for item in raw_warnings] if isinstance(raw_warnings, list) else []
    if warning not in warnings:
        warnings.append(warning)
    result["warnings"] = warnings
    return SceneTimelinePayloadV1.model_validate(result).model_dump(mode="json")


def _revalidate_overlay_v1(
    timeline: Mapping[str, Any],
    overlay: Mapping[str, Any],
) -> dict[str, Any]:
    """Prove that persisted claims are still exactly what frozen G2.4 accepts for this Timeline.

    ``SceneNarrativeOverlayPayloadV1`` proves shape, not provenance. Replaying each stored claim through
    the frozen validator prevents a hand-written artifact with a correct fingerprint from bypassing
    the G2.4 support/ASR-authority rules.
    """

    normalized_timeline = SceneTimelinePayloadV1.model_validate(timeline).model_dump(mode="json")
    normalized_overlay = SceneNarrativeOverlayPayloadV1.model_validate(overlay)

    expected_ordinals = {int(scene["ordinal"]) for scene in normalized_timeline["scenes"]}
    actual_ordinals = {scene.scene_ordinal for scene in normalized_overlay.scenes}
    if actual_ordinals != expected_ordinals:
        raise SceneNarrativeArtifactError("Scene Narrative artifact 未覆盖当前 Timeline 的全部 Scene")

    # Frozen apply gate checks Run/ShotRevision/Episode anchors, scene ordinals and fingerprints.
    apply_scene_narrative_overlay_v1(normalized_timeline, normalized_overlay)

    for scene in normalized_overlay.scenes:
        packet = build_scene_grounding_packet_v1(normalized_timeline, scene.scene_ordinal)
        candidate = {
            "scene_ordinal": scene.scene_ordinal,
            "readable_title": (
                scene.readable_title.model_dump(mode="json")
                if scene.readable_title is not None
                else None
            ),
            "story_summary": (
                scene.story_summary.model_dump(mode="json")
                if scene.story_summary is not None
                else None
            ),
        }
        accepted, warnings = validate_scene_narrative_v1(packet, candidate)
        expected = scene.model_dump(mode="json")
        if warnings or accepted != expected:
            raise SceneNarrativeArtifactError("Scene Narrative artifact 未通过 G2.4 一致性复核")

    return normalized_overlay.model_dump(mode="json")


def persist_scene_narrative_overlay_v1(
    draft: Mapping[str, Any],
    overlay: Mapping[str, Any],
) -> Path:
    """Atomically materialize one G2.4-accepted overlay for future read-only API use.

    Before writing, this function assembles the frozen deterministic Timeline, replays every claim
    through the frozen G2.4 validator, and calls the frozen overlay application gate. The raw artifact
    may retain developer-only support references, but it is never returned by the primary API.
    """

    assert_scene_timeline_ready_draft_v1(draft)
    timeline = assemble_scene_timeline_v1(draft)
    try:
        normalized = _revalidate_overlay_v1(timeline, overlay)
    except (ValidationError, SceneNarrativeValidationError, SceneNarrativeArtifactError, ValueError) as exc:
        if isinstance(exc, SceneNarrativeArtifactError):
            raise
        raise SceneNarrativeArtifactError("Scene Narrative overlay 未通过当前 Timeline 校验") from exc

    path = scene_narrative_artifact_path_v1(draft)
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = _stable_json(normalized)
    temp = path.with_name(path.name + ".tmp")
    temp.unlink(missing_ok=True)
    try:
        temp.write_text(serialized, encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    return path


def load_scene_narrative_overlay_v1(draft: Mapping[str, Any]) -> dict[str, Any] | None:
    """Load the canonical overlay without running inference; ``None`` means not materialized yet."""

    path = scene_narrative_artifact_path_v1(draft)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return SceneNarrativeOverlayPayloadV1.model_validate(raw).model_dump(mode="json")
    except (OSError, TypeError, ValueError, ValidationError) as exc:
        raise SceneNarrativeArtifactError("Scene Narrative artifact 无法安全读取") from exc


def build_scene_timeline_result_v1(draft: Mapping[str, Any]) -> dict[str, Any]:
    """Build the ordinary-user G2.5 payload without any model execution or business writes."""

    assert_scene_timeline_ready_draft_v1(draft)
    timeline = assemble_scene_timeline_v1(draft)

    try:
        overlay = load_scene_narrative_overlay_v1(draft)
    except SceneNarrativeArtifactError:
        return _append_user_warning(timeline, NARRATIVE_FALLBACK_WARNING)

    if overlay is None:
        return _append_user_warning(timeline, NARRATIVE_MISSING_WARNING)

    try:
        normalized_overlay = _revalidate_overlay_v1(timeline, overlay)
        applied = apply_scene_narrative_overlay_v1(timeline, normalized_overlay)
    except (ValidationError, SceneNarrativeValidationError, SceneNarrativeArtifactError, ValueError):
        return _append_user_warning(timeline, NARRATIVE_FALLBACK_WARNING)

    # Never expose raw organizer/validator warnings; collapse them to one ordinary-user fallback note.
    if normalized_overlay["status"] == "READY_WITH_WARNINGS":
        applied = _append_user_warning(applied, NARRATIVE_PARTIAL_WARNING)

    # The frozen strict contract is the final leak guard: raw support/provenance cannot survive here.
    return SceneTimelinePayloadV1.model_validate(applied).model_dump(mode="json")


__all__ = [
    "NARRATIVE_FALLBACK_WARNING",
    "NARRATIVE_MISSING_WARNING",
    "NARRATIVE_PARTIAL_WARNING",
    "READY_STATUSES",
    "SCENE_NARRATIVE_ARTIFACT_FILENAME",
    "SCENE_TIMELINE_RESULT_PROFILE",
    "SceneNarrativeArtifactError",
    "SceneTimelineResultError",
    "assert_scene_timeline_ready_draft_v1",
    "build_scene_timeline_result_v1",
    "load_scene_narrative_overlay_v1",
    "persist_scene_narrative_overlay_v1",
    "scene_narrative_artifact_path_v1",
]
