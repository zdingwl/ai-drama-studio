"""2026-09-07 automatic SourceDramaSnapshot loading policy.

The underlying V1 composer remains the stable source-truth contract.  This compatibility
loader changes only product readiness semantics:
- content uncertainty such as PERSON_PRESENCE no longer blocks snapshot materialization;
- unresolved content is retained as warnings and existing best evidence is consumed;
- current source anchors, structural consistency and media/revision requirements still fail
  closed;
- user corrections remain normal source revisions and are still consumed by the V1 composer.

This keeps the migration narrow while FlowState/legacy ReviewCenter are moved away from
content-gating separately.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from engine.app.breakdown_read_model_contract_v1 import BreakdownReadModelV1
from engine.app.breakdown_read_model_v1 import load_episode_breakdown_read_model_v1
from engine.app.shot_revision_v2 import ShotRevisionItem
from engine.app.source_dialogue_speaker_override_v1 import load_episode_source_dialogue_speaker_overrides_v1
from engine.app.source_drama_snapshot_contract_v1 import SourceDramaEpisodeSnapshotV1
from engine.app.source_drama_snapshot_v1 import (
    SourceDramaSnapshotError,
    compose_episode_source_drama_snapshot_v1,
    compose_project_source_drama_snapshot_v1,
    source_drama_episode_fingerprint,
)
from engine.app.studio_v2 import Episode, Project, get_session


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value and value.strip()))


def _append_policy_warnings(snapshot: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    if not warnings:
        return snapshot
    result = dict(snapshot)
    result["warnings"] = _dedupe([*(result.get("warnings") or []), *warnings])
    result["status"] = "READY_WITH_WARNINGS"
    # warnings/status are intentionally omitted from the source fact fingerprint, but
    # recalculate through the canonical helper so this property stays explicit/testable.
    result["source_fingerprint"] = source_drama_episode_fingerprint(result)
    return SourceDramaEpisodeSnapshotV1.model_validate(result).model_dump(mode="json")


def load_episode_source_drama_snapshot_auto_v2(
    episode_id: str,
    *,
    infer_speakers: bool = True,
) -> dict[str, Any] | None:
    """Load current source truth without turning ordinary content uncertainty into a gate."""

    read_model_raw = load_episode_breakdown_read_model_v1(episode_id)
    if read_model_raw is None:
        return None
    read_model = BreakdownReadModelV1.model_validate(read_model_raw)
    if not read_model.timeline.is_current:
        raise SourceDramaSnapshotError("SourceDramaSnapshot only consumes the current Breakdown result")

    policy_warnings: list[str] = []
    presence_count = len(read_model.presence_review)
    if presence_count:
        policy_warnings.append(
            f"{presence_count} 个镜头仍有出镜人物覆盖不确定项，已按当前最佳原片事实继续；可稍后纠错"
        )

    # V1 compose currently interprets presence_review as a mandatory human gate.  Under the
    # new automatic policy it remains evidence/UI metadata, not a source-truth blocker.
    compose_payload = read_model.model_dump(mode="json")
    compose_payload["presence_review"] = []
    speaker_overrides = load_episode_source_dialogue_speaker_overrides_v1(episode_id)

    with get_session() as session:
        episode = session.get(Episode, episode_id)
        if episode is None:
            raise LookupError("Episode 不存在")
        project = session.get(Project, episode.project_id)
        if project is None:
            raise LookupError("Project 不存在")
        items = list(session.scalars(
            select(ShotRevisionItem)
            .where(ShotRevisionItem.revision_id == read_model.timeline.source_shot_revision_id)
            .order_by(ShotRevisionItem.ordinal)
        ).all())
        item_map = {item.ordinal: item for item in items}
        snapshot = compose_episode_source_drama_snapshot_v1(
            compose_payload,
            project_id=project.id,
            episode_id=episode.id,
            episode_title=episode.title,
            episode_order=episode.sort_order,
            source_language=project.source_language,
            revision_items_by_ordinal=item_map,
            speaker_overrides=speaker_overrides,
            infer_speakers=infer_speakers,
        )
    return _append_policy_warnings(snapshot, policy_warnings)


def load_project_source_drama_snapshot_auto_v2(project_id: str) -> dict[str, Any]:
    """Project-level counterpart using only current automatic-policy Episode snapshots."""

    with get_session() as session:
        project = session.get(Project, project_id)
        if project is None:
            raise LookupError("Project 不存在")
        episode_ids = list(session.scalars(
            select(Episode.id).where(Episode.project_id == project_id).order_by(Episode.sort_order)
        ).all())
        project_name = project.name
        source_language = project.source_language

    if not episode_ids:
        raise SourceDramaSnapshotError("项目还没有剧集")

    snapshots: list[dict[str, Any]] = []
    missing: list[str] = []
    for episode_id in episode_ids:
        snapshot = load_episode_source_drama_snapshot_auto_v2(episode_id)
        if snapshot is None:
            missing.append(episode_id)
        else:
            snapshots.append(snapshot)
    if missing:
        raise SourceDramaSnapshotError(
            f"{len(missing)} 个 Episode 还没有当前可消费的原片理解结果"
        )

    return compose_project_source_drama_snapshot_v1(
        project_id=project_id,
        project_name=project_name,
        source_language=source_language,
        episodes=snapshots,
    )


__all__ = [
    "load_episode_source_drama_snapshot_auto_v2",
    "load_project_source_drama_snapshot_auto_v2",
]
