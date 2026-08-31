"""P5 deterministic Breakdown LocalSubject -> Final Character bridge.

Identity authority is one-way:

    Final ShotCharacterBinding -> P5 reconciliation -> anonymous Breakdown display

Breakdown prose, dialogue, role hints and appearance hints never create or override a
Character identity.  The bridge is read-only and fail-closed.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select

from engine.app.asset_workspace_v3 import AssetRevision, ShotCharacterBinding
from engine.app.breakdown_character_bridge_contract_v1 import (
    BREAKDOWN_CHARACTER_BRIDGE_PROFILE,
    BreakdownCharacterPersonResolutionV1,
    BreakdownCharacterResolutionPayloadV1,
    BreakdownCharacterSceneResolutionV1,
)
from engine.app.breakdown_models_v1 import (
    BreakdownRun,
    LocalSubject,
    SceneSegmentDraft,
    ShotLocalSubject,
    ShotSemanticDraft,
)
from engine.app.shot_revision_v2 import ShotRevision, ShotRevisionItem
from engine.app.studio_v2 import Character, Episode, Shot, get_session


_CONSUMABLE_RUN_STATUSES = ("READY", "READY_WITH_WARNINGS")
RESOLVED_BASIS = "FINAL_SHOT_BINDING_SIGNATURE_V1"
UNRESOLVED_EMPTY = "NO_ANONYMOUS_SHOT_PRESENCE"
UNRESOLVED_ANON_DUPLICATE = "ANONYMOUS_SIGNATURE_NOT_UNIQUE"
UNRESOLVED_NO_CHARACTER = "NO_MATCHING_FINAL_CHARACTER_SIGNATURE"
UNRESOLVED_CHARACTER_DUPLICATE = "FINAL_CHARACTER_SIGNATURE_NOT_UNIQUE"


class BreakdownCharacterBridgeError(RuntimeError):
    """Current Breakdown / ShotRevision anchors are unsafe for P5 consumption."""


@dataclass(frozen=True)
class SubjectPresenceSignature:
    local_subject_id: str
    local_subject_ordinal: int
    local_display_name: str
    scene_person_ref: str
    shot_ids: frozenset[str]


@dataclass(frozen=True)
class CharacterPresenceSignature:
    character_id: str
    character_name: str
    shot_ids: frozenset[str]


def _ordered_support(signature: frozenset[str], shot_ordinals: dict[str, int]) -> tuple[list[str], list[int]]:
    rows = sorted(
        ((shot_ordinals[shot_id], shot_id) for shot_id in signature if shot_id in shot_ordinals),
        key=lambda item: (item[0], item[1]),
    )
    return [shot_id for _ordinal, shot_id in rows], [ordinal for ordinal, _shot_id in rows]


def resolve_scene_presence_signatures_v1(
    *,
    subjects: Iterable[SubjectPresenceSignature],
    characters: Iterable[CharacterPresenceSignature],
    shot_ordinals: dict[str, int],
) -> list[BreakdownCharacterPersonResolutionV1]:
    """Resolve unique Scene-local presence signatures against Final Character bindings.

    Shots where no LocalSubject is recognized are intentionally ignored when projecting
    Character signatures.  They cannot distinguish one anonymous LocalSubject from
    another, so treating them as contradictions would only punish Breakdown recall.
    """

    subject_rows = list(subjects)
    character_rows = list(characters)
    subject_aware_shots = frozenset().union(*(item.shot_ids for item in subject_rows)) if subject_rows else frozenset()

    subjects_by_signature: dict[frozenset[str], list[SubjectPresenceSignature]] = defaultdict(list)
    for item in subject_rows:
        subjects_by_signature[item.shot_ids].append(item)

    characters_by_signature: dict[frozenset[str], list[CharacterPresenceSignature]] = defaultdict(list)
    for item in character_rows:
        projected = item.shot_ids & subject_aware_shots
        if projected:
            characters_by_signature[projected].append(item)

    output: list[BreakdownCharacterPersonResolutionV1] = []
    for subject in sorted(subject_rows, key=lambda item: (item.local_subject_ordinal, item.local_subject_id)):
        support_ids, support_ordinals = _ordered_support(subject.shot_ids, shot_ordinals)
        status = "UNRESOLVED"
        character_id: str | None = None
        character_name: str | None = None

        if not subject.shot_ids:
            basis = UNRESOLVED_EMPTY
        elif len(subjects_by_signature[subject.shot_ids]) != 1:
            basis = UNRESOLVED_ANON_DUPLICATE
        else:
            candidates = characters_by_signature.get(subject.shot_ids, [])
            if not candidates:
                basis = UNRESOLVED_NO_CHARACTER
            elif len(candidates) != 1:
                basis = UNRESOLVED_CHARACTER_DUPLICATE
            else:
                matched = candidates[0]
                status = "RESOLVED"
                character_id = matched.character_id
                character_name = matched.character_name
                basis = RESOLVED_BASIS

        output.append(BreakdownCharacterPersonResolutionV1(
            scene_person_ref=subject.scene_person_ref,
            local_subject_id=subject.local_subject_id,
            local_subject_ordinal=subject.local_subject_ordinal,
            local_display_name=subject.local_display_name,
            status=status,
            character_id=character_id,
            character_name=character_name,
            support_shot_ids=support_ids,
            support_shot_ordinals=support_ordinals,
            resolution_basis=basis,
        ))
    return output


def _current_breakdown_run(session: object, episode: Episode, revision: ShotRevision) -> BreakdownRun | None:
    return session.scalar(  # type: ignore[attr-defined]
        select(BreakdownRun)
        .where(
            BreakdownRun.project_id == episode.project_id,
            BreakdownRun.episode_id == episode.id,
            BreakdownRun.source_shot_revision_id == revision.id,
            BreakdownRun.is_current.is_(True),
            BreakdownRun.status.in_(_CONSUMABLE_RUN_STATUSES),
        )
        .order_by(BreakdownRun.completed_at.desc(), BreakdownRun.started_at.desc())
        .limit(1)
    )


def _validate_and_map_drafts(
    *,
    drafts: list[ShotSemanticDraft],
    items_by_id: dict[str, ShotRevisionItem],
    current_shots: dict[str, Shot],
) -> tuple[dict[str, str], dict[str, int]]:
    draft_to_shot: dict[str, str] = {}
    shot_ordinals: dict[str, int] = {}
    for draft in drafts:
        item = items_by_id.get(draft.source_shot_revision_item_id)
        if item is None:
            raise BreakdownCharacterBridgeError(
                f"ShotDraft {draft.id} 不属于当前 ShotRevision，P5 已拒绝解析"
            )
        if draft.source_shot_id_snapshot != item.original_shot_id:
            raise BreakdownCharacterBridgeError(
                f"ShotDraft {draft.id} 的 Shot snapshot 与 RevisionItem 不一致，P5 已拒绝解析"
            )
        shot = current_shots.get(item.original_shot_id)
        if shot is None:
            raise BreakdownCharacterBridgeError(
                f"RevisionItem {item.id} 对应当前 Shot 已不存在，P5 已拒绝解析"
            )
        draft_to_shot[draft.id] = shot.id
        shot_ordinals[shot.id] = int(item.ordinal)
    return draft_to_shot, shot_ordinals


def load_episode_character_resolution_v1(episode_id: str) -> BreakdownCharacterResolutionPayloadV1 | None:
    """Build current revision-safe P5 resolution for one Episode.

    Missing current consumable Breakdown is a normal `None` state.  Unsafe anchors raise
    an explicit error instead of remapping historical semantics to current Shots.
    """

    with get_session() as session:
        episode = session.get(Episode, episode_id)
        if episode is None:
            raise LookupError("剧集不存在")

        revision = session.scalar(select(ShotRevision).where(
            ShotRevision.episode_id == episode.id,
            ShotRevision.is_current.is_(True),
        ))
        if revision is None:
            return None

        run = _current_breakdown_run(session, episode, revision)
        if run is None:
            return None

        revision_items = list(session.scalars(
            select(ShotRevisionItem)
            .where(ShotRevisionItem.revision_id == revision.id)
            .order_by(ShotRevisionItem.ordinal)
        ).all())
        items_by_id = {item.id: item for item in revision_items}
        current_shots = {
            shot.id: shot
            for shot in session.scalars(select(Shot).where(Shot.episode_id == episode.id)).all()
        }
        drafts = list(session.scalars(
            select(ShotSemanticDraft)
            .where(ShotSemanticDraft.run_id == run.id)
            .order_by(ShotSemanticDraft.shot_ordinal_snapshot, ShotSemanticDraft.id)
        ).all())
        draft_to_shot, shot_ordinals = _validate_and_map_drafts(
            drafts=drafts,
            items_by_id=items_by_id,
            current_shots=current_shots,
        )

        segments = list(session.scalars(
            select(SceneSegmentDraft)
            .where(SceneSegmentDraft.run_id == run.id)
            .order_by(SceneSegmentDraft.ordinal, SceneSegmentDraft.id)
        ).all())
        subjects = list(session.scalars(
            select(LocalSubject)
            .where(LocalSubject.run_id == run.id)
            .order_by(LocalSubject.scene_segment_id, LocalSubject.ordinal, LocalSubject.id)
        ).all())
        presences = list(session.scalars(
            select(ShotLocalSubject).where(ShotLocalSubject.run_id == run.id)
        ).all())

        draft_by_id = {draft.id: draft for draft in drafts}
        subject_by_id = {subject.id: subject for subject in subjects}
        subject_shots: dict[str, set[str]] = defaultdict(set)
        for presence in presences:
            subject = subject_by_id.get(presence.local_subject_id)
            draft = draft_by_id.get(presence.shot_draft_id)
            if subject is None or draft is None:
                raise BreakdownCharacterBridgeError("ShotLocalSubject 引用了当前 Run 之外的数据")
            if subject.scene_segment_id != draft.scene_segment_id:
                raise BreakdownCharacterBridgeError("ShotLocalSubject 跨 Scene 关联，P5 已拒绝解析")
            shot_id = draft_to_shot.get(draft.id)
            if not shot_id:
                raise BreakdownCharacterBridgeError("ShotLocalSubject 无法解析到当前 Shot")
            subject_shots[subject.id].add(shot_id)

        current_asset_revision = session.scalar(select(AssetRevision).where(
            AssetRevision.project_id == episode.project_id,
            AssetRevision.is_current.is_(True),
        ))

        all_current_shot_ids = tuple(current_shots)
        bindings = list(session.scalars(
            select(ShotCharacterBinding).where(
                ShotCharacterBinding.project_id == episode.project_id,
                ShotCharacterBinding.shot_id.in_(all_current_shot_ids),
            )
        ).all()) if current_asset_revision is not None and all_current_shot_ids else []
        character_ids = tuple(dict.fromkeys(binding.character_id for binding in bindings))
        characters = {
            character.id: character
            for character in session.scalars(
                select(Character).where(
                    Character.project_id == episode.project_id,
                    Character.id.in_(character_ids),
                )
            ).all()
        } if character_ids else {}
        character_shots: dict[str, set[str]] = defaultdict(set)
        for binding in bindings:
            if binding.character_id in characters:
                character_shots[binding.character_id].add(binding.shot_id)

        drafts_by_segment: dict[str, list[ShotSemanticDraft]] = defaultdict(list)
        for draft in drafts:
            drafts_by_segment[draft.scene_segment_id].append(draft)
        subjects_by_segment: dict[str, list[LocalSubject]] = defaultdict(list)
        for subject in subjects:
            subjects_by_segment[subject.scene_segment_id].append(subject)

        scene_results: list[BreakdownCharacterSceneResolutionV1] = []
        warnings: list[str] = []
        if current_asset_revision is None:
            warnings.append("当前项目还没有可用的 Final Asset Revision，人物将保持未解析。")
        elif not bindings:
            warnings.append("当前剧集还没有 Final Character Shot 绑定，人物将保持未解析。")

        for segment in segments:
            scene_drafts = drafts_by_segment.get(segment.id, [])
            scene_shot_ids = {draft_to_shot[draft.id] for draft in scene_drafts if draft.id in draft_to_shot}
            scene_subjects = sorted(
                subjects_by_segment.get(segment.id, []),
                key=lambda item: (item.ordinal, item.id),
            )
            subject_signatures = [
                SubjectPresenceSignature(
                    local_subject_id=subject.id,
                    local_subject_ordinal=int(subject.ordinal),
                    local_display_name=f"人物{index}",
                    scene_person_ref=f"P{index}",
                    shot_ids=frozenset(subject_shots.get(subject.id, set()) & scene_shot_ids),
                )
                for index, subject in enumerate(scene_subjects, start=1)
            ]
            character_signatures = [
                CharacterPresenceSignature(
                    character_id=character_id,
                    character_name=characters[character_id].name,
                    shot_ids=frozenset(shots & scene_shot_ids),
                )
                for character_id, shots in sorted(character_shots.items())
                if character_id in characters and shots & scene_shot_ids
            ]
            people = resolve_scene_presence_signatures_v1(
                subjects=subject_signatures,
                characters=character_signatures,
                shot_ordinals=shot_ordinals,
            )
            resolved_count = sum(1 for item in people if item.status == "RESOLVED")
            scene_results.append(BreakdownCharacterSceneResolutionV1(
                scene_segment_id=segment.id,
                scene_ordinal=int(segment.ordinal),
                subject_aware_shot_count=len(set().union(*(item.shot_ids for item in subject_signatures))) if subject_signatures else 0,
                resolved_count=resolved_count,
                unresolved_count=len(people) - resolved_count,
                people=people,
            ))

        person_count = sum(len(scene.people) for scene in scene_results)
        resolved_count = sum(scene.resolved_count for scene in scene_results)
        return BreakdownCharacterResolutionPayloadV1(
            profile=BREAKDOWN_CHARACTER_BRIDGE_PROFILE,
            project_id=episode.project_id,
            episode_id=episode.id,
            breakdown_run_id=run.id,
            shot_revision_id=revision.id,
            asset_revision_id=current_asset_revision.id if current_asset_revision is not None else None,
            scene_count=len(scene_results),
            person_count=person_count,
            resolved_count=resolved_count,
            unresolved_count=person_count - resolved_count,
            warnings=warnings,
            scenes=scene_results,
        )


__all__ = [
    "BreakdownCharacterBridgeError",
    "CharacterPresenceSignature",
    "SubjectPresenceSignature",
    "load_episode_character_resolution_v1",
    "resolve_scene_presence_signatures_v1",
]
