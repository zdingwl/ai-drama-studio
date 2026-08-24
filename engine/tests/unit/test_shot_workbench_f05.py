from __future__ import annotations

from datetime import datetime, timezone

import pytest

from engine.app.shot_workbench import (
    FinalShotRecord,
    ShotWorkbenchError,
    _merge_origin_ids,
    _validate_final_timeline,
    generate_final_shot_id,
    generate_shot_edit_set_id,
)

NOW = datetime.now(timezone.utc)


def _shot(ordinal: int, start: int, end: int) -> FinalShotRecord:
    return FinalShotRecord(
        id=f"SHOT_{ordinal}",
        edit_set_id="SHOT_EDIT_test",
        project_id="PROJECT_test",
        ordinal=ordinal,
        final_start_us=start,
        final_end_us=end,
        duration_us=end - start,
        origin_kind="auto",
        origin_candidate_ids=(f"CANDIDATE_{ordinal}",),
        created_at=NOW,
        updated_at=NOW,
    )


def test_f05_business_ids_have_expected_prefix() -> None:
    assert generate_shot_edit_set_id().startswith("SHOT_EDIT_")
    assert generate_final_shot_id().startswith("SHOT_")


def test_final_timeline_accepts_continuous_half_open_ranges() -> None:
    shots = (_shot(1, 0, 800_000), _shot(2, 800_000, 3_640_000), _shot(3, 3_640_000, 5_000_000))
    _validate_final_timeline(shots=shots, source_start_us=0, source_end_us=5_000_000)


def test_final_timeline_rejects_gap() -> None:
    shots = (_shot(1, 0, 800_000), _shot(2, 900_000, 2_000_000))
    with pytest.raises(ShotWorkbenchError) as error:
        _validate_final_timeline(shots=shots, source_start_us=0, source_end_us=2_000_000)
    assert error.value.code == "SHOT_WORKBENCH_INVALID_RESULT"


def test_final_timeline_rejects_wrong_ordinal() -> None:
    first = _shot(1, 0, 1_000_000)
    second = FinalShotRecord(**{**first.__dict__, "id": "SHOT_2", "ordinal": 3, "final_start_us": 1_000_000, "final_end_us": 2_000_000, "duration_us": 1_000_000})
    with pytest.raises(ShotWorkbenchError):
        _validate_final_timeline(shots=(first, second), source_start_us=0, source_end_us=2_000_000)


def test_merge_origin_ids_preserves_order_and_removes_duplicates() -> None:
    assert _merge_origin_ids(("A", "B"), ("B", "C")) == ("A", "B", "C")
