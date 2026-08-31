from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from engine.app import breakdown_g1_fusion_replay_v1 as replay
from engine.app import breakdown_p2_fusion_episode_v2 as e1
from engine.app import breakdown_p2_fusion_episode_v4 as e4
from engine.app import breakdown_p2_fusion_v1 as legacy
from engine.app import breakdown_p2_sidecar_v1 as p2


def shot(ordinal: int) -> p2.P2ShotInput:
    return p2.P2ShotInput(
        revision_item_id=f"ITEM_{ordinal}",
        original_shot_id=f"SHOT_{ordinal}",
        ordinal=ordinal,
        start_us=(ordinal - 1) * 1_000_000,
        end_us=ordinal * 1_000_000,
        duration_us=1_000_000,
        reference_clip_path=f"unused-{ordinal}.mp4",
        thumbnail_path=None,
        keyframes=(),
    )


def semantic(location: str, subjects: list[dict] | None = None) -> dict:
    return {
        "scene": {
            "location_hint": location,
            "interior_exterior": "INT",
            "time_of_day": "白天",
            "environment_description": "",
        },
        "shot": {"summary": "fixture"},
        "subjects": subjects or [],
        "events": [],
        "props": [],
    }


def record(item: p2.P2ShotInput, location: str) -> p2.P2EvidenceRecord:
    return p2.P2EvidenceRecord(
        source_type="VLM_OUTPUT",
        source_id=f"VLM_{item.ordinal}",
        source_start_us=item.start_us,
        source_end_us=item.end_us,
        shot_revision_item_id=item.revision_item_id,
        payload={"semantic": semantic(location)},
    )


def subject(label: str, appearance: str) -> dict:
    return {
        "label": label,
        "appearance_summary": appearance,
        "activity_summary": "",
        "screen_position": "",
        "visibility": "FULL",
        "speaking_state": "UNKNOWN",
    }


def test_replay_script_bootstraps_repo_root_when_run_directly(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    script = repo_root / "scripts" / "replay_breakdown_g1_fusion.py"

    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Read-only G1 Fusion replay" in completed.stdout


def test_corridor_qualifier_drift_does_not_split_without_direct_new_scene() -> None:
    shots = tuple(shot(index) for index in range(1, 4))
    records = {
        shots[0].revision_item_id: record(shots[0], "公寓走廊"),
        shots[1].revision_item_id: record(shots[1], "酒店走廊"),
        shots[2].revision_item_id: record(shots[2], "公寓楼道"),
    }

    details = replay._candidate_scene_plans(shots, records, [])

    assert len(details) == 1
    assert [item.ordinal for item in details[0][0].shots] == [1, 2, 3]


def test_direct_window_new_scene_still_splits_same_corridor_family() -> None:
    shots = (shot(1), shot(2))
    records = {
        shots[0].revision_item_id: record(shots[0], "公寓走廊"),
        shots[1].revision_item_id: record(shots[1], "酒店走廊"),
    }
    windows = [{
        "shot_scene_hints": [{
            "ordinal": 2,
            "scene_continuity": "NEW_SCENE",
            "scene_basis": "DIRECT",
        }]
    }]

    details = replay._candidate_scene_plans(shots, records, windows)

    assert len(details) == 2


def test_corridor_to_living_room_remains_strong_scene_change() -> None:
    left = e1._scene_hint(semantic("公寓走廊"))
    right = e1._scene_hint(semantic("客厅"))

    assert replay._strong_scene_change(left, right) is True


def test_strong_stable_appearance_can_bridge_three_shot_reappearance_gap() -> None:
    observations = [
        e4.SubjectObservation("ITEM_24", 24, "subject_B", "年轻男性，黑色短发，黑色西装，白色衬衫"),
        e4.SubjectObservation("ITEM_27", 27, "subject_B", "年轻男性，黑色短发，黑色西装，白色衬衫"),
    ]

    assert replay._candidate_fallback_pairs(observations) == [(0, 1)]


def test_ambiguous_gap_bridge_does_not_force_same_gender_people_together() -> None:
    observations = [
        e4.SubjectObservation("ITEM_24", 24, "subject_A", "年轻女性，黑色长发，白色上衣，黑色裤子"),
        e4.SubjectObservation("ITEM_24", 24, "subject_B", "年轻女性，黑色长发，白色上衣，黑色裤子"),
        e4.SubjectObservation("ITEM_27", 27, "subject_A", "年轻女性，黑色长发，白色上衣，黑色裤子"),
        e4.SubjectObservation("ITEM_27", 27, "subject_B", "年轻女性，黑色长发，白色上衣，黑色裤子"),
    ]

    assert replay._candidate_fallback_pairs(observations) == []


def test_candidate_clusters_preserve_same_shot_hard_cannot_link() -> None:
    shots = [shot(1), shot(2), shot(3)]
    plan = legacy._SegmentPlan(
        index=1,
        shots=shots,
        semantics=[
            semantic("客厅", [
                subject("subject_A", "年轻女性，黑色长发，白色上衣"),
                subject("subject_B", "年轻女性，黑色长发，白色上衣"),
            ]),
            semantic("客厅", [subject("subject_A", "年轻女性，黑色长发，白色上衣")]),
            semantic("客厅", [subject("subject_A", "年轻女性，黑色长发，白色上衣")]),
        ],
    )
    windows = [{
        "subject_continuity_hints": [{
            "appearance_summary": "年轻女性，黑色长发，白色上衣",
            "shot_ordinals": [1, 2, 3],
            "members": [
                {"revision_item_id": "ITEM_1", "label": "subject_A"},
                {"revision_item_id": "ITEM_2", "label": "subject_A"},
                {"revision_item_id": "ITEM_1", "label": "subject_B"},
                {"revision_item_id": "ITEM_3", "label": "subject_A"},
            ],
        }]
    }]

    clusters, conflicts = replay._candidate_clusters(plan, windows)

    assert conflicts == 0
    assert all(item["same_shot_conflicts"] == 0 for item in clusters)
    assert len(clusters) >= 2
