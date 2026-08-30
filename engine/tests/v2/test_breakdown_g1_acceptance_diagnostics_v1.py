from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from engine.app import breakdown_g1_acceptance_diagnostics_v1 as diagnostics


def test_runtime_snapshot_uses_full_run_elapsed_and_keeps_provider_timings() -> None:
    started = datetime(2026, 8, 30, 10, 0, tzinfo=timezone.utc)
    run = SimpleNamespace(
        started_at=started,
        completed_at=started + timedelta(minutes=18, seconds=30),
        provider_metadata_json='{"p2_pipeline":{"timings_seconds":{"ASR":120.5,"OCR":40.25,"VLM":850.0}}}',
    )

    snapshot = diagnostics._runtime_snapshot(run)

    assert snapshot["total_elapsed_seconds"] == 1110.0
    assert snapshot["total_elapsed_minutes"] == 18.5
    assert snapshot["provider_timings_seconds"] == {
        "ASR": 120.5,
        "OCR": 40.25,
        "VLM": 850.0,
    }
    assert snapshot["targets"]["under_30_minutes"] is True
    assert snapshot["targets"]["at_or_below_20_minutes"] is True


def test_same_shot_conflict_detection_catches_bad_transitive_cluster() -> None:
    conflicts = diagnostics._same_shot_conflicts([
        {
            "shot_revision_item_id": "ITEM_1",
            "shot_ordinal": 4,
            "source_label": "subject_A",
        },
        {
            "shot_revision_item_id": "ITEM_2",
            "shot_ordinal": 5,
            "source_label": "subject_A",
        },
        {
            "shot_revision_item_id": "ITEM_1",
            "shot_ordinal": 4,
            "source_label": "subject_B",
        },
    ])

    assert conflicts == [{
        "shot_revision_item_id": "ITEM_1",
        "shot_ordinal": 4,
        "source_labels": ["subject_A", "subject_B"],
    }]


def test_short_ocr_noise_samples_records_only_short_unique_text() -> None:
    assert diagnostics._short_ocr_noise_samples([
        "人",
        "人民",
        "副",
        "V",
        "这是正常字幕",
        "人",
    ]) == ["人", "人民", "副", "V"]
