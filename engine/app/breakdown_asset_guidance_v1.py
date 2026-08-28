"""P4.1 Breakdown Draft -> asset-side search guidance adapter.

This module is deliberately read-only with respect to Breakdown data and Final assets.
It exposes only current, revision-safe semantic hints for the existing Scene/Prop
Evidence pipeline.

Safety rules:
- only READY / READY_WITH_WARNINGS BreakdownRun with is_current=true;
- BreakdownRun.source_shot_revision_id must equal the Episode current ShotRevision;
- ShotSemanticDraft must point at a ShotRevisionItem from that exact revision;
- ShotRevisionItem.original_shot_id must still be a current Shot in the Episode;
- Draft scene/prop text remains a soft search prior, never Final Scene/Prop truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from sqlalchemy import select

from engine.app.breakdown_models_v1 import (
    BreakdownRun,
    DraftPropHint,
    DraftPropOccurrence,
    SceneSegmentDraft,
    ShotSemanticDraft,
)
from engine.app.shot_revision_v2 import ShotRevision, ShotRevisionItem
from engine.app.studio_v2 import Episode, Shot, get_session

GUIDANCE_PROFILE = "breakdown-asset-guidance-p4-v1"
_CONSUMABLE_RUN_STATUSES = ("READY", "READY_WITH_WARNINGS")


@dataclass(frozen=True)
class SceneSearchGuide:
    breakdown_run_id: str
    scene_segment_id: str
    location_hint: str | None
    interior_exterior: str
    time_of_day: str
    summary: str | None
    environment_description: str | None


@dataclass(frozen=True)
class PropSearchGuide:
    breakdown_run_id: str
    prop_hint_id: str
    occurrence_id: str
    label_hint: str
    normalized_hint: str | None
    importance: str
    narrative_reason: str | None
    source_start_us: int
    source_end_us: int
    screen_position_hint: str | None
    interaction_summary: str | None
    confidence: float | None


@dataclass(frozen=True)
class ShotAssetGuidance:
    shot_id: str
    episode_id: str
    shot_revision_id: str
    shot_revision_item_id: str
    breakdown_run_id: str
    scene: SceneSearchGuide | None
    props: tuple[PropSearchGuide, ...]


@dataclass(frozen=True)
class ProjectAssetGuidance:
    project_id: str
    profile: str
    shots: Mapping[str, ShotAssetGuidance]
    breakdown_run_ids: tuple[str, ...]
    skipped_episode_ids: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def guided_shot_count(self) -> int:
        return len(self.shots)

    @property
    def prop_target_count(self) -> int:
        return sum(len(item.props) for item in self.shots.values())


def _text(value: object, *, max_len: int = 2000) -> str | None:
    text = " ".join(str(value or "").strip().split())
    return text[:max_len] if text else None


def _current_breakdown_run(session: object, project_id: str, episode_id: str, revision_id: str) -> BreakdownRun | None:
    # ``session`` is a SQLAlchemy Session; object keeps this small adapter free of a
    # second Session type import and mirrors the project's existing service style.
    return session.scalar(  # type: ignore[attr-defined]
        select(BreakdownRun)
        .where(
            BreakdownRun.project_id == project_id,
            BreakdownRun.episode_id == episode_id,
            BreakdownRun.source_shot_revision_id == revision_id,
            BreakdownRun.is_current.is_(True),
            BreakdownRun.status.in_(_CONSUMABLE_RUN_STATUSES),
        )
        .order_by(BreakdownRun.completed_at.desc(), BreakdownRun.started_at.desc())
        .limit(1)
    )


def load_project_asset_guidance(project_id: str) -> ProjectAssetGuidance:
    """Load revision-safe current Breakdown hints for current project Shots.

    Missing Draft is a normal state. The caller can fall back to the legacy unguided
    asset semantics path. Stale/history Draft is never silently remapped by ordinal or
    timestamps because doing so would turn a historical semantic guess into current
    asset evidence.
    """

    shot_guidance: dict[str, ShotAssetGuidance] = {}
    run_ids: list[str] = []
    skipped_episode_ids: list[str] = []
    warnings: list[str] = []

    with get_session() as session:
        episodes = list(session.scalars(
            select(Episode)
            .where(Episode.project_id == project_id)
            .order_by(Episode.sort_order, Episode.id)
        ).all())

        for episode in episodes:
            revision = session.scalar(
                select(ShotRevision).where(
                    ShotRevision.episode_id == episode.id,
                    ShotRevision.is_current.is_(True),
                )
            )
            if revision is None:
                skipped_episode_ids.append(episode.id)
                continue

            run = _current_breakdown_run(session, project_id, episode.id, revision.id)
            if run is None:
                skipped_episode_ids.append(episode.id)
                continue
            run_ids.append(run.id)

            current_shots = {
                item.id: item
                for item in session.scalars(
                    select(Shot).where(Shot.episode_id == episode.id)
                ).all()
            }
            revision_items = list(session.scalars(
                select(ShotRevisionItem)
                .where(ShotRevisionItem.revision_id == revision.id)
                .order_by(ShotRevisionItem.ordinal)
            ).all())
            items_by_id = {item.id: item for item in revision_items}

            scenes = {
                item.id: item
                for item in session.scalars(
                    select(SceneSegmentDraft).where(SceneSegmentDraft.run_id == run.id)
                ).all()
            }
            drafts = list(session.scalars(
                select(ShotSemanticDraft)
                .where(ShotSemanticDraft.run_id == run.id)
                .order_by(ShotSemanticDraft.shot_ordinal_snapshot)
            ).all())
            drafts_by_id = {item.id: item for item in drafts}

            prop_hints = {
                item.id: item
                for item in session.scalars(
                    select(DraftPropHint).where(DraftPropHint.run_id == run.id)
                ).all()
            }
            occurrences_by_draft: dict[str, list[DraftPropOccurrence]] = {}
            if prop_hints:
                occurrences = list(session.scalars(
                    select(DraftPropOccurrence)
                    .where(DraftPropOccurrence.prop_hint_id.in_(tuple(prop_hints)))
                    .order_by(DraftPropOccurrence.source_start_us, DraftPropOccurrence.id)
                ).all())
                for occurrence in occurrences:
                    occurrences_by_draft.setdefault(occurrence.shot_draft_id, []).append(occurrence)

            for draft in drafts:
                item = items_by_id.get(draft.source_shot_revision_item_id)
                if item is None:
                    warnings.append(
                        f"Run {run.id} ShotDraft {draft.id} 不属于当前 ShotRevision，P4 已忽略"
                    )
                    continue
                if draft.source_shot_id_snapshot != item.original_shot_id:
                    warnings.append(
                        f"Run {run.id} ShotDraft {draft.id} 的 Shot snapshot 与 RevisionItem 不一致，P4 已忽略"
                    )
                    continue
                current_shot = current_shots.get(item.original_shot_id)
                if current_shot is None:
                    warnings.append(
                        f"Run {run.id} RevisionItem {item.id} 对应 Shot 已不存在，P4 已忽略"
                    )
                    continue

                segment = scenes.get(draft.scene_segment_id)
                scene_guide = None
                if segment is not None:
                    scene_guide = SceneSearchGuide(
                        breakdown_run_id=run.id,
                        scene_segment_id=segment.id,
                        location_hint=_text(segment.location_hint, max_len=255),
                        interior_exterior=str(segment.interior_exterior or "UNKNOWN"),
                        time_of_day=str(segment.time_of_day or "UNKNOWN"),
                        summary=_text(segment.summary),
                        environment_description=_text(segment.environment_description),
                    )

                prop_guides: list[PropSearchGuide] = []
                for occurrence in occurrences_by_draft.get(draft.id, []):
                    hint = prop_hints.get(occurrence.prop_hint_id)
                    if hint is None:
                        continue
                    label = _text(hint.label_hint, max_len=255)
                    if not label:
                        continue
                    prop_guides.append(PropSearchGuide(
                        breakdown_run_id=run.id,
                        prop_hint_id=hint.id,
                        occurrence_id=occurrence.id,
                        label_hint=label,
                        normalized_hint=_text(hint.normalized_hint, max_len=255),
                        importance=str(hint.importance or "UNKNOWN"),
                        narrative_reason=_text(hint.narrative_reason),
                        source_start_us=int(occurrence.source_start_us),
                        source_end_us=int(occurrence.source_end_us),
                        screen_position_hint=_text(occurrence.screen_position_hint, max_len=64),
                        interaction_summary=_text(occurrence.interaction_summary),
                        confidence=(float(occurrence.confidence) if occurrence.confidence is not None else None),
                    ))

                shot_guidance[current_shot.id] = ShotAssetGuidance(
                    shot_id=current_shot.id,
                    episode_id=episode.id,
                    shot_revision_id=revision.id,
                    shot_revision_item_id=item.id,
                    breakdown_run_id=run.id,
                    scene=scene_guide,
                    props=tuple(prop_guides),
                )

    return ProjectAssetGuidance(
        project_id=project_id,
        profile=GUIDANCE_PROFILE,
        shots=shot_guidance,
        breakdown_run_ids=tuple(dict.fromkeys(run_ids)),
        skipped_episode_ids=tuple(dict.fromkeys(skipped_episode_ids)),
        warnings=tuple(warnings),
    )


def serialize_project_asset_guidance(guidance: ProjectAssetGuidance) -> dict[str, object]:
    """Compact diagnostics payload; contains hints/provenance but no Final bindings."""

    return {
        "profile": guidance.profile,
        "project_id": guidance.project_id,
        "guided_shot_count": guidance.guided_shot_count,
        "prop_target_count": guidance.prop_target_count,
        "breakdown_run_ids": list(guidance.breakdown_run_ids),
        "skipped_episode_ids": list(guidance.skipped_episode_ids),
        "warnings": list(guidance.warnings),
    }
