from __future__ import annotations

from engine.app import breakdown_g1_fusion_replay_v4 as replay
from engine.app import breakdown_g1_subject_hint_resolver_v2 as resolver
from engine.app import breakdown_p2_fusion_episode_v4 as e4
from engine.app import breakdown_p2_fusion_v1 as legacy
from engine.app import breakdown_p2_sidecar_v1 as p2


def shot(ordinal: int) -> p2.P2ShotInput:
    return p2.P2ShotInput(
        revision_item_id=f"ITEM_{ordinal}", original_shot_id=f"SHOT_{ordinal}", ordinal=ordinal,
        start_us=(ordinal - 1) * 1_000_000, end_us=ordinal * 1_000_000,
        duration_us=1_000_000, reference_clip_path="unused.mp4", thumbnail_path=None, keyframes=(),
    )


def subj(label: str, appearance: str) -> dict:
    return {"label": label, "appearance_summary": appearance, "activity_summary": "",
            "screen_position": "", "visibility": "FULL", "speaking_state": "UNKNOWN"}


def sem(subjects: list[dict]) -> dict:
    return {"scene": {"location_hint": "客厅", "interior_exterior": "INT", "time_of_day": "白天",
                      "environment_description": ""},
            "shot": {"summary": "fixture"}, "subjects": subjects, "events": [], "props": []}


def hint(appearance: str, ordinals: list[int]) -> dict:
    return {"appearance_summary": appearance, "continuity_summary": "", "shot_ordinals": ordinals,
            "members": []}


def test_single_visible_person_is_not_auto_bound_when_appearance_conflicts() -> None:
    observations = [e4.SubjectObservation("ITEM_14", 14, "subject_A", "黑发男子，灰卫衣")]
    indexes = {item.node_id: index for index, item in enumerate(observations)}
    assert resolver.resolve_hint_nodes(hint("穿白色露肩上衣的女性", [14]), observations, indexes) == []


def test_compact_aliases_gray_hoodie_and_white_offshoulder_resolve() -> None:
    observations = [
        e4.SubjectObservation("ITEM_16", 16, "subject_A", "长发，白露肩上衣"),
        e4.SubjectObservation("ITEM_16", 16, "subject_B", "灰衣，短发"),
        e4.SubjectObservation("ITEM_17", 17, "subject_A", "短发，灰卫衣"),
    ]
    indexes = {item.node_id: index for index, item in enumerate(observations)}
    assert resolver.resolve_hint_nodes(hint("穿白色露肩上衣的女性", [16]), observations, indexes) == [0]
    assert resolver.resolve_hint_nodes(hint("穿灰色连帽衫的男性", [16, 17]), observations, indexes) == [1, 2]


def test_replay_v4_does_not_cross_bind_alternating_single_person_shots() -> None:
    shots = [shot(i) for i in range(1, 7)]
    semantics = [
        sem([subj("subject_A", "白衣女性，长发"), subj("subject_B", "灰衣男子，短发")]),
        sem([subj("subject_A", "黑发男子，灰卫衣")]),
        sem([subj("subject_A", "黑发女性，白露肩上衣")]),
        sem([subj("subject_A", "长发，白露肩上衣"), subj("subject_B", "灰衣，短发")]),
        sem([subj("subject_A", "短发，灰连帽衫")]),
        sem([subj("subject_A", "长发，白上衣")]),
    ]
    plan = legacy._SegmentPlan(index=1, shots=shots, semantics=semantics)
    windows = [{"window_id": "window-1", "subject_continuity_hints": [
        hint("穿白色露肩上衣的女性", [1, 2, 3, 4, 5, 6]),
        hint("穿灰色连帽衫的男性", [1, 2, 3, 4, 5, 6]),
    ]}]

    clusters, conflicts = replay._candidate_clusters(plan, windows)

    assert conflicts == 0
    assert len(clusters) == 2
    assert sorted(item["shot_ordinals"] for item in clusters) == [[1, 2, 4, 5], [1, 3, 4, 6]]


def test_replay_v4_keeps_same_shot_cannot_link() -> None:
    shots = [shot(1), shot(2)]
    plan = legacy._SegmentPlan(index=1, shots=shots, semantics=[
        sem([subj("subject_A", "白衣女性，长发"), subj("subject_B", "白衣女性，长发")]),
        sem([subj("subject_A", "白衣女性，长发")]),
    ])
    windows = [{"window_id": "window-1", "subject_continuity_hints": [hint("穿白色上衣的女性", [1, 2])]}]

    _clusters, conflicts = replay._candidate_clusters(plan, windows)

    assert conflicts == 0
