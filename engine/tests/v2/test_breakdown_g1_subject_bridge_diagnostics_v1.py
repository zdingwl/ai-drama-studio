from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from engine.app import breakdown_g1_subject_bridge_diagnostics_v1 as diag


def cluster(label: str, rows: list[tuple[int, str]]) -> dict:
    return {
        "display_label": label,
        "shot_ordinals": [shot for shot, _appearance in rows],
        "source_members": [
            {
                "revision_item_id": f"ITEM_{shot}",
                "shot_ordinal": shot,
                "label": "subject_A",
                "appearance_summary": appearance,
            }
            for shot, appearance in rows
        ],
    }


def test_bridge_diagnostics_expose_common_cannot_link_neighbor() -> None:
    clusters = [
        cluster("人物C", [
            (16, "年轻女性，黑色长发，白色上衣"),
            (18, "年轻女性，黑色长发，白色上衣"),
            (27, "年轻女性，黑色长发，白色上衣"),
            (30, "年轻女性，黑色长发，白色上衣"),
        ]),
        cluster("人物D", [
            (16, "年轻男性，黑色短发，黑色西装，白色衬衫"),
            (24, "年轻男性，黑色短发，黑色西装，白色衬衫"),
        ]),
        cluster("人物E", [
            (27, "年轻男性，黑色短发，黑色西装，白色衬衫"),
            (29, "年轻男性，黑色短发，黑色西装，白色衬衫"),
        ]),
    ]

    _profiles, bridges = diag._bridge_candidates(clusters)
    bridge = next(item for item in bridges if {item["left"], item["right"]} == {"人物D", "人物E"})

    assert bridge["gap_shots"] == 3
    assert bridge["gender_conflict"] is False
    assert bridge["common_cannot_link_neighbors"] == ["人物C"]
    assert bridge["support_4_strong2"] >= 1


def test_bridge_diagnostics_mark_gender_conflict() -> None:
    clusters = [
        cluster("人物A", [(1, "年轻女性，黑色长发，白色上衣")]),
        cluster("人物B", [(2, "年轻男性，黑色短发，黑色西装")]),
    ]

    _profiles, bridges = diag._bridge_candidates(clusters)

    assert len(bridges) == 1
    assert bridges[0]["gender_conflict"] is True
    assert bridges[0]["max_score"] is None


def test_subject_bridge_script_bootstraps_repo_root(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    script = repo_root / "scripts" / "inspect_breakdown_g1_subject_bridges.py"

    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "subject bridge diagnostics" in completed.stdout
