from __future__ import annotations

from engine.app import breakdown_g1_subject_cluster_bridge_v2 as bridge
from engine.app import breakdown_p2_fusion_episode_v4 as e4


def obs(shot: int, label: str, appearance: str) -> e4.SubjectObservation:
    return e4.SubjectObservation(
        shot_revision_item_id=f"ITEM_{shot}",
        shot_ordinal=shot,
        label=label,
        appearance_summary=appearance,
    )


def _union_chain(uf: e4._UnionFind, indexes: list[int]) -> None:
    for left, right in zip(indexes, indexes[1:]):
        assert uf.union(left, right) is True


def _groups(uf: e4._UnionFind, size: int) -> list[set[int]]:
    grouped: dict[int, set[int]] = {}
    for index in range(size):
        grouped.setdefault(uf.find(index), set()).add(index)
    return sorted(grouped.values(), key=lambda item: (min(item), len(item)))


def test_real_scene_shape_converges_to_woman_and_man_without_same_shot_conflict() -> None:
    observations = [
        # A: early woman fragment.
        obs(13, "subject_A", "黑发长发，穿白色露肩上衣和白色阔腿裤。"),       # 0
        obs(15, "subject_A", "黑色长发，身穿白色露肩上衣和白色裤子。"),       # 1
        # B: early man fragment.
        obs(13, "subject_B", "黑发短发，穿灰色连帽衫，内搭白色T恤。"),          # 2
        obs(14, "subject_A", "短发，身穿灰色连帽衫，内搭白色T恤。"),            # 3
        # C: stable woman fragment; shares Shots with D/E/F and is their hard cannot-link co-star.
        obs(16, "subject_A", "长发女性，身穿白色露肩上衣，搭配白色裤子。"),       # 4
        obs(18, "subject_A", "长发女性，身穿白色露肩上衣和白色裤子。"),          # 5
        obs(27, "subject_A", "长发女性，身穿白色露肩上衣和白色裤子。"),          # 6
        obs(30, "subject_B", "长发女性，身穿白色露肩上衣和白色裤子。"),          # 7
        # D: main man fragment.
        obs(16, "subject_B", "短发男性，身穿灰色连帽衫，手持手机。"),             # 8
        obs(17, "subject_A", "短发男性，身穿灰色连帽衫，内搭白色T恤。"),          # 9
        obs(24, "subject_B", "短发男性，身穿灰色连帽衫，内搭白色T恤。"),          # 10
        # E: late man fragment.
        obs(27, "subject_B", "短发，身穿灰色连帽衫，低头看手机。"),              # 11
        obs(28, "subject_B", "短发，身穿灰色连帽衫，专注操作手机。"),            # 12
        obs(29, "subject_B", "短发，身穿灰色连帽衫。"),                         # 13
        # F: final one-Shot man fragment.
        obs(30, "subject_A", "短发，身穿灰色连帽衫，手指放在嘴边。"),            # 14
    ]
    uf = e4._UnionFind(observations)
    _union_chain(uf, [0, 1])
    _union_chain(uf, [2, 3])
    _union_chain(uf, [4, 5, 6, 7])
    _union_chain(uf, [8, 9, 10])
    _union_chain(uf, [11, 12, 13])

    accepted = bridge.apply_cluster_bridges(observations, uf)
    groups = _groups(uf, len(observations))

    assert len(accepted) >= 4
    assert len(groups) == 2
    assert {0, 1, 4, 5, 6, 7} in groups
    assert {2, 3, 8, 9, 10, 11, 12, 13, 14} in groups
    assert uf.rejected_cannot_link_count == 0


def test_equal_best_candidates_remain_unmerged_as_ambiguous() -> None:
    appearance = "短发，身穿灰色连帽衫，内搭白色T恤。"
    observations = [
        obs(2, "subject_A", appearance),
        obs(1, "subject_A", appearance),
        obs(3, "subject_A", appearance),
    ]
    uf = e4._UnionFind(observations)

    accepted = bridge.apply_cluster_bridges(observations, uf)

    assert accepted == []
    assert len(_groups(uf, len(observations))) == 3


def test_explicit_long_vs_short_hair_consensus_blocks_bridge() -> None:
    observations = [
        obs(1, "subject_A", "年轻女性，黑色长发，白色上衣，白色裤子"),
        obs(2, "subject_A", "年轻女性，黑色短发，白色上衣，白色裤子"),
    ]
    uf = e4._UnionFind(observations)

    accepted = bridge.apply_cluster_bridges(observations, uf)

    assert accepted == []
    assert len(_groups(uf, len(observations))) == 2
